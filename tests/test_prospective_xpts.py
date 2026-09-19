"""Offline prospective lifecycle: test clocks are never exposed by the CLI."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fpl_ai import prospective_xpts as xp
from fpl_ai import prospective as live
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv
from fpl_ai.minutes import run_minutes
from tests.test_minutes import build_fixture
from tests.test_prospective import Client, clock, fingerprint
from tests.test_xpts_v2 import fixture


def republish(folder, root, *, metadata=None, tables=None):
    m = verify_bundle(folder)
    def writer(out):
        for n in m['artifacts']: shutil.copyfile(folder/n,out/n)
        for n,v in (tables or {}).items():
            if n.endswith('.csv'): xp.write_table(out,n,v)
            else: atomic_write_json(out/n,v)
    return publish(root, metadata or m['metadata'],writer)[0]


class ProspectiveXptsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); root = Path(cls.temp.name)
        cls.minutes_model = run_minutes(build_fixture(root/'features'),root/'minutes')[0]
        cls.patches = [patch.object(xp,'MINUTES_ID',cls.minutes_model.name),
                       patch.object(xp,'MINUTES_BINDING',{'manifest_sha256':sha256_file(cls.minutes_model/'manifest.json'),
                                                        'artifacts':verify_bundle(cls.minutes_model)['artifacts']}),
                       patch.object(xp,'EXPECTED_COUNTS',{'2024-25':60})]
        for p in cls.patches:p.start()
        rows,ps,aa = fixture();fs,a = xp.join_rows(rows,ps,aa)
        models,state,training = xp.fit_operational(fs,xp.labels_for(rows),a)
        blobs={n:xp.model_bytes(m) for n,m in models.items()}
        state['model_hashes']={n:xp.sha256_bytes(b) for n,b in blobs.items()}
        state['preprocessing_hashes']={n:xp.sha256_bytes(xp.model_bytes(m.named_steps['preprocess'])) for n,m in models.items()}
        state['model_identities']={n:xp.digest({'name':n,'state':state.copy(),'protocol':xp.PROTOCOL}) for n in models}
        def writer(out):
            atomic_write_json(out/'protocol.json',xp.PROTOCOL);atomic_write_json(out/'fit.json',state)
            atomic_write_json(out/'sources.json',{n:{'identity_sha256':v} for n,v in zip(('m3','minutes_oos','frozen_m4_holdout'),(xp.M3_ID,xp.OOS_ID,xp.HOLDOUT_ID))})
            xp.write_table(out,'training.csv',training)
            for n,b in blobs.items():(out/f'{n}.pickle').write_bytes(b)
        cls.model=publish(root/'models',{'kind':'prospective-xpts-model','protocol':xp.PROTOCOL,'environment':xp.environment()},writer)[0]

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):p.stop()
        cls.temp.cleanup()

    def inputs(self,root,gw=2,empty=False):
        c=Client(gw=gw,empty=empty)
        for p in c.bootstrap['elements']:
            p.update(now_cost=50,selected_by_percent='2.5',transfers_in_event=0,transfers_out_event=10)
        day='17' if gw==2 else '25'
        snap=live.capture_snapshot('2026-27',gw,root/'snap',client=c,clock=clock(f'2026-09-{day}T10:00:00Z'))[0]
        mins=live.freeze_predictions(snap,self.minutes_model,root/'mins',clock=clock(f'2026-09-{day}T10:01:00Z'))[0]
        return snap,mins

    def forecast(self,root,empty=False):
        snap,mins=self.inputs(root,empty=empty)
        out=xp.freeze(snap,mins,self.model,root/'xpts',clock=clock('2026-09-17T10:02:00Z'))[0]
        return snap,mins,out

    def test_valid_forecast_replay_determinism_reuse_and_outcome_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,mins,out=self.forecast(root);before=fingerprint(out)
            m=xp.verify_forecast(out,self.model)
            fresh=xp.freeze(snap,mins,self.model,root/'fresh',clock=clock('2026-09-17T10:02:00Z'))[0]
            self.assertEqual(m,verify_bundle(fresh))
            self.assertTrue(xp.freeze(snap,mins,self.model,root/'xpts',clock=clock('2026-09-17T10:02:00Z'))[1])
            self.assertEqual(before,fingerprint(out))
            for name in ('features.csv','predictions.csv'):
                self.assertNotIn('target_points',(out/name).read_text());self.assertNotIn('target_minutes',(out/name).read_text())
            fs=read_csv(out/'features.csv');ps=read_csv(out/'predictions.csv')
            self.assertEqual([xp.key(r) for r in fs],[xp.key(r) for r in ps])
            self.assertEqual(fs[0]['season_points_count'],'0');self.assertEqual(fs[0]['previous_points'],'')
            self.assertEqual(tuple(fs[0]),xp.KEYS+xp.ORDERS['xpts_v2'])

    def test_missed_deadline_and_computation_and_final_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,mins=self.inputs(root)
            early=clock('2026-09-17T10:02:00Z')();late=clock('2026-09-18T12:00:00Z')()
            for seq in ([late],[early,late],[early,early,late],[early]*3+[late],[early]*4+[late]):
                times=iter(seq)
                with self.subTest(seq=seq),self.assertRaisesRegex(ValueError,'deadline'):
                    xp.freeze(snap,mins,self.model,root/'bad',clock=lambda:next(times))
                self.assertFalse(list((root/'bad').glob('*/manifest.json')))

    def test_capture_after_deadline_rejected(self):
        with tempfile.TemporaryDirectory() as tmp,self.assertRaisesRegex(ValueError,'deadline'):
            live.capture_snapshot('2026-27',2,tmp,client=Client(),clock=clock('2026-09-18T12:00:00Z'))

    def test_snapshot_and_wrong_gameweek_minutes_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,mins=self.inputs(root);other,other_mins=self.inputs(root,3)
            for a,b in ((snap,other_mins),(other,mins)):
                with self.assertRaises(ValueError):xp.adapter(a,b)
            m=copy.deepcopy(verify_bundle(mins)['metadata']);m['snapshot_artifacts']['bootstrap.json']='f'*64
            bad=republish(mins,root/'bad',metadata=m)
            with self.assertRaisesRegex(ValueError,'identity'):xp.adapter(snap,bad)

    def test_wrong_elements_duplicates_missing_minutes_and_model_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,mins=self.inputs(root)
            for mode in ('elements','duplicates','missing','model','contract','model_hash'):
                metadata=copy.deepcopy(verify_bundle(mins)['metadata']);ps=read_csv(mins/'predictions.csv');fs=read_csv(mins/'features.csv')
                if mode=='elements':ps[0]['element']=fs[0]['element']='99'
                elif mode=='duplicates':ps.append(ps[0]);fs.append(fs[0])
                elif mode=='missing':ps[0]['expected_minutes']=''
                elif mode=='model':metadata['model_identity']='wrong'
                elif mode=='model_hash':metadata['model_artifacts']['model.pickle']='wrong'
                else:metadata['contract']['version']='wrong'
                bad=republish(mins,root/mode,metadata=metadata,tables={'predictions.csv':ps,'features.csv':fs})
                with self.subTest(mode=mode),self.assertRaises(ValueError):xp.adapter(snap,bad)
            (mins/'predictions.csv').write_text('corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):xp.adapter(snap,mins)

    def test_prior_history_missing_zero_and_future_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,mins=self.inputs(root)
            settled=live.capture_settlement(mins,root/'settle',client=Client(settled=True),clock=clock('2026-09-20T10:00:00Z'))[0]
            future,future_minutes=self.inputs(root,3)
            fs,obs,*_=xp.adapter(future,future_minutes,[(mins,settled)])
            self.assertEqual([f['previous_points'] for f in fs],[4,0]);self.assertEqual(len(obs),2)
            # An absent player in retained history stays missing, never zero.
            c=Client(settled=True);c.live['elements'].pop()
            raw=republish(settled,root/'partial',tables={'live.json':c.live})
            with self.assertRaisesRegex(ValueError,'forecast population'):xp.adapter(future,future_minutes,[(mins,raw)])
            c=Client(gw=3);c.bootstrap['elements'].append(dict(c.bootstrap['elements'][1],id=3))
            added=live.capture_snapshot('2026-27',3,root/'added',client=c,clock=clock('2026-09-25T10:00:00Z'))[0]
            added_mins=live.freeze_predictions(added,self.minutes_model,root/'added_mins',clock=clock('2026-09-25T10:01:00Z'))[0]
            fs,_,*_=xp.adapter(added,added_mins,[(mins,settled)])
            self.assertIsNone(fs[2]['previous_points']);self.assertEqual(fs[2]['season_points_count'],0)
            for pairs in ([(mins,settled)],[(mins,settled)]*2):
                with self.assertRaises(ValueError):xp.adapter(snap,mins,pairs)
            late=live.capture_settlement(mins,root/'late',client=Client(settled=True),clock=clock('2026-09-27T10:00:00Z'))[0]
            with self.assertRaisesRegex(ValueError,'future'):xp.adapter(future,future_minutes,[(mins,late)])
            c=Client(settled=True);c.bootstrap['events'][1]['data_checked']=False
            bad=republish(settled,root/'unsettled',tables={'bootstrap.json':c.bootstrap})
            with self.assertRaisesRegex(ValueError,'settled'):xp.adapter(future,future_minutes,[(mins,bad)])

    def test_history_windows_and_explicit_zero(self):
        p={'element_type':2,'status':None,'now_cost':50}
        f=xp.points_features(7,p,{1:4,3:0,5:8})
        self.assertIsNone(f['previous_points']);self.assertEqual(f['points_mean_3'],8)
        self.assertEqual(f['points_mean_5'],4);self.assertEqual(f['points_count_5'],2)
        self.assertEqual(f['season_points_mean'],4);self.assertEqual(f['season_points_count'],3)
        self.assertEqual(f['status_missing'],1)
        for h in ({7:0},{8:4},{1:None},{1:True}):
            with self.assertRaises(ValueError):xp.points_features(7,p,h)

    def test_double_blank_scores_target_mutation_never_rewrites_forecast(self):
        for empty in (False,True):
            with self.subTest(empty=empty),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);_,mins,out=self.forecast(root,empty);before=fingerprint(out)
                settled=live.capture_settlement(mins,root/'settle',client=Client(settled=True,empty=empty),clock=clock('2026-09-20T10:00:00Z'))[0]
                scored=xp.score(out,settled,self.model,root/'score')[0]
                self.assertTrue(xp.score(out,settled,self.model,root/'score')[1])
                report=json.loads((scored/'metrics.json').read_text())
                self.assertEqual(report['paired']['rows'],0 if empty else 2)
                self.assertEqual(report['segments']['overall']['control']['predicted_rows'],report['segments']['overall']['xpts_v2']['predicted_rows'])
                self.assertEqual(before,fingerprint(out))
                if not empty:
                    c=Client(settled=True);c.live['elements'][0]['stats']['total_points']+=10;c.live['elements'][0]['explain'][0]['stats'][0]['points']+=10
                    changed=republish(settled,root/'changed',tables={'live.json':c.live})
                    self.assertNotEqual(scored.name,xp.score(out,changed,self.model,root/'score')[0].name)
                    self.assertEqual(before,fingerprint(out))

    def test_empty_malformed_schedule_missing_outcome_and_contract_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,mins,out=self.forecast(root)
            settled=live.capture_settlement(mins,root/'settle',client=Client(settled=True),clock=clock('2026-09-20T10:00:00Z'))[0]
            for i,fixtures in enumerate(([],{},[None],[{'id':10}])):
                bad=republish(settled,root/str(i),tables={'fixtures.json':fixtures})
                with self.assertRaises(ValueError):xp.score(out,bad,self.model,root/'score')
            c=Client(settled=True);c.live['elements'].pop()
            bad=republish(settled,root/'missing',tables={'live.json':c.live})
            with self.assertRaisesRegex(ValueError,'missing explicit'):xp.score(out,bad,self.model,root/'score')
            metadata=copy.deepcopy(verify_bundle(out)['metadata']);metadata['protocol']['version']='wrong'
            bad=republish(out,root/'contract',metadata=metadata)
            with self.assertRaisesRegex(ValueError,'protocol'):xp.verify_forecast(bad,self.model)

    def test_current_season_and_late_labels_cannot_fit(self):
        rows,ps,aa=fixture();fs,a=xp.join_rows(rows,ps,aa);ys=xp.labels_for(rows)
        ys[0]['label_available_at']=xp.CUTOFF
        with self.assertRaisesRegex(ValueError,'unsafe'):xp.fit_operational(fs,ys,a)
        for table in (fs,a,ys):table[0]['season']='2026-27'
        with self.assertRaisesRegex(ValueError,'prior-season'):xp.fit_operational(fs,ys,a)

    def test_cli_no_clock_override(self):
        from fpl_ai.cli import main
        import contextlib,io
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            main(['prospective','xpts','freeze','--model-dir','m','--snapshot-dir','s','--minutes-dir','p','--timestamp','2026-09-17'])

    def test_target_and_forbidden_snapshot_fields_never_enter_features(self):
        p={'element_type':2,'now_cost':50,'status':'a'}
        original=xp.points_features(6,p,{2:0,4:5})
        p.update(total_points=9999,event_points=9999,minutes=9999,xP=9999,ep_next=9999,
                 team=99,opponent=99,difficulty=99)
        self.assertEqual(original,xp.points_features(6,p,{2:0,4:5}))
        self.assertEqual(type(original['previous_points']),type(None))
        self.assertIs(type(original['points_mean_3']),float)
        self.assertIs(type(original['points_count_3']),int)
