"""Known-dependence, independent arithmetic and immutable M5D lifecycle tests."""
import copy
import hashlib
import itertools
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from fpl_ai import joint_simulation as js, simulation_plans as sp, transfer_path as tp
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json
from tests import test_multi_uncertainty as uc_tests
from tests.test_multi_uncertainty import republish, residual_fixture
from tests.test_prospective import clock, fingerprint
from tests.test_transfer_optimiser import fixture
from tests.test_transfer_path import projection, oracle


def synthetic(values):
    """values[block][donor][horizon]; preserve deliberately known residuals."""
    return [{'season': '2025-26', 'as_of_gameweek': g+1, 'element': e+1, 'horizon': h,
             'target_gameweek': g+1+h, 'outcome': v, 'xpts': 0., 'residual': v,
             'label_available_at': '2026-05-25T10:23:00Z'}
            for g, block in enumerate(values) for e, trajectory in enumerate(block) for h, v in enumerate(trajectory)]


def sample(values, players=4, count=8192, seed=17, model=js.JOINT):
    donor = js.donor_population(synthetic(values), len(values[0][0]))
    result, _ = js.generate(*donor[:3], players, js.configuration(count, seed), model)
    return result


class KernelTests(unittest.TestCase):
    def test_perfect_positive_and_negative_trajectories(self):
        for sign in (1, -1):
            rs = sample([[[-2., -2.*sign], [3., 3.*sign]]])
            np.testing.assert_array_equal(rs[:, 1], rs[:, 0]*sign)
            self.assertAlmostEqual(np.corrcoef(rs[:, 0, 0], rs[:, 1, 0])[0, 1], sign)

    def test_shared_gameweek_shocks_move_all_players(self):
        rs = sample([[[-3., 4.], [-3., 4.]], [[2., -5.], [2., -5.]]])
        self.assertTrue(np.all(rs == rs[:, :, :1]))
        self.assertEqual(set(rs[:, 0, 0]), {-3., 2.})
        self.assertLess(np.corrcoef(rs[:, 0, 0], rs[:, 1, 1])[0, 1], -.999)

    def test_player_specific_trajectory_not_shared_idiosyncratic_draw(self):
        rs = sample([[[-2., -2.], [2., 2.]]], count=20000)
        np.testing.assert_array_equal(rs[:, 0], rs[:, 1])
        self.assertLess(abs(np.corrcoef(rs[:, 0, 0], rs[:, 0, 1])[0, 1]), .03)

    def test_independent_factorial_population_and_null(self):
        vals = [[list(v) for v in itertools.product((-2., 2.), repeat=2)]]
        for model in (js.JOINT, js.NULL):
            rs = sample(vals, count=20000, model=model)
            self.assertLess(abs(np.corrcoef(rs[:, 0, 0], rs[:, 1, 0])[0, 1]), .03)
        null = sample([[[-3., -3.]], [[3., 3.]]], count=20000, model=js.NULL)
        self.assertLess(abs(np.corrcoef(null[:, 0, 0], null[:, 1, 0])[0, 1]), .03)
        self.assertLess(abs(np.corrcoef(null[:, 0, 0], null[:, 0, 1])[0, 1]), .03)

    def test_size_weighted_block_and_no_clipping_or_recentering(self):
        rs = sample([[[-10.]], [[2.], [3.], [4.]]], players=1, count=30000)
        self.assertAlmostEqual(float(np.mean(rs == -10)), .25, delta=.01)
        self.assertAlmostEqual(float(rs.mean()), -.25, delta=.10)
        self.assertLess(float(rs.min()), 0)

    def test_independent_scalar_rng_reconstruction_and_prefixes(self):
        donor = js.donor_population(synthetic([[[-2., 3.]], [[1., 4.], [5., 6.]]]), 2)
        config = js.configuration(20, 412)
        actual, trace = js.generate(*donor[:3], 3, config)
        rng = np.random.Generator(np.random.PCG64(412))
        expected = []; hasher = hashlib.sha256()
        for _ in range(20):
            a = int(rng.integers(3, dtype=np.int64))
            members = [i for i, key in enumerate(donor[1]) if key[0] == donor[1][a][0]]
            picks = [members[int(i)] for i in rng.integers(len(members), size=3, dtype=np.int64)]
            expected.append([[donor[0][i, h] for i in picks] for h in range(2)])
            hasher.update(np.array([a], dtype='<i8').tobytes())
            hasher.update(np.array(picks, dtype='<i8').tobytes())
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(trace, hasher.hexdigest())
        np.testing.assert_array_equal(actual[:7], js.generate(*donor[:3], 3, js.configuration(7, 412))[0])
        self.assertNotEqual(js.array_hash(actual), js.array_hash(js.generate(*donor[:3], 3, js.configuration(20, 413))[0]))

    def test_missing_windows_season_end_and_invalid_sources(self):
        rs = residual_fixture()
        rs[0]['outcome'] = rs[0]['residual'] = None
        donor = js.donor_population(rs, 5)
        self.assertEqual(donor[3]['exclusion_counts'], {'missing_horizon_or_label': 1, 'season_end': 16})
        self.assertNotIn([1, 1], donor[1])
        self.assertEqual(donor[3]['complete_trajectories'], 135)
        for bad in (rs+rs[:1], [dict(r, season='2026-27') for r in rs],
                    [dict(r, label_available_at='2026-08-01T00:00:00Z') for r in rs],
                    [dict(r, residual=None, outcome=None) for r in rs]):
            with self.assertRaises(ValueError): js.donor_population(bad, 5)
        for h in (0, 6, True):
            with self.assertRaises(ValueError): js.donor_population(rs, h)

    def test_covariance_reference_independently_enumerated(self):
        donors, keys, groups, _ = js.donor_population(synthetic([[[-2., 2.], [0., 0.]], [[3., -3.]]]), 2)
        ref = js.dependency_reference(donors, groups, 2)
        # Enumerate all possible ordered donor pairs, weighting the anchor law.
        tuples = [(a, b, len(ids)/3/len(ids)**2) for ids in groups.values() for a in ids for b in ids]
        mean = sum(weight*donors[a] for a, b, weight in tuples)
        cross = sum(weight*np.outer(donors[a]-mean, donors[b]-mean) for a, b, weight in tuples)
        aggregate = sum(weight*np.outer((donors[a]+donors[b])/2-mean, (donors[a]+donors[b])/2-mean) for a, b, weight in tuples)
        np.testing.assert_allclose(ref['cross_player_covariance_from_shared_block'], cross, atol=1e-14)
        np.testing.assert_allclose(ref['aggregate_mean_covariance_joint'], aggregate, atol=1e-14)

    def test_config_rejects_boolean_out_of_range_and_unknown_model(self):
        for kwargs in ({'count': True}, {'count': 1}, {'count': 131073}, {'seed': -1}, {'seed': 1.5}):
            with self.assertRaises(ValueError): js.configuration(**kwargs)
        donor = js.donor_population(synthetic([[[1.]]]), 1)
        with self.assertRaises(ValueError): js.generate(*donor[:3], 1, js.configuration(2), 'Gaussian')


