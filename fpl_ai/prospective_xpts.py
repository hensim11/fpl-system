"""Fixed M4E operational refit and actual-clock xPts publication.

Only trusted local estimator bundles may be loaded. Evidence copies are verified
through the original prospective readers, never treated as arbitrary CSV inputs.
"""
import json
import pickle
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np
from threadpoolctl import threadpool_limits

from fpl_ai import prospective as live
from fpl_ai.evaluation import metrics
from fpl_ai.experiment_io import digest, key, load_rows, publish, verify_bundle
from fpl_ai.experiments import environment
from fpl_ai.features import number
from fpl_ai.historical_io import atomic_write_json, sha256_bytes, sha256_file
from fpl_ai.historical_transform import json_optional_int, json_optional_decimal, parse_utc
from fpl_ai.modelling import read_csv
from fpl_ai.modelling_contract import FEATURE_TYPES, NULLABLE_FEATURES, STATE_FIELDS, KEYS
from fpl_ai.playing_time import players
from fpl_ai.xpts_v2 import (M3_ID, OOS_ID, HOLDOUT_ID, EXPECTED_COUNTS, MODEL_FEATURES,
    EXTRA, ORDERS, PROTOCOL as M4D, indexed, join_rows, labels_for, model_bytes,
    model_matrix, pipeline, require, top10, upstream, write_table)

MINUTES_ID = 'e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc'
MINUTES_BINDING = {
    'manifest_sha256': '719d6aa60615a91d5fe7fb0306ad9ff0b0528128d34822bb1ab1a83506570acc',
    'artifacts': {
        'development.json': 'a915f6cf5044f206fc557e478794b246f3060baf8fbd309ef704968458bab499',
        'frozen.json': '342e8e9d797db0f6902d271a541d57c65bc8a0df440c0d2acfa6a5aaa8bdc817',
        'model.pickle': 'b06796cc1b742be8df0e832f62af5c1b7f6913bf00b65aac9ce9df312ef75f0c',
        'predictions.csv': '3287609ed8c7fc436fe7073d86de4696f3f6f0bc4d32bfd96c520f91a12b1842',
    },
}
SEASON = '2026-27'
CUTOFF = '2026-07-01T00:00:00Z'
PROTOCOL = {
    'version': 'm4e-prospective-xpts-v1', 'season': SEASON,
    'first_supported_state': CUTOFF,
    'fit_seasons': list(EXPECTED_COUNTS), 'fit_counts': EXPECTED_COUNTS,
    'historical_protocol': M4D, 'minutes_model_identity': MINUTES_ID,
    'selection': 'none; fixed hist_15 control and v2 coexist; no automatic winner or refit',
    'history': 'verified prospective settlement/forecast pairs; strictly earlier same-season GWs; received by target bootstrap request; explicit integer points; blank GW and absent players remain missing',
    'state': 'bootstrap now_cost in tenths, ownership, transfers, chance, position and status; exact M3 types and history windows; no team or fixture inputs',
    'minutes': 'verified prospective-predictions-v1 from the exact frozen M4B model; exact snapshot, bootstrap, deadline, keys and feature contract; no fallback',
    'publication': 'actual runtime UTC; begin, computation, semantic verification and final published checksum verification before deadline; failure removes new publication; verify reuses without redating',
    'attestation': 'local clock only; not externally witnessed',
    'outcomes': 'separate immutable score; verified fixture-v2 settlements; common rows and frozen M4D top10 tie rule',
}


