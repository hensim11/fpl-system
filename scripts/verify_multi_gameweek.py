"""Offline M5B saved-model replay, independent arithmetic and fresh/reuse evidence."""
import argparse
import itertools
import json
import math
import pickle
import shutil
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import mean

import numpy as np
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits

from fpl_ai import multi_projection as mp
from fpl_ai.experiment_io import key, load_rows, verify_bundle, verify_m3, digest, publish
from fpl_ai.experiments import matrix
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv
from fpl_ai.prospective_xpts import M3_ID
from fpl_ai.transfer_path import build_plan
from scripts.verify_transfer_optimiser import MODEL, SQUAD

MODELS=Path('data/multi_projection/models/b0e9cf270c6524278ddb6c288c393aef580159c2a36a02b9a01e81cfadf4235b')
SCORE=Path('data/multi_projection/scores/15330198b278c5b82eca1b756d46236ac998a573ce755022957c89d0c7394c4f')
M3=Path('data/modelling')/M3_ID


def check(value,message):
    if not value: raise ValueError(message)


def fingerprint(folder):
    return {str(p.relative_to(folder)):[sha256_file(p),p.stat().st_mtime_ns] for p in sorted(folder.rglob('*')) if p.is_file()}


def audit_history():
    verify_m3(M3); manifest=verify_bundle(MODELS,'multi-horizon-model'); verify_bundle(SCORE,'multi-horizon-score')
    rows,_=load_rows(M3,('train','validation','test'))
    lookup={key(r):r for r in rows}
    saved=read_csv(MODELS/'predictions.csv'); outcomes=read_csv(SCORE/'outcomes.csv')
    metrics=json.loads((SCORE/'metrics.json').read_text())
    fits=json.loads((MODELS/'fit.json').read_text())
    indexed={(int(r['horizon']),key(r)):r for r in saved}
    labels={(int(r['horizon']),key(r)):r for r in outcomes}
    check(len(indexed)==len(saved)==len(labels)==len(outcomes),'unique matching historical products')
    expected={(h,key(r)) for h in range(5) for r in rows if r['season']=='2025-26' and r['target_gameweek']+h<=38}
    check(set(indexed)==set(labels)==expected,'full horizon evaluation population')
    coverage={}
    for h in range(5):
        eligible=[r for r in rows if r['target_gameweek']+h<=38]
        future=lambda r: lookup.get((r['season'],r['target_gameweek']+h,r['element']))
        selected=[r for r in eligible if future(r) is not None and future(r)['target_points'] is not None]
        production=fits[str(h)]['production']; historical=fits[str(h)]['historical']
        train=[r for r in selected if r['season']!='2025-26']
        evaluation=[r for r in eligible if r['season']=='2025-26']
        for group,fit in ((selected,production),(train,historical)):
            check(len(group)==fit['rows'] and dict(Counter(r['season'] for r in group))==fit['counts'],'fit population')
            check(digest([key(r) for r in group])==fit['keys_sha256'],'fit key identity')
            check(digest([r['features'] for r in group])==fit['features_sha256'],'as-of feature identity')
            check(digest([(r['target_gameweek']+h,future(r)['target_points'],future(r)['label_available_at']) for r in group])==fit['labels_sha256'],'future outcomes identity')
            check(max(future(r)['label_available_at'] for r in group)==fit['latest_settlement']<fit['cutoff'],'fit chronology')
        pipeline=pickle.loads((MODELS/f'eval_h{h}.pickle').read_bytes())
        with threadpool_limits(limits=1): values=pipeline.predict(matrix(evaluation))
        for r,v in zip(evaluation,values):
            p=indexed[h,key(r)]; y=labels[h,key(r)]; f=future(r)
            check(float(p['direct'])==float(v),'saved-model prediction replay')
            check(int(y['outcome_gameweek'])==r['target_gameweek']+h,'outcome GW')
            check((None if not y['target_points'] else int(y['target_points']))==(f['target_points'] if f else None),'independent label join')
            check(y['label_available_at']==(f['label_available_at'] if f and f['target_points'] is not None else ''),'settlement evidence')
        for name in ('direct','position_mean','recent_points'):
            pairs=[]; groups=defaultdict(list)
            for r in evaluation:
                f=future(r)
                if f and f['target_points'] is not None:
                    pair=(f['target_points'],float(indexed[h,key(r)][name]))
                    pairs.append(pair); groups[r['target_gameweek']].append(pair)
            report=metrics['horizons'][str(h)]['segments']['overall'][name]
            rmse=math.sqrt(mean((a-b)**2 for a,b in pairs)); mae=mean(abs(a-b) for a,b in pairs)
            ranks=[float(spearmanr([a for a,b in vs],[b for a,b in vs]).statistic) for vs in groups.values()]
            ranks=[v for v in ranks if math.isfinite(v)]
            check(abs(rmse-report['rmse'])<1e-14 and abs(mae-report['mae'])<1e-14,'independent RMSE/MAE')
            check(abs(mean(ranks)-report['mean_gameweek_spearman'])<1e-14,'independent within-GW Spearman')
        coverage[str(h)]={'evaluation_population':len(evaluation),'production_labelled':len(selected),'historical_fit':len(train),
                          'excluded_missing_labels':len(eligible)-len(selected), 'horizon_label_join_verified':True}
    return {'model_identity':manifest['identity_sha256'],'coverage':coverage,'metrics':metrics,
            'saved_prediction_replay_exact':True,'independent_fit_keys_features_labels_chronology':True,
            'independent_overall_metrics_match':True,'no_future_features':True,
            'h0_not_M4E_parity':True,'consumed_historical_evaluation':True}


