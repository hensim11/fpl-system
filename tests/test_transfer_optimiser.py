"""Hand-solvable decision cases; no network, fitting or outcome dependency."""
import copy
import itertools
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fpl_ai import transfer_optimiser as opt
from fpl_ai.fpl_rules import Rules
from fpl_ai.experiment_io import verify_bundle


def fixture():
    positions = [1]*2 + [2]*5 + [3]*5 + [4]*3
    population = [{'element': i, 'position': p, 'team': (i-1)//3+1,
                   'purchase_price': 50, 'name': f'Player {i}', 'xpts': 1.0}
                  for i, p in enumerate(positions, 1)]
    population += [{'element': 16, 'position': 3, 'team': 6, 'purchase_price': 55, 'name': 'Star mid', 'xpts': 10.0},
                   {'element': 17, 'position': 4, 'team': 6, 'purchase_price': 55, 'name': 'Star forward', 'xpts': 8.0}]
    for row in population: row['can_select'] = True
    state = {'contract': opt.SQUAD_CONTRACT, 'season': '2026-27', 'target_gameweek': 6,
             'players': [{'element': i, 'selling_price': 49} for i in range(1, 16)], 'bank': 12, 'free_transfers': 1}
    return population, state


class TransferTests(unittest.TestCase):
    def test_baseline_and_lineup(self):
        p, s = fixture()
        result = opt.optimise(p, s, max_transfers=0, top_n=3)
        b = result['baseline']
        self.assertEqual(result['plans'], [b])
        self.assertEqual(b['net_points'], 12)
        self.assertEqual(b['gross_xi_points'], 11)
        self.assertEqual(b['captain_bonus'], 1)
        self.assertIn(b['captain'], b['starting_xi'])
        self.assertEqual(b['next_free_transfers'], 2)

    def test_one_transfer_optimum(self):
        p, s = fixture()
        plan = opt.optimise(p, s, max_transfers=1, top_n=1)['plans'][0]
        self.assertEqual(plan['transfers_in'], [16])
        self.assertEqual(plan['transfers_out'], [12])
        self.assertEqual(plan['net_points'], 30)
        self.assertEqual(plan['gain_vs_no_transfer'], 18)
        self.assertEqual(plan['resulting_bank'], 6)
        self.assertEqual(plan['captain'], 16)

    def test_multi_transfer_and_hit(self):
        p, s = fixture()
        plan = opt.optimise(p, s, max_transfers=2, top_n=1)['plans'][0]
        self.assertEqual(plan['transfers_in'], [16, 17])
        self.assertEqual(plan['transfers_out'], [12, 15])
        self.assertEqual(plan['net_points'], 33)
        self.assertEqual(plan['gross_xi_points'], 27)
        self.assertEqual(plan['captain_bonus'], 10)
        self.assertEqual(plan['transfer_hit'], 4)
        self.assertEqual(plan['resulting_bank'], 0)

    def test_budget_uses_exact_selling_prices(self):
        p, s = fixture(); s['bank'] = 5
        self.assertEqual(opt.optimise(p, s, top_n=1)['plans'][0]['transfer_count'], 0)
        s['players'][11]['selling_price'] = 50
        self.assertEqual(opt.optimise(p, s, top_n=1)['plans'][0]['transfers_out'], [12])

    def test_free_transfers_zero_and_cap(self):
        p, s = fixture()
        for free, hit in ((0, 8), (1, 4), (2, 0), (5, 0)):
            s['free_transfers'] = free
            r = opt.optimise(p, s, top_n=1)['plans'][0]
            self.assertEqual(r['transfer_hit'], hit)
            self.assertEqual(r['next_free_transfers'], min(5, max(0, free-2)+1))

    def test_top_n_deterministic_unique_and_exhaustive_reference(self):
        p, s = fixture()
        a = opt.optimise(p, s, top_n=10)
        b = opt.optimise(list(reversed(p)), {**s, 'players': list(reversed(s['players']))}, top_n=10)
        self.assertEqual(a, b)
        self.assertEqual(len({tuple(x['squad']) for x in a['plans']}), 10)
        players = {x['element']: x for x in p}
        exhaustive = []
        for ids in itertools.combinations(players, 15):
            try: plan = opt.make_plan(ids, s, players, Rules())
            except ValueError: continue
            exhaustive.append(plan)
        exhaustive.sort(key=lambda r: (-r['net_points'], r['transfer_count'], r['squad']))
        self.assertEqual([r['squad'] for r in a['plans']], [r['squad'] for r in exhaustive[:10]])

    def test_negative_predictions_still_legal_captain(self):
        p, s = fixture()
        for row in p: row['xpts'] = -row['element']
        r = opt.optimise(p, s, max_transfers=0, top_n=1)['baseline']
        self.assertEqual(r['captain'], 1)
        self.assertEqual(len(r['starting_xi']), 11)
        self.assertLess(r['net_points'], 0)

    def test_reject_squad_composition_and_club(self):
        p, s = fixture()
        for edit in ('duplicate', 'size', 'unknown', 'position', 'club'):
            pp, ss = copy.deepcopy(p), copy.deepcopy(s)
            if edit == 'duplicate': ss['players'][1] = ss['players'][0]
            elif edit == 'size': ss['players'].pop()
            elif edit == 'unknown': ss['players'][0]['element'] = 100
            elif edit == 'position': pp[0]['position'] = 2
            else: pp[3]['team'] = 1
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                opt.validate_state(ss, pp, '2026-27', 6)

    def test_invalid_economics_and_contracts(self):
        p, s = fixture()
        changes = [('bank', -1), ('bank', True), ('bank', 1.1), ('free_transfers', 6),
                   ('free_transfers', -1), ('free_transfers', True), ('target_gameweek', True),
                   ('target_gameweek', 39), ('target_gameweek', 5), ('season', '2025-26'), ('contract', 'bad')]
        for k, v in changes:
            with self.subTest(k=k, v=v), self.assertRaises(ValueError):
                opt.validate_state({**s, k: v}, p, '2026-27', 6)
        for value in (None, 0, -1, 1.2, True, 51):
            ss = copy.deepcopy(s); ss['players'][0]['selling_price'] = value
            with self.assertRaises(ValueError): opt.validate_state(ss, p, '2026-27', 6)
        for rules in (replace(Rules(), hit_cost=0), replace(Rules(), club_limit=True), replace(Rules(), season='2027-28')):
            with self.assertRaises(ValueError): opt.optimise(p, s, rules=rules)
        for kwargs in ({'max_transfers': -1}, {'max_transfers': 16}, {'top_n': 0}, {'top_n': True}):
            with self.assertRaises(ValueError): opt.optimise(p, s, **kwargs)

    def test_invalid_population_and_no_feasible_solution(self):
        p, s = fixture()
        for value in (float('nan'), float('inf'), True):
            pp = copy.deepcopy(p); pp[0]['xpts'] = value
            with self.assertRaises(ValueError): opt.optimise(pp, s)
        with self.assertRaises(ValueError): opt.optimise(p[1:], s)
        with self.assertRaises(ValueError): opt.optimise(p + [p[0]], s)
        solver = opt.SquadMILP(p, s, Rules(), 2)
        solver.add({i: 1 for i in range(len(p))}, 0, 0)
        self.assertIsNone(solver.next_squad())
        with patch.object(opt.SquadMILP, 'next_squad', return_value=None), self.assertRaisesRegex(ValueError, 'no feasible'):
            opt.optimise(p, s)

    def test_solve_timeout_fails_closed(self):
        from types import SimpleNamespace
        p, s = fixture()
        with patch.object(opt, 'milp', return_value=SimpleNamespace(status=1, success=False, message='time limit')):
            with self.assertRaisesRegex(ValueError, 'prove optimality'): opt.optimise(p, s)

    def test_json_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            for text in ('{"bank":1,"bank":2}', '{"bank":NaN}'):
                path.write_text(text)
                with self.assertRaises(ValueError): opt.load_json(path)

    def test_explicit_model_and_cli(self):
        with self.assertRaises(ValueError): opt.load_forecast('absent', 'absent', 'automatic')
        from fpl_ai.cli import build_parser
        args = build_parser().parse_args(['optimise', '--forecast-dir', 'f', '--model-dir', 'm', '--model', 'v2', '--squad', 's'])
        self.assertEqual(args.model, 'v2')
        import contextlib
        import io
        from fpl_ai.cli import main
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(['--output-dir', 'ignored', 'optimise', '--forecast-dir', 'f', '--model-dir', 'm',
                  '--model', 'v2', '--squad', 's'])

    def test_publication_fresh_reuse_and_corruption(self):
        p, s = fixture()
        source = {'manifest': {'identity_sha256': 'test', 'metadata': {'season': '2026-27', 'target_gameweek': 6,
                  'deadline': '2026-10-10T10:00:00Z'}}, 'manifest_sha256': 'test'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(opt, 'load_forecast', return_value=(p, source)):
            root = Path(tmp); path = root/'squad.json'; path.write_text(json.dumps(s))
            a, reuse = opt.build_decision(root/'f', root/'m', 'control', path, root/'a', top_n=1)
            before = {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in a.iterdir()}
            b, _ = opt.build_decision(root/'f', root/'m', 'control', path, root/'b', top_n=1)
            self.assertEqual(verify_bundle(a), verify_bundle(b))
            self.assertTrue(opt.build_decision(root/'f', root/'m', 'control', path, root/'a', top_n=1)[1])
            self.assertEqual(before, {f.name: (f.read_bytes(), f.stat().st_mtime_ns) for f in a.iterdir()})
            (a/'decision.json').write_text('{}')
            with self.assertRaises(ValueError): opt.build_decision(root/'f', root/'m', 'control', path, root/'a', top_n=1)


class ForecastBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests import test_prospective_xpts as fixtures
        cls.fixtures = fixtures
        fixtures.ProspectiveXptsTests.setUpClass()
        cls.builder = fixtures.ProspectiveXptsTests()
        original_client = fixtures.Client
        def client(*args, **kwargs):
            instance = original_client(*args, **kwargs)
            for player in instance.bootstrap['elements']:
                player.update(team=player['id'], web_name=f"Player {player['id']}", can_select=player['id'] == 1)
            return instance
        cls.client_patch = patch.object(fixtures, 'Client', side_effect=client)
        cls.client_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.client_patch.stop()
        cls.fixtures.ProspectiveXptsTests.tearDownClass()

    def test_bound_forecast_models_and_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, forecast = self.builder.forecast(root)
            for model in ('control', 'v2'):
                population, source = opt.load_forecast(forecast, self.builder.model, model)
                self.assertEqual(len(population), 2)
                self.assertEqual(source['selected_model'], model)
                self.assertEqual(population[0]['purchase_price'], 50)
                self.assertEqual([p['can_select'] for p in population], [True, False])
                full, state = fixture()
                full[-2]['can_select'] = population[1]['can_select']
                full[-2]['xpts'] = 1000.0
                self.assertEqual(opt.optimise(full, state, top_n=1)['plans'][0]['transfers_in'], [17])

    def test_missing_malformed_snapshot_selectability_and_tampered_evidence(self):
        factory = self.fixtures.Client.side_effect
        for value in ('missing', None, 1, 0, 'true'):
            def client(*args, **kwargs):
                instance = factory(*args, **kwargs)
                if value == 'missing': instance.bootstrap['elements'][1].pop('can_select')
                else: instance.bootstrap['elements'][1]['can_select'] = value
                return instance
            with tempfile.TemporaryDirectory() as tmp, patch.object(self.fixtures, 'Client', side_effect=client):
                root = Path(tmp); _, _, forecast = self.builder.forecast(root)
                for model in ('control', 'v2'):
                    with self.subTest(value=value, model=model), self.assertRaisesRegex(ValueError, 'can_select'):
                        opt.load_forecast(forecast, self.builder.model, model)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, _, forecast = self.builder.forecast(root)
            evidence = json.loads((forecast/'evidence.json').read_text())
            raw = json.loads(evidence['snapshot']['files']['bootstrap.json'])
            raw['elements'][1]['can_select'] = True
            evidence['snapshot']['files']['bootstrap.json'] = json.dumps(raw)
            bad = self.fixtures.republish(forecast, root/'tampered', tables={'evidence.json':evidence})
            for model in ('control', 'v2'):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    opt.load_forecast(bad, self.builder.model, model)

    def test_corrupt_wrong_family_missing_player_and_metadata(self):
        from fpl_ai.modelling import read_csv
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); _, minutes, forecast = self.builder.forecast(root)
            with self.assertRaises(ValueError): opt.load_forecast(minutes, self.builder.model, 'control')
            for field, value in (('season', '2025-26'), ('target_gameweek', 3), ('deadline', '2026-09-19T12:00:00Z'), ('model_identity', 'wrong')):
                metadata = copy.deepcopy(verify_bundle(forecast)['metadata']); metadata[field] = value
                bad = self.fixtures.republish(forecast, root/field, metadata=metadata)
                with self.subTest(field=field), self.assertRaises(ValueError):
                    opt.load_forecast(bad, self.builder.model, 'control')
            rows = read_csv(forecast/'predictions.csv')[:-1]
            bad = self.fixtures.republish(forecast, root/'missing', tables={'predictions.csv': rows})
            with self.assertRaises(ValueError): opt.load_forecast(bad, self.builder.model, 'v2')
            (forecast/'predictions.csv').write_text('corrupt')
            with self.assertRaises(ValueError): opt.load_forecast(forecast, self.builder.model, 'control')


