"""Observed 2022/23 source shape, blank gameweek and cross-season contracts."""

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
from fpl_ai.historical_schema import get_vaastav_source_schema
from fpl_ai.historical_transform import parse_utc, read_source_csv
from tests.test_historical_2023_24 import csv_data
from tests.test_historical_pipeline import synthetic_sources

FIXTURES = Path(__file__).parent / 'fixtures' / 'historical_2022_23'


class Historical202223Tests(unittest.TestCase):
    def test_observed_headers_and_values_match_declared_contract(self):
        schema = get_vaastav_source_schema('vaastav-2022-23-v1', '2022-23', 1)
        older = get_vaastav_source_schema('vaastav-2023-24-v1', '2023-24', 1)
        self.assertEqual(schema['files'], older['files'])
        for filename, contract in schema['files'].items():
            with self.subTest(filename=filename):
                rows, audit = read_source_csv((FIXTURES / filename).read_bytes(), filename, schema, include_schema_audit=True)
                self.assertEqual(len(rows), 1)
                self.assertTrue(audit['known_column_order_matches'])
                self.assertEqual(audit['unexpected_columns'], [])
                self.assertEqual(audit['required_columns_missing'], [])
                self.assertEqual(next(csv.reader(io.StringIO((FIXTURES / filename).read_text()))), contract['known_column_order'])
                self.assertNotIn('xP', rows[0]['trusted'])
                self.assertNotIn('modified', rows[0]['quarantined'])

    def test_source_contract_remains_strict_and_nullable(self):
        schema = get_vaastav_source_schema('vaastav-2022-23-v1', '2022-23', 1)
        with (FIXTURES / 'merged_gw.csv').open() as stream:
            row = next(csv.DictReader(stream))
        for field, value in [('position', 'AM'), ('minutes', '1.5'), ('was_home', 'yes'), ('expected_goals', 'NaN')]:
            with self.subTest(field=field), self.assertRaises(FPLValidationError):
                read_source_csv(csv_data(list(row), [dict(row, **{field: value})]), 'merged_gw.csv', schema)
        for field in ['mng_win', 'modified']:
            with self.subTest(field=field), self.assertRaisesRegex(FPLValidationError, 'unexpected columns'):
                read_source_csv(csv_data([*row, field], [dict(row, **{field: '0'})]), 'merged_gw.csv', schema)
        rows = read_source_csv(csv_data([c for c in row if c != 'expected_goals'], [row]), 'merged_gw.csv', schema)
        self.assertIsNone(rows[0]['trusted']['expected_goals'])
        with self.assertRaisesRegex(FPLValidationError, 'missing required'):
            read_source_csv(csv_data([c for c in row if c != 'fixture'], [row]), 'merged_gw.csv', schema)

    def test_existing_build_identities_and_season_scoping_are_preserved(self):
        catalogue = load_source_catalogue()
        for season, digest in [('2023-24', '7886af1a34dd6293e9ea8bfb8c4b94eedd3bcee2c75f7f93d4a98eef390e35e8'), ('2024-25', '1fbdcc84c93d92367c3f6f2a0b39d039dc04403980bb100491410523c62f9d86')]:
            with self.subTest(season=season):
                identity = create_build_identity(season, catalogue['seasons'][season], catalogue['schema_version'])
                self.assertEqual(sha256_bytes(canonical_json_bytes(identity)), digest)
                with self.assertRaises(FPLValidationError):
                    get_vaastav_source_schema('vaastav-2022-23-v1', season, 1)
        config = catalogue['seasons']['2022-23']
        self.assertEqual(config['expected_gameweeks'], list(range(1, 39)))
        self.assertEqual(config['expected_counts']['fixture_gameweeks'], 37)
        self.assertEqual(config['expected_counts']['gameweeks_with_valid_snapshot'], 38)
        self.assertEqual(config['reconciliation']['total_points']['minimum_coverage_ratio'], 1.0)

    def test_observed_final_settlement_rejects_unsettled_capture(self):
        config = load_source_catalogue()['seasons']['2022-23']['sources']['fplcache']
        for evidence in json.loads((FIXTURES / 'settlement_events.json').read_text()):
            path = evidence['path']
            args = (evidence['payload'], 38, parse_utc('2023-05-28T14:00:00Z', 'deadline'), _capture_from_path(path, config), path)
            if path == config['points_settlement_snapshot_path']:
                _validate_points_settlement_snapshot(*args)
            else:
                with self.assertRaises(FPLValidationError):
                    _validate_points_settlement_snapshot(*args)

    def test_blank_gameweek_keeps_deadline_rows_without_invented_facts(self):
        values, catalogue = synthetic_sources()
        catalogue = json.loads(json.dumps(catalogue).replace('2024-25', '2022-23'))
        schema = get_vaastav_source_schema('vaastav-2022-23-v1', '2022-23', 1)
        converted = {}
        for url, data in values.items():
            if url.endswith('.csv'):
                name = url.rsplit('/', 1)[1]
                data = csv_data(schema['files'][name]['known_column_order'], list(csv.DictReader(io.StringIO(data.decode()))))
            converted[url.replace('2024-25', '2022-23')] = data
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'sources.json'
            config.write_text(json.dumps(catalogue))
            result = run_historical_pipeline('2022-23', root, fetcher=converted.__getitem__, source_catalogue_path=config)
            def rows(name):
                with (result.processed_dir / (name + '.csv')).open() as stream:
                    return list(csv.DictReader(stream))
            self.assertEqual({r['gameweek'] for r in rows('gameweeks')}, {'1', '2', '3'})
            self.assertTrue(any(r['gameweek'] == '2' for r in rows('player_deadline_snapshots')))
            self.assertFalse(any(r['gameweek'] == '2' for r in rows('player_fixture_facts')))
            self.assertTrue(all(r['modified'] == '' for r in rows('quarantined_source_metadata')))
            reconciliation = json.loads((result.processed_dir / 'total_points_reconciliation.json').read_text())
            self.assertEqual(reconciliation['coverage_ratio'], 1.0)
            self.assertNotIn('2', reconciliation['by_gameweek'])
            self.assertEqual(reconciliation['eligible_row_count'], 2)
            self.assertEqual(reconciliation['mismatching_row_count'], 0)

    def test_exact_code_exception_preserves_observation_and_rejects_other_changes(self):
        import lzma
        from copy import deepcopy
        values, catalogue = synthetic_sources()
        config = catalogue['seasons']['2024-25']
        path = config['sources']['fplcache']['reference_snapshot_path']
        url = config['sources']['fplcache']['raw_base_url'] + '/' + path
        payload = json.loads(lzma.decompress(values[url]))
        payload['elements'][0]['code'] = 1009
        values[url] = lzma.compress(json.dumps(payload).encode())
        exception = dict(gameweek=1, element=101, snapshot_player_code=1009,
                         final_player_code=1001, snapshot_source_path=path,
                         reason='Synthetic observed code change')
        config['snapshot_player_code_exceptions'] = [exception]
        for change in [None, {'gameweek': 2}, {'element': 102}, {'snapshot_player_code': 1010},
                       {'final_player_code': 1002}, {'snapshot_source_path': 'wrong/path'}]:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                altered = deepcopy(catalogue)
                if change:
                    altered['seasons']['2024-25']['snapshot_player_code_exceptions'][0].update(change)
                root = Path(directory)
                config_path = root / 'sources.json'
                config_path.write_text(json.dumps(altered))
                kwargs = dict(fetcher=values.__getitem__, source_catalogue_path=config_path)
                if change:
                    with self.assertRaisesRegex(FPLValidationError, 'historical data-quality checks failed'):
                        run_historical_pipeline('2024-25', root, **kwargs)
                    self.assertFalse((root / 'historical/catalogue.json').exists())
                else:
                    result = run_historical_pipeline('2024-25', root, **kwargs)
                    with (result.processed_dir / 'player_deadline_snapshots.csv').open() as stream:
                        observed = next(r for r in csv.DictReader(stream) if r['gameweek'] == '1' and r['element'] == '101')
                    self.assertEqual(observed['player_code'], '1009')
                    report = json.loads((result.processed_dir / 'data_quality_report.json').read_text())
                    self.assertTrue(report['passed'])
        # An unrelated mismatch on a second player is never covered by the first exception.
        payload['elements'][1]['code'] = 9999
        values[url] = lzma.compress(json.dumps(payload).encode())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / 'sources.json'
            p.write_text(json.dumps(catalogue))
            with self.assertRaisesRegex(FPLValidationError, 'snapshots.player_code_consistency'):
                run_historical_pipeline('2024-25', root, fetcher=values.__getitem__, source_catalogue_path=p)

    def test_exception_configuration_is_validated_and_affects_identity(self):
        from copy import deepcopy
        catalogue = load_source_catalogue()
        config = catalogue['seasons']['2022-23']
        original = create_build_identity('2022-23', config, catalogue['schema_version'])
        changed = deepcopy(config)
        changed['snapshot_player_code_exceptions'][0]['snapshot_player_code'] += 1
        self.assertNotEqual(original, create_build_identity('2022-23', changed, catalogue['schema_version']))
        invalid = [None, {}, [config['snapshot_player_code_exceptions'][0]] * 2]
        for field, value in [('gameweek', True), ('gameweek', 39), ('reason', ''), ('element', None)]:
            item = deepcopy(config['snapshot_player_code_exceptions'][0])
            item[field] = value
            invalid.append([item])
        for value in invalid:
            altered = deepcopy(config)
            altered['snapshot_player_code_exceptions'] = value
            with self.subTest(value=value), self.assertRaises(FPLValidationError):
                create_build_identity('2022-23', altered, catalogue['schema_version'])

    def test_code_change_excerpts_support_exact_catalogue_exceptions(self):
        evidence = json.loads((FIXTURES / 'player_code_changes.json').read_text())
        first, second = evidence
        config = load_source_catalogue()['seasons']['2022-23']
        for exception in config['snapshot_player_code_exceptions']:
            before = next(r for r in first['elements'] if r['id'] == exception['element'])
            after = next(r for r in second['elements'] if r['id'] == exception['element'])
            self.assertEqual(exception['snapshot_source_path'], first['source_path'])
            self.assertEqual(before['code'], exception['snapshot_player_code'])
            self.assertEqual(after['code'], exception['final_player_code'])
            self.assertEqual({k:v for k,v in before.items() if k != 'code'},
                             {k:v for k,v in after.items() if k != 'code'})