def audit_plan(folder,projections):
    manifest=verify_bundle(folder,'multi-gw-transfer-path')
    data=json.loads((folder/'decision.json').read_text()); state=json.loads((folder/'squad.json').read_text())
    ps=defaultdict(dict)
    for r in projections: ps[r['horizon']][r['element']]=r
    seen=set(); lineup_cache={}
    for plan in [data['baseline'],data['greedy'],*data['plans']]:
        held={p['element']:p['selling_price'] for p in state['players']}; bank=state['bank']; free=state['free_transfers']; total=Fraction()
        hit_total=0; transfer_total=0
        for t,w in enumerate(plan['weeks']):
            squad=set(w['squad']); players=ps[t]
            check(len(squad)==15 and Counter(players[e]['position'] for e in squad)=={1:2,2:5,3:5,4:3},'squad positions')
            check(max(Counter(players[e]['team'] for e in squad).values())<=3,'club limit')
            incoming,outgoing=squad-held.keys(),held.keys()-squad
            check(sorted(incoming)==w['transfers_in'] and sorted(outgoing)==w['transfers_out'],'transfer set')
            check(all(players[e]['can_select'] is True for e in incoming),'transfer eligibility')
            bank+=sum(held[e] for e in outgoing)-sum(players[e]['purchase_price'] for e in incoming)
            count=len(incoming); hit=4*max(0,count-free)
            check(bank>=0 and bank==w['resulting_bank'],'integer bank evolution')
            check(w['free_transfers_before']==free and w['transfer_hit']==hit,'FT/hit accounting')
            free=min(5,max(0,free-count)+1)
            check(free==w['next_free_transfers'],'rolling FT cap')
            cache_key=(t,tuple(sorted(squad)))
            if cache_key not in lineup_cache:
                options=[]
                for xi in itertools.combinations(sorted(squad),11):
                    counts=Counter(players[e]['position'] for e in xi)
                    if not(counts[1]==1 and 3<=counts[2]<=5 and 2<=counts[3]<=5 and 1<=counts[4]<=3): continue
                    cap=min(xi,key=lambda e:(-players[e]['xpts'],e))
                    score=sum((Fraction(players[e]['xpts']) for e in xi),Fraction())+Fraction(players[cap]['xpts'])
                    options.append((-score,xi,cap))
                lineup_cache[cache_key]=min(options)
            neg,xi,cap=lineup_cache[cache_key]
            check(list(xi)==w['starting_xi'] and cap==w['captain'],'independent exhaustive XI/captain')
            total-=neg+hit; hit_total+=hit; transfer_total+=count
            check(float(total)==w['cumulative_points'],'cumulative points')
            held={e:held.get(e,players[e]['purchase_price']) for e in squad}
        check(plan['total_points']==float(total) and hit_total==plan['total_hit_cost'] and transfer_total==plan['transfer_count'],'path totals')
    for p in data['plans']:
        signature=tuple(tuple(w['squad']) for w in p['weeks'])
        check(signature not in seen,'duplicate ranked path'); seen.add(signature)
    return {'decision_identity':manifest['identity_sha256'],'independent_XI_economics_FT_and_totals':True,
            'baseline':data['baseline'],'greedy':data['greedy'],'plans':data['plans'],'synthetic_squad_not_user_team':True}