def fit_operational(features, labels, audits):
    f, y, a = indexed(features), indexed(labels), indexed(audits)
    require(set(f) == set(y) == set(a) and bool(f), 'fit populations differ')
    require(dict(Counter(k[0] for k in f)) == EXPECTED_COUNTS, 'exact prior-season population required')
    keys = sorted(f)
    for k in keys:
        require(a[k]['eligible'] and type(y[k]['target_points']) is int and
                live.before(a[k]['capture_time_utc'], y[k]['label_available_at']) and
                live.before(y[k]['label_available_at'], CUTOFF), 'unsafe operational fitting evidence')
    selected = [f[k] for k in keys]
    models = {}
    with threadpool_limits(limits=1):
        for name in ORDERS:
            models[name] = pipeline(name).fit(model_matrix(selected, name), [y[k]['target_points'] for k in keys])
    training = [{**dict(zip(KEYS,k)), 'capture':a[k]['capture_time_utc'],
                 'label_available_at':y[k]['label_available_at'], 'feature_sha256':digest(f[k]),
                 'label_sha256':digest(y[k])} for k in keys]
    state = {'training_rows':len(keys), 'counts':dict(Counter(k[0] for k in keys)),
             'training_keys_sha256':digest(keys), 'training_features_sha256':digest(selected),
             'training_labels_sha256':digest([y[k] for k in keys]),
             'latest_training_settlement':max(y[k]['label_available_at'] for k in keys),
             'first_supported_state':CUTOFF, 'feature_order':M4D['feature_order'], 'environment':environment()}
    return models, state, training


def fit(output_dir=Path('data/prospective_xpts/models'), data_dir=Path('data')):
    data_dir = Path(data_dir)
    live.safe_output(output_dir,data_dir/'modelling'/M3_ID,data_dir/'minutes_oos'/OOS_ID,data_dir/'experiment_holdouts'/HOLDOUT_ID)
    sources, forecasts, audits = upstream(data_dir/'modelling'/M3_ID, data_dir/'minutes_oos'/OOS_ID,
                                         data_dir/'experiment_holdouts'/HOLDOUT_ID)
    rows, _ = load_rows(data_dir/'modelling'/M3_ID, ('validation','test'))
    features, audit = join_rows(rows, forecasts, audits)
    require(set(indexed(features)) == set(forecasts), 'operational OOS population differs')
    models, state, training = fit_operational(features, labels_for(rows), audit)
    blobs = {n:model_bytes(m) for n,m in models.items()}
    state['model_hashes'] = {n:sha256_bytes(b) for n,b in blobs.items()}
    state['preprocessing_hashes'] = {n:sha256_bytes(model_bytes(m.named_steps['preprocess'])) for n,m in models.items()}
    state['model_identities'] = {n:digest({'name':n, 'state':state.copy(), 'protocol':PROTOCOL}) for n in ORDERS}
    def writer(folder):
        for name,value in [('protocol.json',PROTOCOL),('fit.json',state),('sources.json',sources)]:
            atomic_write_json(folder/name,value)
        write_table(folder,'training.csv',training)
        for n,b in blobs.items(): (folder/f'{n}.pickle').write_bytes(b)
    return publish(output_dir, {'kind':'prospective-xpts-model','protocol':PROTOCOL,'environment':environment()},writer)


