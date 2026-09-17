"""Independent settlement selection and operational audit regression coverage."""
import copy
import io
import json
import lzma
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import canonical_json_bytes, sha256_bytes
from fpl_ai.historical_pipeline import _decode_snapshot, create_build_identity, load_source_catalogue, run_historical_pipeline
from fpl_ai.historical_settlement import POLICY, STRATEGY, select_settled_events, later_mutations
from fpl_ai.historical_status import season_statuses
from fpl_ai.historical_transform import parse_utc
from scripts.verify_historical_seasons import main, verify
from tests.test_historical_pipeline import synthetic_sources, snapshot_bytes


def utc(value):
    return parse_utc(value, 'test')


def payload(points=1, settled=True, current=True):
    return {'events': [{'id': 17, 'deadline_time': '2021-12-14T18:15:00Z',
                        'finished': settled, 'data_checked': settled, 'is_current': current}],
            'elements': [{'id': 9, 'event_points': points}]}


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = [{'gameweek': 17, 'finished': True, 'kickoff_time_utc': '2021-12-16T20:00:00Z'}]
        self.deadlines = {17: utc('2021-12-14T18:15:00Z'), 18: utc('2021-12-18T16:00:00Z')}
        self.entries = [(utc('2021-12-17T01:00:00Z'), 'first'), (utc('2021-12-17T06:00:00Z'), 'second')]
        self.values = {'first': payload(), 'second': payload(points=0)}

    def select(self, entries=None):
        def obtain(path):
            value = json.dumps(self.values[path]).encode()
            return value, {'source_path': path, 'sha256': sha256_bytes(value)}
        return select_settled_events(self.fixtures, self.deadlines,
                                     self.entries if entries is None else entries,
                                     POLICY, obtain, lambda b, p: json.loads(b))

    def test_independent_of_missing_next_deadline_snapshot_and_point_agreement(self):
        selected, evidence, consumed = self.select()
        self.assertEqual(selected[17][1], 'first')
        self.assertEqual(selected[17][0]['elements'][0]['event_points'], 1)
        self.assertEqual(evidence['17']['capture_time_utc'], '2021-12-17T01:00:00Z')
        self.assertIn('total_points_reconciliation', [role for _, role in consumed])
        self.assertEqual(self.select(list(reversed(self.entries))), (selected, evidence, consumed))

    def test_unsettled_candidate_rejected_and_materially_audited(self):
        self.values['first'] = payload(settled=False)
        selected, evidence, consumed = self.select()
        self.assertEqual(selected[17][1], 'second')
        self.assertEqual(evidence['17']['rejected_candidates'][0]['reason'], 'event_not_settled')
        self.assertEqual({r['source_path'] for r, _ in consumed}, {'first', 'second'})
        self.values['second'] = payload(settled=False)
        with self.assertRaisesRegex(FPLValidationError, 'no valid'):
            self.select()

    def test_capture_before_cutoff_or_after_next_deadline_is_never_used(self):
        for stamp in ('2021-12-16T21:59:00Z', '2021-12-16T22:00:00Z', '2021-12-18T16:00:00Z'):
            with self.subTest(stamp=stamp), self.assertRaisesRegex(FPLValidationError, 'no valid'):
                self.select([(utc(stamp), 'first')])

    def test_missing_ambiguous_stale_and_malformed_evidence_fails(self):
        with self.assertRaisesRegex(FPLValidationError, 'no valid'):
            self.select([])
        with self.assertRaisesRegex(FPLValidationError, 'ambiguous'):
            self.select([self.entries[0], (self.entries[0][0], 'second')])
        changes = []
        p = payload(current=False); changes.append(p)
        p = payload(); p['events'].append(p['events'][0]); changes.append(p)
        p = payload(); p['elements'].append(p['elements'][0]); changes.append(p)
        p = payload(); p['events'][0]['finished'] = 'true'; changes.append(p)
        p = payload(); p['elements'][0]['event_points'] = None; changes.append(p)
        p = payload(); p['events'][0]['deadline_time'] = '2021-12-14T18:14:00Z'; changes.append(p)
        for changed in changes:
            self.values['first'] = changed
            with self.subTest(changed=changed), self.assertRaises(FPLValidationError):
                self.select()

    def test_later_mutation_is_diagnostic_without_changing_selection(self):
        selected, _, _ = self.select()
        later = {18: (utc('2021-12-18T12:00:00Z'), 'later', payload(points=0), {'sha256': 'hash'})}
        differences = later_mutations(selected, later, self.deadlines)
        self.assertEqual(differences[0]['selected_event_points'], 1)
        self.assertEqual(differences[0]['later_event_points'], 0)
        self.assertEqual(selected[17][1], 'first')

    def test_real_james_and_gw17_selected_evidence(self):
        evidence = json.loads((Path(__file__).parent / 'fixtures/historical_2021_22/settled_selection.json').read_text())
        for case in evidence:
            gw = case['gameweek']
            fixtures = [{'gameweek': gw, 'finished': True, 'kickoff_time_utc': case['last_kickoff']}]
            deadline = utc(case['deadline'])
            entries = [(utc(r['capture']), r['path']) for r in case['captures']]
            values = {r['path']: r for r in case['captures']}
            def obtain(path):
                r = values[path]
                return json.dumps(r['payload']).encode(), {'sha256': r['sha256'], 'source_path': path}
            result, audit, _ = select_settled_events(fixtures, {gw: deadline}, entries, POLICY, obtain, lambda b, p: json.loads(b))
            self.assertEqual(result[gw][1], case['expected_selected_path'])
            if gw == 3:
                james = next(e for e in result[gw][0]['elements'] if e['id'] == 287)
                self.assertEqual(james['event_points'], 1)
            self.assertTrue(audit[str(gw)]['finished'])

    def test_policy_participates_in_build_identity_and_invalid_policy_fails(self):
        catalogue = load_source_catalogue(); config = catalogue['seasons']['2021-22']
        current = create_build_identity('2021-22', config, catalogue['schema_version'])
        self.assertEqual(current['reconciliation']['total_points']['comparison_source']['selection_policy'], POLICY)
        old = copy.deepcopy(config)
        comparison = old['reconciliation']['total_points']['comparison_source']
        comparison.pop('selection_policy'); comparison['settlement_strategy'] = 'next_accepted_deadline_snapshot_plus_final_settlement'
        self.assertNotEqual(current, create_build_identity('2021-22', old, catalogue['schema_version']))
        changed = copy.deepcopy(config)
        changed['reconciliation']['total_points']['comparison_source']['selection_policy']['tie_policy'] = 'first'
        with self.assertRaises(FPLValidationError):
            create_build_identity('2021-22', changed, catalogue['schema_version'])

    def test_pipeline_frozen_inventory_rebuild_reuse_and_publication_protection(self):
        values, catalogue = synthetic_sources()
        config = catalogue['seasons']['2024-25']
        config['expected_gameweeks'] = [1]
        policy = config['reconciliation']['total_points']
        policy['policy_version'] = 3
        policy['comparison_source'].update(settlement_strategy=STRATEGY, selection_policy=POLICY)
        cache = config['sources']['fplcache']
        path = 'cache/2024/8/21/0100.json.xz'
        cache['points_settlement_snapshot_path'] = path
        value = json.loads(lzma.decompress(snapshot_bytes(next_gameweek=None, finished_and_checked=(1,))))
        value['events'][0]['is_current'] = True
        values[cache['raw_base_url'] + '/' + path] = lzma.compress(json.dumps(value).encode())
        tree = json.loads(values[cache['tree_url']]); tree['tree'].append({'path': path, 'type': 'blob'})
        values[cache['tree_url']] = json.dumps(tree).encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); cfg = root / 'sources.json'; cfg.write_text(json.dumps(catalogue))
            first = run_historical_pipeline('2024-25', root / 'a', fetcher=values.__getitem__, source_catalogue_path=cfg)
            report = json.loads((first.processed_dir / 'total_points_reconciliation.json').read_text())
            self.assertEqual(report['coverage_ratio'], 1.0)
            digest = report.pop('artifact_sha256')
            self.assertEqual(digest, sha256_bytes(canonical_json_bytes(report)))
            inventory = json.loads((first.processed_dir / 'source_inventory.json').read_text())
            record = next(r for r in inventory['files'] if r['source_path'] == path)
            self.assertIn('total_points_reconciliation', record['consumption_roles'])
            self.assertIn('settlement_selection_evidence', record['consumption_roles'])
            again = run_historical_pipeline('2024-25', root / 'b', fetcher=values.__getitem__, source_catalogue_path=cfg)
            for csv in first.processed_dir.glob('*.csv'):
                self.assertEqual(csv.read_bytes(), (again.processed_dir / csv.name).read_bytes())
            for key in ('source_identity_sha256', 'build_identity_sha256'):
                self.assertEqual(json.loads((first.processed_dir / 'manifest.json').read_text())[key],
                                 json.loads((again.processed_dir / 'manifest.json').read_text())[key])
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / 'a').rglob('*') if p.is_file()}
            self.assertTrue(run_historical_pipeline('2024-25', root / 'a', fetcher=lambda url: self.fail(url), source_catalogue_path=cfg).reused)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in (root / 'a').rglob('*') if p.is_file()})
            config['expected_counts']['gameweeks_with_valid_snapshot'] = 2
            cfg.write_text(json.dumps(catalogue))
            with self.assertRaisesRegex(FPLValidationError, 'gameweeks_with_valid_snapshot'):
                run_historical_pipeline('2024-25', root / 'blocked', fetcher=values.__getitem__, source_catalogue_path=cfg)
            self.assertFalse((root / 'blocked/historical/catalogue.json').exists())


