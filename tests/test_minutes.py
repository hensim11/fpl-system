"""Network-free playing-time evidence, temporal and frozen-model regressions."""
import copy
import json
import pickle
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.features import build_rows
from fpl_ai.historical_io import sha256_file
from fpl_ai.minutes import PROTOCOL, fit, load_rows, matrix, predict, run_minutes
from fpl_ai.playing_time import (CONTRACT, FEATURES, SEASONS, build_playing_time,
                                 construct_rows, evidenced_minutes, feature_values, inspect_season)
from tests.test_modelling import sample


def sample_minutes(season='2021-22'):
    snaps, facts, settled = sample(season)
    year = str(int(season[:4])+1)
    for r in snaps:
        for k in ('capture_time_utc', 'deadline_time_utc'):
            r[k] = year+r[k][4:]
    for r in settled.values():
        r['capture_time_utc'] = year+r['capture_time_utc'][4:]
    base = build_rows(season, snaps, facts, settled)
    observed, targets, evidence = {}, {}, {}
    for gw in range(1,8):
        observed[gw] = {}
        for e in (1,2):
            observed[gw][e] = {'element_type': 2, 'status': 'a', 'chance_of_playing_next_round': None,
                                'minutes': 90*(gw-1) if e==1 else 0, 'starts': None}
            targets[gw,e] = 90 if e==1 else 0
            evidence[gw,e] = settled[gw]['capture_time_utc']
    return base, observed, targets, evidence, set(range(1,8))


def fixture_rows(season):
    return construct_rows(*sample_minutes(season))


def build_fixture(root):
    with patch('fpl_ai.playing_time.inspect_season', side_effect=lambda s,v,d: (fixture_rows(s), {'fixture': True}, {'version': v})):
        return build_playing_time(output_dir=root, builds=dict.fromkeys(SEASONS,'fixture'))[0]