def load_model(folder):
    folder = Path(folder)
    manifest = verify_bundle(folder,'prospective-xpts-model')
    state = json.loads((folder/'fit.json').read_text())
    require(manifest['metadata']['protocol'] == PROTOCOL and
            json.loads((folder/'protocol.json').read_text()) == PROTOCOL and
            state['environment'] == manifest['metadata']['environment'] == environment(), 'incompatible operational protocol/environment')
    training = read_csv(folder/'training.csv'); keys = [key(r) for r in training]
    require(len(keys) == len(set(keys)) == state['training_rows'] and
            dict(Counter(k[0] for k in keys)) == state['counts'] == EXPECTED_COUNTS and
            digest(keys) == state['training_keys_sha256'] and state['first_supported_state'] == CUTOFF and
            state['feature_order'] == M4D['feature_order'], 'operational training population mismatch')
    require(max(r['label_available_at'] for r in training) == state['latest_training_settlement'] and
            all(live.before(r['capture'],r['label_available_at']) and live.before(r['label_available_at'],CUTOFF)
                for r in training), 'operational fitting cutoff violated')
    sources = json.loads((folder/'sources.json').read_text())
    require(tuple(sources[n]['identity_sha256'] for n in ('m3','minutes_oos','frozen_m4_holdout')) ==
            (M3_ID,OOS_ID,HOLDOUT_ID), 'operational source identities differ')
    identity_state = {k:v for k,v in state.items() if k != 'model_identities'}
    models = {}
    for n in ORDERS:
        require(state['model_hashes'][n] == sha256_file(folder/f'{n}.pickle') and
                state['model_identities'][n] == digest({'name':n,'state':identity_state,'protocol':PROTOCOL}), 'operational model identity differs')
        models[n] = pickle.loads((folder/f'{n}.pickle').read_bytes())
        require(sha256_bytes(model_bytes(models[n].named_steps['preprocess'])) == state['preprocessing_hashes'][n], 'preprocessing differs')
        require(models[n].named_steps['model'].get_params() == pipeline(n).named_steps['model'].get_params(), 'model configuration differs')
    return models,state,manifest


def archive(folder):
    """Exact UTF-8 files: hashes retain original serialized bytes, including manifest."""
    manifest = verify_bundle(folder)
    return {'identity':manifest['identity_sha256'],
            'files':{n:(Path(folder)/n).read_bytes().decode('utf-8') for n in sorted(set(manifest['artifacts']) | {'manifest.json'})}}


def restore(root, name, evidence):
    files = evidence['files']
    require(all(Path(n).name == n for n in files), 'unsafe evidence filename')
    identity = evidence['identity']
    require(len(identity) == 64 and all(c in '0123456789abcdef' for c in identity), 'invalid evidence identity')
    folder = root/name/identity
    folder.mkdir(parents=True)
    for n,content in files.items(): (folder/n).write_bytes(content.encode('utf-8'))
    verify_bundle(folder)
    return folder


def points_features(gw, player, history):
    """M3's exact state types and calendar-window means; no aggregate backfill."""
    require(all(type(g) is int and 1 <= g < gw and type(v) is int for g,v in history.items()), 'invalid/future points history')
    mapping = {'deadline_team_id':'team','deadline_position_id':'element_type','price':'now_cost'}
    f = {}
    for name,kind in STATE_FIELDS.items():
        value = player.get(mapping.get(name,name))
        if kind == 'integer': value = json_optional_int(value,name)
        elif kind == 'number': value = json_optional_decimal(value,name)
        else: require(value is None or isinstance(value,str), 'invalid status')
        f[name] = number(value,kind)
    require(f['deadline_position_id'] in (1,2,3,4), 'non-football position')
    f['previous_points'] = history.get(gw-1)
    for w in (3,5):
        values = [history[g] for g in range(max(1,gw-w),gw) if g in history]
        f[f'points_mean_{w}'] = mean(values) if values else None
        f[f'points_count_{w}'] = len(values)
    f['season_points_mean'] = mean(history.values()) if history else None
    f['season_points_count'] = len(history)
    f.update({n+'_missing':int(f[n] is None) for n in NULLABLE_FEATURES})
    return {n:number(f[n],FEATURE_TYPES[n]) for n in MODEL_FEATURES}


