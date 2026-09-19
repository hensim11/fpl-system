"""Read-only frozen M3 adapter and immutable M4 product publication."""
import copy
import csv
import json
import shutil
import tempfile
from pathlib import Path

from fpl_ai.features import number
from fpl_ai.historical_io import atomic_write_json, canonical_json_bytes, sha256_bytes, sha256_file
from fpl_ai.modelling import ALL_ARTIFACTS, DATA_ARTIFACTS, require_artifact_set
from fpl_ai.modelling_contract import CONTRACT, FEATURES, FEATURE_TYPES, KEYS, NULLABLE_FEATURES, SPLITS
from fpl_ai.evaluation import BASELINES


STAGE_ARTIFACTS = {
    'prospective-xpts-model': {'protocol.json', 'fit.json', 'sources.json', 'training.csv', 'control.pickle', 'xpts_v2.pickle'},
    'prospective-xpts-forecast': {'features.csv', 'predictions.csv', 'history.json', 'evidence.json'},
    'prospective-xpts-score': {'outcomes.csv', 'metrics.json'},
    'xpts-v2': {'protocol.json', 'upstream.json', 'fit.json', 'features.csv', 'row_audit.csv', 'training.csv', 'predictions.csv', 'control.pickle', 'xpts_v2.pickle'},
    'xpts-v2-score': {'outcomes.csv', 'metrics.json'},
    'minutes-oos': {'protocol.json', 'sources.json', 'folds.json', 'model_2024-25.pickle', 'model_2025-26.pickle', 'predictions.csv', 'features.csv', 'row_audit.csv', 'training.csv'},
    'minutes-oos-score': {'metrics.json', 'outcomes.csv'},
    'playing-time-features': {'contract.json', 'evidence.json', 'sources.json', 'features.csv', 'labels.csv', 'row_audit.csv'},
    'minutes-freeze': {'frozen.json', 'development.json', 'predictions.csv', 'model.pickle'},
    'prospective-snapshot': {'bootstrap.json', 'fixtures.json'},
    'prospective-predictions': {'features.csv', 'predictions.csv'},
    'prospective-settlement': {'bootstrap.json', 'fixtures.json', 'live.json'},
    'prospective-score': {'outcomes.csv', 'scores.json'},
        'validation-freeze': {'upstream.json','frozen.json','validation.json','diagnostics.json',
                              'interpretation.json','comparisons.json','predictions.csv',
                              'ridge_10.pickle','ridge_100.pickle','hist_15.pickle','hist_31.pickle'},
        'frozen-holdout': {'holdout.json','diagnostics.json','comparisons.json','predictions.csv'},
    }

def digest(value):
    return sha256_bytes(canonical_json_bytes(value))


def verify_m3(folder):
    folder = Path(folder)
    require_artifact_set(folder, ALL_ARTIFACTS)
    manifest = json.loads((folder/'manifest.json').read_text())
    identity = manifest['identity']
    # M3 hashes integer GW keys before JSON serializes them as strings. Restore
    # that exact upstream serialization; do not rewrite the frozen artifact.
    hash_identity = copy.deepcopy(identity)
    for source in hash_identity['sources'].values():
        if 'settlements' in source:
            source['settlements'] = {int(k):v for k,v in source['settlements'].items()}
    if (identity['identity_version'] != 'serialized-products-v2' or
            digest(hash_identity) != manifest['identity_sha256'] or identity['contract'] != CONTRACT or
            json.loads((folder/'schema.json').read_text()) != CONTRACT or
            set(manifest['artifacts']) != DATA_ARTIFACTS or
            set(identity['content_sha256']) != DATA_ARTIFACTS):
        raise ValueError('unsupported or inconsistent frozen M3 identity/contract')
    for name, expected in manifest['artifacts'].items():
        if sha256_file(folder/name) != expected:
            raise ValueError(f'M3 checksum mismatch: {name}')
        if name != 'evaluation.json' and identity['content_sha256'][name] != expected:
            raise ValueError('M3 identity content mismatch')
    # Check serialization identity without using any baseline score for selection.
    evaluation = json.loads((folder/'evaluation.json').read_text())
    if evaluation.pop('identity_sha256') != manifest['identity_sha256']:
        raise ValueError('M3 evaluation identity mismatch')
    encoded = canonical_json_bytes(evaluation)
    if sha256_bytes(encoded) != identity['content_sha256']['evaluation.json']:
        raise ValueError('M3 evaluation content mismatch')
    return manifest