class HardeningTests(unittest.TestCase):
    def test_unselectable_star_excluded_selectable_alternative_and_audit_counts(self):
        population, state = fixture()
        population[-2]['can_select'] = False
        population[-2]['xpts'] = 1000.0
        result = opt.optimise(population, state, top_n=5)
        self.assertEqual(result['plans'][0]['transfers_in'], [17])
        self.assertTrue(all(16 not in p['transfers_in'] for p in result['plans']))
        self.assertEqual(len(population), 17)
        self.assertEqual(result['population_counts'], {'forecast_population': 17,
                         'transfer_in_eligible_population': 16, 'eligible_not_owned': 1,
                         'owned_population': 15, 'owned_unselectable': 0, 'optimisation_population': 16})
        solver = opt.SquadMILP(population, state, Rules(), 2)
        self.assertNotIn(16, solver.players)
        with self.assertRaisesRegex(ValueError, 'unselectable'):
            opt.make_plan([e for e in range(1,16) if e != 12] + [16], state,
                          {p['element']:p for p in population}, Rules())

    def test_owned_unselectable_can_be_retained_started_captained_or_sold(self):
        population, state = fixture()
        population[11].update(can_select=False, xpts=100.0)
        result = opt.optimise(population, state, top_n=1)
        self.assertIn(12, result['plans'][0]['squad'])
        self.assertEqual(result['plans'][0]['captain'], 12)
        self.assertEqual(result['population_counts']['owned_unselectable'], 1)
        self.assertEqual(result['population_counts']['optimisation_population'], 17)
        self.assertIn(12, opt.optimise(population, state, max_transfers=0)['baseline']['squad'])
        population[11]['xpts'] = 0.0
        self.assertEqual(opt.optimise(population, state, max_transfers=1, top_n=1)['plans'][0]['transfers_out'], [12])

    def test_missing_or_nonboolean_candidate_evidence_fails_closed(self):
        for value in ('missing', None, 0, 1, 'true', 'false', [], {}):
            population, state = fixture()
            if value == 'missing': population[-1].pop('can_select')
            else: population[-1]['can_select'] = value
            with self.subTest(value=value), self.assertRaises(ValueError): opt.optimise(population, state)

    def test_tolerance_boundary_fewer_transfers_inclusive_and_deterministic(self):
        import math
        for delta in (0.0, math.nextafter(opt.TOLERANCE, 0), opt.TOLERANCE,
                      math.nextafter(opt.TOLERANCE, math.inf), 2 * opt.TOLERANCE):
            population, state = fixture()
            for p in population: p['xpts'] = 0.0
            population[-2]['xpts'] = delta / 2
            population[-1]['can_select'] = False
            expected = 0 if delta <= opt.TOLERANCE else 1
            with self.subTest(delta=delta):
                a = opt.optimise(population, state, max_transfers=1, top_n=1)
                b = opt.optimise(list(reversed(population)), state, max_transfers=1, top_n=1)
                self.assertEqual(a, b)
                self.assertEqual(a['plans'][0]['transfer_count'], expected)

    def test_tolerance_boundary_lexicographic_only_inside_band(self):
        import math
        for delta in (0.0, math.nextafter(opt.TOLERANCE, 0), opt.TOLERANCE,
                      math.nextafter(opt.TOLERANCE, math.inf), 2 * opt.TOLERANCE):
            population, state = fixture()
            for p in population: p['xpts'] = -1.0
            population[-2].update(position=4, xpts=0.0)
            population[-1]['xpts'] = delta / 2
            with self.subTest(delta=delta):
                a = opt.optimise(population, state, max_transfers=1, top_n=1)
                self.assertEqual(a['plans'][0]['transfers_in'], [16 if delta <= opt.TOLERANCE else 17])
                self.assertEqual(a, opt.optimise(population, state, max_transfers=1, top_n=1))

    def test_tolerance_anchored_to_best_not_chained_between_secondary_stages(self):
        population, state = fixture()
        for p in population: p['xpts'] = -1.0
        population[-2].update(position=4, xpts=0.0)
        population[-1]['xpts'] = opt.TOLERANCE * .375
        population.append({**population[-1], 'element':18, 'xpts':opt.TOLERANCE * .75})
        result = opt.optimise(population, state, max_transfers=1, top_n=1)
        self.assertEqual(result['plans'][0]['transfers_in'], [17])