def adapter(snapshot_dir, minutes_dir, history_pairs=()):
    bootstrap, _, snapshot = live.load_snapshot(snapshot_dir)
    minutes = live.verify_prediction(minutes_dir)
    s,m = snapshot['metadata'],minutes['metadata']
    require(s['season'] == SEASON and live.not_after(CUTOFF,s['bootstrap_timing']['requested_at']), 'unsupported current-season state')
    require(all(m[k] == s[k] for k in ('season','target_gameweek','deadline')) and
            m['snapshot_identity'] == snapshot['identity_sha256'] and
            m['snapshot_manifest_sha256'] == sha256_file(Path(snapshot_dir)/'manifest.json') and
            m['snapshot_artifacts'] == snapshot['artifacts'] and
            m['snapshot_timing'] == {k:s[k] for k in ('bootstrap_timing','fixtures_timing')} and
            m['fixture_context_snapshot_identity'] == snapshot['identity_sha256'] and not m['fixture_features_used'],
            'snapshot/minutes decision identity mismatch')
    require(m['model_identity'] == MINUTES_ID and m['model_manifest_sha256'] == MINUTES_BINDING['manifest_sha256'] and m['model_artifacts'] == MINUTES_BINDING['artifacts'], 'incompatible expected-minutes model identity')
    ps = indexed(read_csv(Path(minutes_dir)/'predictions.csv'))
    population = {e:p for e,p in players(bootstrap).items() if p['element_type'] in (1,2,3,4)}
    require(set(ps) == {(s['season'],s['target_gameweek'],e) for e in population}, 'wrong minutes element set')
    histories, observations, used = {}, [], set()
    for prediction_dir, settlement_dir in history_pairs:
        previous = live.verify_prediction(prediction_dir)
        outcomes, settlement = live.load_settlement(settlement_dir,previous)
        expected = {key(r) for r in read_csv(Path(prediction_dir)/'predictions.csv')}
        require(expected <= set(indexed(outcomes)), 'history settlement lacks its forecast population')
        pm, sm = previous['metadata'],settlement['metadata']; g = pm['target_gameweek']
        require(pm['season'] == s['season'] and g < s['target_gameweek'] and g not in used and
                live.not_after(sm['received_at'],s['bootstrap_timing']['requested_at']), 'future/duplicate/cross-season points history')
        used.add(g)
        for r in outcomes:
            v = r['target_points']
            if v is not None:
                require(type(v) is int, 'history needs explicit integer event points')
                histories.setdefault(r['element'],{})[g] = v
                observations.append({**{k:r[k] for k in KEYS},'points':v,'captured_at':sm['received_at'],
                    'prediction_identity':previous['identity_sha256'],'settlement_identity':settlement['identity_sha256'],
                    'settlement_artifacts':settlement['artifacts'],
                    'settlement_manifest_sha256':sha256_file(Path(settlement_dir)/'manifest.json')})
    fs = [{**dict(zip(KEYS,(s['season'],s['target_gameweek'],e))),
           **points_features(s['target_gameweek'],p,histories.get(e,{})),
           EXTRA:float(ps[(s['season'],s['target_gameweek'],e)]['expected_minutes'])}
          for e,p in sorted(population.items())]
    return fs,observations,snapshot,minutes


def predict(features, models):
    result = [{**{k:f[k] for k in KEYS}} for f in features]
    with threadpool_limits(limits=1):
        for n,m in models.items():
            values = m.predict(model_matrix(features,n))
            require(len(values) == len(features) and np.isfinite(values).all(), 'invalid points prediction')
            for r,v in zip(result,values): r[n] = float(v)
    return result


def evidence_inputs(root, evidence):
    snapshot = restore(root,'snapshot',evidence['snapshot'])
    minutes = restore(root,'minutes',evidence['minutes'])
    history = [(restore(root,f'prior{i}',p),restore(root,f'settled{i}',s))
               for i,(p,s) in enumerate(evidence['history'])]
    return snapshot,minutes,history


