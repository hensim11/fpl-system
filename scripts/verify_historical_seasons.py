"""Offline full-build regression and cross-season sanity audit.

Run after ingesting all configured seasons:
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/historical-audit.json
"""

import argparse
import csv
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from fpl_ai.historical_io import sha256_file
from fpl_ai.historical_pipeline import load_historical_build, load_source_catalogue, run_historical_pipeline
from fpl_ai.historical_schema import schemas_as_dict
from fpl_ai.historical_transform import parse_utc


def read_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def fingerprint(root):
    return {str(p.relative_to(root)): (sha256_file(p), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def no_network(url):
    raise AssertionError(f'unexpected network request: {url}')


def verify(output_dir):
    report = {'canonical_schemas_compatible': True, 'seasons': {}}
    catalogue = load_source_catalogue()
    for season in sorted(catalogue['seasons']):
        config = catalogue['seasons'][season]
        existing = run_historical_pipeline(season, output_dir, fetcher=no_network)
        assert existing.reused
        load_historical_build(season, existing.version, output_dir)
        original_fingerprint = fingerprint(existing.processed_dir)
        manifest = json.loads((existing.processed_dir / 'manifest.json').read_text())
        quality = json.loads((existing.processed_dir / 'data_quality_report.json').read_text())
        assert quality['passed'] and all(c['passed'] for c in quality['checks'])
        assert quality['canonical_schemas'] == schemas_as_dict()
        published_schema = json.loads((existing.processed_dir / 'schemas.json').read_text())
        assert published_schema['tables'] == schemas_as_dict()
        tables = {name: read_rows(existing.processed_dir / (name + '.csv')) for name in schemas_as_dict()}
        for name, rows in tables.items():
            assert list(rows[0]) == [c['name'] for c in schemas_as_dict()[name]]
            assert all(r['season'] == season for r in rows)
        facts, fixtures, snapshots, gameweeks = (tables[k] for k in (
            'player_fixture_facts', 'fixtures', 'player_deadline_snapshots', 'gameweeks'))
        assert {int(r['gameweek']) for r in gameweeks} == set(range(1, 39))
        assert len(fixtures) == 380 and len(tables['teams']) == 20
        # A complete 20-club season has each directed home/away pair exactly once.
        pairs = Counter((r['home_team_id'], r['away_team_id']) for r in fixtures)
        assert len(pairs) == 380 and set(pairs.values()) == {1}
        assert all(a != b for a, b in pairs)
        appearances = Counter(t for r in fixtures for t in (r['home_team_id'], r['away_team_id']))
        assert len(appearances) == 20 and set(appearances.values()) == {38}
        assert all(r['finished'] == 'True' for r in fixtures)
        assert {r['fixture'] for r in facts} == {r['fixture'] for r in fixtures}
        blank = sorted(set(range(1, 39)) - {int(r['gameweek']) for r in fixtures})
        assert blank == ([7] if season == '2022-23' else [])
        deadlines = {r['gameweek']: r for r in gameweeks}
        assert not quality['missing_snapshot_gameweeks']
        for row in snapshots:
            gw = deadlines[row['gameweek']]
            assert row['deadline_time_utc'] == gw['deadline_time_utc']
            assert row['capture_time_utc'] == gw['selected_snapshot_capture_time_utc']
            assert parse_utc(row['capture_time_utc'], 'capture') < parse_utc(row['deadline_time_utc'], 'deadline')
        important = ('player_code', 'deadline_team_id', 'deadline_team_code', 'deadline_team_name',
                     'deadline_position_id', 'deadline_position', 'price', 'selected_by_percent')
        missing = {field: sum(r[field] == '' for r in snapshots) for field in important}
        assert not any(missing.values())
        assert all(0 <= int(r['minutes']) <= 90 for r in facts)
        points = quality['total_points_reconciliation']
        assert points['passed'] and points['coverage_ratio'] == 1.0
        assert points['mismatching_row_count'] == points['unmatched_row_count'] == 0
        assert len({(r['element'], r['gameweek']) for r in facts}) == points['eligible_row_count']
        for gw in blank:
            assert any(int(r['gameweek']) == gw for r in snapshots)
            assert not any(int(r['gameweek']) == gw for r in facts)
            assert str(gw) not in points['by_gameweek']
        totals = Counter()
        for row in facts:
            totals[row['element']] += int(row['total_points'])
        raw_players = read_rows(existing.raw_dir / f'vaastav/data/{season}/players_raw.csv')
        aggregate_differences = [dict(element=int(r['id']), name=r['web_name'],
                                     fixture_sum=totals[r['id']], final_total=int(r['total_points']))
                                 for r in raw_players if totals[r['id']] != int(r['total_points'])]
        # Cumulative final totals are an additional diagnostic, not the settled event-points contract.
        if season == '2022-23':
            assert not aggregate_differences
        teams_by_element = defaultdict(set)
        for row in snapshots:
            teams_by_element[row['element']].add(row['deadline_team_id'])
        inventory = json.loads((existing.processed_dir / 'source_inventory.json').read_text())
        raw_records = json.loads((existing.raw_dir / 'source_manifest.json').read_text())['files']
        sources = {r['source_url']: (existing.raw_dir / r['raw_path']).read_bytes() for r in raw_records}
        with tempfile.TemporaryDirectory() as directory:
            fresh = run_historical_pipeline(season, directory, fetcher=sources.__getitem__)
            assert not fresh.reused
            rebuilt = json.loads((fresh.processed_dir / 'manifest.json').read_text())
            for key in ('source_identity_sha256', 'build_identity_sha256'):
                assert manifest[key] == rebuilt[key]
            fresh_quality = json.loads((fresh.processed_dir / 'data_quality_report.json').read_text())
            assert fresh_quality['passed'] and fresh_quality['canonical_schemas'] == quality['canonical_schemas']
            for path in existing.processed_dir.glob('*.csv'):
                assert sha256_file(path) == sha256_file(fresh.processed_dir / path.name)
            before = fingerprint(Path(directory))
            assert run_historical_pipeline(season, directory, fetcher=no_network).reused
            assert before == fingerprint(Path(directory))
            load_historical_build(season, fresh.version, directory)
        assert fingerprint(existing.processed_dir) == original_fingerprint
        report['seasons'][season] = {
            'version': existing.version,
            'source_identity_sha256': manifest['source_identity_sha256'],
            'build_identity_sha256': manifest['build_identity_sha256'],
            'row_counts': quality['processed_row_counts'],
            'fixture_gameweeks': len(quality['fixture_gameweeks']), 'blank_gameweeks': blank,
            'quality_checks_passed': len(quality['checks']), 'deadline_gameweeks': len(gameweeks),
            'eligible_player_gameweeks': points['eligible_row_count'], 'points_coverage': points['coverage_ratio'],
            'points_mismatches': points['mismatching_row_count'], 'important_snapshot_nulls': missing,
            'all_null_counts': quality['null_counts'],
            'capture_age_hours_min': min(float(r['hours_before_deadline']) for r in gameweeks),
            'capture_age_hours_max': max(float(r['hours_before_deadline']) for r in gameweeks),
            'deadline_team_change_elements': sum(len(v) > 1 for v in teams_by_element.values()),
            'zero_minute_facts': sum(r['minutes'] == '0' for r in facts),
            'final_aggregate_differences': aggregate_differences,
            'fresh_offline_rebuild_identical': True, 'reuse_preserves_bytes_and_mtimes': True,
            'csv_sha256': {p.name: sha256_file(p) for p in sorted(existing.processed_dir.glob('*.csv'))},
            'consumed_source_records': len(inventory['files']),
            'source_inventory_sha256': sha256_file(existing.processed_dir / 'source_inventory.json'),
        }
        print(f'{season}: full offline rebuild, checksums, temporal and football sanity checks passed', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('data'))
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    args.report.write_text(json.dumps(verify(args.output_dir), indent=2, sort_keys=True) + '\n')
