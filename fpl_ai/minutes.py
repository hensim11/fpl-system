"""Bounded expected-total-GW-minutes experiment; no consumed holdout adapter."""
import json
import math
import pickle
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.experiments import environment
from fpl_ai.features import number
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv
from fpl_ai.playing_time import CONTRACT, FEATURES, KEYS, NULLABLE, SEASONS, verify_features

CATEGORICAL = ('position', 'status')
NUMERIC = tuple(f for f in FEATURES if f not in CATEGORICAL)
ORDER = NUMERIC+CATEGORICAL
NAMES = ('training_position_mean', 'recent_minutes', 'availability_recent', 'hist_15')
PROTOCOL = {
    'version': 'expected-minutes-v1', 'contract': CONTRACT,
    'train': list(SEASONS[:2]), 'development': [SEASONS[2]],
    'forbidden_selection_seasons': ['2024-25', '2025-26'],
    'target': CONTRACT['target'], 'primary_metric': 'development RMSE; name breaks ties',
    'candidate': {'loss': 'squared_error', 'learning_rate': .05, 'max_iter': 150,
                  'max_leaf_nodes': 15, 'min_samples_leaf': 50, 'l2_regularization': 10.,
                  'early_stopping': False, 'random_state': 1729, 'categorical_features': None},
    'preprocessing': 'train-only median numeric imputation, all-null computational zero, explicit original missing flags; train-only one-hot position/status, unknown ignored',
    'baselines': 'training position mean (overall fallback); recent three calendar-GW observed minutes (position fallback); recent baseline times chance/100 only when explicitly observed, otherwise unadjusted',
    'prediction_transform': 'lower bound zero; no 90-minute cap; no hindsight opportunity scaling',
    'segments': 'all; actual appearance (target > 0, diagnostic only); useful-history (pre-capture minutes_mean_3 >= 60); cold history; missing chance',
    'downstream_training_allowed': False,
    'stacking_handoff': 'future xPts rows require expanding chronological out-of-sample fits and selection fixed before each row; these development predictions are not stacking features',
}


def load_rows(folder):
    verify_features(folder)
    tables = {}
    expected = {'features.csv': set(KEYS+FEATURES), 'labels.csv': set(KEYS+('target_minutes','label_available_at'))}
    for name in ('features.csv', 'labels.csv', 'row_audit.csv'):
        table = {}
        for r in read_csv(Path(folder)/name):
            if name in expected and set(r) != expected[name]:
                raise ValueError('minutes closed column contract violated')
            k = (r['season'], int(r['target_gameweek']), int(r['element']))
            if k[0] not in SEASONS or k in table:
                raise ValueError('unexpected season or duplicate minutes row')
            table[k] = r
        tables[name] = table
    keys = set(tables['features.csv'])
    if not keys or any(set(t) != keys for t in tables.values()):
        raise ValueError('minutes populations differ')
    result = []
    for k in sorted(keys):
        raw, label, audit = [tables[n][k] for n in ('features.csv','labels.csv','row_audit.csv')]
        f = {n: number(raw[n], 'string' if n == 'status' else 'number') for n in FEATURES}
        if any(f[n+'_missing'] != int(f[n] is None) for n in NULLABLE):
            raise ValueError('minutes missingness mismatch')
        y = number(label['target_minutes'], 'integer')
        if y is not None and (y < 0 or not label['label_available_at'] or label['label_available_at'] <= audit['deadline_time_utc']):
            raise ValueError('invalid minutes target evidence')
        result.append({**dict(zip(KEYS, k)), 'features': f, 'target_minutes': y,
                       'label_available_at': label['label_available_at'], 'audit': audit})
    return result


def matrix(rows):
    if any(set(r['features']) != set(FEATURES) for r in rows):
        raise ValueError('minutes feature allowlist mismatch')
    return np.array([[('__missing__' if r['features'][f] is None else (str(int(r['features'][f])) if f == 'position' else str(r['features'][f]))) if f in CATEGORICAL
                      else (np.nan if r['features'][f] is None else r['features'][f]) for f in ORDER] for r in rows], dtype=object)