def verify_forecast(folder, model_dir):
    folder = Path(folder)
    manifest = verify_bundle(folder,'prospective-xpts-forecast'); m = manifest['metadata']
    models,state,model = load_model(model_dir)
    require(m['protocol'] == PROTOCOL and m['model_identity'] == model['identity_sha256'] and
            m['model_manifest_sha256'] == sha256_file(Path(model_dir)/'manifest.json') and
            m['model_identities'] == state['model_identities'] and m['fitting_cutoff'] == state['latest_training_settlement'], 'forecast model/protocol differs')
    evidence = json.loads((folder/'evidence.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); snap,mins,history = evidence_inputs(root,evidence)
        fs,observations,snapshot,minutes = adapter(snap,mins,history)
        s = snapshot['metadata']
        require(all(m[k] == s[k] for k in ('season','target_gameweek','deadline')) and
                m['snapshot_identity'] == snapshot['identity_sha256'] and m['minutes_identity'] == minutes['identity_sha256'], 'forecast decision identity differs')
        require(live.not_after(minutes['metadata']['prediction_timestamp'],m['started_at']) and
                live.not_after(m['started_at'],m['computed_at']) and live.not_after(m['computed_at'],m['publication_started_at']) and
                live.before(m['publication_started_at'],s['deadline']), 'forecast publication timing differs')
        age = (parse_utc(s['deadline'],'deadline')-parse_utc(s['bootstrap_timing']['requested_at'],'capture')).total_seconds()/60
        require(m['snapshot_age_minutes'] == age, 'forecast freshness differs')
        for name,table in [('features.csv',fs),('predictions.csv',predict(fs,models))]:
            write_table(root,name,table)
            require(sha256_file(root/name) == manifest['artifacts'][name], 'forecast replay differs: '+name)
        require(json.loads((folder/'history.json').read_text()) == observations, 'history provenance differs')
    return manifest


def freeze(snapshot_dir, minutes_dir, model_dir, output_dir=Path('data/prospective_xpts/forecasts'), *, history_pairs=(), clock=live.now_utc):
    live.safe_output(output_dir,snapshot_dir,minutes_dir,model_dir,*[p for pair in history_pairs for p in pair])
    started = live.stamp(clock)
    fs,observations,snapshot,minutes = adapter(snapshot_dir,minutes_dir,history_pairs)
    s = snapshot['metadata']; deadline = s['deadline']
    require(live.not_after(minutes['metadata']['prediction_timestamp'],started) and live.before(started,deadline), 'forecast must start after minutes and before deadline')
    models,state,model = load_model(model_dir)
    predictions = predict(fs,models)
    completed = live.stamp(clock)
    require(live.not_after(started,completed) and live.before(completed,deadline), 'xPts computation reached deadline')
    evidence = {'snapshot':archive(snapshot_dir),'minutes':archive(minutes_dir),
                'history':[(archive(p),archive(t)) for p,t in history_pairs]}
    publication = live.stamp(clock)
    require(live.not_after(completed,publication) and live.before(publication,deadline), 'xPts publication reached deadline')
    metadata = {'kind':'prospective-xpts-forecast','protocol':PROTOCOL,
                **{k:s[k] for k in ('season','target_gameweek','deadline')},
                'started_at':started,'computed_at':completed,'publication_started_at':publication,
                'snapshot_identity':snapshot['identity_sha256'],'minutes_identity':minutes['identity_sha256'],
                'model_identity':model['identity_sha256'],'model_identities':state['model_identities'],
                'model_manifest_sha256':sha256_file(Path(model_dir)/'manifest.json'),
                'fitting_cutoff':state['latest_training_settlement'],
                'snapshot_age_minutes':(parse_utc(deadline,'deadline')-parse_utc(s['bootstrap_timing']['requested_at'],'capture')).total_seconds()/60}
    def writer(folder):
        write_table(folder,'features.csv',fs); write_table(folder,'predictions.csv',predictions)
        atomic_write_json(folder/'evidence.json',evidence); atomic_write_json(folder/'history.json',observations)
    # Verify semantics in a private staging root before publishing, then verify
    # the actual destination and wall clock. Failed new outputs are removed.
    with tempfile.TemporaryDirectory() as tmp:
        candidate,_ = publish(Path(tmp),metadata,writer)
        verify_forecast(candidate,model_dir)
        def copy_writer(folder):
            for n in verify_bundle(candidate)['artifacts']: shutil.copyfile(candidate/n,folder/n)
        out,reused = publish(output_dir,metadata,copy_writer,publication_guard=lambda:live.require_predeadline(clock,deadline))
    try:
        verify_forecast(out,model_dir)
        final = live.stamp(clock)
        require(live.not_after(publication,final) and live.before(final,deadline), 'final publication verification reached deadline or clock reversed')
    except BaseException:
        if not reused: shutil.rmtree(out)
        raise
    return out,reused


def score(forecast_dir, settlement_dir, model_dir, output_dir=Path('data/prospective_xpts/scores')):
    live.safe_output(output_dir,forecast_dir,settlement_dir,model_dir)
    forecast = verify_forecast(forecast_dir,model_dir)
    evidence = json.loads((Path(forecast_dir)/'evidence.json').read_text())
    with tempfile.TemporaryDirectory() as tmp:
        minutes = restore(Path(tmp),'minutes',evidence['minutes'])
        outcomes,settlement = live.load_settlement(settlement_dir,live.verify_prediction(minutes))
    lookup = indexed(outcomes)
    features = read_csv(Path(forecast_dir)/'features.csv')
    predictions = {key(r):{n:float(r[n]) for n in ORDERS} for r in read_csv(Path(forecast_dir)/'predictions.csv')}
    require(set(predictions) <= set(lookup), 'settlement missing explicit player points')
    rows = [{**lookup[key(f)],'features':{n:number(f[n],FEATURE_TYPES[n]) for n in MODEL_FEATURES}} for f in features]
    groups = {'overall':rows,'established_history':[r for r in rows if r['features']['season_points_count']>=3],
              'low_history':[r for r in rows if r['features']['season_points_count']<3],
              'any_missing':[r for r in rows if any(r['features'][n] for n in MODEL_FEATURES if n.endswith('_missing'))],
              'chance_missing':[r for r in rows if r['features']['chance_of_playing_next_round'] is None]}
    groups.update({f'position:{p}':[r for r in rows if r['features']['deadline_position_id']==p] for p in range(1,5)})
    report = {'segments':{g:{n:metrics(rs,predictions,n) for n in ORDERS} for g,rs in groups.items()},
              'ranking':{n:top10(rows,predictions,n) for n in ORDERS},
              'distributions':{n:{'min':min(p[n] for p in predictions.values()),'max':max(p[n] for p in predictions.values()),
                                  'mean':mean(p[n] for p in predictions.values()),
                                  'quantiles':dict(zip(('p05','p25','p50','p75','p95'),np.quantile([p[n] for p in predictions.values()],[.05,.25,.5,.75,.95]).tolist()))} for n in ORDERS}}
    a,b = [report['segments']['overall'][n] for n in ('xpts_v2','control')]
    common = [key(r) for r in rows if r['target_points'] is not None]
    report['paired'] = {'rows':len(common),'keys_sha256':digest(common),
        'v2_minus_control':{n:a[n]-b[n] if a[n] is not None and b[n] is not None else None for n in ('rmse','mae','mean_gameweek_spearman')},
        'top10_delta':report['ranking']['xpts_v2']['mean_top10_realised_points']-report['ranking']['control']['mean_top10_realised_points'] if common else None}
    def writer(folder):
        write_table(folder,'outcomes.csv',[lookup[key(f)] for f in features])
        atomic_write_json(folder/'metrics.json',report)
    return publish(output_dir,{'kind':'prospective-xpts-score','protocol':PROTOCOL,
                   'forecast_identity':forecast['identity_sha256'],'settlement_identity':settlement['identity_sha256'],
                   'forecast_manifest_sha256':sha256_file(Path(forecast_dir)/'manifest.json'),
                   'settlement_manifest_sha256':sha256_file(Path(settlement_dir)/'manifest.json')},writer)
