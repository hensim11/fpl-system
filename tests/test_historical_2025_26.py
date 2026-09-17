"""2025/26 observed schemas, duplicate policy and offline pipeline regression."""

import csv
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_audit import audit_season, audit_cross_season_identity
from fpl_ai.historical_duplicates import filter_exact_duplicates, validate_duplicate_policy
from fpl_ai.historical_io import canonical_json_bytes, sha256_bytes
from fpl_ai.historical_pipeline import (
    _capture_from_path, _valid_snapshot, _validate_points_settlement_snapshot,
    create_build_identity, load_source_catalogue, run_historical_pipeline,
)
from fpl_ai.historical_schema import get_vaastav_source_schema, validate_vaastav_source_schema
from fpl_ai.historical_transform import parse_utc, read_source_csv
from tests.test_historical_pipeline import synthetic_sources, snapshot_bytes
from tests.test_historical_2023_24 import csv_data

FIXTURES = Path(__file__).parent / 'fixtures/historical_2025_26'


def raw_rows(value):
    return list(csv.DictReader(io.StringIO(value.decode())))


def synthetic_2025_sources(duplicate=True):
    values, catalogue = synthetic_sources()
    config = catalogue['seasons'].pop('2024-25')
    catalogue['seasons']['2025-26'] = config
    config['vaastav_source_schema']['schema_id'] = 'vaastav-2025-26-v1'
    catalogue = json.loads(json.dumps(catalogue).replace('data/2024-25/', 'data/2025-26/'))
    config = catalogue['seasons']['2025-26']
    schema = get_vaastav_source_schema('vaastav-2025-26-v1', '2025-26', 1)
    converted = {}
    for url, value in values.items():
        url = url.replace('data/2024-25/', 'data/2025-26/')
        if url.endswith('.csv'):
            name = url.rsplit('/', 1)[1]
            rows = raw_rows(value)
            if name == 'merged_gw.csv' and duplicate:
                rows.append(dict(rows[0]))
            value = csv_data(schema['files'][name]['known_column_order'], rows)
            if name == 'merged_gw.csv' and duplicate:
                config['exact_duplicate_rows'] = {
                    'policy_version': 1, 'season': '2025-26', 'source_path': 'data/2025-26/gws/merged_gw.csv',
                    'resolved_commit_sha': config['sources']['vaastav']['resolved_commit_sha'],
                    'source_sha256': sha256_bytes(value), 'source_row_count': len(rows),
                    'duplicates': [{'element': int(rows[0]['element']), 'fixture': int(rows[0]['fixture']),
                                    'gameweek': int(rows[0]['GW']), 'occurrences': 2}],
                    'reason': 'Synthetic exact-repeat regression fixture; dates intentionally reused from common fixture.',
                }
        converted[url] = value
    cache = config['sources']['fplcache']
    converted[cache['raw_base_url'] + '/cache/2024/8/30/1700.json.xz'] = snapshot_bytes(next_gameweek=3)
    return converted, catalogue