class MinutesEvidenceTests(unittest.TestCase):
    def test_target_and_future_values_do_not_enter_features(self):
        data = sample_minutes()
        before = construct_rows(*data)
        changed = copy.deepcopy(data)
        for (gw,e) in changed[2]:
            if gw >= 4:
                changed[2][gw,e] = 999
        for gw in changed[1]:
            if gw > 4:
                for p in changed[1][gw].values(): p['minutes'] = 9999
        after = construct_rows(*changed)
        self.assertEqual([r['features'] for r in before[:8]], [r['features'] for r in after[:8]])
        self.assertNotEqual(before[6]['target_minutes'], after[6]['target_minutes'])

    def test_delayed_settlement_and_calendar_window(self):
        data = sample_minutes()
        data[3][3,1] = '2022-02-01T00:00:00Z'
        rows = construct_rows(*data)
        self.assertIsNone(rows[6]['features']['previous_minutes'])
        self.assertEqual(rows[8]['features']['minutes_count_3'], 2)
        data[3][3,1] = rows[6]['audit']['capture_time_utc']
        self.assertEqual(construct_rows(*data)[6]['features']['previous_minutes'], 90)

    def test_doubles_blanks_and_globally_empty_gameweek(self):
        base, observed, targets, times, gws = sample_minutes('2022-23')
        targets[3,1] = 180
        targets[3,2] = 0
        gws.remove(7)
        targets = {k:v for k,v in targets.items() if k[0] != 7}
        rows = construct_rows(base, observed, targets, times, gws)
        self.assertEqual(rows[4]['target_minutes'],180)
        self.assertEqual(rows[5]['target_minutes'],0)
        self.assertEqual(rows[6]['features']['previous_minutes'],180)
        self.assertTrue(all(r['target_minutes'] is None for r in rows[-2:]))

    def test_missing_is_not_zero_and_gw1_stale_totals_excluded(self):
        p = {'element_type': 2, 'status': None, 'chance_of_playing_next_round': None, 'minutes': 3000, 'starts': 35}
        f = feature_values(1,p,None,{})
        for name in ('chance','status','observed_season_minutes','observed_season_starts','minutes_mean_3','previous_minutes','status_changed'):
            self.assertIsNone(f[name]);self.assertEqual(f[name+'_missing'],1)
        self.assertEqual(f['minutes_count_3'],0)
        p['minutes']=0
        self.assertEqual(feature_values(2,p,None,{1:0})['previous_minutes'],0)
        self.assertEqual(feature_values(2,p,None,{1:0})['appearance_rate_3'],0)

    def test_consecutive_availability_and_season_local_population(self):
        p = {'element_type':2,'status':'i','chance_of_playing_next_round':25,'minutes':90}
        prior = dict(p,status='a',chance_of_playing_next_round=100)
        f=feature_values(3,p,prior,{})
        self.assertEqual((f['status_changed'],f['chance_change']),(1,-75))
        self.assertIsNone(feature_values(3,p,None,{})['chance_change'])
        data=sample_minutes();del data[1][2][2]
        # No backfill from a later or final identity into missing previous observation.
        row=construct_rows([r for r in data[0] if not (r['target_gameweek']==2 and r['element']==2)],*data[1:])[4]
        self.assertIsNone(row['features']['status_changed'])

    def test_final_fixture_and_forbidden_fields_never_projected(self):
        p={'element_type':2,'status':'a','chance_of_playing_next_round':None,'minutes':90}
        a=feature_values(2,p,None,{})
        p.update(xP=999,ep_next=999,opponent=20,fixture_count=2,kickoff_time='future',final_position=4)
        self.assertEqual(a,feature_values(2,p,None,{}))
        self.assertEqual(set(a),set(FEATURES))

    def test_independent_target_evidence_including_explicit_zero(self):
        self.assertEqual(evidenced_minutes(1,{'minutes':3000},{'minutes':90},90),90)
        self.assertEqual(evidenced_minutes(2,{'minutes':90},{'minutes':270},180),180)
        self.assertEqual(evidenced_minutes(2,{'minutes':0},{'minutes':0},0),0)
        for before,after,expected in [({}, {'minutes':0},0), ({'minutes':0},{},0), ({'minutes':0},{'minutes':False},0), ({'minutes':90},{'minutes':170},90)]:
            with self.assertRaises(ValueError): evidenced_minutes(2,before,after,expected)

    def test_freshness_metadata_and_empty_target_guard(self):
        data=sample_minutes()
        data[0][0]['audit'].update(superseded_deadline_exception=True,snapshot_age_minutes=207,
                                   capture_time_utc='2022-01-03T12:33:00Z',deadline_time_utc='2022-01-03T16:00:00Z')
        r=construct_rows(*data)[0]
        self.assertEqual(r['audit']['snapshot_age_minutes'],207)
        del data[2][1,1]
        with self.assertRaisesRegex(ValueError,'population'): construct_rows(*data)

    def test_consumed_holdout_refused_before_source_loading(self):
        with patch('fpl_ai.playing_time.load_season') as load:
            for season in ('2024-25','2025-26'):
                with self.assertRaises(ValueError): inspect_season(season,'unused',Path('unused'))
            with self.assertRaises(ValueError): inspect_season('2025-26','unused',Path('unused'),False)
            load.assert_not_called()


