"""Fixed historical matched ablation of independently OOS expected minutes.

Only trusted local, verified M3/M4/M4C bundles are accepted. Historical captures
are information cutoffs, not claims of actual historical computation times.
"""
import argparse
import io
import json
import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from fpl_ai.evaluation import BASELINES, metrics
from fpl_ai.experiment_io import digest, key, load_rows, publish, verify_bundle, verify_m3
from fpl_ai.experiments import (CONFIGS, MODEL_FEATURES, PROTOCOL as M4_PROTOCOL,
                                environment, make_pipeline, matrix as m4_matrix)
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json, sha256_file
from fpl_ai.minutes_oos import earlier, load_downstream
from fpl_ai.modelling import read_csv
from fpl_ai.modelling_contract import CONTRACT, FEATURES, KEYS

M3_ID = '57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a'
OOS_ID = '3550ded6a2aff16fa9f799b9c993b8799726d0243a3b1e643e6249af475867be'
HOLDOUT_ID = '21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd'
SEASONS = ('2024-25', '2025-26')
EXPECTED_COUNTS = {'2024-25': 27159, '2025-26': 29645}
EXTRA = 'oos_expected_minutes'
ORDERS = {'control': MODEL_FEATURES, 'xpts_v2': MODEL_FEATURES + (EXTRA,)}
STATE_FIELDS = ('capture_time_utc', 'deadline_time_utc', 'snapshot_source_path',
                'snapshot_sha256', 'snapshot_age_minutes', 'observed_player_code',
                'superseded_deadline_exception', 'payload_deadline_utc')
