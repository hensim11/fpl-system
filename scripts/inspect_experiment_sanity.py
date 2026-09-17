"""Trace predeclared extreme/disagreement diagnostic examples to pinned snapshots."""
import argparse
import json
import lzma
from pathlib import Path

from fpl_ai.experiment_io import key, load_rows, verify_bundle, verify_m3
from fpl_ai.features import number
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling_contract import STATE_FIELDS

RAW_FIELDS = {'deadline_team_id':'team','deadline_position_id':'element_type','price':'now_cost',
              'selected_by_percent':'selected_by_percent','transfers_in_event':'transfers_in_event',
              'transfers_out_event':'transfers_out_event','status':'status',
              'chance_of_playing_next_round':'chance_of_playing_next_round'}


def trace(m3, frozen, holdout, data_dir):
    upstream=verify_m3(m3)
    cases=set()
    for folder in (frozen,holdout):
        verify_bundle(folder)
        diagnostic=json.loads((folder/'diagnostics.json').read_text())
        for model in diagnostic['models'].values():
            for group in ('highest','lowest','largest_scoring_rate_disagreements'):
                cases.update(tuple(e['key']) for e in model[group][:2])
    rows,_=load_rows(m3,('validation','test'))
    by_key={key(r):r for r in rows}
    traces=[]
    for k in sorted(cases):
        r=by_key[k]; audit=r['audit']; source=upstream['identity']['sources'][r['season']]
        raw_dir=Path(data_dir)/'historical/raw'/r['season']/source['version'].split('-build-')[0]
        path=raw_dir/'fplcache'/audit['snapshot_source_path']
        if sha256_file(path)!=audit['snapshot_sha256']:
            raise ValueError('anomaly snapshot hash mismatch')
        payload=json.loads(lzma.decompress(path.read_bytes()))
        player=[p for p in payload['elements'] if p['id']==r['element']]
        if len(player)!=1:
            raise ValueError('anomaly player missing/duplicated in raw snapshot')
        raw=player[0]
        state={f:number(raw.get(RAW_FIELDS[f]),typ) for f,typ in STATE_FIELDS.items()}
        if state!={f:r['features'][f] for f in STATE_FIELDS}:
            raise ValueError('anomaly state differs from accepted raw snapshot')
        if audit['capture_time_utc']>=audit['deadline_time_utc']:
            raise ValueError('anomaly captured too late')
        traces.append({'key':list(k),'observed_name':raw.get('web_name'),
                       'snapshot_path':audit['snapshot_source_path'],'snapshot_sha256':audit['snapshot_sha256'],
                       'capture':audit['capture_time_utc'],'deadline':audit['deadline_time_utc'],
                       'state':state,'target':r['target_points'],'all_state_fields_match_raw':True})
    return {'upstream_identity':upstream['identity_sha256'],'rule':'Top two highs, lows and scoring-rate disagreements for each validation model and frozen test winner',
            'traces':traces,'checked':len(traces)}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('m3-dir','frozen-dir','holdout-dir','report'):
        parser.add_argument('--'+n,type=Path,required=True)
    parser.add_argument('--data-dir',type=Path,default=Path('data'))
    args=parser.parse_args()
    result=trace(args.m3_dir,args.frozen_dir,args.holdout_dir,args.data_dir)
    atomic_write_json(args.report,result)
    print(f"Verified {result['checked']} extreme/disagreement raw snapshot traces")
