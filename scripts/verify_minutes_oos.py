"""Independent raw-evidence audit, annual-window checks and exact OOS replay."""
import argparse
import json
import lzma
import math
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

from fpl_ai.experiment_io import digest, verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.historical_pipeline import load_historical_build
from fpl_ai.minutes_oos import build_oos, collect_rows, load_downstream, verify_oos
from fpl_ai.modelling import read_csv
from scripts.verify_minutes import fingerprint, require


def independent(out, score, data):
    source=json.loads((out/'sources.json').read_text())
    predictions=read_csv(out/'predictions.csv')
    features=read_csv(out/'features.csv')
    audits=read_csv(out/'row_audit.csv')
    outcomes={(r['season'],int(r['target_gameweek']),int(r['element'])):r for r in read_csv(score/'outcomes.csv')}
    counts=Counter(); by_season={}
    for season, src in source['historical'].items():
        build=load_historical_build(season,src['version'],data)
        schedule=read_csv(build.processed_dir/'fixtures.csv')
        schedule_ids={int(r['fixture']):int(r['gameweek']) for r in schedule}
        totals=defaultdict(int); fact_ids=set(); fixtures=defaultdict(set)
        for fact in read_csv(build.processed_dir/'player_fixture_facts.csv'):
            if fact['position_at_fixture']=='AM':continue
            g,e,f=int(fact['gameweek']),int(fact['element']),int(fact['fixture'])
            require(schedule_ids[f]==g,'independent schedule mismatch')
            totals[g,e]+=int(fact['minutes']);fact_ids.add(f);fixtures[g,e].add(f)
        require(fact_ids==set(schedule_ids),'independent missing schedule evidence')
        counts['scheduled_fixtures']+=len(schedule_ids)
        ev=source['evidence'][season]
        raw={}; settled={}
        for field,destination in [('captures',raw),('settlements',settled)]:
            for g, record in ev[field].items():
                path=build.raw_dir/'fplcache'/record['source_path']
                require(sha256_file(path)==record['sha256'],'raw evidence checksum mismatch')
                payload=json.loads(lzma.decompress(path.read_bytes()))
                if field=='settlements':
                    event=next(e for e in payload['events'] if e['id']==int(g))
                    require(event['finished'] is True and event['data_checked'] is True,'unsettled evidence')
                destination[int(g)]={p['id']:p for p in payload['elements']}
        valid={}
        for g in sorted(set(schedule_ids.values())):
            for e,p in raw[g].items():
                if p['element_type']==5:continue
                start=0 if g==1 else p.get('minutes');end=settled[g].get(e,{}).get('minutes')
                require(type(start) is int and type(end) is int,'missing explicit minutes')
                observed=end-start
                if (season,g,e)==('2024-25',27,123):
                    require((start,end,totals[g,e])==(270,304,17),'discrepancy changed')
                    counts['unresolved_targets']+=1
                    continue
                require(observed==totals[g,e],'independent minutes discrepancy')
                valid[g,e]=observed;counts['reconciled_targets']+=1
                if (g,e) not in fixtures:counts['explicit_player_zeros']+=1
                if len(fixtures[g,e])>1:counts['double_rows']+=1
        by_player=defaultdict(dict)
        for (g,e),v in valid.items():by_player[e][g]=v
        selected=[]
        for p,f,a in zip(predictions,features,audits):
            if p['season']!=season:continue
            g,e=int(p['target_gameweek']),int(p['element']);cap=p['prediction_capture']
            history={h:v for h,v in by_player[e].items() if h<g and ev['settlements'][str(h)]['capture_time_utc']<=cap}
            recent=[history[h] for h in range(max(1,g-3),g) if h in history]
            def numeric(field): return float(f[field]) if f[field] else None
            current=raw[g][e]; previous=raw.get(g-1,{}).get(e,{})
            require(numeric('position')==current['element_type'] and
                    (f['status'] or None)==current.get('status') and
                    numeric('chance')==current.get('chance_of_playing_next_round'), 'observed identity/availability mismatch')
            require(numeric('observed_season_starts')==(current.get('starts') if g>1 else None), 'starts mismatch')
            old_status=previous.get('status'); old_chance=previous.get('chance_of_playing_next_round')
            status_change=int(current['status']!=old_status) if current.get('status') is not None and old_status is not None else None
            chance_change=current['chance_of_playing_next_round']-old_chance if current.get('chance_of_playing_next_round') is not None and old_chance is not None else None
            require(numeric('status_changed')==status_change and numeric('chance_change')==chance_change, 'availability history mismatch')
            require(numeric('appearance_rate_3')==(mean(v>0 for v in recent) if recent else None), 'appearance history mismatch')
            require(numeric('previous_minutes')==history.get(g-1),'unresolved/future history consumed')
            require(numeric('minutes_mean_3')==(mean(recent) if recent else None),'independent recent mean mismatch')
            require(numeric('minutes_count_3')==len(recent),'independent recent count mismatch')
            cumulative=raw[g][e].get('minutes') if g>1 else None
            if season=='2024-25' and e==123 and cap>='2025-03-08T06:25:00Z':
                cumulative=None;counts['masked_cumulative_rows']+=1
            require(numeric('observed_season_minutes')==cumulative,'unresolved cumulative value consumed')
            if (season,g,e) in outcomes:
                o=outcomes[season,g,e];actual=int(o['target_minutes']) if o['target_minutes'] else None
                require(actual==valid.get((g,e)),'outcome evidence mismatch')
            if season=='2021-22' and g==18:
                require(a['snapshot_age_minutes']=='207.0' and a['capture_time_utc'].endswith('12:33:00Z') and
                        p['freshness_exception']=='True','GW18 freshness lost')
                counts['gw18_freshness_rows']+=1
            if season=='2022-23' and g==7:
                require((g,e) not in valid,'blank GW7 labelled');counts['blank_gw7_rows']+=1
            counts['independent_feature_rows']+=1
            selected.append(p)
        by_season[season]={'rows':len(selected),'safe':sum(r['downstream_training_allowed']=='True' for r in selected),
                           'gameweeks':sorted({int(r['target_gameweek']) for r in selected})}
    metrics=json.loads((score/'metrics.json').read_text())
    for season in metrics:
        pairs=[(float(outcomes[r['season'],int(r['target_gameweek']),int(r['element'])]['target_minutes']),float(r['expected_minutes']))
               for r in predictions if r['season']==season and outcomes[r['season'],int(r['target_gameweek']),int(r['element'])]['target_minutes']]
        actual=metrics[season]['segments']['all']['hist_15']
        require(actual['scored']==len(pairs) and
                math.isclose(actual['mae'],mean(abs(y-p) for y,p in pairs),abs_tol=1e-12) and
                math.isclose(actual['rmse'],math.sqrt(mean((y-p)**2 for y,p in pairs)),abs_tol=1e-12), 'independent scored metrics differ')
    # Independent population reconstruction verifies all fitted row digests and boundaries.
    rows,_,_=collect_rows(data,{s:r['version'] for s,r in source['historical'].items()})
    indexed={(r['season'],r['target_gameweek'],r['element']):r for r in rows}
    training=read_csv(out/'training.csv');folds=json.loads((out/'folds.json').read_text())
    for season,state in folds.items():
        expected={k for k,r in indexed.items() if k[0]<season and r['target_minutes'] is not None}
        actual={(r['season'],int(r['target_gameweek']),int(r['element'])) for r in training if r['fold']==season}
        require(actual==expected,'expanding training population differs')
        for r in (r for r in training if r['fold']==season):
            original=indexed[r['season'],int(r['target_gameweek']),int(r['element'])]
            require(r['row_sha256']==digest(original) and r['label_available_at']==original['label_available_at'] and
                    r['capture']==original['audit']['capture_time_utc'],'fitting evidence differs from source')
    return {'counts':dict(counts),'coverage':by_season,'downstream_safe_rows':len(load_downstream(out))}