class ConstraintScalingTests(unittest.TestCase):
    def test_valid_input_scaled_tie_retries_without_widening_semantic_band(self):
        from fractions import Fraction
        population, state = fixture()
        for row in population: row['xpts'] = 1.0
        population[-2]['xpts'] = 1.0 + 1.001e-6 / 2
        population[-1]['can_select'] = False
        opt.validate_state(state, population, '2026-27', 6)

        # Reproduce the old validation units using the real HiGHS result, not a
        # manufactured solver vector. Previously every row used scale 1 here.
        add = opt.SquadMILP.add
        def old_units(solver, coefficients, lo, hi, *, scale=1.0, role='structural'):
            # Emulate the original all-row guard, including the semantic row.
            return add(solver, coefficients, lo, hi, scale=1.0)
        with patch.object(opt.SquadMILP, 'add', new=old_units):
            with self.assertRaisesRegex(ValueError, 'solver constraint violation'):
                opt.optimise(population, state, max_transfers=1, top_n=3)

        solver = opt.SquadMILP(population, state, Rules(), 1)
        players = {r['element']: r for r in population}
        # Independent exact objective for this hand-checkable fixture: baseline
        # 12, upgraded starter gains delta/2 and captain gains another delta/2.
        best = Fraction(12) + 2 * (Fraction(population[-2]['xpts']) - 1)
        self.assertGreater(best - 12, Fraction(opt.TOLERANCE))
        rejected = []
        original_solve = solver.solve
        def observe(objective, **kwargs):
            result = original_solve(objective, **kwargs)
            if result is not None and opt.TIE_CONSTRAINT_SCALE in solver.row_scales:
                loss = best - solver.exact_net(result)
                if loss > Fraction(opt.TOLERANCE): rejected.append(loss)
            return result
        with patch.object(solver, 'solve', side_effect=observe):
            squads = [solver.next_squad() for _ in range(3)]
        self.assertTrue(rejected, 'real solver must reach the exact reject/retry path')
        self.assertNotIn(opt.TIE_CONSTRAINT_SCALE, solver.row_scales)
        self.assertEqual(len(solver.rows), len(solver.row_scales))
        result = opt.optimise(population, state, max_transfers=1, top_n=3)
        self.assertEqual(squads, [p['squad'] for p in result['plans']])
        self.assertEqual(len({tuple(squad) for squad in squads}), 3)
        for plan in result['plans']:
            opt.validate_squad(plan['squad'], players, Rules())
            self.assertEqual(plan['transfers_in'], [16])
            xi = plan['starting_xi']
            self.assertEqual(len(xi), 11)
            self.assertIn(plan['captain'], xi)
            exact = sum((Fraction(players[e]['xpts']) for e in xi), Fraction())
            exact += Fraction(players[plan['captain']]['xpts']) - plan['transfer_hit']
            self.assertLessEqual(best-exact, Fraction(opt.TOLERANCE))
            self.assertEqual(best, exact)
        self.assertEqual(result, opt.optimise(population, state, max_transfers=1, top_n=3))

    def test_scaled_feasibility_checks_both_bounds_in_original_units(self):
        from types import SimpleNamespace
        population, state = fixture()
        for side in ('lower', 'upper'):
            for residual, accepted in ((.5e-6, True), (2e-6, False)):
                solver = opt.SquadMILP(population, state, Rules(), 1)
                vector = solver.solve(solver.objective * 1e6)
                value = vector[0] * opt.TIE_CONSTRAINT_SCALE
                bound = value + residual * opt.TIE_CONSTRAINT_SCALE * (1 if side == 'lower' else -1)
                solver.add({0: opt.TIE_CONSTRAINT_SCALE},
                           bound if side == 'lower' else -float('inf'),
                           bound if side == 'upper' else float('inf'), scale=opt.TIE_CONSTRAINT_SCALE)
                response = SimpleNamespace(success=True, status=0, x=vector, message='test vector')
                with self.subTest(side=side, residual=residual), patch.object(opt, 'milp', return_value=response):
                    if accepted: self.assertIsNotNone(solver.solve(solver.objective))
                    else:
                        with self.assertRaisesRegex(ValueError, 'solver constraint violation'):
                            solver.solve(solver.objective)

    def test_nearby_scaled_tie_presolve_infeasibility_retries_same_model(self):
        from fractions import Fraction
        population, state = fixture()
        for row in population: row['xpts'] = 3.0
        population[-2]['xpts'] = 3.0 + 1.001e-6 / 2
        population[-1]['can_select'] = False
        original = opt.milp
        calls = []
        def observe(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append((kwargs['options']['presolve'], result.status))
            return result
        with patch.object(opt, 'milp', side_effect=observe):
            result = opt.optimise(population, state, max_transfers=1, top_n=3)
        self.assertIn((True, 2), calls)
        self.assertIn((False, 0), calls)
        players = {r['element']:r for r in population}
        best = Fraction(36) + 2 * (Fraction(population[-2]['xpts']) - 3)
        for plan in result['plans']:
            self.assertEqual(plan['transfers_in'], [16])
            exact = sum((Fraction(players[e]['xpts']) for e in plan['starting_xi']), Fraction())
            exact += Fraction(players[plan['captain']]['xpts']) - plan['transfer_hit']
            self.assertEqual(exact, best)
        self.assertEqual(result, opt.optimise(population, state, max_transfers=1, top_n=3))


class SemanticAdmissionTests(unittest.TestCase):
    def check_review_case(self, seed, depth):
        from scripts.verify_transfer_sweep import reviewed_fixture, check_case
        population, state, maximum = reviewed_fixture(seed)
        opt.validate_state(state, population, '2026-27', 6)
        # Preserve a live reproduction of Decision 048's all-row numerical guard.
        original_add = opt.SquadMILP.add
        def old_admission(solver, coefficients, lo, hi, *, scale=1.0, role='structural'):
            original_add(solver, coefficients, lo, hi, scale=scale, role='structural')
        with patch.object(opt.SquadMILP, 'add', new=old_admission):
            with self.assertRaisesRegex(ValueError, 'solver constraint violation'):
                opt.optimise(population, state, max_transfers=maximum, top_n=depth)
        checked = check_case(seed, depth)
        self.assertGreater(checked['out_of_band_candidates_rejected'], 0)
        self.assertEqual(checked, check_case(seed, depth))

    def test_review_seed_1596_top_one_exact_exhaustive_ranking(self):
        self.check_review_case(1596, 1)

    def test_review_seed_26_top_ten_exact_exhaustive_ranking(self):
        self.check_review_case(26, 10)
