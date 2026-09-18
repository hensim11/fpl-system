"""Independent M4D join/point-evidence audit, exact replay and corruption probes."""
import argparse
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from unittest.mock import patch

from scipy.stats import spearmanr

from fpl_ai.experiment_io import key, publish, verify_bundle
from fpl_ai.features import number
from fpl_ai.modelling_contract import FEATURE_TYPES
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.minutes_oos import load_downstream
from fpl_ai.modelling import load_season, read_csv
from fpl_ai.xpts_v2 import (EXTRA, EXPECTED_COUNTS, HOLDOUT_ID, M3_ID, MODEL_FEATURES,
                            OOS_ID, SEASONS, STATE_FIELDS, run, upstream, verify, require)
from scripts.verify_minutes import fingerprint


def independent(out, score, data):
    """Rebuild points from historical evidence; independently zip neither table."""
    m3 = data/'modelling'/M3_ID; oos = data/'minutes_oos'/OOS_ID
    upstreams = json.loads((out/'upstream.json').read_text())
    sources = upstreams['m3']['identity']['sources']
    fs = {key(r):r for r in read_csv(out/'features.csv')}
    labels = {key(r):r for r in read_csv(score/'outcomes.csv')}
    audit = {key(r):r for r in read_csv(out/'row_audit.csv')}
    points = {key(r):r for r in read_csv(m3/'features.csv')}
    minutes = {key(r):r for r in load_downstream(oos)}
    ma = {key(r):r for r in read_csv(oos/'row_audit.csv')}
    require(set(fs)==set(labels)==set(audit)==set(minutes), 'independent join population mismatch')
    require(dict(Counter(k[0] for k in fs))==EXPECTED_COUNTS,'independent OOS counts changed')
    require(all(set(r)==set(('season','target_gameweek','element')+MODEL_FEATURES+(EXTRA,)) for r in fs.values()),
            'independent feature allowlist failure')
    counts=Counter(); ferguson={}
    for season in SEASONS:
        rebuilt, source = load_season(season,sources[season]['version'],data)
        # load_season reopens pinned settlement bytes and validates finished/data_checked,
        # canonical point totals and explicit player zeros through the frozen M3 contract.
        require(source['source_identity_sha256']==sources[season]['source_identity_sha256'] and
                source['build_identity_sha256']==sources[season]['build_identity_sha256'], 'independent source mismatch')
        for r in rebuilt:
            k=key(r);p=minutes[k];f=fs[k];y=labels[k];a=audit[k]
            require(all(a[field]==r['audit'][field]==ma[k][field] or
                        str(r['audit'][field])==a[field]==ma[k][field] for field in STATE_FIELDS), 'raw decision state differs')
            require(all(number(f[field],FEATURE_TYPES[field])==number(points[k][field],FEATURE_TYPES[field])
                        for field in MODEL_FEATURES),'point feature changed')
            require(float(f[EXTRA])==float(p['expected_minutes']), 'minutes feature differs')
            require((int(y['target_points']) if y['target_points'] else None)==r['target_points'] and
                    y['label_available_at']==(r['label_available_at'] or ''),'independent points evidence differs')
            require(a['eligible']==str(r['target_points'] is not None),'independent eligibility differs')
            counts['raw_reconstructed_points_rows']+=1
            if r['target_points'] is not None:counts['independent_available_points']+=1
            if k==('2024-25',27,123):
                ferguson={'key':list(k),'expected_minutes':float(p['expected_minutes']),
                          'target_points':r['target_points'],'points_label_available_at':r['label_available_at'],
                          'eligible':a['eligible'],'prediction_capture':p['prediction_capture'],
                          'minutes_outcome_required':False}
    preds={key(r):r for r in read_csv(out/'predictions.csv')}
    require(set(preds)=={k for k,a in audit.items() if k[0]=='2025-26' and a['eligible']=='True'},
            'independent same-row evaluation failure')
    report=json.loads((score/'metrics.json').read_text()); checks={}
    for name in ('control','xpts_v2','frozen_m4'):
        pairs=[(int(labels[k]['target_points']),float(p[name])) for k,p in preds.items()]
        rms=math.sqrt(sum((a-b)**2 for a,b in pairs)/len(pairs));mae=mean(abs(a-b) for a,b in pairs)
        groups=defaultdict(list)
        for k,p in preds.items():groups[k[:2]].append((k[2],int(labels[k]['target_points']),float(p[name])))
        rank=[];top=[]
        for group in groups.values():
            rank.append(float(spearmanr([r[1] for r in group],[r[2] for r in group]).statistic))
            chosen=sorted(group,key=lambda r:(-r[2],r[0]))[:10];top.append(mean(r[1] for r in chosen))
        actual=report['segments']['overall'][name]
        for metric,value in [('rmse',rms),('mae',mae),('mean_gameweek_spearman',mean(rank))]:
            require(math.isclose(actual[metric],value,abs_tol=1e-12), 'independent metric differs')
        require(math.isclose(report['ranking'][name]['mean_top10_realised_points'],mean(top),abs_tol=1e-12),
                'independent top10 differs')
        checks[name]={'rows':len(pairs),'rmse':rms,'mae':mae,'spearman':mean(rank),'top10':mean(top)}
    return {'counts':dict(counts),'join_counts':EXPECTED_COUNTS,'ferguson':ferguson,'independent_metrics':checks,
            'all_features_exact_m3_plus_oos':True,'raw_points_evidence_reconstructed':True}


