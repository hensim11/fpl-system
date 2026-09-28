"""Real subprocess CLI lifecycle on the retained synthetic M5E demonstration.

Generated settlements are deterministic TEST FIXTURES, never fetched/live results.
No model or authority reader is mocked. Synthetic fixtures stay in ignored local/.
The separate real-data pending review receives no fabricated outcome or action.
"""
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from time import perf_counter

from fpl_ai import decision_review as dr
from fpl_ai.experiment_io import verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json
from scripts.verify_decision_review import audit


def lifecycle(retention, root):
    root.mkdir(parents=True,exist_ok=True)
    rm=verify_bundle(retention,'decision-retention'); r=load_json(retention/'record.json'); s=r['summary']
    if s['personal']['provenance']['kind']!='synthetic': raise ValueError('demo requires an explicitly synthetic decision')
    decision=dr.pd.resolve_one(rm['metadata']['decision']['identity'],[Path('data')],'decision')
    u=dr.pd.resolve_one(s['dependencies']['uncertainty']['identity'],[Path('data')],'uncertainty')
    um=verify_bundle(u); product=load_json(u/'uncertainty.json')
    archive=load_json(u/'projection.json')
    source=json.loads(archive['files']['source.json']); evidence=json.loads(source['files']['evidence.json'])
    bootstrap=json.loads(evidence['snapshot']['files']['bootstrap.json'])
    weeks=s['plans']['exact_1']['weeks']; actions=[]; settlements=[]; commands=[]
    roots=['--evidence-root','data','--evidence-root',str(root)]
    def run(name,argv, expected=0):
        start=perf_counter(); log=root/(name+'.log')
        # All review operations are offline. This audit hook fails any socket connect.
        code="import sys; sys.addaudithook(lambda event,args: (_ for _ in ()).throw(RuntimeError('network forbidden')) if event == 'socket.connect' else None); from fpl_ai.cli import main; sys.exit(main(sys.argv[1:]))"
        with log.open('w') as stream:
            result=subprocess.run([sys.executable,'-c',code,*argv,*roots],stdout=stream,stderr=subprocess.STDOUT)
        entry={'name':name,'argv':argv+roots,'exit_code':result.returncode,'seconds':round(perf_counter()-start,3),
               'log_sha256':sha256_file(log),'network_forbidden':True}
        commands.append(entry); print(json.dumps(entry),flush=True)
        if result.returncode!=expected: raise ValueError('CLI failure '+name+': '+log.read_text()[-2500:])
        return log.read_text()
    def output(log):
        return Path(next(line.split(' ',1)[1] for line in log.splitlines() if line.startswith(('Published ','Reused '))))
    # Real-data pending review is isolated: absolutely no manager action or fixture.
    pending=output(run('real-pending',['review','outcomes','--retention',str(retention),'--artifact-dir',str(root/'real-pending')]))
    # Confirm only GW6. Future planned actions must remain unconfirmed, even after
    # all fixture outcomes exist. This is deliberately not a full adherence demo.
    w=weeks[0]; declared=dr.live.stamp(dr.live.now_utc)
    a={'contract':dr.CONTRACT['actions'],'decision_identity':decision.name,'season':s['personal']['squad']['season'],
       'target_gameweek':w['gameweek'],'provenance':{'kind':'synthetic','source':'M5F synthetic CLI fixture; not manager account history',
       'declared_at':declared,'confirmed':True},'choice':{'selected':'exact_1','rejected':['greedy']},
       'actions':{k:copy.deepcopy(w[k]) for k in ('squad','starting_xi','captain','transfer_hit')}}
    a['actions'].update(chip='none',transfers=[{'out':o,'in':i} for position in range(1,5) for o,i in zip([e for e in w['transfers_out'] if s['population'][str(e)]['position']==position], [e for e in w['transfers_in'] if s['population'][str(e)]['position']==position])])
    assertion=root/'synthetic-assertion.json';atomic_write_json(assertion,a)
    args=['review','confirm','--retention',str(retention),'--assertion',str(assertion),'--artifact-dir',str(root/'synthetic-confirmations')]
    action=output(run('confirm',args)); actions.append(action)
    reused=output(run('confirm-reuse',args))
    if action!=reused: raise ValueError('confirmation was redated')
    for w in weeks:
        gw=w['gameweek']; b=copy.deepcopy(bootstrap)
        next(e for e in b['events'] if e['id']==gw).update(finished=True,data_checked=True)
        # Two deterministic completed fixtures; all player totals reconcile.
        fixtures=[{'id':99000+gw*10+i,'event':gw,'team_h':1,'team_a':2,'kickoff_time':None,
                   'started':True,'finished':True,'team_h_score':1,'team_a_score':0,
                   'team_h_difficulty':3,'team_a_difficulty':2} for i in (1,2)]
        elements=[]
        for row in product['rows']:
            if row['target_gameweek']!=gw: continue
            e=row['element']; points=(e+gw)%6
            elements.append({'id':e,'stats':{'minutes':180,'total_points':2*points},
                'explain':[{'fixture':f['id'],'stats':[{'identifier':'minutes','value':90,'points':points}]} for f in fixtures]})
        context=dr.mo.target_context(u,um,gw)
        stamp='2026-12-01T12:00:00Z'
        t={k:{'requested_at':stamp,'received_at':stamp} for k in ('bootstrap','fixtures','live')}
        meta=dr.mo.settlement_metadata(context,um,t)
        settlement=dr.write_products(root/'synthetic-settlements',meta,{'bootstrap.json':b,'fixtures.json':fixtures,'live.json':{'elements':elements}})[0]
        # Calls the existing validator, without claiming fixture provenance is real.
        dr.mo.load_settlement(settlement,u,um,product)
        settlements.append(settlement)
    common=['review','outcomes','--retention',str(retention),'--confirmation',str(action),'--artifact-dir',str(root/'synthetic-reviews')]
    partial=output(run('partial',common+['--settlement',str(settlements[0])]))
    fullargs=common+['--previous',str(partial)]
    for settlement in settlements: fullargs+=['--settlement',str(settlement)]
    full=output(run('complete',fullargs))
    again=output(run('complete-reuse',fullargs))
    if again!=full: raise ValueError('review is not idempotent')
    run('verify',['review','verify','--bundle',str(full)])
    replay=output(run('replay',['review','replay','--bundle',str(full),'--artifact-dir',str(root/'replay')]))
    if verify_bundle(replay)!=verify_bundle(full): raise ValueError('replay mismatch')
    audited=audit(full,[Path('data'),root/'synthetic-confirmations',root/'synthetic-settlements'])
    pending_audit=audit(pending,[Path('data')])
    result={'synthetic_not_live_actions_or_results':True,'retention':str(retention),'pending_review':str(pending),
            'synthetic_review':str(full),'synthetic_confirmation':str(action),'commands':commands,'audit':audited,'pending_audit':pending_audit}
    atomic_write_json(root/'lifecycle.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--retention',type=Path,required=True)
    p.add_argument('--root',type=Path,default=Path('local/m5f/lifecycle'));p.add_argument('--output',type=Path)
    args=p.parse_args();result=lifecycle(args.retention,args.root)
    if args.output: atomic_write_json(args.output,result)
