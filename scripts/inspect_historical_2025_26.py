"""Reproduce the immutable 2025/26 source inspection; offline unless --acquire."""

import argparse
import csv
import io
import json
import lzma
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

from fpl_ai.historical_io import atomic_write_json, sha256_bytes, store_immutable
from fpl_ai.historical_pipeline import _url_fetcher
from fpl_ai.historical_schema import VAASTAV_2024_25_SOURCE_COLUMNS

VAASTAV = '9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88'
CACHE = '33dac28d18953bee5bc4bd56ddd8a5e32e169d68'
CACHE_DIAGNOSTIC = '60211fa056c5bc195c4f9e2b2cc014767c4a2ab5'
CAPTURES = [f'cache/2026/5/{day}/{time}.json.xz' for day, times in [
    (24, ['0416', '0839', '1349', '1925']), (25, ['0438', '1023', '1522', '1951'])] for time in times]
PLAYER_PATHS = [f'data/2025-26/players/{name}/gw.csv' for name in [
    'Ben_Doak_391', 'Ben_Gannon-Doak_391', 'Eli Junior_Kroupi_100', 'Junior_Kroupi_100']]


def source_urls():
    sources = {}
    for name, repo, sha in [('vaastav', 'vaastav/Fantasy-Premier-League', VAASTAV),
                            ('fplcache-old', 'Randdalf/fplcache', CACHE),
                            ('fplcache-new', 'Randdalf/fplcache', CACHE_DIAGNOSTIC)]:
        sources[name+'-tree.json'] = f'https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1'
    for file in ('gws/merged_gw.csv', 'players_raw.csv', 'teams.csv', 'fixtures.csv'):
        sources[file.split('/')[-1]] = f'https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{VAASTAV}/data/2025-26/{file}'
    for path in PLAYER_PATHS + ['data/2025-26/gws/gw1.csv', 'data/2025-26/gws/gw9.csv']:
        sources[path] = f'https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{VAASTAV}/'+quote(path)
    for path in CAPTURES:
        sources[path] = f'https://raw.githubusercontent.com/Randdalf/fplcache/{CACHE}/{path}'
    return sources


def inspect(root, acquire=False):
    fetch = _url_fetcher(60)
    files, inventory = {}, []
    for local, url in source_urls().items():
        path = root / local
        if acquire and not path.exists():
            store_immutable(path, fetch(url))
        value = path.read_bytes()
        files[local] = value
        inventory.append({'local_path': local, 'url': url, 'sha256': sha256_bytes(value), 'byte_size': len(value)})

    def rows(name):
        return list(csv.DictReader(io.StringIO(files[name].decode())))

    tables = {name: rows(name) for name in VAASTAV_2024_25_SOURCE_COLUMNS}
    schema = {}
    for name, table in tables.items():
        header = list(table[0])
        schema[name] = {'row_count': len(table), 'columns': header,
                        'added_since_2024_25': sorted(set(header)-set(VAASTAV_2024_25_SOURCE_COLUMNS[name])),
                        'removed_since_2024_25': sorted(set(VAASTAV_2024_25_SOURCE_COLUMNS[name])-set(header)),
                        'empty_counts': {field: sum(r[field] == '' for r in table) for field in header}}
    groups = defaultdict(list)
    for number, row in enumerate(tables['merged_gw.csv'], 2):
        groups[row['element'], row['fixture']].append((number, row))
    duplicates = [{'element': int(key[0]), 'fixture': int(key[1]), 'gameweek': int(group[0][1]['GW']),
                   'source_rows': [n for n, _ in group], 'all_fields_equal': all(row == group[0][1] for _, row in group),
                   'raw_row': group[0][1]} for key, group in sorted(groups.items()) if len(group) > 1]
    overlaps = []
    for old, new in zip(PLAYER_PATHS[::2], PLAYER_PATHS[1::2]):
        before, after = rows(old), rows(new)
        by_fixture = {r['fixture']: r for r in after}
        overlaps.append({'old_path': old, 'new_path': new, 'old_rows': len(before), 'new_rows': len(after),
                         'overlapping_fixtures': [r['fixture'] for r in before],
                         'all_overlapping_rows_equal': all(r == by_fixture.get(r['fixture']) for r in before)})
    captures = []
    for path in CAPTURES:
        data = json.loads(lzma.decompress(files[path]))
        captures.append({'source_path': path, 'sha256': sha256_bytes(files[path]), 'element_count': len(data['elements']),
                         'event_38': data['events'][-1]})
    trees = {}
    for name in ('vaastav', 'fplcache-old', 'fplcache-new'):
        tree = json.loads(files[name+'-tree.json'])
        if tree['truncated']:
            raise ValueError('source tree truncated')
        trees[name] = {r['path']: r['sha'] for r in tree['tree'] if r['type'] == 'blob'}
    # Numeric path components, not lexicographic month/day ordering.
    season_paths = [p for p in trees['fplcache-old'] if p.endswith('.xz') and
                    (p.startswith('cache/2025/') and int(p.split('/')[2]) >= 8 or
                     p.startswith('cache/2026/') and int(p.split('/')[2]) <= 5)]
    return {'schema_version': 1, 'season': '2025-26', 'provider_revisions': {'vaastav': VAASTAV, 'fplcache': CACHE},
            'diagnostic_newer_fplcache_revision': CACHE_DIAGNOSTIC,
            'required_source_paths_present': (all(f'data/2025-26/{p}' in trees['vaastav'] for p in ['gws/merged_gw.csv', 'players_raw.csv', 'teams.csv', 'fixtures.csv']) and all(p in trees['fplcache-old'] for p in CAPTURES)),
            'archive_season_window_paths': len(season_paths),
            'newer_archive_changes_in_season_window': [p for p in season_paths if trees['fplcache-old'][p] != trees['fplcache-new'].get(p)],
            'inventory': inventory, 'source_schema': schema, 'final_captures': captures,
            'duplicate_merged_rows': duplicates, 'renamed_player_directory_overlaps': overlaps,
            'unique_player_fixture_keys': len(groups),
            'source_positions': dict(Counter(r['position'] for r in tables['merged_gw.csv'])),
            'fixture_gameweeks': dict(sorted(Counter(r['event'] for r in tables['fixtures.csv']).items(), key=lambda v: int(v[0])))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=Path('data/historical/investigation/2025-26'))
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--acquire', action='store_true', help='Download missing immutable evidence; default requires local files')
    args = parser.parse_args()
    atomic_write_json(args.report, inspect(args.source_dir, args.acquire))


if __name__ == '__main__':
    main()
