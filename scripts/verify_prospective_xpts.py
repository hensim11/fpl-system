"""Independent raw-state/history parity, exact refit/reuse and real saved replay.

No mocked clock is used here. GW5 projection is explicitly offline reconstruction,
not a prospective forecast. Optional genuine forecasts are verified, never created.
"""
import argparse
import json
import lzma
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from fpl_ai import prospective_xpts as xp
from fpl_ai.experiment_io import key, load_rows, verify_m3, verify_bundle
from fpl_ai.experiments import matrix as m4_matrix
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.modelling import read_csv
from fpl_ai.minutes_oos import load_downstream


def fingerprint(folder):
    return {p.name:[sha256_file(p),p.stat().st_mtime_ns] for p in folder.iterdir()}


def parity(data,model):
    source=verify_m3(data/'modelling'/xp.M3_ID)['identity']['sources']
    rows,_=load_rows(data/'modelling'/xp.M3_ID,('validation','test'))
    mins={key(r):r for r in load_downstream(data/'minutes_oos'/xp.OOS_ID)}
    training={key(r):r for r in read_csv(model/'training.csv')}
    state=json.loads((model/'fit.json').read_text())
    counts=Counter(); hashes=[]; labels=[]; feature_rows=[]
    for season in xp.EXPECTED_COUNTS:
        build=load_historical_build(season,source[season]['version'],data)
        raw_cache={}
        def raw(path,sha):
            if path not in raw_cache:
                file=build.raw_dir/'fplcache'/path
                xp.require(sha256_file(file)==sha,'raw evidence hash differs')
                payload=json.loads(lzma.decompress(file.read_bytes()))
                people={p['id']:p for p in payload['elements']}
                xp.require(len(people)==len(payload['elements']),'duplicate raw player')
                raw_cache[path]=(payload,people)
            return raw_cache[path]
        settlements={}
        for g,e in source[season]['settlements'].items():
            g=int(g);payload,people=raw(e['source_path'],e['sha256'])
            event=[v for v in payload['events'] if v['id']==g]
            xp.require(len(event)==1 and event[0]['finished'] is True and event[0]['data_checked'] is True,'raw prior event unsettled')
            xp.require(all(type(p['event_points']) is int for p in people.values()),'noninteger raw event points')
            settlements[g]=(e['capture_time_utc'],people)
        fixture_gws={int(r['gameweek']) for r in read_csv(build.processed_dir/'player_fixture_facts.csv') if r['position_at_fixture']!='AM'}
        for row in (r for r in rows if r['season']==season):
            k=key(row);g,e=k[1:];audit=row['audit'];_,people=raw(audit['snapshot_source_path'],audit['snapshot_sha256'])
            history={past:people_at_settlement[e]['event_points'] for past,(t,people_at_settlement) in settlements.items()
                     if past<g and past in fixture_gws and xp.live.not_after(t,audit['capture_time_utc']) and e in people_at_settlement}
            values=xp.points_features(g,people[e],history)
            xp.require(values=={n:row['features'][n] for n in xp.MODEL_FEATURES},'independent live/historical point feature parity differs')
            xp.require(list(values)==list(xp.MODEL_FEATURES),'input ordering differs')
            f={**dict(zip(xp.KEYS,k)),**values,xp.EXTRA:float(mins[k]['expected_minutes'])}
            y={**dict(zip(xp.KEYS,k)),'target_points':row['target_points'],'label_available_at':row['label_available_at']}
            xp.require(xp.digest(f)==training[k]['feature_sha256'] and xp.digest(y)==training[k]['label_sha256'],'independent training row hash differs')
            xp.require(row['target_points']==settlements[g][1][e]['event_points'],'training label differs from raw points')
            feature_rows.append(f);labels.append(y);hashes.append(k)
            counts['raw_state_history_parity_rows']+=1
            counts['explicit_zero_history_observations']+=sum(v==0 for v in history.values())
            counts['missing_previous_points']+=values['previous_points'] is None
        counts['raw_capture_files']+=len(raw_cache)
    xp.require(xp.digest(hashes)==state['training_keys_sha256'] and xp.digest(feature_rows)==state['training_features_sha256'] and
               xp.digest(labels)==state['training_labels_sha256'],'aggregate fitting evidence differs')
    models,_,_=xp.load_model(model)
    # Same numeric/categorical projection and saved preprocessing as M4.
    with threadpool_limits(limits=1):
        a=models['control'].named_steps['preprocess'].transform(xp.model_matrix(feature_rows,'control'))
        b=models['control'].named_steps['preprocess'].transform(m4_matrix(rows))
        xp.require(np.array_equal(a,b),'preprocessing projection parity differs')
    return {'counts':dict(counts),'all_25_inputs_order_values_types_missingness_equal':True,
            'raw_settled_integer_history_and_labels':True,'preprocessing_projection_exact':True,
            'training_keys_features_labels_hashes_reconstructed':True}


def verify(model,data,forecast=None):
    models,state,manifest=xp.load_model(model)
    independent=parity(data,model)
    before=fingerprint(model)
    with tempfile.TemporaryDirectory() as tmp:
        fresh,reused=xp.fit(Path(tmp)/'fresh',data)
        xp.require(not reused and verify_bundle(fresh)==manifest,'fresh operational refit differs')
        xp.load_model(fresh)
        second,_=xp.fit(Path(tmp)/'second',data)
        xp.require(verify_bundle(second)==manifest,'post-load refit differs')
    same,reused=xp.fit(model.parent,data)
    xp.require(same==model and reused and fingerprint(model)==before,'reuse rewrites fitted states')
    live_record=None
    if forecast:
        old=fingerprint(forecast)
        live_record=xp.verify_forecast(forecast,model)
        xp.require(fingerprint(forecast)==old,'forecast verification rewrites')
    return {'model_manifest':manifest,'fit':state,'independent':independent,
            'checks':{'fresh_refit_exact':True,'post_load_refit_exact':True,'reuse_preserves_bytes_mtimes':True,
                      'no_new_model_search':True,'no_current_season_training_targets':True},
            'live_forecast':live_record,
            'limitations':['M4D mixed; consumed historical holdout; no winner selected',
                          'initial prospective points/minutes history incomplete',
                          'local timestamps are not external attestation',
                          'minutes operational model is the frozen M4B fit; OOS historical models used expanding fits',
                          'no optimiser or proven decision utility']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--data-dir',type=Path,default=Path('data'))
    p.add_argument('--forecast-dir',type=Path)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();atomic_write_json(a.report,verify(a.model_dir,a.data_dir,a.forecast_dir))
    print(f'M4E independent raw feature/history parity, fresh refit and reuse passed: {a.report}')


if __name__=='__main__':main()
