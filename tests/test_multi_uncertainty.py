"""Deterministic full M5C lifecycle; unittest checks remain active with python -O."""
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fpl_ai import multi_uncertainty as uc, multi_outcomes as mo
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json
from tests.test_prospective import Client, clock, fingerprint


def residual_fixture():
    return [{'season': '2025-26', 'as_of_gameweek': g, 'element': e, 'horizon': h,
             'target_gameweek': g+h, 'position': e, 'xpts': (e+h)/3,
             'outcome': (g+e+h)%7, 'residual': (g+e+h)%7-(e+h)/3,
             'label_available_at': '2026-05-25T10:23:00Z', 'capture': '2025-08-01T00:00:00Z', 'exclusion': None}
            for h in range(5) for g in range(1, 39-h) for e in range(1, 5)]


def republish(folder, root, change):
    manifest = verify_bundle(folder)
    values = {n: load_json(folder/n) for n in manifest['artifacts']}
    meta = copy.deepcopy(manifest['metadata'])
    change(meta, values)
    def writer(out):
        for name, value in values.items(): atomic_write_json(out/name, value)
    return publish(root, meta, writer)[0]


class UncertaintyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.residuals = residual_fixture()
        self.history = patch.object(uc, 'historical_residuals', return_value=(self.residuals, {'fixture': 'synthetic prior-season evidence'}))
        self.history.start(); self.addCleanup(self.history.stop)
        self.calibration = uc.build_calibration(self.root/'calibrations')[0]
        self.rows = [{'season': '2026-27', 'as_of_gameweek': 2, 'target_gameweek': 2+h, 'horizon': h,
                      'element': e, 'position': e, 'xpts': e+h/2} for h in range(5) for e in (1, 2)]
        self.state = {'season': '2026-27', 'as_of_gameweek': 2, 'horizon': 5,
                      'capture': '2026-09-17T09:00:00Z', 'computed_at': '2026-09-17T10:00:00Z',
                      'deadline': '2026-09-18T12:00:00Z', 'model_identity': uc.MODEL_ID}
        self.bootstrap = Client().bootstrap
        self.bootstrap['events'] += [{'id': g, 'deadline_time': f'2026-10-{(g-3)*7:02d}T12:00:00Z',
                                     'finished': False, 'data_checked': False} for g in (4, 5, 6)]
        def writer(folder):
            evidence = {'snapshot': {'files': {'bootstrap.json': json.dumps(self.bootstrap)}}}
            atomic_write_json(folder/'source.json', {'files': {'evidence.json': json.dumps(evidence)}})
            atomic_write_json(folder/'projections.json', self.rows)
            atomic_write_json(folder/'h0_comparison.json', {})
        self.projection = publish(self.root/'projections', {'kind': 'multi-horizon-forecast', **self.state}, writer)[0]
        def verified(folder, *args):
            manifest = verify_bundle(folder, 'multi-horizon-forecast')
            return load_json(Path(folder)/'projections.json'), manifest
        self.replay = patch.object(uc.mp, 'verify_projection', side_effect=verified)
        self.replay.start(); self.addCleanup(self.replay.stop)
        self.common = (self.calibration, self.root/'model', self.root/'m4e')
        self.frozen_clock = clock('2026-09-17T11:00:00Z')
        self.forecast = uc.freeze(self.projection, *self.common, self.root/'forecasts', clock=self.frozen_clock)[0]

    def client(self, gw=2, **kwargs):
        c = Client(gw=gw, **kwargs)
        c.bootstrap = copy.deepcopy(self.bootstrap)
        event = next(e for e in c.bootstrap['events'] if e['id'] == gw)
        event.update(finished=kwargs.get('settled', False), data_checked=kwargs.get('settled', False))
        return c

    def settle(self, gw=2, client=None):
        return mo.capture_settlement(self.forecast, *self.common, gw, self.root/'settlements',
                                     client=client or self.client(gw, settled=True), clock=clock('2026-11-01T12:00:00Z'))[0]

    def score(self, settlements):
        return mo.score([self.forecast], [(self.forecast, s) for s in settlements], *self.common, self.root/'scores')[0]

    def test_quantile_definition_and_small_pool_no_cross_horizon_fallback(self):
        rs = [{'residual': float(v), 'position': 1, 'as_of_gameweek': v//4} for v in range(100)]
        p = uc.pool(rs)
        self.assertEqual(p['intervals']['80'], {'lower_residual': 9., 'upper_residual': 90., 'lower_rank': 10, 'upper_rank': 91})
        self.assertEqual(p['intervals']['90']['lower_residual'], 4.)
        small = uc.pool(rs[:99])
        self.assertFalse(small['available']); self.assertIsNone(small['intervals']['50']['lower_residual'])
        self.assertIsNone(small['fallback'])
        with self.assertRaises(ValueError): uc.pool([dict(r, residual=float('nan')) for r in rs])

    def test_cumulative_calibrates_residual_sum_and_excludes_incomplete_windows(self):
        tables = load_json(self.calibration/'calibration.json')
        residual = [sum((g+1+h)%7 for h in range(3))-sum((1+h)/3 for h in range(3)) for g in range(1, 37)]
        self.assertTrue(residual)
        self.assertEqual(tables['cumulative']['3']['calibration_rows'], 36*4)
        self.assertEqual(tables['cumulative']['5']['exclusions'], {'season_end': 16})
        changed = copy.deepcopy(self.residuals)
        changed[0]['outcome'] = changed[0]['residual'] = None
        other = uc.calibration_tables(changed)
        self.assertEqual(other['cumulative']['3']['excluded_rows'], tables['cumulative']['3']['excluded_rows']+1)
        self.assertNotEqual(tables['cumulative']['3']['intervals']['80']['upper_residual'],
                            sum(tables['horizons'][str(h)]['intervals']['80']['upper_residual'] for h in range(3)))

    def test_fresh_reuse_exact_points_and_no_input_changes(self):
        before = fingerprint(self.calibration), fingerprint(self.projection), fingerprint(self.forecast)
        self.assertTrue(uc.build_calibration(self.root/'calibrations')[1])
        self.assertTrue(uc.freeze(self.projection, *self.common, self.root/'forecasts', clock=self.frozen_clock)[1])
        fresh = uc.freeze(self.projection, *self.common, self.root/'fresh', clock=self.frozen_clock)[0]
        self.assertEqual(fresh.name, self.forecast.name)
        product, _ = uc.verify_uncertainty(self.forecast, *self.common)
        self.assertEqual([r['xpts'] for r in product['rows']], [r['xpts'] for r in self.rows])
        self.assertEqual(before, (fingerprint(self.calibration), fingerprint(self.projection), fingerprint(self.forecast)))

    def test_late_and_reversed_publication_fail(self):
        for stamp in ('2026-09-18T12:00:00Z', '2026-09-17T08:00:00Z'):
            with self.assertRaisesRegex(ValueError, 'deadline'):
                uc.freeze(self.projection, *self.common, self.root/'bad', clock=clock(stamp))
        times = iter(['2026-09-17T11:00:00Z', '2026-09-17T11:01:00Z', '2026-09-18T12:00:00Z'])
        with self.assertRaisesRegex(ValueError, 'deadline'):
            uc.freeze(self.projection, *self.common, self.root/'bad', clock=lambda: clock(next(times))())
        self.assertFalse(any((self.root/'bad').iterdir()))

    def test_one_target_double_and_explicit_zero_independent_of_later_targets(self):
        before = fingerprint(self.forecast), fingerprint(self.calibration)
        settlement = self.settle()
        score = self.score([settlement])
        report = load_json(score/'metrics.json')
        self.assertEqual(report['settled_target_gameweeks'], 1)
        self.assertEqual(report['horizons']['0']['scored_rows'], 2)
        self.assertEqual(report['horizons']['1']['scored_rows'], 0)
        self.assertEqual(report['aggregate']['mae'], 2.5)
        self.assertEqual(report['aggregate']['rmse'], math.sqrt(6.5))
        self.assertEqual(report['aggregate']['mean_within_gameweek_spearman'], -1.)
        self.assertTrue(report['aggregate']['small_sample'])
        self.assertEqual(report['cumulative']['3']['scored_rows'], 0)
        self.assertEqual(len(report['pending_targets']), 4)
        rows = load_json(score/'rows.json')
        self.assertEqual([r['outcome'] for r in rows], [4, 0])
        for level, metric in report['aggregate']['intervals'].items():
            covered = sum(r['intervals'][level]['lower'] <= r['outcome'] <= r['intervals'][level]['upper'] for r in rows)
            width = sum(r['intervals'][level]['upper']-r['intervals'][level]['lower'] for r in rows)/2
            self.assertEqual(metric['coverage'], covered/2)
            self.assertAlmostEqual(metric['average_width'], width)
        self.assertEqual(before, (fingerprint(self.forecast), fingerprint(self.calibration)))

    def test_accumulation_deduplicates_and_requires_complete_cumulative_window(self):
        s2, s3, s4 = [self.settle(g) for g in (2, 3, 4)]
        partial = load_json(self.score([s2, s4])/'metrics.json')
        self.assertEqual(partial['cumulative']['3']['scored_rows'], 0)
        score = self.score([s4, s2, s3, s2])
        report = load_json(score/'metrics.json')
        self.assertEqual(report['aggregate']['scored_rows'], 6)
        self.assertEqual(report['cumulative']['3']['scored_rows'], 2)
        self.assertEqual(report['cumulative']['5']['scored_rows'], 0)
        self.assertEqual(score.name, self.score([s2, s3, s4]).name)
        full = load_json(self.score([s2, s3, s4, self.settle(5), self.settle(6)])/'metrics.json')
        self.assertEqual(full['cumulative']['5']['scored_rows'], 2)
        self.assertEqual(full['settled_target_gameweeks'], 5)

    def test_blank_stays_null_and_missing_player_never_zero(self):
        blank = self.settle(client=self.client(2, settled=True, empty=True))
        report = load_json(self.score([blank])/'metrics.json')
        self.assertEqual(report['aggregate']['missing_outcomes'], 2)
        self.assertEqual(report['aggregate']['scored_rows'], 0)
        self.assertIsNone(report['aggregate']['mae'])
        c = self.client(2, settled=True); c.live['elements'].pop()
        with self.assertRaisesRegex(ValueError, 'explicit projected player'): self.settle(client=c)

    def test_premature_flags_fixtures_timing_and_schedule_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'deadline has not passed'):
            mo.capture_settlement(self.forecast, *self.common, 2, self.root/'bad', clock=self.frozen_clock)
        for kind in ('flags', 'unchecked', 'fixture', 'empty_schedule', 'mismatch', 'duplicate', 'deadline', 'early'):
            c = self.client(2, settled=True)
            if kind == 'flags': c.bootstrap['events'][1]['finished'] = False
            if kind == 'unchecked': c.bootstrap['events'][1]['data_checked'] = False
            if kind == 'fixture': c.fixtures[-1]['finished'] = False
            if kind == 'empty_schedule': c.fixtures = []
            if kind == 'mismatch': c.live['elements'][0]['stats']['total_points'] += 1
            if kind == 'duplicate': c.live['elements'].append(c.live['elements'][0])
            if kind == 'deadline': c.bootstrap['events'][1]['deadline_time'] = '2026-10-01T12:00:00Z'
            if kind == 'early':
                with self.assertRaises(ValueError):
                    mo.capture_settlement(self.forecast, *self.common, 3, self.root/'bad', client=c, clock=clock('2026-09-20T10:00:00Z'))
            else:
                with self.subTest(kind=kind), self.assertRaises(ValueError): self.settle(client=c)

    def test_corrupt_calibration_and_semantically_rehashed_artifacts_fail(self):
        for family, original, mutate in (
            ('calibration', self.calibration, lambda m, v: v['calibration.json']['horizons']['0']['intervals']['80'].update(upper_residual=999)),
            ('calibration', self.calibration, lambda m, v: v['residuals.json'][0].update(residual=999)),
            ('forecast', self.forecast, lambda m, v: v['uncertainty.json']['rows'].pop()),
            ('forecast', self.forecast, lambda m, v: v['uncertainty.json']['rows'].append(v['uncertainty.json']['rows'][0])),
            ('forecast', self.forecast, lambda m, v: v['uncertainty.json']['rows'][0].update(xpts=999)),
            ('forecast', self.forecast, lambda m, v: m['state'].update(capture='2026-09-17T01:00:00Z')),
            ('forecast', self.forecast, lambda m, v: m['calibration'].update(identity='0'*64)),
        ):
            bad = republish(original, self.root/'bad', mutate)
            with self.subTest(family=family), self.assertRaises(ValueError):
                if family == 'calibration': uc.load_calibration(bad)
                else: uc.verify_uncertainty(bad, *self.common)
        with self.assertRaises(ValueError): uc.verify_uncertainty(self.calibration, *self.common)
        (self.calibration/'calibration.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum'): uc.load_calibration(self.calibration)

    def test_settlement_corruption_identity_and_conflicts_rejected(self):
        settlement = self.settle()
        for mutate in (lambda m, v: m.update(horizon=1),
                       lambda m, v: m['state'].update(as_of_gameweek=3),
                       lambda m, v: v['live.json']['elements'].pop(),
                       lambda m, v: v['bootstrap.json']['events'][1].update(finished=False)):
            bad = republish(settlement, self.root/'bad', mutate)
            with self.assertRaises(ValueError): self.score([bad])
        # Another legitimate later capture is different evidence, not an automatic correction.
        second = mo.capture_settlement(self.forecast, *self.common, 2, self.root/'settlements',
                                      client=self.client(2, settled=True), clock=clock('2026-11-02T12:00:00Z'))[0]
        with self.assertRaisesRegex(ValueError, 'competing settlements'): self.score([settlement, second])

    def test_short_horizon_season_end_and_missing_keys(self):
        tables = load_json(self.calibration/'calibration.json')
        short = [r for r in self.rows if r['horizon'] == 0]
        self.assertEqual(uc.attach(short, tables)['cumulative'][0]['window_unavailable_reason'], 'projection_horizon_too_short')
        end = [{**r, 'as_of_gameweek': 38, 'target_gameweek': 38} for r in short]
        self.assertEqual(uc.attach(end, tables)['cumulative'][0]['window_unavailable_reason'], 'season_end')
        for bad in (self.rows[:-1], self.rows+self.rows[:1], [r for r in self.rows if r['horizon'] != 2]):
            with self.assertRaises(ValueError): uc.attach(bad, tables)

    def test_zero_outcomes_report_is_explicit_pending(self):
        report = load_json(self.score([])/'metrics.json')
        self.assertEqual(report['settled_target_gameweeks'], 0)
        self.assertEqual(len(report['pending_targets']), 5)
        self.assertIsNone(report['aggregate']['intervals']['90']['coverage'])
        self.assertEqual(report['cumulative']['5']['missing_outcomes'], 2)

    def test_overlapping_projections_keep_distinct_forecasts_but_consistent_outcomes(self):
        def move(meta, values):
            meta['as_of_gameweek'] = 3
            meta['deadline'] = '2026-09-26T12:00:00Z'
            for r in values['projections.json']:
                r['as_of_gameweek'] = 3
                r['target_gameweek'] += 1
        projection = republish(self.projection, self.root/'later_projection', move)
        later = uc.freeze(projection, *self.common, self.root/'forecasts', clock=self.frozen_clock)[0]
        first_settlement = self.settle(3)
        later_settlement = mo.capture_settlement(later, *self.common, 3, self.root/'settlements',
                                                 client=self.client(3, settled=True), clock=clock('2026-11-01T12:00:00Z'))[0]
        pairs = [(self.forecast, first_settlement), (later, later_settlement)]
        scored = mo.score([], pairs+pairs, *self.common, self.root/'scores')[0]
        report = load_json(scored/'metrics.json')
        self.assertEqual(report['settled_target_gameweeks'], 1)
        self.assertEqual(report['settled_projection_targets'], 2)
        self.assertEqual(report['scored_player_rows'], 4)
        self.assertEqual(report['horizons']['0']['scored_rows'], 2)
        self.assertEqual(report['horizons']['1']['scored_rows'], 2)
        self.assertEqual(len(report['targets']), 2)
        c = self.client(3, settled=True)
        c.live['elements'][0]['stats']['total_points'] += 1
        c.live['elements'][0]['explain'][0]['stats'][0]['points'] += 1
        revised = mo.capture_settlement(later, *self.common, 3, self.root/'settlements',
                                       client=c, clock=clock('2026-11-02T12:00:00Z'))[0]
        with self.assertRaisesRegex(ValueError, 'conflicting outcomes'):
            mo.score([], [(self.forecast, first_settlement), (later, revised)], *self.common, self.root/'scores')

    def test_final_publication_guard_removes_new_late_bundle(self):
        times = iter(['2026-09-17T11:01:00Z', '2026-09-17T11:02:00Z',
                      '2026-09-17T11:03:00Z', '2026-09-18T12:00:00Z'])
        with self.assertRaisesRegex(ValueError, 'deadline'):
            uc.freeze(self.projection, *self.common, self.root/'late', clock=lambda: clock(next(times))())
        self.assertEqual(list((self.root/'late').iterdir()), [])

    def test_calibration_incompatible_contract_or_model_fails(self):
        bad = republish(self.calibration, self.root/'bad', lambda m, v: m['contract'].update(model_identity='f'*64))
        with self.assertRaisesRegex(ValueError, 'contract'): uc.load_calibration(bad)
        wrong = republish(self.projection, self.root/'wrong', lambda m, v: m.update(model_identity='f'*64))
        with self.assertRaisesRegex(ValueError, 'model'):
            uc.freeze(wrong, *self.common, self.root/'wrong_forecast', clock=self.frozen_clock)

    def test_conflicting_uncertainty_versions_cannot_double_count(self):
        another = uc.freeze(self.projection, *self.common, self.root/'forecasts', clock=clock('2026-09-17T11:01:00Z'))[0]
        with self.assertRaisesRegex(ValueError, 'competing uncertainty'):
            mo.score([self.forecast, another], [], *self.common, self.root/'scores')

    def test_corrupt_score_reuse_fails_without_changing_calibration(self):
        settlement = self.settle()
        scored = self.score([settlement])
        before = fingerprint(self.calibration)
        (scored/'metrics.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'checksum'): self.score([settlement])
        self.assertEqual(before, fingerprint(self.calibration))

    def test_cli_and_no_global_ingestion_override(self):
        from fpl_ai.cli import build_parser, main
        args = build_parser().parse_args(['uncertainty', 'score', '--calibration-dir', 'c', '--m4e-model-dir', 'm',
                                         '--settlement-pair', 'f', 's'])
        self.assertEqual(args.settlement_pair, [[Path('f'), Path('s')]])
        with self.assertRaises(SystemExit): main(['--timeout', '1', 'uncertainty', 'calibrate'])
