"""Synthetic M5F boundary tests; real publisher, exact planner and M5C validator."""
import io
from contextlib import redirect_stdout
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fpl_ai import decision_review as dr, personal_decision as pd
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json
from tests import test_personal_decision as pd_tests
from tests.test_personal_decision import IMPORTED
from tests.test_prospective import clock, fingerprint, Client


def tamper(folder, root, change):
    m = verify_bundle(folder)
    products = {n: load_json(folder/n) if n.endswith('.json') else (folder/n).read_text() for n in m['artifacts']}
    change(m['metadata'], products)
    return dr.write_products(root, m['metadata'], products)[0]


class ReviewTests(unittest.TestCase):
    def setUp(self):
        pd_tests.WorkflowTests.setUp(self)
        # Replace only synthetic upstream uncertainty boundary with a complete M5C
        # target archive. Settlement readers and authority checks are never mocked.
        self.bootstrap = Client().bootstrap
        self.bootstrap['events'] += [{'id': g, 'deadline_time': f'2026-09-{24+(g-6)*2}T10:00:00Z', 'finished': False, 'data_checked': False} for g in (6,7)]
        self.bootstrap['elements'] = [{'id':e} for e in range(1,18)]
        evidence = {'snapshot': {'files': {'bootstrap.json':json.dumps(self.bootstrap)}}}
        archive = {'files': {'source.json':json.dumps({'files':{'evidence.json':json.dumps(evidence)}})}}
        pm = verify_bundle(self.paths['projection'])
        meta = {'kind':'multi-uncertainty-forecast', 'state':pm['metadata'],
                'projection':pd.js.uc.reference(self.paths['projection'],pm), 'computed_at':'2026-09-23T08:35:00Z'}
        self.paths['uncertainty'] = dr.write_products(self.root/'valid-uncertainty', meta,
            {'uncertainty.json':pd.js.uc.attach(self.rows,self.tables), 'projection.json':archive})[0]
        self.refs['uncertainty'] = pd.reference(self.paths['uncertainty'],verify_bundle(self.paths['uncertainty']))
        config=load_json(self.config_path); config['mode']='pre-deadline'; atomic_write_json(self.config_path,config)
        self.decision, _, self.summary, _ = pd.run(self.config_path,progress=lambda t:None)
        self.retention, _, self.retained = dr.retain(self.decision,[self.root],self.root/'retentions')
        self.assertion = self.root/'assertion.json'

    def action(self, full=False, gw=6, candidate='exact_1'):
        w = next(w for w in self.summary['plans'][candidate]['weeks'] if w['gameweek']==gw)
        a = {'contract':dr.CONTRACT['actions'], 'decision_identity':self.decision.name,
             'season':'2026-27','target_gameweek':gw,
             'provenance':{'kind':'synthetic','source':'Synthetic test assertion <script>', 'declared_at':IMPORTED,'confirmed':True},
             'choice':{'selected':candidate,'rejected':[]}, 'actions':dict.fromkeys(dr.FIELDS)}
        if full:
            a['actions'] = {k:copy.deepcopy(w[k]) for k in ('squad','starting_xi','captain','transfer_hit')}
            a['actions'].update(chip='none',transfers=[{'out':o,'in':i} for position in range(1,5) for o,i in zip([e for e in w['transfers_out'] if self.summary['population'][str(e)]['position']==position], [e for e in w['transfers_in'] if self.summary['population'][str(e)]['position']==position])])
        return a

    def confirm(self,a=None,previous=None,output=None):
        atomic_write_json(self.assertion,a or self.action())
        return dr.confirm(self.retention,self.assertion,[self.root],output or self.root/'confirmations',previous)

    def settle(self, gw=6, blank=False, double=True, changed=False):
        u = self.paths['uncertainty']; um = verify_bundle(u)
        context = dr.mo.target_context(u,um,gw)
        c = Client(gw=gw,settled=True,empty=blank)
        c.bootstrap = copy.deepcopy(self.bootstrap)
        next(e for e in c.bootstrap['events'] if e['id']==gw).update(finished=True,data_checked=True)
        if not double: c.fixtures=c.fixtures[:1]
        c.live['elements']=[]
        for e in range(1,18):
            points = (e%5)+(1 if changed else 0)
            explanations=[] if blank else [{'fixture':f['id'],'stats':[{'identifier':'minutes','value':90,'points':points}]} for f in c.fixtures]
            c.live['elements'].append({'id':e,'stats':{'minutes':90*len(explanations),'total_points':points*len(explanations)},'explain':explanations})
        t = {k:{'requested_at':'2026-10-01T12:00:00Z','received_at':'2026-10-01T12:00:00Z'} for k in ('bootstrap','fixtures','live')}
        m = dr.mo.settlement_metadata(context,um,t)
        return dr.write_products(self.root/'settlements',m,dict(zip(('bootstrap.json','fixtures.json','live.json'),(c.bootstrap,c.fixtures,c.live))))[0]

    def review(self, actions=(), settlements=(), previous=None):
        return dr.review(self.retention,[self.root],actions,settlements,self.root/'reviews',previous)

    def test_pending_intention_is_not_action(self):
        action,_,p=self.confirm()
        self.assertEqual(p['relationship_to_intention'],'partial')
        _,_,r=self.review([action])
        self.assertEqual(r['pending_targets'],[6,7])
        self.assertIsNone(r['confirmed_horizon_points'])
        self.assertEqual(r['confirmed'][0]['status'],'partial confirmation')
        self.assertFalse(r['decision_value_claim'])

    def test_predeadline_late_and_declared_time_cannot_backdate_import(self):
        a=self.action(True)
        _,_,early=self.confirm(a)
        self.assertFalse(early['attestation']['late'])
        with patch.object(dr.live,'now_utc',clock('2026-09-24T10:00:00Z')):
            _,_,late=self.confirm(a,output=self.root/'late')
        self.assertTrue(late['attestation']['late'])
        self.assertIn('confirmation recorded after target deadline',late['prospective_exclusions'])
        self.assertEqual(late['assertion']['provenance']['declared_at'],IMPORTED)

    def test_manual_eligibility_snapshot_and_synthetic_exclusions(self):
        r=dr.with_identity(copy.deepcopy(self.retained),{'identity':self.decision.name})
        r['prospective_exclusions']=[]
        a=self.action(True); a['provenance']['kind']='manual'
        t=dr.timing(IMPORTED,IMPORTED,IMPORTED,r['deadlines']['6'])
        self.assertEqual(dr.confirmation_product(a,r,t)['prospective_exclusions'],[])
        self.assertIn('synthetic decision',self.retained['prospective_exclusions'])
        summary=copy.deepcopy(self.summary); summary['config']['mode']='snapshot'
        p=dr.retention_product(summary,dr.Reader([self.root]),self.retained['attestation'])
        self.assertIn('snapshot/what-if decision',p['prospective_exclusions'])

    def test_extension_partial_divergent_and_conflicting_heads(self):
        first,_,_=self.confirm()
        a=self.action(True)
        second,_,p=self.confirm(a,first)
        self.assertEqual(p['relationship_to_intention'],'full declared match')
        _,_,r=self.review([first,second,second],[self.settle()])
        self.assertEqual(r['confirmed'][0]['confirmation_identity'],second.name)
        a['actions']['captain']=next(e for e in a['actions']['starting_xi'] if e!=a['actions']['captain'])
        with self.assertRaisesRegex(ValueError,'cannot revise'): self.confirm(a,second)
        other,_,p=self.confirm(a)
        self.assertEqual(p['relationship_to_intention'],'divergent')
        with self.assertRaisesRegex(ValueError,'competing confirmations'): self.review([second,other])
        # Execute just one of the proposed transfers. Known execution differs
        # from the path; missing XI/captain must not imply future adherence.
        w=self.summary['plans']['exact_1']['weeks'][0]
        incoming=w['transfers_in'][0]
        outgoing=next(e for e in w['transfers_out'] if self.summary['population'][str(e)]['position']==self.summary['population'][str(incoming)]['position'])
        held={p['element'] for p in self.personal['squad']['players']}
        partial=self.action()
        partial['actions'].update(transfers=[{'out':outgoing,'in':incoming}],
            squad=sorted((held-{outgoing})|{incoming}),transfer_hit=0,chip='none')
        _,_,p=self.confirm(partial)
        self.assertEqual(p['relationship_to_intention'],'divergent')
        self.assertEqual(p['component_match']['transfers'],'divergent')
        self.assertIn('starting_xi',p['unscorable_fields'])

    def test_partial_action_with_no_intention_scores_only_when_explicit(self):
        a=self.action(True); a['choice']=None; a['actions']['transfers']=None
        action,_,p=self.confirm(a)
        self.assertEqual(p['relationship_to_intention'],'no selected intention')
        _,_,r=self.review([action],[self.settle()])
        self.assertEqual(r['confirmed'][0]['status'],'scored')
        self.assertEqual(r['confirmed'][0]['points'],r['candidates'][2]['weeks'][0]['points'])
        for key in ('squad','starting_xi','captain','transfer_hit','chip'):
            partial=copy.deepcopy(a); partial['actions'][key]=None
            _,_,record=self.confirm(partial)
            self.assertIn(key,record['unscorable_fields'])

    def test_complete_partial_horizon_double_and_explicit_zero(self):
        s6,s7=self.settle(6),self.settle(7)
        one,_,partial=self.review(settlements=[s7])
        self.assertEqual(partial['pending_targets'],[6])
        self.assertTrue(all(c['horizon_points'] is None for c in partial['candidates']))
        actions=[self.confirm(self.action(True,gw=g))[0] for g in (6,7)]
        out,_,r=self.review(actions,[s6],one)
        self.assertEqual(r['pending_targets'],[])
        self.assertIsNotNone(r['confirmed_horizon_points'])
        for c in r['candidates']:
            plan=self.summary['plans'][c['candidate']]
            expected=[]
            for h,w in enumerate(plan['weeks']):
                score=sum((e%5)*2 for e in w['starting_xi'])+(w['captain']%5)*2-w['transfer_hit']
                self.assertEqual(c['weeks'][h]['points'],score); expected.append(score)
            self.assertEqual(c['horizon_points'],sum(expected))
        dr.verify(out,[self.root])
        from scripts.verify_decision_review import audit
        audited=audit(out,[self.root])
        self.assertTrue(audited['fixed_lineup_arithmetic_and_identities_pass'])
        self.assertEqual(audited['candidate_gameweeks_checked'],10)

    def test_blank_null_not_zero_and_missing_outcome_rejects(self):
        _,_,r=self.review(settlements=[self.settle(blank=True)])
        self.assertEqual(r['pending_targets'],[7])
        self.assertEqual(r['candidates'][0]['weeks'][0]['status'],'unscorable outcome')
        self.assertIsNone(r['candidates'][0]['weeks'][0]['points'])
        bad=tamper(self.settle(),self.root/'bad',lambda m,v:v['live.json']['elements'].pop())
        with self.assertRaisesRegex(ValueError,'explicit projected player'): self.review(settlements=[bad])

    def test_duplicates_conflicts_and_previous_review_evidence(self):
        s=self.settle(); action=self.confirm(self.action(True))[0]
        original,_,_=self.review([action],[s])
        again,reused,_=self.review([action,action],[s,s],original)
        self.assertEqual(original,again); self.assertTrue(reused)
        with self.assertRaisesRegex(ValueError,'conflicting settlements'): self.review(settlements=[self.settle(changed=True)],previous=original)
        bad=tamper(s,self.root/'other',lambda m,v:m.update(received_at='2026-10-02T12:00:00Z'))
        with self.assertRaises(ValueError): self.review(settlements=[bad])

    def test_rehashed_semantic_tampering(self):
        action=self.confirm(self.action(True))[0]
        review=self.review([action],[self.settle()])[0]
        probes=[(self.retention,lambda m,v:v['record.json']['candidate_order'].reverse()),
                (self.retention,lambda m,v:v['record.json']['summary']['plans']['exact_1']['weeks'][0].update(captain=999)),
                (action,lambda m,v:v['record.json'].update(relationship_to_intention='invented adherence')),
                (action,lambda m,v:v['record.json']['assertion']['actions'].update(transfer_hit=999)),
                (action,lambda m,v:v['record.json']['attestation'].update(late=True)),
                (review,lambda m,v:v['record.json']['candidates'][0]['weeks'][0].update(points=999)),
                (review,lambda m,v:v['record.json'].update(confirmed_horizon_points=99)),
                (review,lambda m,v:v['record.json']['candidate_order'].reverse())]
        for original,change in probes:
            bad=tamper(original,self.root/'bad',change)
            with self.subTest(original=original),self.assertRaises(ValueError): dr.verify(bad,[self.root])

    def test_altered_action_reference_and_wrong_decision_fail(self):
        a=self.action(); a['decision_identity']='0'*64
        with self.assertRaisesRegex(ValueError,'decision mismatch'): self.confirm(a)
        action=self.confirm(self.action(True))[0]
        review=self.review([action])[0]
        bad=tamper(review,self.root/'bad',lambda m,v:m['confirmations'][0].update(manifest_file_sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'altered confirmation'): dr.verify(bad,[self.root])
        (action/'record.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'checksum'): dr.verify(review,[self.root])

    def test_immutable_reuse_replay_and_source_preservation(self):
        before=fingerprint(self.decision),fingerprint(self.retention)
        action,_,p=self.confirm(self.action(True)); ab=fingerprint(action)
        with patch.object(dr.live,'now_utc',clock('2026-10-02T12:00:00Z')):
            same,reused,r=self.confirm(self.action(True))
        self.assertTrue(reused); self.assertEqual(same,action); self.assertEqual(r,p)
        review=self.review([action],[self.settle()])[0]
        replay,_,_=dr.replay(review,[self.root],self.root/'replayed')
        self.assertEqual(review.name,replay.name)
        self.assertEqual(verify_bundle(review),verify_bundle(replay))
        dr.verify(replay,[self.root])
        self.assertEqual(before,(fingerprint(self.decision),fingerprint(self.retention)))
        self.assertEqual(ab,fingerprint(action))

    def test_invalid_partial_and_divergent_assertions(self):
        for key,value in [('captain',True),('captain',999),('transfer_hit',True),('transfer_hit',2),('chip','wildcard'),('starting_xi',[1]*11),('squad',[1]*15),('transfers',[{'out':1,'in':1}])]:
            a=self.action(True); a['actions'][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): self.confirm(a)
        a=self.action(True); a['actions']['transfers']=[]
        with self.assertRaisesRegex(ValueError,'contradict'): self.confirm(a)
        a=self.action(); a['provenance']['declared_at']='2027-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'declared action'): self.confirm(a)

    def test_final_clock_guard_boundary_and_reversed(self):
        for final in ('2026-09-24T10:00:00Z','2026-09-23T09:59:59Z'):
            a=self.action(); atomic_write_json(self.assertion,a)
            with patch.object(dr.live,'now_utc',side_effect=[clock(IMPORTED)(),clock(IMPORTED)(),clock(final)()]):
                with self.assertRaises(ValueError): dr.confirm(self.retention,self.assertion,[self.root],self.root/'bad-time')
            self.assertEqual(list((self.root/'bad-time').iterdir()),[])

    def test_same_target_duplicate_declared_records_require_extension(self):
        first=self.confirm()[0]
        a=self.action(); a['provenance']['source']='Different assertion'
        second=self.confirm(a)[0]
        with self.assertRaisesRegex(ValueError,'competing confirmations'): self.review([first,second])

    def test_duplicate_identity_with_changed_manifest_bytes_is_ambiguous(self):
        for source, kind in ((self.confirm()[0], 'confirmation'), (self.settle(), 'settlement')):
            other=self.root/('alias-'+kind)/source.name
            shutil.copytree(source,other)
            # Same logical manifest hash; different exact evidence bytes.
            (other/'manifest.json').write_text(json.dumps(load_json(other/'manifest.json')))
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError,'conflicting '+kind+' bytes'):
                if kind=='confirmation': self.review([source,other])
                else: self.review(settlements=[source,other])

    def test_later_hit_feasibility_uses_rules_without_inferred_ft(self):
        rules=dr.Rules().validate()
        a=self.action(True,gw=7,candidate='no_transfer')
        a['actions']['transfer_hit']=rules.hit_cost
        with self.assertRaisesRegex(ValueError,'every valid FT state'): self.confirm(a)
        a['actions']['transfer_hit']=0
        valid=self.confirm(a)[0]
        self.assertEqual(self.review([valid],[self.settle(7)])[2]['confirmed'][1]['status'],'scored')
        retained=dr.with_identity(self.retained,{'identity':self.decision.name})
        # Enumerate neighbours around both limits, including the cap-induced minimum.
        same_position=next((x,y) for x in range(1,18) for y in range(x+1,18)
            if self.summary['population'][str(x)]['position']==self.summary['population'][str(y)]['position'])
        for count in (0,1,2,rules.free_transfer_cap+1):
            expected={rules.hit(count,free) for free in range(rules.free_transfer_cap+1)}
            for hit in range(0,(count+2)*rules.hit_cost,rules.hit_cost):
                partial=self.action(gw=7)
                x,y=same_position
                partial['actions'].update(transfers=[{'out':x if i%2==0 else y,'in':y if i%2==0 else x} for i in range(count)],transfer_hit=hit)
                with self.subTest(count=count,hit=hit):
                    if hit in expected: dr.validate_assertion(partial,retained,IMPORTED)
                    else:
                        with self.assertRaisesRegex(ValueError,'every valid FT state'): dr.validate_assertion(partial,retained,IMPORTED)
        for field in ('transfers','transfer_hit'):
            partial=copy.deepcopy(a);partial['actions'][field]=None
            dr.validate_assertion(partial,retained,IMPORTED)
        def impossible(m,v):
            v['record.json']['assertion']['actions']['transfer_hit']=rules.hit_cost
            m['request_key']=dr.confirmation_metadata(m['retention'],m['previous'],v['record.json']['assertion'],m['attestation'])['request_key']
        bad=tamper(valid,self.root/'bad-hit',impossible)
        with self.assertRaisesRegex(ValueError,'every valid FT state'): self.review([bad],[self.settle(7)])

    def test_swapped_cross_position_pairs_rejected_with_identical_sets(self):
        a=self.action(True)
        pairs=a['actions']['transfers']
        self.assertEqual(len(pairs),2)
        self.assertNotEqual(self.summary['population'][str(pairs[0]['out'])]['position'],self.summary['population'][str(pairs[1]['out'])]['position'])
        _,_,p=self.confirm(a)
        self.assertEqual(p['relationship_to_intention'],'full declared match')
        bad=copy.deepcopy(a)
        bad['actions']['transfers'][0]['in'],bad['actions']['transfers'][1]['in']=pairs[1]['in'],pairs[0]['in']
        for key in ('out','in'):
            self.assertEqual(sorted(p[key] for p in pairs),sorted(p[key] for p in bad['actions']['transfers']))
        for gw in (6,7):
            bad['target_gameweek']=gw
            with self.subTest(gw=gw),self.assertRaisesRegex(ValueError,'incompatible frozen positions'): self.confirm(bad)

    def test_eligible_retention_excluded_actions_reconstruct_all_headlines(self):
        from fpl_ai.cli import main
        # All data remains a synthetic test fixture; manual label exercises the gate.
        self.personal['provenance']['kind']='manual'
        atomic_write_json(self.root/'personal.json',self.personal)
        self.decision,_,self.summary,_=pd.run(self.config_path,progress=lambda t:None)
        self.retention,_,self.retained=dr.retain(self.decision,[self.root],self.root/'retentions')
        self.assertEqual(self.retained['prospective_exclusions'],[])
        for kind,stamp,reason in [('synthetic',IMPORTED,'synthetic confirmation'),
                                  ('manual','2026-09-24T10:00:00Z','confirmation recorded after target deadline')]:
            a=self.action(True);a['provenance']['kind']=kind
            with patch.object(dr.live,'now_utc',clock(stamp)): action=self.confirm(a)[0]
            out,_,r=self.review([action,action],[self.settle()])
            self.assertEqual(r['retention_exclusions'],[])
            self.assertEqual(r['confirmation_exclusions'],[reason])
            self.assertEqual(r['prospective_exclusions'],[reason])
            for name in ('report.md','report.html'):
                self.assertIn('Prospective exclusions: '+reason,(out/name).read_text())
            self.assertEqual(dr.verify(out,[self.root])[1],r)
            replay,_,rr=dr.replay(out,[self.root],self.root/('headline-replay-'+kind))
            self.assertEqual(rr,r);self.assertEqual(verify_bundle(out),verify_bundle(replay))
            stdout=io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(['review','verify','--bundle',str(out),'--evidence-root',str(self.root)]),0)
            self.assertIn('Prospective exclusions: '+str([reason]),stdout.getvalue())
            bad=tamper(out,self.root/'hidden-exclusions',lambda m,v:v['record.json'].update(prospective_exclusions=[]))
            with self.assertRaisesRegex(ValueError,'semantic reconstruction'): dr.verify(bad,[self.root])

    def test_pre_hardening_contract_is_rejected_without_reinterpretation(self):
        def old_contract(m,v):
            for key in ('action_validation','review_exclusions'): m['contract'].pop(key)
        old=tamper(self.retention,self.root/'old-contract',old_contract)
        with self.assertRaisesRegex(ValueError,'M5F contract mismatch'): dr.verify(old,[self.root])

    def test_cli_lifecycle(self):
        from fpl_ai.cli import main
        atomic_write_json(self.assertion,self.action(True))
        base=['--evidence-root',str(self.root)]
        out=self.root/'cli-actions'
        self.assertEqual(main(['review','confirm','--retention',str(self.retention),'--assertion',str(self.assertion),'--artifact-dir',str(out),*base]),0)
        action=next(out.glob('*/manifest.json')).parent
        self.assertEqual(main(['review','outcomes','--retention',str(self.retention),'--confirmation',str(action),'--settlement',str(self.settle()),'--artifact-dir',str(self.root/'cli-reviews'),*base]),0)
        review=next((self.root/'cli-reviews').glob('*/manifest.json')).parent
        self.assertEqual(main(['review','verify','--bundle',str(review),*base]),0)
        self.assertEqual(main(['review','replay','--bundle',str(review),'--artifact-dir',str(self.root/'cli-replay'),*base]),0)
        with self.assertRaises(SystemExit): main(['--timeout','1','review','verify','--bundle',str(review)])