class PlanTests(unittest.TestCase):
    def setUp(self):
        p, self.state = fixture()
        self.rows = projection([p, p])
        self.decision = tp.optimise_paths(self.rows, self.state, horizon=2, top_n=3)
        self.decision['greedy'] = tp.greedy_path(self.rows, self.state, horizon=2)
        self.candidates = {'no_transfer': self.decision['baseline'], 'greedy': self.decision['greedy'],
                           **{f'exact_{i}': p for i, p in enumerate(self.decision['plans'], 1)}}

    def test_scenario_returns_independent_XI_captain_hits_and_horizon(self):
        rs = np.arange(4*2*17, dtype=float).reshape(4, 2, 17)/7-10
        actual = sp.scenario_returns(rs, self.rows, self.candidates)
        for name, plan in self.candidates.items():
            expected = []
            for s in range(4):
                score = 0.
                for h, week in enumerate(plan['weeks']):
                    points = {r['element']: r['xpts']+rs[s, h, r['element']-1] for r in self.rows if r['horizon'] == h}
                    score += sum(points[e] for e in week['starting_xi'])+points[week['captain']]-week['transfer_hit']
                expected.append(score)
            np.testing.assert_allclose(actual[name], expected, atol=1e-12)
        self.assertEqual(self.candidates['exact_1']['total_hit_cost'], 4)
        # Scenario samples never choose a new XI or captain.
        self.assertEqual(self.decision['plans'][0]['total_points'], float(oracle([self.rows[:17], self.rows[17:]], self.state, 2, 3)[0][0]))

    def test_metrics_paired_ties_tail_mass_independent_arithmetic(self):
        returns = {'no_transfer': np.array([0., 2., 4., 6.]), 'greedy': np.array([1., 2., 3., 8.]),
                   'exact_1': np.array([1., 1., 5., 8.])}
        metric = sp.metrics(returns)
        self.assertEqual(metric['exact_1']['mean'], 3.75)
        self.assertEqual(metric['exact_1']['median'], 3.)
        self.assertEqual(metric['exact_1']['vs_no_transfer']['probability_win'], .75)
        self.assertEqual(metric['exact_1']['vs_greedy']['probability_tie'], .5)
        self.assertEqual(metric['exact_1']['probability_highest_split_ties'], .5)
        self.assertEqual(metric['greedy']['probability_highest_split_ties'], .375)
        self.assertEqual(metric['no_transfer']['probability_highest_split_ties'], .125)
        self.assertAlmostEqual(metric['exact_1']['sd'], (sum((v-3.75)**2 for v in returns['exact_1'])/4)**.5)
        self.assertEqual(sp.shortfall(np.arange(15, dtype=float)), 1/3)
        self.assertEqual(metric['exact_1']['lower_tail_mean_10pct'], 1.)
        identical = sp.metrics({'no_transfer': returns['greedy'], 'greedy': returns['greedy']})
        self.assertEqual(identical['greedy']['vs_no_transfer']['probability_win'], 0)
        self.assertEqual(identical['greedy']['probability_highest_split_ties'], .5)

    def test_evaluation_publication_reuse_and_rehashed_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            donor = js.donor_population(residual_fixture(), 2)
            config = js.configuration(32, 4)
            simulation = {'metadata': {'binding': {'projection': {'identity': 'fixture'}}}, 'identity_sha256': 'simulation', 'artifacts': {}}
            plan = {'identity_sha256': 'plan', 'artifacts': {}}
            for name in ('simulation', 'plan'):
                (root/name).mkdir()
                atomic_write_json(root/name/'manifest.json', simulation if name == 'simulation' else plan)
            common = (root/'simulation', root/'plan', root/'uncertainty', root/'calibration', root/'model', root/'m4e')
            with patch.object(js, 'verify', return_value=((self.rows, donor, config), simulation)), \
                 patch.object(sp, 'load_plans', return_value=(self.candidates, plan)):
                out, reused = sp.evaluate(*common, root/'eval')
                self.assertFalse(reused)
                before = fingerprint(out)
                self.assertTrue(sp.evaluate(*common, root/'eval')[1])
                self.assertEqual(before, fingerprint(out))
                self.assertEqual(sp.verify(out, *common)['identity_sha256'], out.name)
                bad = republish(out, root/'bad', lambda m, v: v['evaluation.json']['models'][js.JOINT]['metrics']['exact_1'].update(mean=999))
                with self.assertRaises(ValueError): sp.verify(bad, *common)

    def test_plan_loader_replays_and_rejects_rehashed_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = {'identity_sha256': 'projection', 'metadata': {'model_identity': js.uc.MODEL_ID}}
            reference = {'identity': 'projection', 'manifest_sha256': js.digest(source)}
            meta = {'kind': 'multi-gw-transfer-path', 'contract': tp.CONTRACT, 'rules': tp.Rules().as_dict(),
                    'assumptions': tp.ASSUMPTIONS, 'implementation_sha256': sha256_file(Path(tp.__file__)),
                    'projection_identity': 'projection', 'model_identity': js.uc.MODEL_ID,
                    'horizon': 2, 'max_transfers': 2, 'top_n': 3}
            def writer(folder):
                for name, value in [('source.json', source), ('decision.json', self.decision), ('squad.json', self.state)]:
                    atomic_write_json(folder/name, value)
                atomic_write_json(folder/'report.md', 'synthetic test')
            path = publish(root/'plans', meta, writer)[0]
            self.assertEqual(sp.load_plans(path, self.rows, reference)[0], self.candidates)
            for mutate in (lambda m, v: v['decision.json']['plans'][0]['weeks'][0].update(captain=1),
                           lambda m, v: v['decision.json']['plans'].reverse(),
                           lambda m, v: m.update(max_transfers=0),
                           lambda m, v: v['decision.json']['baseline']['weeks'].pop()):
                changed = republish(path, root/'bad', mutate)
                with self.assertRaises(ValueError): sp.load_plans(changed, self.rows, reference)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = uc_tests.UncertaintyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root = f.root
        self.common = (f.forecast, *f.common)
        self.time = patch.object(js.live, 'now_utc', clock('2026-09-17T11:30:00Z'))
        self.time.start(); self.addCleanup(self.time.stop)
        self.out = js.freeze(*self.common, self.root/'simulations', count=64, seed=1)[0]

    def test_fresh_reuse_seed_and_offline_replay_preserve_inputs(self):
        before = fingerprint(self.fixture.forecast), fingerprint(self.fixture.calibration), fingerprint(self.out)
        self.assertTrue(js.freeze(*self.common, self.root/'simulations', count=64, seed=1)[1])
        fresh = js.freeze(*self.common, self.root/'fresh', count=64, seed=1)[0]
        self.assertEqual(fresh.name, self.out.name)
        changed = js.freeze(*self.common, self.root/'changed', count=64, seed=2)[0]
        self.assertNotEqual(changed.name, self.out.name)
        self.assertNotEqual(load_json(changed/'scenario_hashes.json'), load_json(self.out/'scenario_hashes.json'))
        with patch.object(js.live, 'now_utc', clock('2027-01-01T00:00:00Z')):
            js.verify(self.out, *self.common)
            replay, reused = js.replay(self.out, *self.common, self.root/'replay')
            self.assertFalse(reused); self.assertEqual(replay.name, self.out.name)
            self.assertTrue(js.replay(self.out, *self.common, self.root/'replay')[1])
            self.assertTrue(js.freeze(*self.common, self.root/'simulations', count=64, seed=1)[1])
        self.assertEqual(before, (fingerprint(self.fixture.forecast), fingerprint(self.fixture.calibration), fingerprint(self.out)))

    def test_original_forecasts_and_M5C_bounds_exact(self):
        rows = load_json(self.out/'projections.json')
        self.assertEqual(rows, self.fixture.rows)
        reports = load_json(self.out/'diagnostics.json')
        for model in (js.JOINT, js.NULL):
            for row, original in zip(reports[model]['player_horizons'], rows):
                self.assertTrue(all(row[k] == v for k, v in original.items()))
                self.assertEqual(row['m5c_fixed_intervals']['90']['lower'],
                                 original['xpts']+load_json(self.fixture.calibration/'calibration.json')['horizons'][str(row['horizon'])]['intervals']['90']['lower_residual'])

    def test_late_reversed_computation_and_final_verification_gate(self):
        for stamps in (['2026-09-18T12:00:00Z'], ['2026-09-17T09:00:00Z'],
                       ['2026-09-17T11:30:00Z', '2026-09-17T11:29:00Z'],
                       ['2026-09-17T11:30:00Z', '2026-09-17T11:31:00Z', '2026-09-18T12:00:00Z'],
                       ['2026-09-17T11:30:00Z', '2026-09-17T11:31:00Z', '2026-09-17T11:32:00Z', '2026-09-18T12:00:00Z']):
            ticks = iter(stamps)
            with patch.object(js.live, 'now_utc', side_effect=lambda: clock(next(ticks))()):
                with self.assertRaises(ValueError): js.freeze(*self.common, self.root/'late', count=16)
            self.assertFalse(list((self.root/'late').glob('*/manifest.json')))

    def test_rehashed_semantic_corruptions_fail(self):
        for change in (lambda m, v: v['projections.json'][0].update(xpts=999),
                       lambda m, v: v['projections.json'].pop(),
                       lambda m, v: v['population.json']['eligible_keys'].pop(),
                       lambda m, v: m['config'].update(seed=999),
                       lambda m, v: m['binding']['calibration'].update(identity='wrong'),
                       lambda m, v: m.update(computed_at='2027-01-01T00:00:00Z'),
                       lambda m, v: v['scenario_hashes.json'][js.JOINT].update(points_sha256='bad'),
                       lambda m, v: v['contract.json'].update(dependency_model=js.NULL)):
            bad = republish(self.out, self.root/'bad', change)
            with self.assertRaises(ValueError): js.verify(bad, *self.common)

    def test_rehashed_calibration_and_missing_upstream_fail(self):
        bad = republish(self.fixture.calibration, self.root/'badcal', lambda m, v: v['residuals.json'][0].update(residual=999))
        with self.assertRaises(ValueError): js.freeze(self.fixture.forecast, bad, *self.fixture.common[1:], self.root/'out', count=16)
        (self.fixture.calibration/'residuals.json').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)): js.verify(self.out, *self.common)

    def test_closed_artifact_set_and_checksum_fail(self):
        (self.out/'unexpected.txt').write_text('extra')
        with self.assertRaises(ValueError): js.verify(self.out, *self.common)
        (self.out/'unexpected.txt').unlink()
        (self.out/'scenario_hashes.json').write_text('{}')
        with self.assertRaises(ValueError): js.verify(self.out, *self.common)

    def test_cli_no_clock_override_or_ingestion_options(self):
        from fpl_ai.cli import build_parser, main
        args = ['simulate', 'freeze', '--uncertainty-dir', 'u', '--calibration-dir', 'c', '--m4e-model-dir', 'm']
        parsed = build_parser().parse_args(args)
        self.assertEqual(parsed.count, js.DEFAULT_COUNT)
        with self.assertRaises(SystemExit): build_parser().parse_args(args+['--clock', '2020-01-01'])
        with self.assertRaises(SystemExit): main(['--timeout', '1']+args)
