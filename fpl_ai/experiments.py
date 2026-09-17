"""Bounded train-only fits, validation selection, then frozen-model holdout scoring."""
import importlib.metadata
import json
import pickle
import platform
from pathlib import Path

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from fpl_ai.evaluation import BASELINES, evaluate
from fpl_ai.experiment_io import digest, key, load_rows, publish, verify_bundle, verify_m3
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, sha256_file
from fpl_ai.modelling_contract import CONTRACT, FEATURES, KEYS

SEED = 1729
CATEGORICAL = ('deadline_position_id', 'status')
EXCLUDED = ('deadline_team_id', 'deadline_team_id_missing')
NUMERIC = tuple(f for f in FEATURES if f not in CATEGORICAL + EXCLUDED and not f.endswith('_missing'))
INDICATORS = tuple(f for f in FEATURES if f not in EXCLUDED and f.endswith('_missing'))
MODEL_FEATURES = NUMERIC + INDICATORS + CATEGORICAL
CONFIGS = {
    'ridge_10': {'family': 'ridge', 'alpha': 10.0},
    'ridge_100': {'family': 'ridge', 'alpha': 100.0},
    'hist_15': {'family': 'hist_gradient_boosting', 'max_leaf_nodes': 15},
    'hist_31': {'family': 'hist_gradient_boosting', 'max_leaf_nodes': 31},
}
PROTOCOL = {
    'version': 'm4-first-regressors-v1', 'm3_contract': CONTRACT,
    'primary_metric': 'validation overall RMSE; minimize, tie break by configuration name',
    'reason': 'Squared error targets the conditional mean required for expected points.',
    'fit': 'labelled train rows only; no validation refit; all train labels settled before validation begins',
    'holdout': 'only selected saved pipeline; no other ML candidate scored on test',
    'candidates': CONFIGS, 'seed': SEED, 'threads': 1,
    'features': list(MODEL_FEATURES),
    'excluded_features': {f: 'Season-local team number is not a cross-season club identity.' for f in EXCLUDED},
    'preprocessing': {
        'numeric': list(NUMERIC), 'numeric_imputation': 'training median; all-null column fallback 0 with indicator retained',
        'scaling': 'training StandardScaler on imputed numeric columns; both families use same projection',
        'indicators': list(INDICATORS), 'indicator_transform': 'passthrough; never imputed or scaled',
        'categorical': list(CATEGORICAL), 'encoding': 'training one-hot, all categories retained; unknown all-zero',
        'categorical_null': 'literal __missing__; does not imply any actual status',
        'null_semantics': 'Computational fills only; original missingness indicators retain meaning. No null-as-fit interpretation.',
    },
    'nonlinear': {'loss':'squared_error', 'learning_rate':0.05, 'max_iter':150,
                  'min_samples_leaf':50, 'l2_regularization':10.0, 'early_stopping':False,
                  'categorical_features':None, 'random_state':SEED},
    'linear': {'solver':'svd', 'fit_intercept':True},
    'output_transform': 'none; no clipping',
    'diagnostics': 'all validation candidates; coefficients; within-GW grouped permutation MSE increase, fixed 4096-row sample, 3 repeats, seed 1729',
    'uncertainty': 'paired GW cluster bootstrap RMSE delta, 2000 replicates, seed 1729; descriptive, ignores inter-GW dependence',
}


def environment():
    return {'python': platform.python_version(), 'machine': platform.machine(),
            'system': platform.system(), 'libraries': {n:importlib.metadata.version(n) for n in
            ('scikit-learn','numpy','scipy','joblib','threadpoolctl')}}


def matrix(rows):
    if any(set(r['features']) != set(FEATURES) for r in rows):
        raise ValueError('model matrix requires exact M3 allowlist')
    return np.array([[('__missing__' if r['features'][f] is None else str(r['features'][f]))
                      if f in CATEGORICAL else (np.nan if r['features'][f] is None else r['features'][f])
                      for f in MODEL_FEATURES] for r in rows], dtype=object)


def make_pipeline(config):
    n, i = len(NUMERIC), len(INDICATORS)
    preprocessing = ColumnTransformer([
        ('numeric', Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),
                              ('scale',StandardScaler())]), list(range(n))),
        ('indicators','passthrough',list(range(n,n+i))),
        ('categorical',OneHotEncoder(handle_unknown='ignore',sparse_output=False),list(range(n+i,len(MODEL_FEATURES)))),
    ], remainder='drop', sparse_threshold=0)
    if config['family'] == 'ridge':
        estimator = Ridge(alpha=config['alpha'], **PROTOCOL['linear'])
    else:
        estimator = HistGradientBoostingRegressor(max_leaf_nodes=config['max_leaf_nodes'], **PROTOCOL['nonlinear'])
    return Pipeline([('preprocess',preprocessing),('model',estimator)])


def fit_candidates(rows):
    if any(r['split'] not in ('train','validation') for r in rows):
        raise ValueError('test rows forbidden during selection')
    train = [r for r in rows if r['split']=='train' and r['target_points'] is not None]
    validation = [r for r in rows if r['split']=='validation']
    if not train or not validation:
        raise ValueError('requires training and validation populations')
    if max(r['label_available_at'] for r in train) >= min(r['audit']['capture_time_utc'] for r in validation):
        raise ValueError('training labels not settled before validation')
    x, y = matrix(train), np.array([r['target_points'] for r in train])
    models = {}
    with threadpool_limits(limits=1):
        for name, config in CONFIGS.items():
            models[name] = make_pipeline(config).fit(x,y)
    return models