def verify(out,score,features,model,data):
    om=verify_oos(out);sm=verify_bundle(score,'minutes-oos-score')
    require(sm['metadata']['prediction_identity']==om['identity_sha256'] and
            sm['metadata']['prediction_manifest_sha256']==sha256_file(out/'manifest.json'),'score references wrong forecast')
    checked=independent(out,score,data)
    before={str(p):fingerprint(p) for p in (out,score)}
    builds={s:r['version'] for s,r in json.loads((out/'sources.json').read_text())['historical'].items()}
    with tempfile.TemporaryDirectory() as tmp:
        fresh,reused,scored,sr=build_oos(features,model,data,Path(tmp),builds=builds)
        require(not reused and not sr and verify_oos(fresh)==om and verify_bundle(scored)==sm,'fresh OOS rebuild differs')
    p,reused,s,sr=build_oos(features,model,data,out.parent,builds=builds)
    require(reused and sr and p==out and s==score,'OOS exact reuse failed')
    for p,previous in before.items():require(fingerprint(Path(p))==previous,'OOS reuse rewrote files')
    return {'prediction_manifest':om,'score_manifest':sm,'independent':checked,
            'folds':json.loads((out/'folds.json').read_text()),
            'metrics':json.loads((score/'metrics.json').read_text()),
            'checks':{'fresh_deterministic':True,'exact_reuse_preserves_hashes_mtimes':True,
                      'independent_raw_history_targets_schedule':True,'annual_expanding_populations':True,
                      'earliest_unsupported_rows_unavailable':True,'separate_outcome_bundle':True}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('oos-dir','score-dir','features-dir','model-dir','report'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--data-dir',type=Path,default=Path('data'))
    a=p.parse_args()
    atomic_write_json(a.report,verify(a.oos_dir,a.score_dir,a.features_dir,a.model_dir,a.data_dir))
    print(f'OOS independent checks, fresh rebuild and reuse passed: {a.report}')


if __name__=='__main__':main()