class MinutesModelTests(unittest.TestCase):
    def test_train_only_fit_and_development_labels_cannot_change_model(self):
        rows=sum((fixture_rows(s) for s in SEASONS),[])
        a,frozen=fit(rows)
        changed=copy.deepcopy(rows)
        for r in changed:
            if r['season']=='2023-24':r['target_minutes']=999
        b,again=fit(changed)
        self.assertEqual(pickle.dumps(a),pickle.dumps(b));self.assertEqual(frozen,again)
        self.assertFalse(PROTOCOL['downstream_training_allowed'])
        self.assertFalse(PROTOCOL['candidate']['early_stopping'])
        self.assertEqual(frozen['training_rows'],28)

    def test_temporal_fit_boundary_and_exact_seasons(self):
        rows=sum((fixture_rows(s) for s in SEASONS),[])
        rows[0]['label_available_at']='2024-12-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'settled'):fit(rows)
        rows[-1]['season']='2025-26'
        with self.assertRaisesRegex(ValueError,'seasons'):fit(rows)

    def test_null_processing_integer_float_categories_and_no_upper_clip(self):
        rows=sum((fixture_rows(s) for s in SEASONS),[])
        model,frozen=fit(rows)
        changed=copy.deepcopy(rows[:1]);changed[0]['features']['position']=2.0
        self.assertEqual(matrix(rows[:1]).tolist(),matrix(changed).tolist())
        changed[0]['features']['status']='unseen'
        self.assertTrue(np.isfinite(model.predict(matrix(changed))).all())
        changed[0]['features']['minutes_mean_3']=180
        predictions=predict(changed,model,frozen)
        self.assertEqual(predictions[0]['recent_minutes'],180)
        self.assertEqual(predictions[0]['availability_recent'],180)
        self.assertIsNone(changed[0]['features']['chance'])

    def test_publication_replay_freeze_only_development_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);features=build_fixture(root/'features')
            rows=load_rows(features);self.assertEqual(len(rows),42)
            a,_=run_minutes(features,root/'models');b,_=run_minutes(features,root/'fresh')
            self.assertEqual(a.name,b.name)
            before={p.name:(sha256_file(p),p.stat().st_mtime_ns) for p in a.iterdir()}
            self.assertTrue(run_minutes(features,root/'models')[1])
            self.assertEqual(before,{p.name:(sha256_file(p),p.stat().st_mtime_ns) for p in a.iterdir()})
            self.assertNotIn('2021-22',(a/'predictions.csv').read_text())
            (a/'model.pickle').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'checksum'):verify_bundle(a)

    def test_nonfinite_model_output_is_not_hidden_by_lower_bound(self):
        from unittest.mock import Mock
        rows = fixture_rows('2021-22')[:1]
        model = Mock()
        model.predict.return_value = np.array([float('nan')])
        with self.assertRaisesRegex(ValueError, 'raw minutes'):
            predict(rows, model, {'position_means': {'2': 40}, 'overall_mean': 40})

    def test_closed_artifacts_failure_cleanup_and_optimized_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):publish(tmp,{'kind':'minutes-freeze'},lambda p:(p/'frozen.json').write_text('{}'))
            self.assertEqual(list(Path(tmp).iterdir()),[])
        code="from fpl_ai.playing_time import evidenced_minutes; evidenced_minutes(2, {'minutes': 0}, {}, 0)"
        for flags in ([],['-O']):
            p=subprocess.run([sys.executable,*flags,'-c',code],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0);self.assertIn('explicit cumulative evidence',p.stderr)


