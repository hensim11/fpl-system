"""Offline full-build regression and cross-season sanity audit.

By default verify published seasons only; use --investigate-season for rejected builds.
Run after ingesting supported seasons:
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/historical-audit.json
"""

import argparse
import csv
import json
import lzma
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import sha256_file
from fpl_ai.historical_pipeline import (
    _SourceStore, _url_fetcher, load_historical_build, load_source_catalogue, run_historical_pipeline,
)
from fpl_ai.historical_schema import schemas_as_dict
from fpl_ai.historical_status import season_statuses
from fpl_ai.historical_transform import parse_utc


def read_rows(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def fingerprint(root):
    return {str(p.relative_to(root)): (sha256_file(p), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def no_network(url):
    raise AssertionError(f'unexpected network request: {url}')


def verify(output_dir, seasons=None):
    report = {'canonical_schemas_compatible': True, 'seasons': {}}
    catalogue = load_source_catalogue()
    statuses = season_statuses(output_dir, catalogue['seasons'])
    chosen = seasons if seasons is not None else [s for s, status in statuses.items() if status == 'published']
    if any(statuses.get(s) != 'published' for s in chosen):
        raise FPLValidationError('unpublished seasons require --investigate-season')
    for season in sorted(chosen):
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
        if 'snapshot_deadline_exceptions' in quality:
            from fpl_ai.historical_snapshot_policy import accept_superseded_snapshot
            policy = config['superseded_deadline_exception']
            exception_gw = deadlines[str(policy['gameweek'])]
            record = next(r for r in inventory['files'] if r['source_path'] == policy['source_path'])
            raw_path = existing.raw_dir / record['raw_path']
            assert sha256_file(raw_path) == policy['source_sha256']
            payload = json.loads(lzma.decompress(raw_path.read_bytes()))
            evidence = accept_superseded_snapshot(
                policy, season, policy['gameweek'], exception_gw['snapshot_source_path'],
                parse_utc(exception_gw['selected_snapshot_capture_time_utc'], 'capture'),
                parse_utc(exception_gw['deadline_time_utc'], 'deadline'), payload, record,
            )
            assert quality['snapshot_deadline_exceptions'] == [evidence]
            assert fresh_quality['snapshot_deadline_exceptions'] == [evidence]
            report['seasons'][season]['snapshot_deadline_exceptions'] = [evidence]
            report['seasons'][season]['settlement_selection'] = points['settlement_selection']
        print(f'{season}: full offline rebuild, checksums, temporal and football sanity checks passed', flush=True)
    return report


def acquire_2021_22_diagnostic_sources(output_dir):
    """Cache pinned diagnostic captures using the same immutable raw-store contract."""
    catalogue = load_source_catalogue()
    config = catalogue['seasons']['2021-22']['sources']
    version = f"v{catalogue['schema_version']}-{config['vaastav']['resolved_commit_sha'][:12]}-{config['fplcache']['resolved_commit_sha'][:12]}"
    raw = output_dir / 'historical/raw/2021-22' / version
    store = _SourceStore(raw, '2021-22', datetime.now(timezone.utc), _url_fetcher(60))
    cache = config['fplcache']
    for path in ('cache/2021/8/30/0624.json.xz', 'cache/2021/12/18/1825.json.xz'):
        store.obtain('fplcache', cache, path, cache['raw_base_url'] + '/' + path)
    store.write_manifest()


def verify_2021_22_rejection(output_dir):
    """Reproduce the pinned source blockers without publishing or weakening gates."""
    root = output_dir / 'historical'
    before = fingerprint(root / 'processed')
    catalogue_before = (root / 'catalogue.json').read_bytes()
    attempts = []
    for _ in range(2):
        try:
            run_historical_pipeline('2021-22', output_dir, fetcher=no_network)
        except FPLValidationError as exc:
            assert 'historical data-quality checks failed' in str(exc), str(exc)
        else:
            raise AssertionError('2021/22 unexpectedly published; reassess blocker evidence')
        latest = max((root / 'failed' / '2021-22').glob('*.json'), key=lambda p: p.stat().st_mtime_ns)
        attempts.append(json.loads(latest.read_text()))
    a, b = attempts
    assert a['total_points_reconciliation']['settlement_selection'] == b['total_points_reconciliation']['settlement_selection']
    for key in ('source_identity_sha256', 'build_identity_sha256', 'processed_row_counts',
                'checks', 'missing_snapshot_gameweeks', 'fixture_kickoff_reconciliation'):
        assert a[key] == b[key]
    assert before == fingerprint(root / 'processed')
    assert catalogue_before == (root / 'catalogue.json').read_bytes()
    assert not (root / 'processed' / '2021-22').exists()
    assert a['missing_snapshot_gameweeks'] == [18]
    failed_checks = [c['name'] for c in a['checks'] if not c['passed']]
    assert failed_checks == ['expectation.gameweeks_with_valid_snapshot']
    points = a['total_points_reconciliation']
    assert points['eligible_row_count'] == 23230
    assert points['compared_row_count'] == 23230
    assert points['unmatched_row_count'] == 0 and points['mismatching_row_count'] == 0
    assert points['passed'] and points['coverage_ratio'] == 1.0
    raw = root / 'raw' / '2021-22' / a['source_version']
    records = json.loads((raw / 'source_manifest.json').read_text())['files']
    sources = {r['source_url']: (raw / r['raw_path']).read_bytes() for r in records}
    with tempfile.TemporaryDirectory() as temporary:
        fresh_root = Path(temporary)
        try:
            run_historical_pipeline('2021-22', fresh_root, fetcher=sources.__getitem__)
        except FPLValidationError as exc:
            assert 'gameweeks_with_valid_snapshot' in str(exc)
        else:
            raise AssertionError('fresh incomplete build published')
        fresh_file = next((fresh_root / 'historical/failed/2021-22').glob('*.json'))
        fresh = json.loads(fresh_file.read_text())
        for key in ('source_identity_sha256', 'build_identity_sha256', 'checks', 'processed_row_counts'):
            assert a[key] == fresh[key]
        assert a['total_points_reconciliation']['settlement_selection'] == fresh['total_points_reconciliation']['settlement_selection']
        assert not (fresh_root / 'historical/catalogue.json').exists()
    facts = read_rows(raw / 'vaastav/data/2021-22/gws/merged_gw.csv')
    fixtures = read_rows(raw / 'vaastav/data/2021-22/fixtures.csv')
    players = read_rows(raw / 'vaastav/data/2021-22/players_raw.csv')
    assert len(facts) == 25447 and len(players) == 737 and len(fixtures) == 380
    pairs = Counter((r['team_h'], r['team_a']) for r in fixtures)
    assert len(pairs) == 380 and set(pairs.values()) == {1}
    assert set(Counter(t for r in fixtures for t in (r['team_h'], r['team_a'])).values()) == {38}
    groups = Counter((r['element'], r['GW']) for r in facts)
    totals = Counter()
    for row in facts:
        totals[row['element']] += int(row['total_points'])
    aggregate_differences = [dict(element=int(r['id']), name=r['web_name'],
                                  fixture_sum=totals[r['id']], final_total=int(r['total_points']))
                             for r in players if totals[r['id']] != int(r['total_points'])]
    assert not aggregate_differences
    alias_rows = [r for r in facts if r['position'] == 'GKP']
    assert len(alias_rows) == 101 and {r['GW'] for r in alias_rows} == {'37'}
    gw37 = json.loads(lzma.decompress((raw / 'fplcache/cache/2022/5/15/0629.json.xz').read_bytes()))
    positions = {str(e['id']): e['element_type'] for e in gw37['elements']}
    assert all(positions[r['element']] == 1 for r in alias_rows)
    tree = json.loads((raw / 'fplcache/github-tree.json').read_text())
    assert tree['truncated'] is False
    capture_paths = sorted(r['path'] for r in tree['tree'] if r['path'].startswith('cache/2021/12/18/'))
    captures = []
    for path in capture_paths:
        payload = json.loads(lzma.decompress((raw / 'fplcache' / path).read_bytes()))
        captures.append({'path': path, 'event': payload['events'][17],
                         'sha256': sha256_file(raw / 'fplcache' / path)})
    teams_by_element = defaultdict(set)
    prices, statuses = [], Counter()
    for artifact in a['source_identity']['immutable_artifacts']:
        if 'accepted_predeadline_snapshot' not in artifact['consumption_roles']:
            continue
        payload = json.loads(lzma.decompress((raw / 'fplcache' / artifact['source_path']).read_bytes()))
        for element in payload['elements']:
            teams_by_element[element['id']].add(element['team'])
            prices.append(element['now_cost'] / 10)
            statuses[element['status']] += 1
    james = []
    for path in ('cache/2021/8/30/0624.json.xz', 'cache/2021/9/11/0623.json.xz'):
        file = raw / 'fplcache' / path
        payload = json.loads(lzma.decompress(file.read_bytes()))
        element = next(e for e in payload['elements'] if e['id'] == 287)
        james.append({'path': path, 'sha256': sha256_file(file),
                      'event': payload['events'][2],
                      'player': {k: element[k] for k in ('id', 'team', 'event_points', 'total_points')}})
    assert [e['player']['event_points'] for e in james] == [1, 0]
    assert all(e['event']['finished'] and e['event']['data_checked'] for e in james)
    return {
        'deadline_team_change_elements': sum(len(v) > 1 for v in teams_by_element.values()),
        'observed_price_range_millions': [min(prices), max(prices)],
        'snapshot_status_counts': dict(statuses),
        'james_points_captures': james,
        'status': 'blocked_not_supported', 'published': False,
        'source_identity_sha256': a['source_identity_sha256'],
        'build_identity_sha256': a['build_identity_sha256'],
        'source_identity': a['source_identity'], 'build_identity': a['build_identity'],
        'row_counts_before_rejection': a['processed_row_counts'],
        'quality_checks_passed': sum(c['passed'] for c in a['checks']),
        'quality_check_count': len(a['checks']), 'failed_checks': failed_checks,
        'missing_snapshot_gameweeks': a['missing_snapshot_gameweeks'],
        # Full per-row exclusions remain in the retained failed quality report.
        'total_points_reconciliation': {k: v for k, v in points.items() if k not in {
            'unavailable', 'source_identity', 'build_identity',
            'artifact_created_at_utc', 'artifact_sha256',
        }},
        'fixture_kickoff_reconciliation': a['fixture_kickoff_reconciliation'],
        'fixture_counts_by_gameweek': dict(sorted(Counter(int(r['event']) for r in fixtures).items())),
        'player_gameweek_fixture_multiplicity': dict(sorted(Counter(groups.values()).items())),
        'source_positions': dict(Counter(r['position'] for r in facts)),
        'final_aggregate_differences': aggregate_differences,
        'zero_minute_facts': sum(r['minutes'] == '0' for r in facts),
        'gw18_archive_captures': captures,
        'fresh_offline_rejection_identical': True,
        'repeat_rejection_identical': True, 'catalogue_and_published_builds_unchanged': True,
        'null_counts_before_rejection': a['null_counts'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('data'))
    parser.add_argument('--report', type=Path, required=True)
    configured = load_source_catalogue()['seasons']
    parser.add_argument('--season', action='append', choices=sorted(configured),
                        help='Select a published season; default: all published seasons')
    parser.add_argument('--investigate-season', action='append', choices=sorted(configured),
                        help='Reproduce an unpublished season rejection alongside published-season audits')
    parser.add_argument('--acquire-2021-22-evidence', action='store_true',
                        help='Fetch two pinned diagnostic captures before the 2021/22 investigation')
    args = parser.parse_args(argv)
    try:
        statuses = season_statuses(args.output_dir, configured)
        investigations = args.investigate_season or []
        if any(statuses[s] != 'published' for s in args.season or []):
            parser.error('unpublished seasons require --investigate-season, not --season')
        if any(statuses[s] == 'published' for s in investigations):
            parser.error('published seasons must use the normal audit, not --investigate-season')
        if args.acquire_2021_22_evidence:
            if '2021-22' not in investigations:
                parser.error('--acquire-2021-22-evidence requires --investigate-season 2021-22')
            acquire_2021_22_diagnostic_sources(args.output_dir)
        report = verify(args.output_dir, args.season)
        report['season_statuses'] = statuses
        for season in investigations:
            report.setdefault('rejected_seasons', {})[season] = (
                verify_2021_22_rejection(args.output_dir) if season == '2021-22'
                else verify_rejection(args.output_dir, season)
            )
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    except (FPLValidationError, OSError, AssertionError, KeyError) as exc:
        parser.error(str(exc) or 'audit invariant failed; inspect retained build evidence')
    return 0


def verify_rejection(output_dir, season):
    root = output_dir / 'historical'
    before = fingerprint(root / 'processed')
    catalogue = root / 'catalogue.json'
    original = catalogue.read_bytes() if catalogue.exists() else None
    try:
        run_historical_pipeline(season, output_dir, fetcher=no_network)
    except FPLValidationError as exc:
        result = {'status': 'blocked', 'error': str(exc), 'published': False}
    else:
        raise FPLValidationError('investigation unexpectedly succeeded; rerun the normal supported audit')
    assert fingerprint(root / 'processed') == before
    assert (catalogue.read_bytes() if catalogue.exists() else None) == original
    return result


if __name__ == '__main__':
    raise SystemExit(main())
