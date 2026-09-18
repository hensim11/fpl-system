"""Reproducible pinned Ferguson audit; additional captures never replace settlement."""
import argparse
import hashlib
import json
import lzma
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import urlopen

from fpl_ai.client import _verified_ssl_context
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.modelling import capture_from_path, read_csv
from fpl_ai.playing_time import inspect_season

COMMIT = '33dac28d18953bee5bc4bd56ddd8a5e32e169d68'


def investigate(data=Path('data'), download=False):
    cat = json.loads((data/'historical/catalogue.json').read_text())
    version = cat['seasons']['2024-25']['latest_successful_version']
    _, audit, source = inspect_season('2024-25', version, data, False)
    build = load_historical_build('2024-25', version, data)
    tree_path = build.raw_dir/'fplcache/github-tree.json'
    tree = json.loads(tree_path.read_text())
    if tree['truncated'] is not False:
        raise ValueError('incomplete pinned archive tree')
    entries = [r for r in tree['tree'] if r['type'] == 'blob' and r['path'].endswith('.json.xz')
               and '2025-02-24T00:00:00Z' <= capture_from_path(r['path']) <= '2025-03-09T23:59:59Z']
    def inspect(record):
        path = record['path']
        url = f'https://raw.githubusercontent.com/Randdalf/fplcache/{COMMIT}/{path}'
        dest = data/'m4c_investigation'/COMMIT/path
        if not dest.exists():
            if not download:
                raise ValueError(f'missing investigation evidence: {path}; use --download')
            with urlopen(url, context=_verified_ssl_context(), timeout=60) as response:
                content = response.read()
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as stream:
                stream.write(content)
        content = dest.read_bytes()
        git_sha = hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
        if git_sha != record['sha'] or len(content) != record['size']:
            raise ValueError('pinned tree blob mismatch')
        payload = json.loads(lzma.decompress(content))
        p = next(p for p in payload['elements'] if p['id'] == 123)
        event = next(e for e in payload['events'] if e['id'] == 27)
        return {'source_path': path, 'source_url': url, 'git_blob_sha1': git_sha,
                'sha256': sha256_file(dest), 'bytes': len(content), 'capture': capture_from_path(path),
                'minutes': p['minutes'], 'event_points': p['event_points'], 'total_points': p['total_points'],
                'team': p['team'], 'starts': p.get('starts'),
                'gw27_finished': event['finished'], 'gw27_data_checked': event['data_checked']}
    with ThreadPoolExecutor(max_workers=6) as pool:
        observations = sorted(pool.map(inspect, entries), key=lambda r:r['capture'])
    facts = [r for r in read_csv(build.processed_dir/'player_fixture_facts.csv') if int(r['element']) == 123]
    return {'version': 'minutes-discrepancy-investigation-v1', 'season': '2024-25', 'element': 123,
            'player': 'Evan Ferguson', 'selection': 'all pinned archive captures Feb 24 through Mar 9 inclusive, chosen by time, never by minutes',
            'source': source, 'tree_sha256': sha256_file(tree_path), 'observations': observations,
            'accepted_before': audit['captures']['27'], 'selected_settlement': audit['settlements']['27'],
            'fixture_values': [{k:r[k] for k in ('gameweek','fixture','minutes','total_points','kickoff_time_utc')} for r in facts],
            'minutes_target_disagreements': audit['minutes_target_disagreements'],
            'cumulative_disagreements': audit['cumulative_disagreements'],
            'comparisons': audit['minutes_target_comparisons'],
            'archive_live_paths': [r['path'] for r in tree['tree'] if 'live' in r['path'].lower()],
            'conclusion': 'Unresolved; no correction and no replacement settlement. Only element 123 GW27 delta disagrees; +17 cumulative offset persists through GW38.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--download', action='store_true')
    p.add_argument('--report', type=Path, default=Path('docs/M4C_DISCREPANCY.json'))
    a = p.parse_args()
    atomic_write_json(a.report, investigate(download=a.download))
    print(a.report)


if __name__ == '__main__':
    main()