def key(row):
    return (row['season'], int(row['target_gameweek']), int(row['element']))


def load_rows(folder, splits):
    """Filter by season before parsing values; selection never materializes test data."""
    if not set(splits) <= {'train', 'validation', 'test'}:
        raise ValueError('unknown split')
    folder = Path(folder)
    headers = {
        'features.csv': set(KEYS) | set(FEATURES),
        'labels.csv': set(KEYS) | {'split', 'target_points', 'label_available_at'},
        'predictions.csv': set(KEYS) | set(BASELINES),
    }
    tables = {}
    for name in (*headers, 'row_audit.csv'):
        table = {}
        with (folder/name).open(newline='') as stream:
            reader = csv.DictReader(stream)
            if name in headers and (set(reader.fieldnames) != headers[name] or len(reader.fieldnames) != len(headers[name])):
                raise ValueError(f'closed columns violated: {name}')
            for raw in reader:
                if raw['season'] not in SPLITS:
                    raise ValueError('unknown season')
                if SPLITS[raw['season']] not in splits:
                    continue
                k = key(raw)
                if k in table:
                    raise ValueError('duplicate evaluation key')
                table[k] = raw
        tables[name] = table
    population = set(tables['features.csv'])
    if not population or any(set(t) != population for t in tables.values()):
        raise ValueError('M3 row populations differ or are empty')
    rows, baselines = [], {}
    for k in sorted(population):
        raw, label, audit = (tables[n][k] for n in ('features.csv','labels.csv','row_audit.csv'))
        features = {f: number(raw[f], FEATURE_TYPES[f]) for f in FEATURES}
        if any(features[f+'_missing'] != int(features[f] is None) for f in NULLABLE_FEATURES):
            raise ValueError('missingness indicator mismatch')
        if features['deadline_position_id'] not in (1,2,3,4):
            raise ValueError('non-football population')
        if label['split'] != SPLITS[k[0]]:
            raise ValueError('split contract violated')
        y = number(label['target_points'], 'integer')
        if y is not None and (not label['label_available_at'] or label['label_available_at'] <= audit['capture_time_utc']):
            raise ValueError('invalid label availability')
        rows.append(dict(zip(KEYS,k), features=features, target_points=y,
                         split=label['split'], label_available_at=label['label_available_at'], audit=audit))
        baselines[k] = {b: number(tables['predictions.csv'][k][b]) for b in BASELINES}
    return rows, baselines


def verify_bundle(folder, kind=None):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    if kind and manifest['metadata']['kind'] != kind:
        raise ValueError('wrong experiment stage')
    if digest({k:v for k,v in manifest.items() if k != 'identity_sha256'}) != manifest['identity_sha256']:
        raise ValueError('experiment identity mismatch')
    if folder.name != manifest['identity_sha256']:
        raise ValueError('experiment directory identity mismatch')
    required = STAGE_ARTIFACTS.get(manifest['metadata'].get('kind'))
    if required is not None and set(manifest['artifacts']) != required:
        raise ValueError('experiment manifest artifact set mismatch')
    require_artifact_set(folder, set(manifest['artifacts']) | {'manifest.json'})
    for name, expected in manifest['artifacts'].items():
        if Path(name).name != name or sha256_file(folder/name) != expected:
            raise ValueError(f'experiment checksum mismatch: {name}')
    return manifest


def publish(root, metadata, writer, *, publication_guard=None):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.building-', dir=root))
    try:
        writer(staging)
        required = STAGE_ARTIFACTS.get(metadata.get('kind'))
        if required is not None:
            require_artifact_set(staging, required)
        payload = {'metadata': metadata, 'artifacts': {p.name:sha256_file(p) for p in sorted(staging.iterdir())}}
        manifest = dict(payload, identity_sha256=digest(payload))
        atomic_write_json(staging/'manifest.json', manifest)
        destination = root/manifest['identity_sha256']
        if publication_guard is not None:
            publication_guard()
        if destination.exists():
            if verify_bundle(destination) != manifest:
                raise ValueError('different experiment at existing identity')
            return destination, True
        staging.rename(destination)
        return destination, False
    finally:
        if staging.exists():
            shutil.rmtree(staging)