def predict(rows, models, baselines):
    predictions = {key(r):dict(baselines[key(r)]) for r in rows}
    x = matrix(rows)
    with threadpool_limits(limits=1):
        for name, model in models.items():
            values = model.predict(x)
            if len(values) != len(rows) or not np.isfinite(values).all():
                raise ValueError('invalid prediction population or values')
            for r,v in zip(rows,values):
                predictions[key(r)][name] = float(v)
    return predictions


def select_model(report):
    return min(CONFIGS, key=lambda n:(report['overall'][n]['rmse'],n))


def write_predictions(folder, rows, predictions, names):
    atomic_write_csv(folder/'predictions.csv',
                     ({**dict(zip(KEYS,key(r))), **predictions[key(r)]} for r in rows), list(KEYS)+list(names))


def run_validation(m3_dir, output_dir=Path('data/experiments')):
    from fpl_ai.experiment_diagnostics import diagnostics, interpretation, comparisons
    upstream = verify_m3(m3_dir)
    rows, baselines = load_rows(m3_dir, ('train','validation'))
    models = fit_candidates(rows)
    validation = [r for r in rows if r['split']=='validation']
    predictions = predict(validation,models,baselines)
    names = BASELINES + tuple(models)
    report = evaluate(validation,predictions,names)['validation']
    selected = select_model(report)
    fit_rows = [r for r in rows if r['split']=='train' and r['target_points'] is not None]
    frozen = {'selected':selected, 'configuration':CONFIGS[selected], 'protocol':PROTOCOL,
              'environment':environment(), 'training_rows':len(fit_rows),
              'training_keys_sha256':digest([key(r) for r in fit_rows]),
              'latest_training_settlement':max(r['label_available_at'] for r in fit_rows),
              'first_validation_capture':min(r['audit']['capture_time_utc'] for r in validation),
              'validation_rows':len(validation), 'holdout_evaluated':False}
    sanity = diagnostics(validation,predictions,tuple(models))
    info = interpretation(validation,models)
    deltas = comparisons(validation,predictions,tuple(models))
    def writer(folder):
        atomic_write_json(folder/'upstream.json',upstream)
        atomic_write_json(folder/'frozen.json',frozen)
        atomic_write_json(folder/'validation.json',report)
        atomic_write_json(folder/'diagnostics.json',sanity)
        atomic_write_json(folder/'interpretation.json',info)
        atomic_write_json(folder/'comparisons.json',deltas)
        write_predictions(folder,validation,predictions,names)
        for name,model in models.items():
            (folder/f'{name}.pickle').write_bytes(pickle.dumps(model,protocol=5))
    return publish(output_dir, {'kind':'validation-freeze','protocol':PROTOCOL,
                   'upstream_identity':upstream['identity_sha256'],'environment':environment()},writer)


def run_holdout(m3_dir, frozen_dir, output_dir=Path('data/experiment_holdouts')):
    from fpl_ai.experiment_diagnostics import diagnostics, comparisons
    frozen_dir = Path(frozen_dir)
    manifest = verify_bundle(frozen_dir,'validation-freeze')
    upstream = verify_m3(m3_dir)
    if json.loads((frozen_dir/'upstream.json').read_text()) != upstream:
        raise ValueError('frozen experiment requires exact original M3 artifact')
    frozen = json.loads((frozen_dir/'frozen.json').read_text())
    if frozen['protocol'] != PROTOCOL or frozen['environment'] != environment():
        raise ValueError('frozen protocol or training environment differs')
    report = json.loads((frozen_dir/'validation.json').read_text())
    selected = frozen['selected']
    if selected != select_model(report) or frozen['configuration'] != CONFIGS[selected]:
        raise ValueError('invalid frozen selection')
    # Only load locally generated, hash-verified pickle bundles. Never unpickle untrusted downloads.
    model = pickle.loads((frozen_dir/f'{selected}.pickle').read_bytes())
    rows, baselines = load_rows(m3_dir,('test',))
    if frozen['latest_training_settlement'] >= min(r['audit']['capture_time_utc'] for r in rows):
        raise ValueError('training extends beyond holdout start')
    predictions = predict(rows,{selected:model},baselines)
    names = BASELINES + (selected,)
    report = evaluate(rows,predictions,names)['test']
    def writer(folder):
        atomic_write_json(folder/'holdout.json',report)
        atomic_write_json(folder/'diagnostics.json',diagnostics(rows,predictions,(selected,)))
        atomic_write_json(folder/'comparisons.json',comparisons(rows,predictions,(selected,)))
        write_predictions(folder,rows,predictions,names)
    return publish(output_dir, {'kind':'frozen-holdout','frozen_identity':manifest['identity_sha256'],
                   'frozen_manifest_sha256':sha256_file(frozen_dir/'manifest.json'),
                   'upstream_identity':upstream['identity_sha256'], 'selected':selected,
                   'protocol':PROTOCOL,'environment':environment()},writer)