def fit(rows):
    if {r['season'] for r in rows} != set(SEASONS):
        raise ValueError('exact chronological minutes seasons required')
    train = [r for r in rows if r['season'] in SEASONS[:2] and r['target_minutes'] is not None]
    dev = [r for r in rows if r['season'] == SEASONS[2]]
    latest = max(r['label_available_at'] for r in train)
    first = min(r['audit']['capture_time_utc'] for r in dev)
    if latest >= first:
        raise ValueError('training minutes not settled before development')
    prep = ColumnTransformer([
        ('numeric', SimpleImputer(strategy='median', keep_empty_features=True), list(range(len(NUMERIC)))),
        ('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), list(range(len(NUMERIC), len(ORDER)))),
    ], sparse_threshold=0)
    model = Pipeline([('preprocess', prep), ('model', HistGradientBoostingRegressor(**PROTOCOL['candidate']))])
    with threadpool_limits(limits=1):
        model.fit(matrix(train), [r['target_minutes'] for r in train])
    means = {str(p): mean(r['target_minutes'] for r in train if r['features']['position'] == p)
             for p in sorted({r['features']['position'] for r in train})}
    # Stable integer-looking keys across CSV float parsing and prospective JSON ints.
    means = {str(int(float(k))): v for k, v in means.items()}
    return model, {'position_means': means, 'overall_mean': mean(r['target_minutes'] for r in train),
                   'training_rows': len(train), 'latest_training_settlement': latest,
                   'first_development_capture': first, 'training_keys_sha256': digest([[r[k] for k in KEYS] for r in train])}


def predict(rows, model, frozen):
    if not rows:
        raise ValueError('empty prediction population')
    with threadpool_limits(limits=1):
        values = model.predict(matrix(rows))
    if len(values) != len(rows) or not np.isfinite(values).all():
        raise ValueError('invalid raw minutes predictions')
    result = []
    for r, v in zip(rows, values):
        f = r['features']
        average = frozen['position_means'].get(str(int(f['position'])), frozen['overall_mean'])
        recent = f['minutes_mean_3'] if f['minutes_mean_3'] is not None else average
        adjusted = recent*f['chance']/100 if f['chance'] is not None else recent
        preds = dict(zip(NAMES, (average, recent, adjusted, max(0., float(v)))))
        if not all(math.isfinite(p) and p >= 0 for p in preds.values()):
            raise ValueError('invalid minutes forecast')
        result.append({**{k:r[k] for k in KEYS}, **preds})
    return result


def metrics(rows, predictions, name):
    if len(rows) != len(predictions):
        raise ValueError('metrics population mismatch')
    pairs = [(r['target_minutes'], p[name]) for r, p in zip(rows, predictions) if r['target_minutes'] is not None and p[name] is not None]
    return {'rows': len(rows), 'scored': len(pairs),
            'mae': mean(abs(y-p) for y,p in pairs) if pairs else None,
            'rmse': math.sqrt(mean((y-p)**2 for y,p in pairs)) if pairs else None}


def evaluate(rows, predictions):
    filters = {'all': lambda r: True,
               'actual_appearance': lambda r: r['target_minutes'] is not None and r['target_minutes'] > 0,
               'useful_history': lambda r: (r['features']['minutes_mean_3'] or 0) >= 60,
               'cold_history': lambda r: r['features']['minutes_count_3'] == 0,
               'missing_chance': lambda r: r['features']['chance'] is None}
    filters.update({f'position_{p}': lambda r, p=p: r['features']['position'] == p for p in (1,2,3,4)})
    report = {}
    for segment, accept in filters.items():
        selected = [(r,p) for r,p in zip(rows,predictions) if accept(r)]
        a,b = zip(*selected) if selected else ([],[])
        report[segment] = {n: metrics(a,b,n) for n in NAMES}
    return report


def run_minutes(feature_dir, output_dir=Path('data/minutes')):
    upstream = verify_features(feature_dir)
    rows = load_rows(feature_dir)
    model, frozen = fit(rows)
    dev = [r for r in rows if r['season'] == SEASONS[2]]
    predictions = predict(dev, model, frozen)
    report = evaluate(dev, predictions)
    selected = min(NAMES, key=lambda n: (report['all'][n]['rmse'], n))
    frozen.update(protocol=PROTOCOL, selected=selected, environment=environment(),
                  features_identity=upstream['identity_sha256'],
                  features_manifest_sha256=sha256_file(Path(feature_dir)/'manifest.json'))
    def writer(folder):
        atomic_write_json(folder/'frozen.json', frozen)
        atomic_write_json(folder/'development.json', report)
        atomic_write_csv(folder/'predictions.csv', predictions, list(KEYS+NAMES))
        (folder/'model.pickle').write_bytes(pickle.dumps(model, protocol=5))
    return publish(output_dir, {'kind': 'minutes-freeze', 'protocol': PROTOCOL,
                               'features_identity': upstream['identity_sha256'], 'environment': environment()}, writer)


def load_frozen(folder):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'minutes-freeze')
    frozen = json.loads((folder/'frozen.json').read_text())
    if (manifest['metadata']['protocol'] != PROTOCOL or frozen['protocol'] != PROTOCOL or
            frozen['environment'] != environment() or frozen['selected'] not in NAMES or
            frozen['features_identity'] != manifest['metadata']['features_identity']):
        raise ValueError('minutes frozen contract mismatch')
    report = json.loads((folder/'development.json').read_text())
    if frozen['selected'] != min(NAMES, key=lambda n: (report['all'][n]['rmse'],n)):
        raise ValueError('minutes selection mismatch')
    # Only trusted locally produced artifacts may be unpickled.
    return pickle.loads((folder/'model.pickle').read_bytes()), frozen, manifest
