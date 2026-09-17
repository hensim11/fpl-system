"""Observed older schema and shared historical contracts, without network access."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import canonical_json_bytes, sha256_bytes
from fpl_ai.historical_pipeline import (
    _capture_from_path, _validate_points_settlement_snapshot,
    create_build_identity, load_source_catalogue, run_historical_pipeline,
)
from fpl_ai.historical_schema import get_vaastav_source_schema, POST_EVENT_FIXTURE_CONTEXT_FIELDS
from fpl_ai.historical_transform import parse_utc, read_source_csv
from tests.test_historical_2023_24 import csv_data
from tests.test_historical_pipeline import synthetic_sources

FIXTURES = Path(__file__).parent / 'fixtures' / 'historical_2021_22'
ABSENT_METRICS = ('starts', 'expected_goals', 'expected_assists',
                  'expected_goal_involvements', 'expected_goals_conceded')


class Historical202122Tests(unittest.TestCase):
    def setUp(self):
        self.schema = get_vaastav_source_schema('vaastav-2021-22-v1', '2021-22', 1)

    def test_observed_headers_types_and_unavailable_metrics(self):
        for name, contract in self.schema['files'].items():
            with self.subTest(name=name):
                data = (FIXTURES / name).read_bytes()
                rows, audit = read_source_csv(data, name, self.schema, include_schema_audit=True)
                self.assertEqual(next(csv.reader(io.StringIO(data.decode()))), contract['known_column_order'])
                self.assertEqual(len(rows), 1)
                self.assertEqual(audit['unexpected_columns'], [])
                self.assertEqual(audit['required_columns_missing'], [])
                self.assertTrue(audit['known_column_order_matches'])
        facts = read_source_csv((FIXTURES / 'merged_gw.csv').read_bytes(), 'merged_gw.csv', self.schema)
        self.assertTrue(all(facts[0]['trusted'].get(k) is None for k in ABSENT_METRICS))
        self.assertEqual(self.schema['expected_metric_fields_available'], [])
        self.assertNotIn('modified', facts[0]['quarantined'])

    def test_rejects_newer_columns_invalid_types_and_required_field_loss(self):
        row = next(csv.DictReader(io.StringIO((FIXTURES / 'merged_gw.csv').read_text())))
        for field in (*ABSENT_METRICS, 'modified', 'mng_win'):
            with self.subTest(field=field), self.assertRaisesRegex(FPLValidationError, 'unexpected columns'):
                read_source_csv(csv_data([*row, field], [dict(row, **{field: '0'})]), 'merged_gw.csv', self.schema)
        for field, value in [('minutes', '1.5'), ('position', 'AM'), ('was_home', 'yes')]:
            with self.subTest(field=field), self.assertRaises(FPLValidationError):
                read_source_csv(csv_data(list(row), [dict(row, **{field: value})]), 'merged_gw.csv', self.schema)
        with self.assertRaisesRegex(FPLValidationError, 'missing required'):
            read_source_csv(csv_data([c for c in row if c != 'total_points'], [row]), 'merged_gw.csv', self.schema)

    def test_xp_cannot_enter_trusted_or_quarantined_output(self):
        row = next(csv.DictReader(io.StringIO((FIXTURES / 'merged_gw.csv').read_text())))
        row['xP'] = 'untrusted'
        rows = read_source_csv(csv_data(list(row), [row]), 'merged_gw.csv', self.schema)
        for namespace in ('trusted', 'quarantined'):
            self.assertNotIn('xP', rows[0][namespace])

    def test_config_and_prior_build_identities_are_preserved(self):
        catalogue = load_source_catalogue()
        c = catalogue['seasons']['2021-22']
        self.assertEqual(c['expected_counts']['player_fixture_facts'], 25447)
        self.assertEqual(c['reconciliation']['total_points']['minimum_coverage_ratio'], 1.0)
        self.assertEqual(c['reconciliation']['total_points']['mode'], 'required')
        digests = {'2022-23': '9227d246d3718724d8118898b6548077c8963837bdf49e9bc6bf64b30a7762a0',
                   '2023-24': '7886af1a34dd6293e9ea8bfb8c4b94eedd3bcee2c75f7f93d4a98eef390e35e8',
                   '2024-25': '1fbdcc84c93d92367c3f6f2a0b39d039dc04403980bb100491410523c62f9d86'}
        for season, digest in digests.items():
            with self.subTest(season=season):
                identity = create_build_identity(season, catalogue['seasons'][season], catalogue['schema_version'])
                self.assertEqual(sha256_bytes(canonical_json_bytes(identity)), digest)
                with self.assertRaises(FPLValidationError):
                    get_vaastav_source_schema('vaastav-2021-22-v1', season, 1)

    def test_real_final_settlement_flags_are_enforced(self):
        config = load_source_catalogue()['seasons']['2021-22']['sources']['fplcache']
        evidence = json.loads((FIXTURES / 'settlement_events.json').read_text())
        for entry in evidence[1:]:
            path = entry['path']
            args = (entry['payload'], 38, parse_utc('2022-05-22T13:30:00Z', 'deadline'),
                    _capture_from_path(path, config), path)
            if path == config['points_settlement_snapshot_path']:
                _validate_points_settlement_snapshot(*args)
            else:
                with self.assertRaisesRegex(FPLValidationError, 'finished and data_checked'):
                    _validate_points_settlement_snapshot(*args)

    def test_generic_build_preserves_nulls_deadline_identity_and_reuses(self):
        values, catalogue = synthetic_sources()
        catalogue = json.loads(json.dumps(catalogue).replace('2024-25', '2021-22'))
        converted = {}
        for url, data in values.items():
            if url.endswith('.csv'):
                name = url.rsplit('/', 1)[1]
                data = csv_data(self.schema['files'][name]['known_column_order'], list(csv.DictReader(io.StringIO(data.decode()))))
            converted[url.replace('2024-25', '2021-22')] = data
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'sources.json'
            config.write_text(json.dumps(catalogue))
            result = run_historical_pipeline('2021-22', root, fetcher=converted.__getitem__, source_catalogue_path=config)
            def rows(name):
                with (result.processed_dir / (name + '.csv')).open() as stream:
                    return list(csv.DictReader(stream))
            self.assertTrue(all(r[k] == '' for r in rows('player_fixture_facts') for k in ABSENT_METRICS))
            self.assertTrue(all(r['modified'] == '' for r in rows('quarantined_source_metadata')))
            snapshots = rows('player_deadline_snapshots')
            self.assertFalse(set(snapshots[0]) & set(POST_EVENT_FIXTURE_CONTEXT_FIELDS))
            self.assertTrue(all(r['deadline_position'] and r['deadline_team_id'] for r in snapshots))
            self.assertTrue(all(parse_utc(r['capture_time_utc'], 'capture') < parse_utc(r['deadline_time_utc'], 'deadline') for r in snapshots))
            report = json.loads((result.processed_dir / 'total_points_reconciliation.json').read_text())
            self.assertEqual(report['coverage_ratio'], 1.0)
            self.assertEqual(report['mismatching_row_count'], 0)
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
            def no_network(url):
                self.fail(f'unexpected fetch: {url}')
            self.assertTrue(run_historical_pipeline('2021-22', root, fetcher=no_network, source_catalogue_path=config).reused)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()})

    def test_observed_goalkeeper_alias_and_unknown_position_rejection(self):
        data = (FIXTURES / 'goalkeeper_alias.csv').read_bytes()
        rows = read_source_csv(data, 'merged_gw.csv', self.schema)
        self.assertEqual(rows[0]['trusted']['position_at_fixture'], 'GK')
        self.assertEqual(rows[0]['trusted']['gameweek'], 37)
        raw = next(csv.DictReader(io.StringIO(data.decode())))
        raw['position'] = 'KEEPER'
        with self.assertRaises(FPLValidationError):
            read_source_csv(csv_data(list(raw), [raw]), 'merged_gw.csv', self.schema)
        newer = get_vaastav_source_schema('vaastav-2022-23-v1', '2022-23', 1)
        raw['position'] = 'GKP'
        with self.assertRaises(FPLValidationError):
            read_source_csv(csv_data(list(raw), [raw]), 'merged_gw.csv', newer)

    def test_alias_policy_is_validated_and_hashed(self):
        from copy import deepcopy
        from unittest.mock import patch
        from fpl_ai.historical_schema import validate_vaastav_source_schema, VAASTAV_SOURCE_SCHEMAS
        for aliases in ({'GK': 'DEF'}, {'GKP': 'UNKNOWN'}, {'GKP': 1}, {'GKP': 'OTHER', 'OTHER': 'GK'}, {}, [], {'': 'GK'}, {'null': 'GK'}):
            schema = deepcopy(self.schema)
            schema['files']['merged_gw.csv']['type_expectations']['position']['value_aliases'] = aliases
            with self.subTest(aliases=aliases), self.assertRaises(FPLValidationError):
                validate_vaastav_source_schema(schema)
        schema = deepcopy(self.schema)
        schema['adapter_id'] = 'declarative-normalization-v1'
        with self.assertRaisesRegex(FPLValidationError, 'requires adapter v2'):
            validate_vaastav_source_schema(schema)
        catalogue = load_source_catalogue()
        config = catalogue['seasons']['2021-22']
        before = create_build_identity('2021-22', config, catalogue['schema_version'])
        schema = deepcopy(self.schema)
        schema['files']['merged_gw.csv']['type_expectations']['position']['value_aliases'] = {'GOALKEEPER': 'GK'}
        with patch.dict(VAASTAV_SOURCE_SCHEMAS, {'vaastav-2021-22-v1': schema}):
            self.assertNotEqual(before, create_build_identity('2021-22', config, catalogue['schema_version']))

    def test_exact_kickoff_policy_preserves_raw_and_rejects_stale_changes(self):
        from copy import deepcopy
        from fpl_ai.historical_transform import reconcile_fixture_kickoffs, transform_fixtures
        rows = read_source_csv((FIXTURES / 'delayed_fixture_facts.csv').read_bytes(), 'merged_gw.csv', self.schema)
        fixtures = transform_fixtures('2021-22', read_source_csv((FIXTURES / 'delayed_fixture.csv').read_bytes(), 'fixtures.csv', self.schema))
        policy = load_source_catalogue()['seasons']['2021-22']['fixture_kickoff_reconciliation']
        before = deepcopy(rows)
        corrected, audit = reconcile_fixture_kickoffs(rows, fixtures, policy)
        self.assertEqual(rows, before)
        self.assertEqual(audit[0]['normalized_rows'], 78)
        self.assertTrue(all(r['trusted']['kickoff_time_utc'] == '2022-02-26T15:30:00Z' for r in corrected))
        for change in ({'fixture': 264}, {'gameweek': 28}, {'expected_rows': 77},
                       {'source_kickoff': '2022-02-26T14:00:00Z'},
                       {'fixture_kickoff': '2022-02-26T16:00:00Z'}):
            altered = [dict(policy[0], **change)]
            with self.subTest(change=change), self.assertRaises(FPLValidationError):
                reconcile_fixture_kickoffs(rows, fixtures, altered)

    def test_kickoff_policy_configuration_is_validated_and_hashed(self):
        from copy import deepcopy
        catalogue = load_source_catalogue()
        config = catalogue['seasons']['2021-22']
        identity = create_build_identity('2021-22', config, catalogue['schema_version'])
        changed = deepcopy(config)
        changed['fixture_kickoff_reconciliation'][0]['expected_rows'] = 77
        self.assertNotEqual(identity, create_build_identity('2021-22', changed, catalogue['schema_version']))
        for field, value in [('fixture', True), ('expected_rows', 0), ('reason', ''),
                             ('source_kickoff', 'invalid'), ('fixture_kickoff', '2022-02-26T15:00:00Z')]:
            changed = deepcopy(config)
            changed['fixture_kickoff_reconciliation'][0][field] = value
            with self.subTest(field=field), self.assertRaises(FPLValidationError):
                create_build_identity('2021-22', changed, catalogue['schema_version'])
        for policy in ([], None, [{}, {}], config['fixture_kickoff_reconciliation'] * 2):
            changed = dict(config, fixture_kickoff_reconciliation=policy)
            with self.subTest(policy=policy), self.assertRaises(FPLValidationError):
                create_build_identity('2021-22', changed, catalogue['schema_version'])

    def test_observed_gw18_deadline_gap_is_not_backfilled(self):
        from fpl_ai.historical_pipeline import _valid_snapshot
        evidence = json.loads((FIXTURES / 'acceptance_blockers.json').read_text())
        config = load_source_catalogue()['seasons']['2021-22']['sources']['fplcache']
        deadline = parse_utc('2021-12-18T16:00:00Z', 'deadline')
        for entry in evidence['gw18_captures']:
            self.assertFalse(_valid_snapshot({'events': [entry['event']]}, 18, deadline,
                                             _capture_from_path(entry['path'], config)))
        self.assertEqual(load_source_catalogue()['seasons']['2021-22']['expected_counts']['gameweeks_with_valid_snapshot'], 38)

    def test_observed_transfer_points_change_is_not_a_match(self):
        from tests.test_historical_pipeline import reconcile_for_test
        evidence = json.loads((FIXTURES / 'acceptance_blockers.json').read_text())
        captures = evidence['james_captures']
        self.assertEqual(captures[0]['player']['event_points'], 1)
        self.assertEqual(captures[1]['player']['event_points'], 0)
        self.assertTrue(all(e['event']['finished'] and e['event']['data_checked'] for e in captures))
        later = captures[1]
        facts = [{'season': '2021-22', 'gameweek': 3, 'element': 287, 'total_points': 1}]
        result = reconcile_for_test(facts, {3: ({'events': [later['event']], 'elements': [later['player']]}, later['path'], 'abc')})
        self.assertFalse(result['passed'])
        self.assertEqual(result['mismatching_row_count'], 1)

    def test_pipeline_kickoff_audit_and_failed_attempt_do_not_publish(self):
        from copy import deepcopy
        values, catalogue = synthetic_sources()
        catalogue = json.loads(json.dumps(catalogue).replace('2024-25', '2021-22'))
        converted = {}
        policy = None
        for url, data in values.items():
            if url.endswith('.csv'):
                name = url.rsplit('/', 1)[1]
                rows = list(csv.DictReader(io.StringIO(data.decode())))
                if name == 'merged_gw.csv':
                    first = rows[0]
                    policy = dict(fixture=int(first['fixture']), gameweek=int(first['GW']),
                                  source_kickoff='2025-05-01T12:00:00Z',
                                  fixture_kickoff=first['kickoff_time'],
                                  expected_rows=sum(r['fixture'] == first['fixture'] for r in rows),
                                  reason='Synthetic delayed kickoff')
                    for row in rows:
                        if row['fixture'] == first['fixture']:
                            row['kickoff_time'] = policy['source_kickoff']
                data = csv_data(self.schema['files'][name]['known_column_order'], rows)
            converted[url.replace('2024-25', '2021-22')] = data
        for valid in (True, False):
            with self.subTest(valid=valid), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = deepcopy(catalogue)
                rule = dict(policy, expected_rows=policy['expected_rows'] + (0 if valid else 1))
                config['seasons']['2021-22']['fixture_kickoff_reconciliation'] = [rule]
                path = root / 'sources.json'
                path.write_text(json.dumps(config))
                if valid:
                    result = run_historical_pipeline('2021-22', root, fetcher=converted.__getitem__, source_catalogue_path=path)
                    report = json.loads((result.processed_dir / 'data_quality_report.json').read_text())
                    self.assertTrue(report['passed'])
                    self.assertEqual(report['fixture_kickoff_reconciliation'][0]['normalized_rows'], policy['expected_rows'])
                else:
                    with self.assertRaisesRegex(FPLValidationError, 'row count mismatch'):
                        run_historical_pipeline('2021-22', root, fetcher=converted.__getitem__, source_catalogue_path=path)
                    self.assertFalse((root / 'historical/catalogue.json').exists())
                    failed = list((root / 'historical/failed/2021-22').glob('*.json'))
                    self.assertEqual(len(failed), 1)
                    report = json.loads(failed[0].read_text())
                    self.assertFalse(report['catalogue_updated'])
                    self.assertEqual(report['failures'], ['facts.transformation'])