class AuditStatusTests(unittest.TestCase):
    def test_statuses_use_publication_not_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); h = root / 'historical'; h.mkdir()
            (h / 'catalogue.json').write_text(json.dumps({'seasons': {'2022-23': {}}}))
            failed = h / 'failed/2021-22'; failed.mkdir(parents=True); (failed / 'attempt.json').write_text('{}')
            self.assertEqual(season_statuses(root, ['2021-22', '2022-23', '2025-26']),
                             {'2021-22': 'blocked', '2022-23': 'published', '2025-26': 'investigatory'})

    def test_default_empty_publication_does_not_attempt_configured_builds(self):
        with tempfile.TemporaryDirectory() as tmp, patch('scripts.verify_historical_seasons.run_historical_pipeline') as run:
            self.assertEqual(verify(Path(tmp))['seasons'], {})
            run.assert_not_called()
            with self.assertRaisesRegex(FPLValidationError, 'unpublished'):
                verify(Path(tmp), ['2021-22'])

    def test_invalid_cli_combinations_are_argparse_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            common = ['--output-dir', tmp, '--report', str(Path(tmp) / 'audit.json')]
            for flags in (['--season', '2021-22'], ['--acquire-2021-22-evidence']):
                stderr = io.StringIO()
                with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                    main(common + flags)
                self.assertEqual(caught.exception.code, 2)
                self.assertNotIn('Traceback', stderr.getvalue())

    def test_explicit_blocked_investigation_is_separate(self):
        with tempfile.TemporaryDirectory() as tmp, patch('scripts.verify_historical_seasons.verify_2021_22_rejection', return_value={'published': False}) as investigation:
            report = Path(tmp) / 'audit.json'
            self.assertEqual(main(['--output-dir', tmp, '--report', str(report), '--investigate-season', '2021-22']), 0)
            self.assertFalse(json.loads(report.read_text())['rejected_seasons']['2021-22']['published'])
            investigation.assert_called_once()

    def test_published_investigation_and_malformed_catalogue_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'historical').mkdir()
            path = root / 'historical/catalogue.json'
            path.write_text(json.dumps({'seasons': {'2022-23': {}}}))
            stderr = io.StringIO()
            with redirect_stderr(stderr), self.assertRaises(SystemExit) as caught:
                main(['--output-dir', tmp, '--report', str(root / 'report.json'), '--investigate-season', '2022-23'])
            self.assertEqual(caught.exception.code, 2)
            self.assertNotIn('Traceback', stderr.getvalue())
            path.write_text('{')
            with self.assertRaisesRegex(FPLValidationError, 'invalid published'):
                season_statuses(root, ['2022-23'])