class Historical202526Tests(unittest.TestCase):
    def setUp(self):
        self.schema = get_vaastav_source_schema('vaastav-2025-26-v1', '2025-26', 1)

    def test_observed_headers_and_new_field_types(self):
        for name, contract in self.schema['files'].items():
            rows, audit = read_source_csv((FIXTURES/name).read_bytes(), name, self.schema, include_schema_audit=True)
            self.assertEqual(list(raw_rows((FIXTURES/name).read_bytes())[0]), contract['known_column_order'])
            self.assertTrue(audit['known_column_order_matches'])
            self.assertEqual(audit['unexpected_columns'], [])
            self.assertEqual(len(rows), 1)
        raw = raw_rows((FIXTURES/'merged_gw.csv').read_bytes())[0]
        for field in ['clearances_blocks_interceptions', 'defensive_contribution', 'recoveries', 'tackles']:
            self.assertIn(field, self.schema['files']['merged_gw.csv']['ignored_columns'])
            with self.subTest(field=field), self.assertRaises(FPLValidationError):
                read_source_csv(csv_data(list(raw), [dict(raw, **{field: '1.5'})]), 'merged_gw.csv', self.schema)
        normalized = read_source_csv((FIXTURES/'merged_gw.csv').read_bytes(), 'merged_gw.csv', self.schema)[0]
        self.assertNotIn('defensive_contribution', normalized['trusted'])
        self.assertNotIn('xP', normalized['trusted'])
        self.assertNotIn('xP', normalized['quarantined'])

    def test_missing_optional_and_invalid_core_types(self):
        raw = raw_rows((FIXTURES/'merged_gw.csv').read_bytes())[0]
        rows, audit = read_source_csv(csv_data([k for k in raw if k != 'starts'], [raw]), 'merged_gw.csv', self.schema, include_schema_audit=True)
        self.assertIsNone(rows[0]['trusted']['starts'])
        self.assertEqual(audit['optional_columns_absent'], ['starts'])
        for field, value in [('position', 'AM'), ('position', 'GKP'), ('minutes', '1.5'), ('modified', 'yes'), ('expected_goals', 'NaN')]:
            with self.subTest(field=field, value=value), self.assertRaises(FPLValidationError):
                read_source_csv(csv_data(list(raw), [dict(raw, **{field:value})]), 'merged_gw.csv', self.schema)
        with self.assertRaises(FPLValidationError):
            read_source_csv(csv_data([k for k in raw if k != 'fixture'], [raw]), 'merged_gw.csv', self.schema)
        with self.assertRaises(FPLValidationError):
            read_source_csv(csv_data([*raw, 'mng_win'], [dict(raw, mng_win='0')]), 'merged_gw.csv', self.schema)

    def test_xp_cannot_be_mapped_or_reclassified(self):
        schema = deepcopy(self.schema)
        contract = schema['files']['merged_gw.csv']
        contract['source_to_canonical_mappings']['xP'] = 'player_fixture_facts.expected_goals'
        with self.assertRaises(FPLValidationError):
            validate_vaastav_source_schema(schema)
        with self.assertRaises(FPLValidationError):
            get_vaastav_source_schema('vaastav-2025-26-v1', '2024-25', 1)

    def test_final_day_postdeadline_is_next_is_rejected_and_settlement_is_flag_based(self):
        evidence = json.loads((FIXTURES/'events.json').read_text())
        cache = load_source_catalogue()['seasons']['2025-26']['sources']['fplcache']
        deadline = parse_utc('2026-05-24T13:30:00Z', 'deadline')
        for item in evidence:
            capture = _capture_from_path(item['path'], cache)
            self.assertEqual(_valid_snapshot(item['payload'], 38, deadline, capture), item['path'].endswith('0839.json.xz'))
            if item['path'].endswith('1023.json.xz'):
                _validate_points_settlement_snapshot(item['payload'], 38, deadline, capture, item['path'])
            else:
                with self.assertRaises(FPLValidationError):
                    _validate_points_settlement_snapshot(item['payload'], 38, deadline, capture, item['path'])
        changed = deepcopy(evidence[0]['payload'])
        changed['events'][0]['deadline_time'] = '2026-05-24T14:30:00Z'
        self.assertFalse(_valid_snapshot(changed, 38, deadline, _capture_from_path(evidence[0]['path'], cache)))

    def test_exact_duplicates_preserve_first_raw_row_numbers(self):
        values, catalogue = synthetic_2025_sources()
        policy = catalogue['seasons']['2025-26']['exact_duplicate_rows']
        value = next(v for k,v in values.items() if k.endswith('merged_gw.csv'))
        rows = raw_rows(value)
        indexed, audit = filter_exact_duplicates(value, rows, policy, '2025-26')
        self.assertEqual([r for _,r in indexed], rows[:-1])
        self.assertEqual(indexed[0][0], 2)
        self.assertEqual(audit['removed_row_count'], 1)
        self.assertEqual(audit['duplicates'][0]['omitted_source_rows'], [len(rows)+1])

    def test_duplicate_policy_rejects_changed_hash_keys_counts_season_and_conflicts(self):
        values, catalogue = synthetic_2025_sources()
        policy = catalogue['seasons']['2025-26']['exact_duplicate_rows']
        value = next(v for k,v in values.items() if k.endswith('merged_gw.csv'))
        rows = raw_rows(value)
        for key, replacement in [('source_sha256', 'f'*64), ('source_row_count', 99), ('season', '2024-25'), ('policy_version', 2), ('policy_version', True)]:
            altered = dict(policy, **{key: replacement})
            with self.subTest(key=key), self.assertRaises(FPLValidationError):
                filter_exact_duplicates(value, rows, altered, '2025-26')
        for field, replacement in [('element', 999), ('gameweek', 9), ('occurrences', 3)]:
            altered = deepcopy(policy); altered['duplicates'][0][field] = replacement
            with self.subTest(field=field), self.assertRaises(FPLValidationError):
                filter_exact_duplicates(value, rows, altered, '2025-26')
        # Even if a revised file hash is explicitly pinned, conflicting ignored/forbidden
        # values cannot be silently collapsed after normalization discards them.
        for field in ['xP', 'name', 'total_points']:
            changed = deepcopy(rows); changed[-1][field] = '99'
            data = csv_data(list(changed[0]), changed)
            altered = dict(policy, source_sha256=sha256_bytes(data))
            with self.subTest(field=field), self.assertRaisesRegex(FPLValidationError, 'conflicting'):
                filter_exact_duplicates(data, changed, altered, '2025-26')
        changed = rows[:-1]
        data = csv_data(list(changed[0]), changed)
        altered = dict(policy, source_sha256=sha256_bytes(data), source_row_count=len(changed))
        with self.assertRaisesRegex(FPLValidationError, 'undeclared or stale'):
            filter_exact_duplicates(data, changed, altered, '2025-26')
        changed = rows + [dict(rows[1])]
        data = csv_data(list(changed[0]), changed)
        altered = dict(policy, source_sha256=sha256_bytes(data), source_row_count=len(changed))
        with self.assertRaisesRegex(FPLValidationError, 'undeclared or stale'):
            filter_exact_duplicates(data, changed, altered, '2025-26')
        altered = deepcopy(policy); altered['duplicates'].append(dict(altered['duplicates'][0]))
        with self.assertRaises(FPLValidationError):
            validate_duplicate_policy(altered, '2025-26')

    def test_old_build_hashes_and_new_policy_identity(self):
        catalogue = load_source_catalogue()
        hashes = {'2021-22': '5644015b364e43177485c5d5c3f520efe64b7a17d4113b84b56c400bab2c57d8',
                  '2022-23': '9227d246d3718724d8118898b6548077c8963837bdf49e9bc6bf64b30a7762a0',
                  '2023-24': '7886af1a34dd6293e9ea8bfb8c4b94eedd3bcee2c75f7f93d4a98eef390e35e8',
                  '2024-25': '1fbdcc84c93d92367c3f6f2a0b39d039dc04403980bb100491410523c62f9d86'}
        for season, expected in hashes.items():
            identity = create_build_identity(season, catalogue['seasons'][season], catalogue['schema_version'])
            self.assertEqual(sha256_bytes(canonical_json_bytes(identity)), expected)
            self.assertNotIn('exact_duplicate_rows', identity['season_contract'])
        config = deepcopy(catalogue['seasons']['2025-26'])
        before = deepcopy(create_build_identity('2025-26', config, 3))
        config['exact_duplicate_rows']['duplicates'][0]['occurrences'] += 1
        self.assertNotEqual(before, create_build_identity('2025-26', config, 3))
        config['exact_duplicate_rows']['resolved_commit_sha'] = 'a'*40
        with self.assertRaises(FPLValidationError):
            create_build_identity('2025-26', config, 3)

    def test_pipeline_reconciliation_inventory_offline_reuse_and_audit_failures(self):
        values, catalogue = synthetic_2025_sources()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root/'sources.json'; path.write_text(json.dumps(catalogue))
            result = run_historical_pipeline('2025-26', root, fetcher=values.__getitem__, source_catalogue_path=path)
            quality = json.loads((result.processed_dir/'data_quality_report.json').read_text())
            self.assertEqual(quality['total_points_reconciliation']['coverage_ratio'], 1.0)
            self.assertEqual(quality['total_points_reconciliation']['mismatching_row_count'], 0)
            self.assertEqual(quality['source_schema_changes']['merged_gw.csv']['exact_duplicate_rows']['removed_row_count'], 1)
            inventory = json.loads((result.processed_dir/'source_inventory.json').read_text())
            policy = catalogue['seasons']['2025-26']['exact_duplicate_rows']
            record = next(r for r in inventory['files'] if r['source_path'] == policy['source_path'])
            self.assertEqual(record['sha256'], policy['source_sha256'])
            self.assertIn('vaastav_transform:merged_gw.csv', record['consumption_roles'])
            tables = {p.stem: raw_rows(p.read_bytes()) for p in result.processed_dir.glob('*.csv')}
            args = ('2025-26', tables, result.raw_dir, inventory, catalogue['seasons']['2025-26'], quality)
            evidence = audit_season(*args)
            self.assertTrue(evidence['all_deadline_rows_equal_raw_observations'])
            self.assertEqual(evidence['source_duplicate_rows']['removed_row_count'], 1)
            self.assertIn('status', evidence['raw_snapshot_field_availability'])
            original = tables['player_deadline_snapshots'][0]['price']
            tables['player_deadline_snapshots'][0]['price'] = '999'
            with self.assertRaisesRegex(FPLValidationError, 'differs from raw'):
                audit_season(*args)
            tables['player_deadline_snapshots'][0]['price'] = original
            original = tables['fixtures'][0]['kickoff_time_utc']
            tables['fixtures'][0]['kickoff_time_utc'] = '2099-01-01T00:00:00Z'
            with self.assertRaisesRegex(FPLValidationError, 'premature settlement'):
                audit_season(*args)
            tables['fixtures'][0]['kickoff_time_utc'] = original
            snapshot_record = next(r for r in inventory['files'] if 'accepted_predeadline_snapshot' in r['consumption_roles'])
            original = snapshot_record['sha256']
            snapshot_record['sha256'] = 'f'*64
            with self.assertRaisesRegex(FPLValidationError, 'checksum'):
                audit_season(*args)
            snapshot_record['sha256'] = original
            before = {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
            def no_network(url):
                self.fail(f'unexpected network request {url}')
            self.assertTrue(run_historical_pipeline('2025-26', root, fetcher=no_network, source_catalogue_path=path).reused)
            self.assertEqual(before, {p:(p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()})

    def test_without_duplicate_policy_original_hard_failure_remains(self):
        values, catalogue = synthetic_2025_sources()
        del catalogue['seasons']['2025-26']['exact_duplicate_rows']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'sources.json';path.write_text(json.dumps(catalogue))
            with self.assertRaisesRegex(FPLValidationError, 'duplicate player-fixture'):
                run_historical_pipeline('2025-26', root, fetcher=values.__getitem__, source_catalogue_path=path)
            self.assertFalse((root/'historical/catalogue.json').exists())

    def test_cross_season_identity_excludes_manager_slots_and_preserves_position_changes(self):
        player = {'element': '1', 'player_code': '10', 'web_name': 'Player', 'end_of_season_position': 'MID'}
        data = {'2024-25':[player,dict(player,element='2',player_code='20',end_of_season_position='AM')],
                '2025-26':[dict(player,element='9',end_of_season_position='FWD'),dict(player,player_code='30')]}
        audit = audit_cross_season_identity(data)
        self.assertEqual(audit['football_player_codes'], 2)
        self.assertEqual(audit['codes_in_multiple_seasons'], 1)
        self.assertEqual(audit['element_ids_reused_for_different_codes'], 1)
        self.assertEqual(list(audit['cross_season_position_changes']), ['10'])
        data['2025-26'].append(dict(player))
        with self.assertRaises(FPLValidationError):
            audit_cross_season_identity(data)


if __name__ == '__main__':
    unittest.main()
