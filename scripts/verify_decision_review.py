"""Independent M5F identity and scalar arithmetic audit (no production scorer)."""
import argparse
import json
import math
from datetime import datetime
from pathlib import Path

from fpl_ai.experiment_io import verify_bundle, digest
from fpl_ai.historical_io import sha256_file, atomic_write_json
from fpl_ai.transfer_optimiser import load_json


def check(ok, message):
    if not ok: raise ValueError(message)


def later_hit_boundary(rules):
    # Independent of Rules.next_free/hit and the production action validator.
    minimum = min(rules['free_transfer_cap'], rules['weekly_free_transfers'])
    def feasible(n, hit):
        return hit in {rules['hit_cost'] * max(0, n-f)
                       for f in range(minimum, rules['free_transfer_cap']+1)}
    cases = [(0,0,True),(0,1,False),(1,0,True),(1,1,False),
             (2,0,True),(2,1,True),(2,2,False)]
    probes = []
    for n, units, expected in cases:
        hit = units * rules['hit_cost']; result = feasible(n, hit)
        check(result == expected, 'later-GW boundary mismatch')
        probes.append({'transfers':n,'hit':hit,'feasible':result})
    return minimum, probes


def audit(folder, roots):
    def locate(ref):
        matches={p.parent.resolve() for root in roots for p in Path(root).rglob(ref['identity']+'/manifest.json')}
        check(len(matches)==1,'ambiguous/missing audit dependency')
        path=matches.pop(); m=verify_bundle(path)
        check(m['identity_sha256']==ref['identity'] and m['artifacts']==ref['artifacts'], 'identity/artifact mismatch')
        check(sha256_file(path/'manifest.json')==ref['manifest_file_sha256'],'manifest bytes changed')
        return path,m
    m=verify_bundle(folder,'decision-outcome-review'); r=load_json(folder/'record.json')
    retention,rm=locate(m['metadata']['retention']); retained=load_json(retention/'record.json')
    decision,dm=locate(rm['metadata']['decision']); s=load_json(decision/'summary.json')
    check(digest(retained['summary'])==digest(s),'frozen decision changed')
    check(m['metadata']['contract'].get('action_validation',{}).get('rules')==s['rules'], 'missing/incompatible hardened action contract')
    names=['no_transfer','greedy']+[f'exact_{i}' for i in range(1,s['returned_exact_paths']+1)]
    check(r['candidate_order']==retained['candidate_order']==names,'candidate order changed')
    check(len(r['candidates'])==len(names),'candidate entries missing/duplicated')
    check([v['gameweek'] for v in r['confirmed']]==sorted(map(int,retained['deadlines'])), 'confirmed target population mismatch')
    outcomes={}; settlement_ids=set()
    for ref in m['metadata']['settlements']:
        path,sm=locate(ref); gw=sm['metadata']['target_gameweek']
        check(gw not in outcomes,'duplicate target')
        check(sm['metadata']['projection']==load_json(locate(s['dependencies']['uncertainty'])[0]/'manifest.json')['metadata']['projection'],'projection mismatch')
        events=load_json(path/'bootstrap.json')['events']; event=next(e for e in events if e['id']==gw)
        check(event['finished'] is True and event['data_checked'] is True,'unsettled event')
        fixtures=[f for f in load_json(path/'fixtures.json') if f['event']==gw]
        values={}
        for e in load_json(path/'live.json')['elements']:
            score=sum(stat['points'] for f in e['explain'] for stat in f['stats'])
            check(score==e['stats']['total_points'],'explanation total mismatch')
            check(e['id'] not in values,'duplicate player')
            values[e['id']]=score if fixtures else None
        outcomes[gw]=values; settlement_ids.add(sm['identity_sha256'])
    forecasts={(v['target_gameweek'],v['element']):v['xpts'] for v in s['empirical_player_intervals']['rows']}
    def score(w,values):
        keys=list(w['starting_xi'])+[w['captain']]
        if values is None or any(values.get(e) is None for e in keys): return None
        return sum(values[e] for e in keys)-w['transfer_hit']
    def equal(a,b):
        check((a is None and b is None) or (a is not None and b is not None and math.isclose(a,b,abs_tol=1e-10,rel_tol=1e-12)),f'arithmetic mismatch {a} != {b}')
    def delta(a,b): return None if a is None or b is None else a-b
    def complete(v): return sum(v) if all(x is not None for x in v) else None
    computed={}; count=0
    for name,c in zip(names,r['candidates']):
        check(name==c['candidate'],'reordered candidates')
        check(len(c['weeks'])==len(s['plans'][name]['weeks']),'candidate horizon truncated')
        parts=[]
        for w,got in zip(s['plans'][name]['weeks'],c['weeks']):
            check(w['gameweek']==got['gameweek'],'candidate target identity mismatch')
            gw=w['gameweek']; value=score(w,outcomes.get(gw)); parts.append(value)
            forecast=score(w,{e:v for (g,e),v in forecasts.items() if g==gw})
            equal(got['points'],value); equal(got['forecast_points'],forecast)
            equal(got['settled_minus_forecast'],delta(value,forecast))
            check(got['counterfactual_supported'] is False,'unsupported counterfactual claim')
            for base in names[:2]:
                bw=next(x for x in s['plans'][base]['weeks'] if x['gameweek']==gw)
                equal(got['vs_baselines'][base],delta(value,score(bw,outcomes.get(gw))))
            count+=1
        computed[name]=complete(parts); equal(c['horizon_points'],computed[name])
    for c in r['candidates']:
        for base in names[:2]: equal(c['horizon_vs_baselines'][base],delta(computed[c['candidate']],computed[base]))
    confirmations={}; action_exclusions=set(); rules=s['rules']
    minimum, boundary = later_hit_boundary(rules)
    check('Rules.next_free(0, 0)..cap' in m['metadata']['contract']['action_validation']['hits'], 'obsolete FT lower-bound contract')
    for ref in m['metadata']['confirmations']:
        path,cm=locate(ref)
        check(cm['metadata']['retention']==m['metadata']['retention'],'action retention mismatch')
        p=load_json(path/'record.json'); a=p['assertion']
        check(a['decision_identity']==dm['identity_sha256'],'action decision mismatch')
        actions=a['actions']; moves=actions['transfers']; hit=actions['transfer_hit']
        if hit is not None:
            check(type(hit) is int and hit>=0 and hit%rules['hit_cost']==0,'invalid hit unit')
        if moves is not None:
            for pair in moves:
                check(s['population'][str(pair['out'])]['position']==s['population'][str(pair['in'])]['position'], 'cross-position asserted pair')
            if hit is not None:
                paid=hit//rules['hit_cost']; n=len(moves)
                first = a['target_gameweek']==s['personal']['squad']['target_gameweek']
                lower = 0 if first else minimum
                check(max(0,n-rules['free_transfer_cap'])<=paid<=max(0,n-lower),'impossible transfer-count/hit combination')
                if a['target_gameweek']==s['personal']['squad']['target_gameweek']:
                    check(paid==max(0,n-s['personal']['squad']['free_transfers']),'first-GW hit mismatch')
        reasons=set(retained['prospective_exclusions'])
        parse=lambda t:datetime.fromisoformat(t.replace('Z','+00:00'))
        if parse(p['attestation']['publication_checked_at'])>=parse(retained['deadlines'][str(a['target_gameweek'])]): reasons.add('confirmation recorded after target deadline')
        if a['provenance']['kind']=='synthetic': reasons.add('synthetic confirmation')
        action_exclusions.update(reasons)
        confirmations[ref['identity']]=p
    check(r['retention_exclusions']==sorted(set(retained['prospective_exclusions'])),'retention exclusions mismatch')
    check(r['confirmation_exclusions']==sorted(action_exclusions),'confirmation exclusions mismatch')
    check(r['prospective_exclusions']==sorted(action_exclusions|set(retained['prospective_exclusions'])),'headline exclusions mismatch')
    confirmed=[]
    for got in r['confirmed']:
        if 'confirmation_identity' not in got:
            equal(got['points'],None); confirmed.append(None); continue
        p=confirmations[got['confirmation_identity']]; a=p['assertion']['actions']
        required=('squad','starting_xi','captain','transfer_hit','chip')
        missing=any(a[k] is None for k in required)
        value=None if missing else score(a,outcomes.get(got['gameweek']))
        equal(got['points'],value); confirmed.append(value)
    equal(r['confirmed_horizon_points'],complete(confirmed))
    for base in names[:2]: equal(r['confirmed_horizon_vs_baselines'][base],delta(complete(confirmed),computed[base]))
    check(r['pending_targets']==sorted(int(g) for g in retained['deadlines'] if int(g) not in outcomes),'pending targets mismatch')
    check(r['decision_value_claim'] is False,'unsupported decision value claim')
    return {'review_identity':m['identity_sha256'],'decision_identity':dm['identity_sha256'],
            'candidate_count':len(names),'candidate_gameweeks_checked':count,
            'settled_targets':sorted(outcomes),'pending_targets':r['pending_targets'],
            'confirmed_records_checked':len(confirmations),'fixed_lineup_arithmetic_and_identities_pass':True,
            'action_hit_pair_and_headline_checks_pass':True,
            'minimum_later_free_transfers':minimum,'later_hit_boundary':boundary}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--review',type=Path,required=True)
    p.add_argument('--evidence-root',type=Path,action='append',default=[]);p.add_argument('--output',type=Path)
    a=p.parse_args(); result=audit(a.review,a.evidence_root or [Path('data')])
    if a.output: atomic_write_json(a.output,result)
    print(json.dumps(result,indent=2))
