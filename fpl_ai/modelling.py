"""Offline adapter and atomic, content-addressed M3 artifact publication."""
import csv
import json
import lzma
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fpl_ai.evaluation import BASELINES, evaluate, predict_baselines
from fpl_ai.features import build_rows
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, canonical_json_bytes, sha256_bytes, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.historical_schema import schemas_as_dict
from fpl_ai.modelling_contract import CONTRACT, FEATURES, KEYS, SPLITS


DATA_ARTIFACTS = frozenset({
    'features.csv', 'labels.csv', 'row_audit.csv', 'predictions.csv',
    'evaluation.json', 'schema.json',
})
ALL_ARTIFACTS = DATA_ARTIFACTS | {'manifest.json'}


def require_artifact_set(folder, expected):
    actual = {p.name for p in folder.iterdir()}
    if actual != expected:
        raise ValueError(f'modelling artifact set mismatch: missing={sorted(expected-actual)}, '
                         f'unexpected={sorted(actual-expected)}')
    if any(not (folder/name).is_file() or (folder/name).is_symlink() for name in expected):
        raise ValueError('modelling artifacts must be regular files, not directories or symlinks')


def verify_reuse(destination, expected_manifest):
    require_artifact_set(destination, ALL_ARTIFACTS)
    manifest = json.loads((destination/'manifest.json').read_text())
    if not isinstance(manifest.get('artifacts'), dict) or set(manifest['artifacts']) != DATA_ARTIFACTS:
        raise ValueError('modelling manifest artifact set mismatch')
    if manifest != json.loads(canonical_json_bytes(expected_manifest)):
        raise ValueError('modelling manifest differs from regenerated identity/content')
    for name in sorted(DATA_ARTIFACTS):
        if sha256_file(destination/name) != manifest['artifacts'][name]:
            raise ValueError(f'modelling artifact checksum mismatch: {name}')