PROTOCOL = {
    'version': 'm4d-xpts-v2-v1', 'm3_identity': M3_ID, 'minutes_oos_identity': OOS_ID,
    'frozen_m4_holdout_identity': HOLDOUT_ID, 'point_contract': CONTRACT,
    'fit_season': SEASONS[0], 'evaluation_season': SEASONS[1],
    'evaluation_role': 'fixed consumed historical evidence; no new untouched holdout or prospective confirmation',
    'candidate': {'configuration': CONFIGS['hist_15'], **M4_PROTOCOL['nonlinear']},
    'preprocessing': M4_PROTOCOL['preprocessing'],
    'extra_preprocessing': 'append one numeric input; training median and StandardScaler, same M4 semantics; missing OOS rows excluded before preprocessing, never filled',
    'feature_order': {n:list(fs) for n,fs in ORDERS.items()},
    'output_transform': 'none; no clipping', 'threads': 1,
    'serialization': 'pickle protocol 5 with memoization disabled for these acyclic local estimator states; object alias sharing is not model state; fail on cycles',
    'join': {'key': list(KEYS), 'decision_state': list(STATE_FIELDS),
             'source': 'exact historical source/build identity and shared consumed table hashes',
             'missing': 'retain audit and null feature; exclude from both matched populations; no fallback'},
    'fit': '2024-25 independently evidenced points labels only; all preprocessing and fit evidence strictly before first 2025-26 capture',
    'selection': 'none; xpts_v2 is the predefined candidate, control is only an ablation',
    'primary_metric': 'RMSE',
    'ranking': 'per GW forecast top min(10,n), descending prediction then ascending element ID; mean realised points per selected player, then equal mean across GWs; only independently labelled common rows',
    'segments': 'overall; each GW; position 1..4; established history count>=3, low history count<3; any original feature missing; chance missing',
    'references': 'frozen M4 hist_15 has different fitting population, not a feature ablation; original M3 baselines unchanged; ep_next remains reference only',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def indexed(rows):
    result = {key(r):r for r in rows}
    require(len(result) == len(rows), 'duplicate downstream key')
    return result


def upstream(m3_dir, oos_dir, holdout_dir):
    m3 = verify_m3(m3_dir)
    # Deliberately call the downstream boundary, never a generic prediction CSV reader.
    forecasts = load_downstream(oos_dir)
    oos = verify_bundle(oos_dir, 'minutes-oos')
    holdout = verify_bundle(holdout_dir, 'frozen-holdout')
    require((m3['identity_sha256'], oos['identity_sha256'], holdout['identity_sha256']) ==
            (M3_ID, OOS_ID, HOLDOUT_ID), 'unaccepted exact upstream identity')
    require(holdout['metadata']['upstream_identity'] == M3_ID and
            holdout['metadata']['selected'] == 'hist_15' and
            holdout['metadata']['protocol'] == M4_PROTOCOL, 'incompatible frozen M4 reference')
    sources = json.loads((Path(oos_dir)/'sources.json').read_text())['historical']
    for season in SEASONS:
        a, b = m3['identity']['sources'][season], sources[season]
        for field in ('version', 'source_identity_sha256', 'build_identity_sha256',
                      'source_identity', 'build_identity', 'snapshot_exception'):
            require(a[field] == b[field], 'different historical source/build state')
        require(all(b['consumed_tables'].get(k) == v for k,v in a['consumed_tables'].items()),
                'different shared historical table bytes')
    require(dict(Counter(r['season'] for r in forecasts)) == EXPECTED_COUNTS,
            'accepted OOS population changed')
    indexed(forecasts)
    audits = indexed(read_csv(Path(oos_dir)/'row_audit.csv'))
    return {'m3':m3, 'minutes_oos':oos, 'frozen_m4_holdout':holdout}, indexed(forecasts), audits


def join_rows(rows, forecasts, minutes_audits):
    """Feature-only public product; outcome availability affects audit, never value."""
    indexed(rows)
    features, audits = [], []
    for r in rows:
        k = key(r); p = forecasts.get(k); a = r['audit']
        expected = None
        if p is not None:
            require(key(p) == k and k in minutes_audits, 'missing minutes decision state')
            b = minutes_audits[k]
            require(all(a[field] == b[field] for field in STATE_FIELDS), 'different decision-time state')
            require(p['prediction_class'] == 'chronological_oos' and
                    p['downstream_training_allowed'] == 'True' and not p['unavailable_reason'],
                    'ineligible expected-minutes forecast')
            require(p['prediction_capture'] == a['capture_time_utc'] and
                    earlier(p['prediction_capture'], a['deadline_time_utc']) and
                    earlier(p['training_cutoff'], p['prediction_capture']) and
                    earlier(p['selection_cutoff'], p['prediction_capture']), 'unsafe minutes chronology')
            expected = float(p['expected_minutes'])
            require(math.isfinite(expected) and expected >= 0, 'invalid OOS expected minutes')
        require(set(r['features']) == set(FEATURES), 'point feature allowlist violated')
        features.append({**dict(zip(KEYS,k)), **{f:r['features'][f] for f in MODEL_FEATURES}, EXTRA:expected})
        reason = 'missing_oos_minutes' if p is None else ('missing_points_label' if r['target_points'] is None else '')
        audits.append({**dict(zip(KEYS,k)), **{f:a[f] for f in STATE_FIELDS},
                       'minutes_model_identity':p['model_identity'] if p else '',
                       'minutes_feature_identity':p['feature_identity'] if p else '',
                       'minutes_training_cutoff':p['training_cutoff'] if p else '',
                       'minutes_selection_cutoff':p['selection_cutoff'] if p else '',
                       'eligible': not reason, 'unavailable_reason': reason})
    return features, audits


def model_matrix(features, name):
    require(name in ORDERS, 'unknown downstream candidate')
    require(all(set(f) == set(KEYS + ORDERS['xpts_v2']) for f in features), 'closed xPts feature allowlist violated')
    require(all(f[EXTRA] is not None and math.isfinite(f[EXTRA]) and f[EXTRA] >= 0 for f in features),
            'missing OOS minutes cannot fall back or be imputed')
    # Reuse M4's exact categorical/null projection. Excluded team fields are inert.
    rows = [{'features': {f:r.get(f) for f in FEATURES}} for r in features]
    x = m4_matrix(rows)
    return np.column_stack((x, [r[EXTRA] for r in features])) if name == 'xpts_v2' else x


def pipeline(name):
    require(name in ORDERS, 'unknown downstream candidate')
    model = make_pipeline(CONFIGS['hist_15'])
    if name == 'xpts_v2':
        # Leave every existing M4 transform and its feature order intact.
        model.named_steps['preprocess'].transformers.append((
            'expected_minutes', Pipeline([('impute',SimpleImputer(strategy='median', keep_empty_features=True)),
                                          ('scale',StandardScaler())]), [len(MODEL_FEATURES)]))
    return model


def model_bytes(model):
    """Serialize values without incidental Python/NumPy object alias sharing.

    Prior unpickling changes dtype caches and hence pickle memo references without
    changing numerical state. These pipelines have acyclic estimator state, so
    disabling memoization removes that source of nondeterminism. A cyclic state
    fails closed. Only trusted local estimators are ever serialized or loaded.
    """
    stream = io.BytesIO()
    serializer = pickle.Pickler(stream, protocol=5)
    serializer.fast = True  # Pickler's explicit no-memo mode; requires acyclic state.
    try:
        serializer.dump(model)
    except (ValueError, RecursionError) as exc:
        raise ValueError('model state must be acyclic for deterministic serialization') from exc
    return stream.getvalue()


def fit_models(features, labels, audits, first_evaluation_capture):
    f, y, a = indexed(features), indexed(labels), indexed(audits)
    require(set(f) == set(y) == set(a) and bool(f), 'fit populations differ')
    require(all(k[0] == SEASONS[0] for k in f), 'only 2024-25 points labels may fit')
    eligible = [k for k in f if a[k]['eligible']]
    require(bool(eligible), 'no eligible fitting rows')
    for k in eligible:
        require(y[k]['target_points'] is not None and
                earlier(a[k]['capture_time_utc'], y[k]['label_available_at']) and
                earlier(y[k]['label_available_at'], first_evaluation_capture) and
                earlier(a[k]['capture_time_utc'], first_evaluation_capture), 'points fitting cutoff violated')
    selected = [f[k] for k in eligible]
    models = {}
    with threadpool_limits(limits=1):
        for name in ORDERS:
            models[name] = pipeline(name).fit(model_matrix(selected,name), [y[k]['target_points'] for k in eligible])
    training = [{**dict(zip(KEYS,k)), 'capture':a[k]['capture_time_utc'],
                 'label_available_at':y[k]['label_available_at'],
                 'feature_sha256':digest(f[k]), 'label_sha256':digest(y[k])} for k in eligible]
    state = {'training_rows':len(eligible), 'training_keys_sha256':digest(eligible),
             'training_features_sha256':digest(selected), 'training_labels_sha256':digest([y[k] for k in eligible]),
             'latest_training_settlement':max(y[k]['label_available_at'] for k in eligible),
             'first_evaluation_capture':first_evaluation_capture,
             'model_features':PROTOCOL['feature_order'], 'environment':environment()}
    return models, state, training


def top10(rows, predictions, name):
    groups = defaultdict(list)
    for r in rows:
        if r['target_points'] is not None and predictions[key(r)].get(name) is not None:
            groups[(r['season'],r['target_gameweek'])].append(r)
    values = {}
    for (s,g), group in groups.items():
        chosen = sorted(group, key=lambda r:(-predictions[key(r)][name],r['element']))[:10]
        values[f'{s}:{g}'] = {'rows':len(chosen), 'elements':[r['element'] for r in chosen],
                              'mean_realised_points':mean(r['target_points'] for r in chosen)}
    return {'mean_top10_realised_points':mean(v['mean_realised_points'] for v in values.values()) if values else None,
            'gameweeks':values}


def evaluate(rows, predictions):
    require(set(predictions) == set(indexed(rows)), 'common-row prediction population mismatch')
    require(all(set(p) == set(ORDERS) | set(BASELINES) | {'frozen_m4'} for p in predictions.values()),
            'prediction model set mismatch')
    groups = {'overall':rows, 'established_history':[r for r in rows if r['features']['season_points_count'] >= 3],
              'low_history':[r for r in rows if r['features']['season_points_count'] < 3],
              'any_missing':[r for r in rows if any(r['features'][f] for f in MODEL_FEATURES if f.endswith('_missing'))],
              'chance_missing':[r for r in rows if r['features']['chance_of_playing_next_round'] is None]}
    groups.update({f'position:{p}':[r for r in rows if r['features']['deadline_position_id'] == p] for p in range(1,5)})
    groups.update({f'gw:{g}':[r for r in rows if r['target_gameweek'] == g] for g in range(1,39)})
    names = tuple(ORDERS) + ('frozen_m4',) + BASELINES
    result = {'segments':{g:{n:metrics(rs,predictions,n) for n in names} for g,rs in groups.items()},
              'ranking':{n:top10(rows,predictions,n) for n in names}, 'paired':{}}
    for reference in ('control','frozen_m4') + BASELINES:
        common = [r for r in rows if predictions[key(r)][reference] is not None]
        a,b = [metrics(common,predictions,n) for n in ('xpts_v2',reference)]
        result['paired'][reference] = {'rows':len(common), 'keys_sha256':digest([key(r) for r in common]),
            'v2_minus_reference':{m:a[m]-b[m] if a[m] is not None and b[m] is not None else None
                                 for m in ('rmse','mae','mean_gameweek_spearman')},
            'top10_delta':top10(common,predictions,'xpts_v2')['mean_top10_realised_points'] -
                          top10(common,predictions,reference)['mean_top10_realised_points'] if common else None}
    return result


def labels_for(rows):
    return [{**dict(zip(KEYS,key(r))), 'target_points':r['target_points'],
             'label_available_at':r['label_available_at']} for r in rows]


def write_table(folder, name, rows):
    require(bool(rows), f'empty required artifact: {name}')
    atomic_write_csv(folder/name, rows, list(rows[0]))


def coverage_report(all_features, all_audit, evaluation_rows, minutes_audits):
    return {'seasons':{s:{'rows':sum(f['season']==s for f in all_features),
                            'eligible':sum(a['season']==s and a['eligible'] for a in all_audit),
                            'reasons':dict(Counter(a['unavailable_reason'] for a in all_audit if a['season']==s))}
                            for s in SEASONS},
                'gameweeks':{f'{s}:{g}':sum(a['season']==s and a['target_gameweek']==g and a['eligible'] for a in all_audit)
                             for s in SEASONS for g in range(1,39)},
                'earlier_unavailable':sum(k[0] not in SEASONS for k in minutes_audits), 'earlier_reason':'insufficient_prior_selection_history',
                'joined_rows':len(all_features), 'evaluation_keys_sha256':digest([key(r) for r in evaluation_rows])}


def run(m3_dir, oos_dir, holdout_dir, output_dir=Path('data/xpts_v2')):
    upstreams, forecasts, minutes_audits = upstream(m3_dir, oos_dir, holdout_dir)
    # First evaluation capture comes only from predictor provenance, never labels.
    first = min(p['prediction_capture'] for k,p in forecasts.items() if k[0] == SEASONS[1])
    train_rows, _ = load_rows(m3_dir, ('validation',))
    train_features, train_audit = join_rows(train_rows, forecasts, minutes_audits)
    models, state, training = fit_models(train_features, labels_for(train_rows), train_audit, first)
    # Materialize evaluation labels only after both pipelines have been fitted.
    test_rows, baselines = load_rows(m3_dir, ('test',))
    test_features, test_audit = join_rows(test_rows, forecasts, minutes_audits)
    all_features, all_audit = train_features + test_features, train_audit + test_audit
    require(set(indexed(all_features)) == set(forecasts), 'current one-to-one join population mismatch')
    eligible_keys = {key(a) for a in test_audit if a['eligible']}
    evaluation_rows = [r for r in test_rows if key(r) in eligible_keys]
    x = [f for f in test_features if key(f) in eligible_keys]
    frozen = indexed(read_csv(Path(holdout_dir)/'predictions.csv'))
    require(set(frozen) == set(indexed(test_rows)), 'frozen M4 population mismatch')
    predictions = {key(r):{**baselines[key(r)], 'frozen_m4':float(frozen[key(r)]['hist_15'])} for r in evaluation_rows}
    with threadpool_limits(limits=1):
        for name, model in models.items():
            values = model.predict(model_matrix(x,name))
            require(np.isfinite(values).all(), 'nonfinite downstream predictions')
            for r,v in zip(evaluation_rows,values): predictions[key(r)][name] = float(v)
    report = evaluate(evaluation_rows,predictions)
    coverage = coverage_report(all_features, all_audit, evaluation_rows, minutes_audits)
    state['coverage'] = coverage
    def writer(folder):
        atomic_write_json(folder/'protocol.json', PROTOCOL)
        atomic_write_json(folder/'upstream.json', upstreams)
        atomic_write_json(folder/'fit.json', state)
        write_table(folder,'features.csv',all_features)
        write_table(folder,'row_audit.csv',all_audit)
        write_table(folder,'training.csv',training)
        write_table(folder,'predictions.csv',[{**dict(zip(KEYS,k)), **p} for k,p in predictions.items()])
        for n,m in models.items(): (folder/f'{n}.pickle').write_bytes(model_bytes(m))
    out,reused = publish(output_dir, {'kind':'xpts-v2', 'protocol':PROTOCOL, 'environment':environment()}, writer)
    def score_writer(folder):
        write_table(folder,'outcomes.csv',labels_for(train_rows + test_rows))
        atomic_write_json(folder/'metrics.json',report)
    score,sr = publish(Path(output_dir)/'scores', {'kind':'xpts-v2-score', 'prediction_identity':out.name,
                       'prediction_manifest_sha256':sha256_file(out/'manifest.json'), 'protocol':PROTOCOL}, score_writer)
    return out,reused,score,sr


def verify(out, score, m3_dir, oos_dir, holdout_dir):
    """Reconstruct join and outcomes; replay saved states without fitting on test."""
    out,score = Path(out),Path(score)
    manifest = verify_bundle(out,'xpts-v2'); sm = verify_bundle(score,'xpts-v2-score')
    require(manifest['metadata']['protocol'] == PROTOCOL and
            json.loads((out/'protocol.json').read_text()) == PROTOCOL and
            sm['metadata']['protocol'] == PROTOCOL and sm['metadata']['prediction_identity'] == out.name and
            sm['metadata']['prediction_manifest_sha256'] == sha256_file(out/'manifest.json'), 'xPts protocol/link mismatch')
    sources, forecasts, audits = upstream(m3_dir,oos_dir,holdout_dir)
    require(json.loads((out/'upstream.json').read_text()) == sources, 'xPts upstream binding mismatch')
    rows, baselines = load_rows(m3_dir,('validation','test'))
    fs, aa = join_rows(rows,forecasts,audits)
    # Compare canonical serialized tables, including exact headers and row order.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        for name, table, source in [('features.csv',fs,out), ('row_audit.csv',aa,out),
                                    ('outcomes.csv',labels_for(rows),score)]:
            write_table(temp,name,table)
            require(sha256_file(temp/name) == sha256_file(source/name), f'reconstructed {name} mismatch')
    require(set(indexed(fs)) == set(forecasts), 'xPts join population mismatch')
    state = json.loads((out/'fit.json').read_text())
    train = [r for r,a in zip(rows,aa) if r['season']==SEASONS[0] and a['eligible']]
    train_f = [f for f,a in zip(fs,aa) if f['season']==SEASONS[0] and a['eligible']]
    first = min(r['audit']['capture_time_utc'] for r in rows if r['season']==SEASONS[1])
    require(state['training_rows']==len(train) and state['training_keys_sha256']==digest([key(r) for r in train]) and
            state['training_features_sha256']==digest(train_f) and state['training_labels_sha256']==digest(labels_for(train)) and
            state['latest_training_settlement']==max(r['label_available_at'] for r in train) and
            state['first_evaluation_capture']==first and state['model_features']==PROTOCOL['feature_order'] and
            state['environment']==manifest['metadata']['environment']==environment(), 'invalid xPts fitting state')
    require(all(earlier(r['label_available_at'],first) and earlier(r['audit']['capture_time_utc'],first) for r in train),
            'xPts fitting boundary violated')
    training = read_csv(out/'training.csv')
    require(len(training)==len(train), 'training artifact population mismatch')
    for saved,r,f in zip(training,train,train_f):
        require(key(saved)==key(r) and saved['capture']==r['audit']['capture_time_utc'] and
                saved['label_available_at']==r['label_available_at'] and saved['feature_sha256']==digest(f) and
                saved['label_sha256']==digest(labels_for([r])[0]), 'training evidence mismatch')
    selected = [r for r,a in zip(rows,aa) if r['season']==SEASONS[1] and a['eligible']]
    xf = [f for f,a in zip(fs,aa) if f['season']==SEASONS[1] and a['eligible']]
    require(state['coverage']==coverage_report(fs,aa,selected,audits), 'coverage metadata differs')
    saved = indexed(read_csv(out/'predictions.csv'))
    require(set(saved)==set(indexed(selected)), 'same-row control/v2 population mismatch')
    reference = indexed(read_csv(Path(holdout_dir)/'predictions.csv'))
    predicted = {key(r):{**baselines[key(r)],'frozen_m4':float(reference[key(r)]['hist_15'])} for r in selected}
    with threadpool_limits(limits=1):
        for name in ORDERS:
            model = pickle.loads((out/f'{name}.pickle').read_bytes())
            require(model.named_steps['model'].get_params()==pipeline(name).named_steps['model'].get_params(),
                    'changed xPts model configuration')
            values = model.predict(model_matrix(xf,name))
            for r,v in zip(selected,values):predicted[key(r)][name]=float(v)
    for k,p in predicted.items():
        require(set(saved[k])==set(KEYS)|set(p), 'closed prediction columns violated')
        require(all((float(saved[k][n]) if saved[k][n] else None)==v for n,v in p.items()), 'xPts saved prediction replay mismatch')
    require(json.loads((score/'metrics.json').read_text())==evaluate(selected,predicted), 'xPts metrics replay mismatch')
    return manifest,sm


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('data'))
    parser.add_argument('--output-dir', type=Path, default=Path('data/xpts_v2'))
    args = parser.parse_args()
    d = args.data_dir
    out,reused,score,sr = run(d/'modelling'/M3_ID,d/'minutes_oos'/OOS_ID,d/'experiment_holdouts'/HOLDOUT_ID,args.output_dir)
    verify(out,score,d/'modelling'/M3_ID,d/'minutes_oos'/OOS_ID,d/'experiment_holdouts'/HOLDOUT_ID)
    print(json.dumps({'predictions':str(out), 'reused':reused, 'score':str(score), 'score_reused':sr}))


if __name__ == '__main__':
    main()
