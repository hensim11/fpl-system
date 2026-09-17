"""No network: genuine clock boundaries, immutable forecasts and independent scores."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fpl_ai.client import DEFAULT_BASE_URL
from fpl_ai.experiment_io import digest, verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.minutes import run_minutes
from fpl_ai.prospective import (capture_snapshot, freeze_predictions, capture_settlement,
                                load_snapshot, score_predictions, verify_prediction)
from tests.test_minutes import build_fixture


def clock(value):
    return lambda: datetime.fromisoformat(value.replace('Z','+00:00'))


class Client:
    base_url=DEFAULT_BASE_URL
    def __init__(self, gw=2, settled=False, empty=False):
        self.bootstrap={'events':[
            {'id':1,'deadline_time':'2026-08-15T12:00:00Z','is_next':False,'finished':True,'data_checked':True},
            {'id':2,'deadline_time':'2026-09-18T12:00:00Z','is_next':gw==2 and not settled,'finished':gw>2 or settled,'data_checked':gw>2 or settled},
            {'id':3,'deadline_time':'2026-09-26T12:00:00Z','is_next':gw==3,'finished':False,'data_checked':False}],
            'teams':[{'id':1},{'id':2}],
            'elements':[{'id':e,'element_type':2,'status':'a','chance_of_playing_next_round':None,
                         'minutes':90 if e==1 else 0,'starts':1 if e==1 else 0} for e in (1,2)]}
        self.fixtures=[dict(id=i,event=gw,team_h=1,team_a=2,kickoff_time=None,
                                             started=settled,finished=settled,team_h_score=1 if settled else None,
                                             team_a_score=0 if settled else None,team_h_difficulty=3,team_a_difficulty=2) for i in (10,11)]
        if empty:
            # A real season schedule positively establishes target-specific absence.
            for fixture in self.fixtures:
                fixture['event'] = 1
        self.live={'elements':[{'id':1,'stats':{'minutes':0 if empty else 180,'total_points':0 if empty else 4},
                               'explain':[] if empty else [{'fixture':i,'stats':[{'identifier':'minutes','value':90,'points':2}]} for i in (10,11)]},
                              {'id':2,'stats':{'minutes':0,'total_points':0},'explain':[]}]}
    def get_bootstrap(self):return copy.deepcopy(self.bootstrap)
    def get_fixtures(self):return copy.deepcopy(self.fixtures)
    def get_event_live(self,gw):return copy.deepcopy(self.live)


def fingerprint(path):
    return {p.name:(sha256_file(p),p.stat().st_mtime_ns) for p in path.iterdir()}


class ProspectiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models=tempfile.TemporaryDirectory()
        root=Path(cls.models.name)
        cls.model=run_minutes(build_fixture(root/'features'),root/'models')[0]
    @classmethod
    def tearDownClass(cls):cls.models.cleanup()

    def make_prediction(self,root,empty=False):
        snap=capture_snapshot('2026-27',2,root/'snapshots',client=Client(empty=empty),clock=clock('2026-09-17T10:00:00Z'))[0]
        pred=freeze_predictions(snap,self.model,root/'predictions',clock=clock('2026-09-17T10:01:00Z'))[0]
        return snap,pred

    def test_freeze_has_provenance_no_outcomes_and_reuses_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,pred=self.make_prediction(root)
            m=verify_prediction(pred)['metadata']
            for key in ('prediction_timestamp','deadline','snapshot_identity','snapshot_artifacts','feature_contract_identity','model_identity','model_artifacts','fixture_context_snapshot_identity'):
                self.assertIn(key,m)
            for name in ('features.csv','predictions.csv'):
                self.assertNotIn('target_minutes',(pred/name).read_text())
                self.assertNotIn('total_points',(pred/name).read_text())
            before=fingerprint(pred)
            self.assertTrue(freeze_predictions(snap,self.model,root/'predictions',clock=clock('2026-09-17T10:01:00Z'))[1])
            self.assertEqual(before,fingerprint(pred))
            verify_prediction(pred)  # Verification doesn't pretend to make a new forecast.

    def test_late_capture_late_forecast_and_late_publication_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with self.assertRaisesRegex(ValueError,'deadline'):
                capture_snapshot('2026-27',2,root/'late',client=Client(),clock=clock('2026-09-18T12:00:00Z'))
            snap,pred=self.make_prediction(root)
            with self.assertRaisesRegex(ValueError,'before deadline'):
                freeze_predictions(snap,self.model,root/'late',clock=clock('2026-09-18T12:00:00Z'))
            times=iter([datetime(2026,9,17,11,tzinfo=timezone.utc)]*3+[datetime(2026,9,18,12,tzinfo=timezone.utc)])
            with self.assertRaisesRegex(ValueError,'deadline'):
                freeze_predictions(snap,self.model,root/'failure',clock=lambda:next(times))
            self.assertEqual(list((root/'failure').iterdir()),[])

    def test_request_crossing_deadline_and_clock_reversal_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            times=iter([datetime(2026,9,18,11,tzinfo=timezone.utc)]*3+[datetime(2026,9,18,12,tzinfo=timezone.utc)])
            with self.assertRaisesRegex(ValueError,'deadline'):
                capture_snapshot('2026-27',2,tmp,client=Client(),clock=lambda:next(times))
            times=iter([datetime(2026,9,18,11,tzinfo=timezone.utc),datetime(2026,9,18,10,tzinfo=timezone.utc)])
            with self.assertRaisesRegex(ValueError,'backwards'):
                capture_snapshot('2026-27',2,tmp,client=Client(),clock=lambda:next(times))

    def test_authoritative_season_event_and_no_outcomes_at_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            for kind in ('season','started','ambiguous','duplicate_fixture'):
                c=Client();season='2026-27'
                if kind=='season':season='2025-26'
                elif kind=='started':c.fixtures[0]['started']=True
                elif kind=='ambiguous':c.bootstrap['events'][0]['is_next']=True
                else:c.fixtures.append(c.fixtures[0])
                with self.subTest(kind=kind),self.assertRaises(ValueError):
                    capture_snapshot(season,2,tmp,client=c,clock=clock('2026-09-17T10:00:00Z'))

    def test_doubles_zero_minutes_scoring_never_modifies_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,pred=self.make_prediction(root);before=fingerprint(pred)
            settled=capture_settlement(pred,root/'settled',client=Client(settled=True),clock=clock('2026-09-20T10:00:00Z'))[0]
            scores=score_predictions(pred,settled,root/'scores')[0]
            self.assertEqual(before,fingerprint(pred))
            self.assertIn(',180,4',(scores/'outcomes.csv').read_text())
            self.assertIn(',0,0',(scores/'outcomes.csv').read_text())
            report=json.loads((scores/'scores.json').read_text())
            self.assertEqual(report['expected_minutes']['scored'],2)
            self.assertEqual(report['expected_points']['scored'],0)
            self.assertTrue(score_predictions(pred,settled,root/'scores')[1])

    def test_empty_full_schedule_cannot_publish_a_blank_settlement_or_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            c=Client(empty=True);c.fixtures=[]
            with self.assertRaisesRegex(ValueError, 'missing/empty.*schedule'):
                capture_snapshot('2026-27',2,root/'bad_capture',client=c,clock=clock('2026-09-17T10:00:00Z'))
            _,pred=self.make_prediction(root,True)
            c=Client(settled=True,empty=True);c.fixtures=[]
            with self.assertRaisesRegex(ValueError, 'missing/empty.*schedule'):
                capture_settlement(pred,root/'bad_settlement',client=c,clock=clock('2026-09-20T10:00:00Z'))
            self.assertFalse((root/'bad_settlement').exists())
            self.assertFalse((root/'scores').exists())
            # Even a checksum-valid manually assembled bundle fails on the scoring read path.
            from fpl_ai.experiment_io import publish
            from fpl_ai.prospective import SETTLEMENT_CONTRACT
            t={'requested_at':'2026-09-20T10:00:00Z','received_at':'2026-09-20T10:00:00Z'}
            metadata={'kind':'prospective-settlement','contract':SETTLEMENT_CONTRACT,
                      'season':'2026-27','target_gameweek':2,'deadline':'2026-09-18T12:00:00Z',
                      'prediction_identity':pred.name,'received_at':t['received_at'],
                      'request_timing':dict.fromkeys(('bootstrap','fixtures','live'),t)}
            def writer(folder):
                for name,value in [('bootstrap.json',c.bootstrap),('fixtures.json',[]),('live.json',c.live)]:
                    atomic_write_json(folder/name,value)
            invalid=publish(root/'invalid',metadata,writer)[0]
            with self.assertRaisesRegex(ValueError, 'missing/empty.*schedule'):
                score_predictions(pred,invalid,root/'scores')
            self.assertFalse((root/'scores').exists())

    def test_malformed_or_unusable_full_schedule_fails(self):
        for mode in ('none','object','row','missing_event','unknown_event','boolean_event','unassigned','missing_finished','bad_finished','missing_kickoff'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);_,pred=self.make_prediction(root,True)
                c=Client(settled=True,empty=True)
                if mode=='none':c.fixtures=None
                elif mode=='object':c.fixtures={}
                elif mode=='row':c.fixtures=[None]
                elif mode.startswith('missing_'):
                    del c.fixtures[0][mode.removeprefix('missing_') if mode!='missing_kickoff' else 'kickoff_time']
                elif mode=='unknown_event':c.fixtures[0]['event']=99
                elif mode=='boolean_event':c.fixtures[0]['event']=True
                elif mode=='bad_finished':c.fixtures[0]['finished']='True'
                else:
                    for f in c.fixtures:f['event']=None
                with self.assertRaisesRegex(ValueError, 'schedule'):
                    capture_settlement(pred,root/'bad',client=c,clock=clock('2026-09-20T10:00:00Z'))
                self.assertFalse((root/'bad').exists())

    def test_fixture_empty_gw_stays_unlabelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,pred=self.make_prediction(root,True)
            settled=capture_settlement(pred,root/'settled',client=Client(settled=True,empty=True),clock=clock('2026-09-20T10:00:00Z'))[0]
            score=score_predictions(pred,settled,root/'scores')[0]
            self.assertEqual(json.loads((score/'scores.json').read_text())['expected_minutes']['scored'],0)

    def test_unsettled_incomplete_or_disagreeing_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);_,pred=self.make_prediction(root)
            for kind in ('flags','fixture','minutes','missing_player','foreign_fixture','points'):
                c=Client(settled=True)
                if kind=='flags':c.bootstrap['events'][1]['data_checked']=False
                elif kind=='fixture':c.fixtures[0]['finished']=False
                elif kind=='minutes':c.live['elements'][0]['stats']['minutes']=90
                elif kind=='missing_player':c.live['elements'].pop()
                elif kind=='foreign_fixture':c.live['elements'][0]['explain'][0]['fixture']=999
                else:c.live['elements'][0]['stats']['total_points']=5
                with self.subTest(kind=kind),self.assertRaises(ValueError):
                    capture_settlement(pred,root/'bad',client=c,clock=clock('2026-09-20T10:00:00Z'))
            self.assertFalse((root/'bad').exists())

    def test_only_prior_settled_forecasts_feed_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,pred=self.make_prediction(root)
            settled=capture_settlement(pred,root/'settled',client=Client(settled=True),clock=clock('2026-09-20T10:00:00Z'))[0]
            next_snap=capture_snapshot('2026-27',3,root/'snapshots',client=Client(gw=3),clock=clock('2026-09-25T10:00:00Z'))[0]
            next_pred=freeze_predictions(next_snap,self.model,root/'predictions',previous_dir=snap,history_pairs=[(pred,settled)],clock=clock('2026-09-25T10:01:00Z'))[0]
            from fpl_ai.modelling import read_csv
            rows=read_csv(next_pred/'features.csv')
            self.assertEqual(rows[0]['previous_minutes'],'180')
            self.assertEqual(rows[0]['minutes_count_3'],'1')
            for pairs in ([(pred,settled)],[(pred,settled),(pred,settled)]):
                with self.assertRaises(ValueError):
                    freeze_predictions(snap,self.model,root/'bad',history_pairs=pairs,clock=clock('2026-09-17T11:00:00Z'))

    def test_corruption_missing_files_contract_mismatch_and_input_output_alias(self):
        for mode in ('corruption','missing','contract'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);snap,pred=self.make_prediction(root)
                if mode=='corruption':(pred/'predictions.csv').write_text('bad')
                elif mode=='missing':(pred/'features.csv').unlink()
                else:
                    m=json.loads((pred/'manifest.json').read_text());m['metadata']['contract']['version']='wrong'
                    m['identity_sha256']=digest({k:v for k,v in m.items() if k!='identity_sha256'})
                    atomic_write_json(pred/'manifest.json',m);new=pred.with_name(m['identity_sha256']);pred.rename(new);pred=new
                with self.assertRaises(ValueError):verify_prediction(pred)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);snap,pred=self.make_prediction(root)
            with self.assertRaisesRegex(ValueError,'input artifact'):
                freeze_predictions(snap,self.model,snap,clock=clock('2026-09-17T11:00:00Z'))

    def test_cli_has_no_timestamp_backdating_option(self):
        from fpl_ai.cli import main
        import contextlib,io
        with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
            main(['prospective','capture','--season','2026-27','--gameweek','2','--timestamp','2026-09-17T10:00:00Z'])
        self.assertEqual(caught.exception.code,2)


if __name__=='__main__':unittest.main()