def audit_corruption(folder):
    original=verify_bundle(folder,'multi-horizon-forecast')
    rejected=[]
    with tempfile.TemporaryDirectory() as tmp:
        for mutation in ('points','population','model_identity','snapshot_identity','horizon','timing','h0_comparison'):
            meta=dict(original['metadata'])
            if mutation in ('model_identity','snapshot_identity'): meta[mutation]='0'*64
            if mutation=='horizon': meta['horizon']=4
            if mutation=='timing': meta['computed_at']=meta['deadline']
            def writer(out):
                for name in original['artifacts']: shutil.copyfile(folder/name,out/name)
                if mutation in ('points','population'):
                    rows=json.loads((out/'projections.json').read_text())
                    if mutation=='points': rows[0]['xpts']+=1
                    else: rows.pop()
                    atomic_write_json(out/'projections.json',rows)
                if mutation=='h0_comparison': atomic_write_json(out/'h0_comparison.json',{})
            changed,_=publish(Path(tmp)/mutation,meta,writer)
            try: mp.verify_projection(changed,MODELS,MODEL)
            except ValueError: rejected.append(mutation)
            else: raise ValueError('semantic corruption accepted: '+mutation)
        try: mp.verify_projection(folder,MODEL,MODEL)
        except ValueError: rejected.append('wrong_model_bundle')
        else: raise ValueError('wrong model accepted')
    return rejected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--projections-dir',type=Path,required=True)
    parser.add_argument('--plan-dir',type=Path,required=True)
    parser.add_argument('--rebuild',action='store_true')
    parser.add_argument('--report',type=Path,default=Path('docs/M5B_VERIFICATION.json'))
    args=parser.parse_args()
    historical=audit_history()
    rows,forecast=mp.verify_projection(args.projections_dir,MODELS,MODEL)
    rejected=audit_corruption(args.projections_dir)
    plan=audit_plan(args.plan_dir,rows)
    rebuild={}
    if args.rebuild:
        configuration=verify_bundle(args.plan_dir,'multi-gw-transfer-path')['metadata']
        plan_options={k:configuration[k] for k in ('horizon','max_transfers','top_n')}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            fresh,reused,score,sr=mp.build_models(M3,root/'models')
            check(not reused and not sr and fresh.name==MODELS.name and score.name==SCORE.name,'fresh model/score identity')
            before=fingerprint(root)
            again,used,again_score,score_used=mp.build_models(M3,root/'models')
            check(used and score_used and before==fingerprint(root),'model reuse bytes/mtime')
            # Offline projection replay retains original runtime attestation.
            archived=mp.xp.archive(args.projections_dir)
            restored=mp.xp.restore(root,'forecast',archived)
            replay,_=mp.verify_projection(restored,fresh,MODEL)
            check(replay==rows,'fresh model projection replay')
            new,used=build_plan(restored,fresh,MODEL,SQUAD,root/'plans',**plan_options)
            check(not used and new.name==args.plan_dir.name,'fresh path identity')
            before_plan=fingerprint(root/'plans')
            again,used=build_plan(restored,fresh,MODEL,SQUAD,root/'plans',**plan_options)
            check(used and before_plan==fingerprint(root/'plans'),'path reuse bytes/mtime')
        rebuild={'fresh_models_scores_and_paths_identical':True,'reuse_byte_and_mtime_preserved':True,
                 'offline_projection_replay_identical':True}
    atomic_write_json(args.report,{'historical':historical,'forecast':forecast,'plan':plan,'rebuild':rebuild,
                                  'semantic_corruptions_rejected':rejected})
    print(args.report,flush=True)


if __name__=='__main__': main()