def read_csv(path):
    with path.open(newline='', encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def capture_from_path(path):
    match = re.fullmatch(r'cache/(\d{4})/(\d{1,2})/(\d{1,2})/(\d{2})(\d{2})\.json\.xz', path)
    if not match:
        raise ValueError('invalid pinned capture path')
    return datetime(*map(int, match.groups()), tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load_season(season, version, data_dir):
    build = load_historical_build(season, version, data_dir)
    folder = build.processed_dir
    manifest = json.loads((folder/'manifest.json').read_text())
    quality = json.loads((folder/'data_quality_report.json').read_text())
    reconciliation = json.loads((folder/'total_points_reconciliation.json').read_text())
    if not quality['passed'] or not reconciliation['passed'] or reconciliation['coverage_ratio'] != 1:
        raise ValueError('requires accepted fully reconciled historical build')
    if json.loads((folder/'schemas.json').read_text())['tables'] != schemas_as_dict():
        raise ValueError('unsupported historical schema')
    snapshots = read_csv(folder/'player_deadline_snapshots.csv')
    facts = read_csv(folder/'player_fixture_facts.csv')
    gameweeks = {int(r['gameweek']): r for r in read_csv(folder/'gameweeks.csv')}
    config = manifest['build_identity']['snapshot_selection']
    inventory = {r['source_path']: r for r in manifest['source_identity']['immutable_artifacts']
                 if r['provider_key'] == 'fplcache'}
    settlements, evidence_records = {}, {}
    selected = reconciliation.get('settlement_selection', {}).get('by_gameweek')
    for gw_string in reconciliation['by_gameweek']:
        gw = int(gw_string)
        path = selected[gw_string]['source_path'] if selected else (
            config['points_settlement_snapshot_path'] if gw == max(gameweeks) else gameweeks[gw+1]['snapshot_source_path'])
        record = inventory[path]
        raw = build.raw_dir/'fplcache'/path
        if sha256_file(raw) != record['sha256']:
            raise ValueError('settlement source checksum mismatch')
        payload = json.loads(lzma.decompress(raw.read_bytes()))
        events = [e for e in payload['events'] if e['id'] == gw]
        if len(events) != 1 or events[0]['finished'] is not True or events[0]['data_checked'] is not True:
            raise ValueError('unsettled historical evidence')
        points = {}
        for p in payload['elements']:
            if p['id'] in points or type(p['event_points']) is not int:
                raise ValueError('invalid settlement player points')
            points[p['id']] = p['event_points']
        settlements[gw] = {'capture_time_utc': capture_from_path(path), 'points': points}
        evidence_records[gw] = {'capture_time_utc': capture_from_path(path), 'source_path': path, 'sha256': record['sha256']}
    # Read-only M2 boundaries are independently checked before feature construction.
    for s in snapshots:
        g = gameweeks[int(s['gameweek'])]
        if (s['capture_time_utc'] != g['selected_snapshot_capture_time_utc'] or
                s['deadline_time_utc'] != g['deadline_time_utc']):
            raise ValueError('snapshot/Gameweek time mismatch')
    exception = config.get('superseded_deadline_exception')
    rows = build_rows(season, snapshots, facts, settlements, exception)
    source = {
        'version': version, 'source_identity_sha256': manifest['source_identity_sha256'],
        'build_identity_sha256': manifest['build_identity_sha256'],
        'source_identity': manifest['source_identity'],
        'build_identity': manifest['build_identity'],
        'consumed_tables': {name: sha256_file(folder/name) for name in
                            ('player_deadline_snapshots.csv', 'player_fixture_facts.csv', 'gameweeks.csv')},
        'settlements': evidence_records, 'snapshot_exception': exception,
    }
    return rows, source


def summary(rows):
    labelled = [r['target_points'] for r in rows if r['target_points'] is not None]
    return {
        'rows': len(rows), 'labelled_rows': len(labelled),
        'by_season': dict(sorted(Counter(r['season'] for r in rows).items())),
        'by_position': dict(sorted(Counter(r['features']['deadline_position_id'] for r in rows).items())),
        'by_split': dict(sorted(Counter(r['split'] for r in rows).items())),
        'label_status': dict(sorted(Counter(r['audit']['label_status'] for r in rows).items())),
        'target': {'min': min(labelled), 'max': max(labelled), 'mean': sum(labelled)/len(labelled),
                   'zero': labelled.count(0), 'negative': sum(y < 0 for y in labelled)},
        'feature_missingness': {f: sum(r['features'][f] is None for r in rows) for f in FEATURES},
        'external_ep_next_missing': sum(r['external_ep_next'] is None for r in rows),
        'exception_rows': sum(r['audit']['superseded_deadline_exception'] for r in rows),
    }


def run_modelling(data_dir=Path('data'), output_dir=None, builds=None):
    data_dir = Path(data_dir)
    root = Path(output_dir) if output_dir is not None else data_dir/'modelling'
    if builds is None:
        catalogue = json.loads((data_dir/'historical/catalogue.json').read_text())
        builds = {s: catalogue['seasons'][s]['latest_successful_version'] for s in SPLITS}
    if set(builds) != set(SPLITS):
        raise ValueError('exactly the five contract seasons must be pinned')
    rows, sources = [], {}
    for season in SPLITS:
        season_rows, sources[season] = load_season(season, builds[season], data_dir)
        rows.extend(season_rows)
    predictions = predict_baselines(rows)
    # Hash actual serialized products rather than an incomplete dependency list.
    # evaluation.json is hashed before adding its identity reference to avoid a cycle.
    report = {'contract': CONTRACT, 'summary': summary(rows),
              'splits': evaluate(rows, predictions)}
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.building-', dir=root))
    try:
        def key(r):
            return {k: r[k] for k in KEYS}
        atomic_write_csv(staging/'features.csv', ({**key(r), **r['features']} for r in rows), list(KEYS)+list(FEATURES))
        atomic_write_csv(staging/'labels.csv', ({**key(r), 'split': r['split'], 'target_points': r['target_points'],
                          'label_available_at': r['label_available_at']} for r in rows),
                         list(KEYS)+['split', 'target_points', 'label_available_at'])
        atomic_write_csv(staging/'row_audit.csv', ({**key(r), **r['audit']} for r in rows), list(KEYS)+list(rows[0]['audit']))
        atomic_write_csv(staging/'predictions.csv', ({**key(r), **predictions[tuple(r[k] for k in KEYS)]} for r in rows),
                         list(KEYS)+list(BASELINES))
        atomic_write_json(staging/'evaluation.json', report)
        atomic_write_json(staging/'schema.json', CONTRACT)
        require_artifact_set(staging, DATA_ARTIFACTS)
        content_hashes = {name: sha256_file(staging/name) for name in sorted(DATA_ARTIFACTS)}
        identity = {'identity_version': 'serialized-products-v2', 'contract': CONTRACT,
                    'sources': sources, 'content_sha256': content_hashes,
                    'content_boundary': 'exact artifact bytes; evaluation.json before identity_sha256 insertion'}
        digest = sha256_bytes(canonical_json_bytes(identity))
        destination = root/digest
        report['identity_sha256'] = digest
        atomic_write_json(staging/'evaluation.json', report)
        artifacts = {name: sha256_file(staging/name) for name in sorted(DATA_ARTIFACTS)}
        manifest = {'identity_sha256': digest, 'identity': identity,
                    'rows': len(rows), 'artifacts': artifacts}
        atomic_write_json(staging/'manifest.json', manifest)
        require_artifact_set(staging, ALL_ARTIFACTS)
        if destination.exists():
            verify_reuse(destination, manifest)
            return destination, True
        staging.rename(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination, False
