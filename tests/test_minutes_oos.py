"""Temporal, exception and immutable handoff contracts; no live network."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.historical_io import atomic_write_csv, atomic_write_json
from fpl_ai.minutes import run_minutes
from fpl_ai.minutes_oos import (ALL_SEASONS, EXCEPTION, PROTOCOL, build_oos, evidence_policy,
                               load_downstream, partition, verify_oos)
from fpl_ai.modelling import read_csv
from tests.test_minutes import build_fixture, fixture_rows
from scripts.verify_minutes import fingerprint


def population():
    rows = sum((fixture_rows(s) for s in ALL_SEASONS), [])
    for r in rows:
        r['evidence_exception'] = ''
    return rows


class OOSTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.features = build_fixture(cls.root/'features')
        cls.model = run_minutes(cls.features, cls.root/'models')[0]
        cls.rows = population()
        cls.audits = {s:{'settlements':{str(r['target_gameweek']):{'capture_time_utc':r['label_available_at']}
                      for r in cls.rows if r['season']==s}} for s in ALL_SEASONS}
        cls.sources = {s:{'source_identity_sha256':digest(s)} for s in ALL_SEASONS}
        with patch('fpl_ai.minutes_oos.collect_rows', return_value=(cls.rows, cls.audits, cls.sources)):
            cls.out, _, cls.score, _ = build_oos(cls.features, cls.model, output_dir=cls.root/'oos')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def republish(self, mutate):
        import shutil
        def writer(folder):
            for p in self.out.iterdir():
                if p.name != 'manifest.json':shutil.copyfile(p, folder/p.name)
            mutate(folder)
        return publish(self.root/'mutations', verify_bundle(self.out)['metadata'], writer)[0]

    def test_earliest_period_unavailable_and_development_refused(self):
        safe = load_downstream(self.out)
        self.assertEqual(len(safe), 28)
        self.assertEqual({r['season'] for r in safe}, {'2024-25','2025-26'})
        early = [r for r in read_csv(self.out/'predictions.csv') if r['season']<'2024-25']
        self.assertTrue(all(r['expected_minutes']=='' and r['downstream_training_allowed']=='False' for r in early))
        with self.assertRaisesRegex(ValueError,'wrong experiment stage'):load_downstream(self.model)

    def test_expanding_annual_refits_and_strict_training_cutoff(self):
        selection = {'cutoff':'2024-06-01T00:00:00Z'}
        for season, count in [('2024-25',42),('2025-26',56)]:
            train, forecast, first = partition(self.rows, season, selection)
            self.assertEqual(len(train),count)
            self.assertTrue(all(r['season']<season for r in train))
            for field in ('label_available_at','capture'):
                bad = copy.deepcopy(self.rows)
                if field=='capture':bad[0]['audit']['capture_time_utc']=first
                else:bad[0][field]=first
                with self.assertRaisesRegex(ValueError,'training evidence'):partition(bad,season,selection)
        with self.assertRaisesRegex(ValueError,'unsupported'):partition(self.rows,'2023-24',selection)

    def test_selection_at_or_after_capture_rejected(self):
        first = min(r['audit']['capture_time_utc'] for r in self.rows if r['season']=='2024-25')
        for cutoff in (first,'2030-01-01T00:00:00Z'):
            with self.assertRaisesRegex(ValueError,'selection evidence'):partition(self.rows,'2024-25',{'cutoff':cutoff})

    def test_fresh_determinism_reuse_and_separate_outcomes(self):
        before = fingerprint(self.out)
        with patch('fpl_ai.minutes_oos.collect_rows', return_value=(self.rows,self.audits,self.sources)):
            again, reused, score, sr = build_oos(self.features,self.model,output_dir=self.root/'oos')
            fresh, reused_fresh, fs, _ = build_oos(self.features,self.model,output_dir=self.root/'fresh')
        self.assertTrue(reused and sr);self.assertFalse(reused_fresh)
        self.assertEqual(again.name,fresh.name);self.assertEqual(score.name,fs.name)
        self.assertEqual(fingerprint(self.out),before)
        self.assertNotIn('target_minutes',(self.out/'predictions.csv').read_text())
        self.assertNotIn('outcomes.csv',verify_bundle(self.out)['artifacts'])
        self.assertEqual(verify_bundle(self.score)['metadata']['prediction_identity'],self.out.name)

    def test_semantic_identity_and_closed_corrupt_missing_artifacts(self):
        self.assertNotEqual(digest(PROTOCOL),digest(dict(PROTOCOL,version='new')))
        for mode in ('corrupt','missing','extra'):
            with tempfile.TemporaryDirectory() as tmp:
                import shutil
                target=Path(tmp)/self.out.name;shutil.copytree(self.out,target)
                if mode=='corrupt':(target/'predictions.csv').write_text('bad')
                elif mode=='missing':(target/'training.csv').unlink()
                else:(target/'extra').write_text('bad')
                with self.assertRaises(ValueError):verify_oos(target)

    def test_checksum_valid_development_safe_flag_rejected(self):
        def mutate(folder):
            rows=read_csv(folder/'predictions.csv');rows[0]['downstream_training_allowed']='True'
            atomic_write_csv(folder/'predictions.csv',rows,list(rows[0]))
        with self.assertRaisesRegex(ValueError,'eligibility'):verify_oos(self.republish(mutate))

    def test_checksum_valid_training_or_selection_boundary_rejected(self):
        for mode in ('training','selection','model'):
            def mutate(folder):
                folds=json.loads((folder/'folds.json').read_text())
                if mode=='training':
                    rows=read_csv(folder/'training.csv');rows[0]['label_available_at']=folds['2024-25']['first_prediction_capture']
                    atomic_write_csv(folder/'training.csv',rows,list(rows[0]))
                elif mode=='model':(folder/'model_2024-25.pickle').write_bytes(b'wrong model')
                else:
                    source=json.loads((folder/'sources.json').read_text());source['selection']['cutoff']=folds['2024-25']['first_prediction_capture']
                    atomic_write_json(folder/'sources.json',source)
            with self.subTest(mode=mode),self.assertRaises(ValueError):verify_oos(self.republish(mutate))

    def test_target_labels_do_not_change_same_or_earlier_forecasts(self):
        changed=copy.deepcopy(self.rows)
        for r in changed:
            if r['season']=='2025-26':r['target_minutes']=999
        with patch('fpl_ai.minutes_oos.collect_rows',return_value=(changed,self.audits,self.sources)):
            out,_,_,_=build_oos(self.features,self.model,output_dir=self.root/'changed_targets')
        self.assertEqual(out.name,self.out.name)
        fields=('season','target_gameweek','element','expected_minutes','model_identity')
        self.assertEqual([[r[k] for k in fields] for r in read_csv(out/'predictions.csv')],
                         [[r[k] for k in fields] for r in read_csv(self.out/'predictions.csv')])
        altered=dict(PROTOCOL,version='semantic-version-test')
        with patch('fpl_ai.minutes_oos.PROTOCOL',altered), patch('fpl_ai.minutes_oos.collect_rows',return_value=(self.rows,self.audits,self.sources)):
            out,_,_,_=build_oos(self.features,self.model,output_dir=self.root/'protocol_change')
        self.assertNotEqual(out.name,self.out.name)

    def test_unknown_discrepancies_fail_closed(self):
        audit={'season':'2025-26','minutes_target_disagreements':[{'element':1}],'cumulative_disagreements':[]}
        with self.assertRaisesRegex(ValueError,'outside exact'):evidence_policy([],{}, {}, {}, set(),audit,{})
        audit['season']='2024-25';audit.update(captures={'27':{'sha256':'wrong'}},settlements={})
        with self.assertRaisesRegex(ValueError,'exception cannot'):evidence_policy([],{}, {}, {}, set(),audit,{'source_identity_sha256':'wrong'})

    def test_exact_exception_never_enters_history_or_becomes_zero(self):
        audit={'season':'2024-25','captures':{'27':{'sha256':EXCEPTION['before_sha256']}},
               'settlements':{'27':{'sha256':EXCEPTION['after_sha256'],'capture_time_utc':EXCEPTION['known_at']}},
               'minutes_target_disagreements':[{'gameweek':27,'element':123,'reason':'minutes target disagrees with independent evidence: GW27: 34 != 17'}],
               'cumulative_disagreements':[{'gameweek':g,'element':123,'observed':304,'canonical':287} for g in range(27,39)]}
        rows=[];players={};targets={};times={}
        for g in range(27,32):
            players[g]={}
            for e in (123,124):
                capture='2025-02-25T12:45:00Z' if g==27 else f'2025-03-{g-20:02}T12:00:00Z'
                rows.append({'season':'2024-25','target_gameweek':g,'element':e,'audit':{'capture_time_utc':capture}})
                players[g][e]={'element_type':4,'minutes':270 if g==27 else 304,'status':'a'}
                if (g,e)!=(27,123):targets[g,e]=21
                times[g,e]=EXCEPTION['known_at'] if g==27 else f'2025-03-{g-20:02}T18:00:00Z'
        result=evidence_policy(rows,players,targets,times,set(players),audit,{'source_identity_sha256':EXCEPTION['source_identity']})
        a=[r for r in result if r['element']==123]
        self.assertIsNone(a[0]['target_minutes']);self.assertIsNone(a[0]['label_available_at'])
        self.assertEqual(a[0]['features']['observed_season_minutes'],270)
        for r in a[1:]:self.assertIsNone(r['features']['observed_season_minutes'])
        self.assertIsNone(a[1]['features']['previous_minutes'])
        self.assertEqual(a[2]['features']['minutes_count_3'],1)
        self.assertEqual(a[2]['features']['previous_minutes'],21)
        self.assertTrue(all(r['features']['observed_season_minutes'] is not None for r in result if r['element']==124))
        targets[27,123]=34
        with self.assertRaisesRegex(ValueError,'never become numeric'):
            evidence_policy(rows,players,targets,times,set(players),audit,{'source_identity_sha256':EXCEPTION['source_identity']})


if __name__=='__main__':unittest.main()