def rejection_checks(out, score, data):
    results={}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for kind in ('corrupt','missing','extra'):
            target=root/kind/out.name;shutil.copytree(out,target)
            if kind=='corrupt':(target/'features.csv').write_text('corrupt')
            elif kind=='missing':(target/'features.csv').unlink()
            else:(target/'unexpected.csv').write_text('extra')
            try:verify_bundle(target,'xpts-v2')
            except (ValueError,FileNotFoundError):results[kind]=True
            else:raise ValueError(f'{kind} bundle accepted')
        for root_name in ('minutes','playing_time','prospective_predictions','prospective_snapshots'):
            candidates=list((data/root_name).glob('*/manifest.json'))
            require(bool(candidates),f'no family fixture for {root_name}')
            try:upstream(data/'modelling'/M3_ID,candidates[0].parent,data/'experiment_holdouts'/HOLDOUT_ID)
            except ValueError:results[root_name+'_rejected']=True
            else:raise ValueError('incompatible minutes family accepted')
        for family,candidate in [('minutes_oos_score',next((data/'minutes_oos/scores').glob('*/manifest.json')).parent),
                                 ('xpts_score',score)]:
            try:upstream(data/'modelling'/M3_ID,candidate,data/'experiment_holdouts'/HOLDOUT_ID)
            except ValueError:results[family+'_rejected']=True
            else:raise ValueError('outcome bundle accepted as feature source')
        original=data/'minutes_oos'/OOS_ID
        for kind in ('corrupt','missing','extra'):
            target=root/('oos_'+kind)/OOS_ID;shutil.copytree(original,target)
            if kind=='corrupt':(target/'predictions.csv').write_text('corrupt')
            elif kind=='missing':(target/'predictions.csv').unlink()
            else:(target/'unexpected.csv').write_text('extra')
            try:upstream(data/'modelling'/M3_ID,target,data/'experiment_holdouts'/HOLDOUT_ID)
            except (ValueError,FileNotFoundError):results['oos_'+kind]=True
            else:raise ValueError('corrupt OOS accepted')
        # Rehash a structurally complete but incompatible OOS protocol: rejection
        # must not rely only on detecting accidental byte corruption.
        metadata=json.loads(json.dumps(verify_bundle(original)['metadata']))
        metadata['protocol']['version']='incompatible-contract'
        def writer(folder):
            for p in original.iterdir():
                if p.name!='manifest.json':shutil.copyfile(p,folder/p.name)
            atomic_write_json(folder/'protocol.json',metadata['protocol'])
        incompatible,_=publish(root/'incompatible',metadata,writer)
        try:load_downstream(incompatible)
        except ValueError:results['rehashed_incompatible_oos_contract']=True
        else:raise ValueError('incompatible OOS contract accepted')
    return results


def verify_all(out,score,data):
    m3=data/'modelling'/M3_ID;oos=data/'minutes_oos'/OOS_ID;holdout=data/'experiment_holdouts'/HOLDOUT_ID
    manifests=verify(out,score,m3,oos,holdout)
    checked=independent(out,score,data)
    rejections=rejection_checks(out,score,data)
    before={str(p):fingerprint(p) for p in (out,score)}
    with tempfile.TemporaryDirectory() as tmp:
        fresh,reused,scored,sr=run(m3,oos,holdout,Path(tmp)/'fresh')
        rebuilt=verify(fresh,scored,m3,oos,holdout)
        differences=[{k:v for k,v in new['artifacts'].items() if old['artifacts'].get(k)!=v}
                     for old,new in zip(manifests,rebuilt)]
        require(not reused and not sr and rebuilt==manifests,f'fresh M4D rebuild differs: {differences}')
        # A real workflow mutation proves all evaluation targets cannot influence fitted
        # preprocessing/model state or any feature or prediction bytes.
        from fpl_ai.xpts_v2 import load_rows as original_loader
        def changed_labels(folder,splits):
            rows,base=original_loader(folder,splits)
            for r in rows:
                if r['season']=='2025-26' and r['target_points'] is not None:r['target_points']+=1000
            return rows,base
        with patch('fpl_ai.xpts_v2.load_rows',side_effect=changed_labels):
            altered,_,altered_score,_=run(m3,oos,holdout,Path(tmp)/'mutated')
        require(verify_bundle(altered)==manifests[0] and altered_score.name!=score.name,
                'evaluation labels leaked into fitted state or predictions')
    same,reused,scored,sr=run(m3,oos,holdout,out.parent)
    require(same==out and scored==score and reused and sr,'M4D deterministic reuse failed')
    for p,previous in before.items():require(fingerprint(Path(p))==previous,'M4D reuse rewrites')
    return {'prediction_manifest':manifests[0],'score_manifest':manifests[1],
            'fit':json.loads((out/'fit.json').read_text()),'metrics':json.loads((score/'metrics.json').read_text()),
            'independent':checked,'rejections':rejections,
            'checks':{'fresh_deterministic':True,'same_root_reuse_bytes_mtimes':True,
                      'evaluation_target_mutation_leaves_prediction_bundle_identical':True,
                      'independent_raw_point_evidence_and_join':True,'saved_model_prediction_metric_replay':True}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('prediction-dir','score-dir','report'):parser.add_argument('--'+field,type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    args=parser.parse_args()
    atomic_write_json(args.report,verify_all(args.prediction_dir,args.score_dir,args.data_dir))
    print(f'M4D independent evidence, fresh/reuse and mutation checks passed: {args.report}')


if __name__=='__main__':main()