class HistoricalScheduleEvidenceTests(unittest.TestCase):
    """Exercise the adapter/verifier boundary with independently mutable tables."""
    def inputs(self, root, blank=False):
        from types import SimpleNamespace
        from fpl_ai.historical_io import atomic_write_csv
        base, observed, targets, times, gws = sample_minutes('2022-23')
        schedule=[{'season':'2022-23','fixture':g,'gameweek':g} for g in range(1,8) if not (blank and g==7)]
        facts=[{'season':'2022-23','fixture':g,'gameweek':g,'element':e,
                'position_at_fixture':'DEF','minutes':90 if e==1 else 0}
               for g in range(1,8) for e in (1,2) if not (blank and g==7)]
        payloads={};settlements={};gameweeks=[]
        for g in range(1,8):
            before=f'cache/2023/1/{g*3:02}/1000.json.xz'
            after=f'cache/2023/1/{g*3+1:02}/1200.json.xz'
            for r in base:
                if r['target_gameweek']==g:r['audit']['snapshot_source_path']=before
            payloads[before]={'elements':[dict(p,id=e) for e,p in observed[g].items()]}
            payloads[after]={'events':[{'id':g,'finished':True,'data_checked':True}],
                             'elements':[dict(p,id=e,minutes=(90*g if e==1 else 0)) for e,p in observed[g].items()]}
            gameweeks.append({'gameweek':g,'selected_snapshot_capture_time_utc':base[(g-1)*2]['audit']['capture_time_utc'],
                              'deadline_time_utc':base[(g-1)*2]['audit']['deadline_time_utc']})
            if not (blank and g==7):settlements[g]={'source_path':after,'sha256':'b'*64,'capture_time_utc':times[g,1]}
        source={'version':'fixture','source_identity_sha256':'a'*64,'build_identity_sha256':'b'*64,
                'consumed_tables':{},'settlements':settlements,'snapshot_exception':None}
        for name,rows in [('fixtures.csv',schedule),('player_fixture_facts.csv',facts),('gameweeks.csv',gameweeks)]:
            atomic_write_csv(root/name,rows,list(rows[0]))
        return base,source,SimpleNamespace(processed_dir=root),payloads

    def inspect(self, root, evidence):
        base,source,build,payloads=evidence
        with patch('fpl_ai.playing_time.load_season',return_value=(base,source)), \
             patch('fpl_ai.playing_time.load_historical_build',return_value=build), \
             patch('fpl_ai.playing_time.raw_payload',side_effect=lambda b,r:payloads[r['source_path']]):
            return inspect_season('2022-23','fixture',root)

    def remove_facts(self,root,gw):
        from fpl_ai.modelling import read_csv
        from fpl_ai.historical_io import atomic_write_csv
        p=root/'player_fixture_facts.csv';rows=read_csv(p)
        atomic_write_csv(p,[r for r in rows if int(r['gameweek'])!=gw],list(rows[0]))

    def test_missing_whole_scheduled_gw_is_not_a_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self.inputs(root)
            schedule=(root/'fixtures.csv').read_bytes()
            self.remove_facts(root,3)
            with self.assertRaisesRegex(ValueError,'scheduled fixtures lack player facts'):
                self.inspect(root,evidence)
            self.assertEqual(schedule,(root/'fixtures.csv').read_bytes())

    def test_missing_one_double_fixture_also_fails(self):
        from fpl_ai.modelling import read_csv
        from fpl_ai.historical_io import atomic_write_csv
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self.inputs(root)
            p=root/'fixtures.csv';rows=read_csv(p)
            rows.append(dict(rows[2],fixture='99'))
            atomic_write_csv(p,rows,list(rows[0]))
            with self.assertRaisesRegex(ValueError,'scheduled fixtures lack player facts'):
                self.inspect(root,evidence)

    def test_schedule_establishes_gw7_blank_and_explicit_player_zeros(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);evidence=self.inputs(root,blank=True)
            rows,audit,source=self.inspect(root,evidence)
            self.assertTrue(all(r['target_minutes'] is None for r in rows if r['target_gameweek']==7))
            self.assertTrue(all(r['target_minutes']==0 for r in rows if r['element']==2 and r['target_gameweek']!=7))
            self.assertEqual(source['consumed_tables']['fixtures.csv'],sha256_file(root/'fixtures.csv'))
            self.assertFalse(any('fixture' in f for f in rows[0]['features']))

    def test_verifier_rejects_fact_derived_false_blank_independently(self):
        from scripts.verify_minutes import independent_checks
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);base,source,build,payloads=self.inputs(root)
            self.remove_facts(root,3)
            (root/'sources.json').write_text(json.dumps({'2022-23':source}))
            (root/'evidence.json').write_text('{}')
            # Simulate a self-consistent circular artifact with null targets for GW3.
            for r in base:
                if r['target_gameweek']==3:r['target_minutes']=None
            with patch('scripts.verify_minutes.SEASONS',('2022-23',)), \
                 patch('scripts.verify_minutes.load_rows',return_value=base), \
                 patch('scripts.verify_minutes.load_historical_build',return_value=build):
                with self.assertRaisesRegex(ValueError,'independent audit: scheduled fixtures missing player facts'):
                    independent_checks(root,root)


if __name__=='__main__':unittest.main()
