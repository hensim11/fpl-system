import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fpl_ai.features import build_rows
from fpl_ai.evaluation import evaluate, predict_baselines, spearman
from fpl_ai.modelling import run_modelling
from fpl_ai.modelling_contract import FEATURES, STATE_FIELDS, SPLITS, split_for


def sample(season='2021-22'):
    snaps, facts, settled = [], [], {}
    for gw in range(1, 8):
        for element in (1,2):
            snap = dict.fromkeys(STATE_FIELDS, '0')
            snap.update(season=season, gameweek=str(gw), element=str(element),
                        deadline_position_id='2', deadline_position='DEF', player_code=str(element),
                        price='50', status='a', chance_of_playing_next_round='',
                        expected_points_next_gameweek='2.5',
                        capture_time_utc=f'2022-01-{gw*3:02}T10:00:00Z',
                        deadline_time_utc=f'2022-01-{gw*3:02}T12:00:00Z',
                        source_path='snapshot', source_sha256='a'*64)
            snaps.append(snap)
            facts.append(dict(season=season, gameweek=str(gw), element=str(element),
                              fixture=str(gw), total_points=str(gw*element), position_at_fixture='DEF'))
        settled[gw] = {'capture_time_utc': f'2022-01-{gw*3+1:02}T12:00:00Z',
                       'points': {1:gw,2:gw*2}}
    return snaps, facts, settled


class FeatureTests(unittest.TestCase):
    def rows(self, data=None, season='2021-22'):
        return build_rows(season, *(data or sample(season)))

    def test_target_and_future_mutations_cannot_change_features(self):
        original = self.rows()
        s,f,e = sample()
        for r in f:
            if int(r['gameweek']) >= 4:
                r['total_points'] = '999'
                e[int(r['gameweek'])]['points'][int(r['element'])] = 999
        mutated = self.rows((s,f,e))
        self.assertEqual([r['features'] for r in original[:8]], [r['features'] for r in mutated[:8]])
        self.assertNotEqual(original[6]['target_points'], mutated[6]['target_points'])

    def test_calendar_windows_lag_and_missing_not_zero(self):
        s,f,e = sample()
        e[3]['capture_time_utc'] = '2022-02-01T00:00:00Z'
        rows = self.rows((s,f,e))
        r = rows[8]['features']  # GW5: calendar window GW2..4, GW3 unknown
        self.assertEqual(r['points_mean_3'], 3)
        self.assertEqual(r['points_count_3'], 2)
        self.assertEqual(r['previous_points'], 4)
        self.assertIsNone(rows[0]['features']['previous_points'])
        self.assertEqual(rows[0]['features']['previous_points_missing'], 1)
        self.assertIsNone(rows[0]['features']['chance_of_playing_next_round'])
        self.assertEqual(rows[0]['features']['transfers_in_event'], 0)

    def test_double_aggregation_no_first_fixture_leak(self):
        s,f,e = sample()
        before = self.rows((s,f,e))
        f.append(dict(f[4], fixture='100', total_points='12'))
        e[3]['points'][1] += 12
        after = self.rows((s,f,e))
        self.assertEqual(after[4]['target_points'], 15)
        self.assertEqual(before[4]['features'], after[4]['features'])
        self.assertEqual(after[6]['features']['previous_points'], 15)

    def test_season_state_reset_and_observed_code_changes(self):
        s,f,e = sample('2022-23')
        s[0]['player_code'] = '536122'
        s[2]['player_code'] = '515024'
        rows = self.rows((s,f,e), '2022-23')
        self.assertIsNone(rows[0]['features']['season_points_mean'])
        self.assertEqual(rows[2]['features']['previous_points'], 1)
        self.assertEqual(rows[0]['audit']['observed_player_code'], '536122')

    def test_empty_gw_and_missing_player_sum(self):
        s,f,e = sample()
        f = [r for r in f if r['gameweek'] != '2' and not (r['gameweek']=='1' and r['element']=='2')]
        e[1]['points'][2] = 0
        rows = self.rows((s,f,e))
        self.assertEqual(rows[1]['target_points'], 0)
        self.assertIsNone(rows[2]['target_points'])
        self.assertIsNone(rows[4]['features']['previous_points'])
        self.assertEqual(rows[4]['features']['points_count_3'], 1)

    def test_closed_allowlist_and_am_exclusion(self):
        s,f,e = sample()
        for r in s:
            r.update(xP='900', value='900', opponent_team_id_at_fixture='20', expected_goals='99')
        s.append(dict(s[0], element='99', deadline_position_id='5', deadline_position='AM'))
        f.append(dict(f[0], element='99', position_at_fixture='AM', total_points='1000'))
        rows = self.rows((s,f,e))
        self.assertEqual(len(rows), 14)
        self.assertTrue(all(set(r['features']) == set(FEATURES) for r in rows))
        self.assertTrue(all('external_ep_next' not in r['features'] for r in rows))

    def test_exception_metadata_retained(self):
        s,f,e = sample()
        exception = {'gameweek': 1, 'payload_deadline_utc': '2022-01-03T11:00:00Z'}
        rows = build_rows('2021-22',s,f,e,exception)
        self.assertTrue(rows[0]['audit']['superseded_deadline_exception'])
        self.assertEqual(rows[0]['audit']['snapshot_age_minutes'],120)
        self.assertEqual(rows[0]['audit']['payload_deadline_utc'],exception['payload_deadline_utc'])

    def test_invalid_keys_times_and_settlement_fail(self):
        for case in ('duplicate_snapshot','duplicate_fact','late','mismatch'):
            with self.subTest(case=case):
                s,f,e = sample()
                if case == 'duplicate_snapshot': s.append(s[0])
                if case == 'duplicate_fact': f.append(f[0])
                if case == 'late': s[0]['capture_time_utc'] = s[0]['deadline_time_utc']
                if case == 'mismatch': e[1]['points'][1] = 100
                with self.assertRaises(ValueError): self.rows((s,f,e))

    def test_settlement_at_capture_allowed_later_not_allowed(self):
        s,f,e = sample()
        e[1]['capture_time_utc'] = s[2]['capture_time_utc']
        self.assertEqual(self.rows((s,f,e))[2]['features']['previous_points'],1)
        e[1]['capture_time_utc'] = '2022-01-06T10:00:01Z'
        self.assertIsNone(self.rows((s,f,e))[2]['features']['previous_points'])


class EvaluationTests(unittest.TestCase):
    def test_splits_and_holdout_not_fitted(self):
        rows = []
        for season in SPLITS:
            s,f,e = sample(season)
            # Give each season chronological timestamps.
            year = str(int(season[:4])+1)
            for r in s:
                for key in ('capture_time_utc','deadline_time_utc'):
                    r[key] = year+r[key][4:]
            for r in e.values(): r['capture_time_utc'] = year+r['capture_time_utc'][4:]
            rows.extend(build_rows(season,s,f,e))
        original = predict_baselines(rows)
        changed = copy.deepcopy(rows)
        for r in changed:
            if r['split'] != 'train': r['target_points'] = 1000000
        self.assertEqual(original,predict_baselines(changed))
        for s in SPLITS: self.assertEqual(split_for(s),SPLITS[s])
        with self.assertRaises(ValueError): split_for('2026-27')
        self.assertEqual(original[('2021-22',1,1)]['historical_mean'],0)
        self.assertEqual(original[('2021-22',2,1)]['historical_mean'],1.5)

    def test_metrics_ties_coverage_and_empty_labels(self):
        self.assertAlmostEqual(spearman([1,1,3],[2,2,4]),1)
        self.assertIsNone(spearman([1,2],[1,1]))
        rows = build_rows('2021-22',*sample())[:2]
        rows[0]['target_points'],rows[1]['target_points'] = 1,3
        preds = {('2021-22',1,1):{'custom':2},('2021-22',1,2):{'custom':None}}
        m = evaluate(rows,preds,('custom',))['train']['overall']['custom']
        self.assertEqual((m['mae'],m['rmse'],m['prediction_coverage']),(1,1,0.5))
        with self.assertRaises(ValueError): evaluate(rows,{},('custom',))

    def test_deterministic_publication_reuse_and_corruption(self):
        def adapter(season,version,data_dir):
            return build_rows(season,*sample(season)), {'version':version}
        with tempfile.TemporaryDirectory() as tmp, patch('fpl_ai.modelling.load_season',side_effect=adapter):
            builds = dict.fromkeys(SPLITS,'synthetic')
            a,reused = run_modelling(output_dir=Path(tmp)/'a',builds=builds)
            self.assertFalse(reused)
            b,_ = run_modelling(output_dir=Path(tmp)/'b',builds=builds)
            self.assertEqual({p.name:p.read_bytes() for p in a.iterdir()},
                             {p.name:p.read_bytes() for p in b.iterdir()})
            mtimes = {p.name:p.stat().st_mtime_ns for p in a.iterdir()}
            self.assertTrue(run_modelling(output_dir=Path(tmp)/'a',builds=builds)[1])
            self.assertEqual(mtimes,{p.name:p.stat().st_mtime_ns for p in a.iterdir()})
            (a/'features.csv').write_text('corrupt')
            with self.assertRaises(ValueError): run_modelling(output_dir=Path(tmp)/'a',builds=builds)


class AdapterTests(unittest.TestCase):
    def test_real_historical_adapter_and_raw_checksum_guard(self):
        from tests.test_historical_pipeline import HistoricalPipelineTests
        from fpl_ai.modelling import load_season
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build, _, _ = HistoricalPipelineTests().run_synthetic(root)
            rows, source = load_season('2024-25',build.version,root/'data')
            self.assertEqual(len(rows),4)
            first = next(r for r in rows if r['target_gameweek']==1 and r['element']==101)
            self.assertEqual(first['target_points'],2)
            record = next(iter(source['settlements'].values()))
            raw = build.raw_dir/'fplcache'/record['source_path']
            raw.write_bytes(b'corrupted settlement')
            from fpl_ai.errors import FPLValidationError
            with self.assertRaises(FPLValidationError):
                load_season('2024-25',build.version,root/'data')

    def test_benchmark_and_future_state_never_enter_features(self):
        s,f,e = sample()
        before = build_rows('2021-22',s,f,e)
        for r in s:
            r['expected_points_next_gameweek']='9999'
            if int(r['gameweek'])>3:
                r['price']='999'
                r['deadline_team_id']='20'
        after = build_rows('2021-22',s,f,e)
        self.assertEqual([r['features'] for r in before[:6]], [r['features'] for r in after[:6]])
        self.assertNotEqual(before[0]['external_ep_next'],after[0]['external_ep_next'])


class HardeningTests(unittest.TestCase):
    def test_empty_player_target_requires_matching_integer_settlement(self):
        # Use final GW so a later history check cannot mask missing target validation.
        for value in (0, None, 4, False, 0.0, '0'):
            with self.subTest(value=value):
                s,f,e = sample()
                f = [r for r in f if not (r['gameweek']=='7' and r['element']=='2')]
                if value is None:
                    del e[7]['points'][2]
                else:
                    e[7]['points'][2] = value
                if type(value) is int and value == 0:
                    rows = build_rows('2021-22',s,f,e)
                    self.assertEqual(rows[-1]['target_points'],0)
                    self.assertEqual(rows[-1]['audit']['label_status'],'empty_player_sum')
                else:
                    with self.assertRaisesRegex(ValueError, 'target'):
                        build_rows('2021-22',s,f,e)

    def test_fixture_target_disagreement_and_absent_settlement_fail(self):
        for mode in ('mismatch','missing'):
            with self.subTest(mode=mode):
                s,f,e = sample()
                if mode == 'mismatch': e[7]['points'][2] = 100
                else: del e[7]
                with self.assertRaisesRegex(ValueError, 'target'):
                    build_rows('2021-22',s,f,e)

    def test_content_change_with_unchanged_metadata_changes_identity(self):
        def adapter(season,version,data_dir):
            return build_rows(season,*sample(season)), {'version':version}
        builds = dict.fromkeys(SPLITS,'synthetic')
        with tempfile.TemporaryDirectory() as tmp:
            with patch('fpl_ai.modelling.load_season',side_effect=adapter):
                first,_ = run_modelling(output_dir=tmp,builds=builds)
            def changed(season,version,data_dir):
                rows,metadata = adapter(season,version,data_dir)
                rows[0]['features']['price'] += 1
                return rows,metadata
            with patch('fpl_ai.modelling.load_season',side_effect=changed):
                second,reused = run_modelling(output_dir=tmp,builds=builds)
            self.assertFalse(reused)
            self.assertNotEqual(first,second)
            self.assertNotEqual((first/'features.csv').read_bytes(),(second/'features.csv').read_bytes())

    def test_serialization_change_changes_identity(self):
        from fpl_ai.modelling import atomic_write_csv
        def adapter(season,version,data_dir):
            return build_rows(season,*sample(season)), {'version':version}
        def different_serializer(path,rows,columns):
            atomic_write_csv(path,rows,columns)
            path.write_bytes(path.read_bytes().replace(b'\r\n',b'\n'))
        with tempfile.TemporaryDirectory() as tmp, patch('fpl_ai.modelling.load_season',side_effect=adapter):
            builds = dict.fromkeys(SPLITS,'synthetic')
            first,_ = run_modelling(output_dir=tmp,builds=builds)
            with patch('fpl_ai.modelling.atomic_write_csv',side_effect=different_serializer):
                second,reused = run_modelling(output_dir=tmp,builds=builds)
            self.assertFalse(reused)
            self.assertNotEqual(first,second)

    def test_reuse_rejects_incomplete_extra_and_corrupt_artifacts(self):
        import json
        def adapter(season,version,data_dir):
            return build_rows(season,*sample(season)), {'version':version}
        for mode in ('removed_checksum','missing_file','extra_file','extra_manifest_entry','corruption'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp, patch('fpl_ai.modelling.load_season',side_effect=adapter):
                builds = dict.fromkeys(SPLITS,'synthetic')
                path,_ = run_modelling(output_dir=tmp,builds=builds)
                manifest_path = path/'manifest.json'
                manifest = json.loads(manifest_path.read_text())
                if mode == 'removed_checksum':
                    del manifest['artifacts']['features.csv']
                    manifest_path.write_text(json.dumps(manifest))
                elif mode == 'extra_manifest_entry':
                    manifest['artifacts']['unexpected.csv'] = 'a'*64
                    manifest_path.write_text(json.dumps(manifest))
                elif mode == 'missing_file': (path/'features.csv').unlink()
                elif mode == 'extra_file': (path/'unexpected.csv').write_text('extra')
                else: (path/'features.csv').write_text('corrupt')
                with self.assertRaises(ValueError):
                    run_modelling(output_dir=tmp,builds=builds)

    def test_verification_failure_remains_active_under_optimized_python(self):
        import subprocess
        import sys
        import textwrap
        code = textwrap.dedent('''
            import json
            import tempfile
            from pathlib import Path
            from unittest.mock import patch
            from scripts.verify_modelling import verify
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'historical/processed').mkdir(parents=True)
                (root/'historical/catalogue.json').write_text('{}')
                model = root/'model'
                model.mkdir()
                (model/'manifest.json').write_text(json.dumps({'identity':{'sources':{}}}))
                # Intentionally claim a fresh temporary output was reused.
                with patch('scripts.verify_modelling.run_modelling',return_value=(model,True)):
                    verify(root)
        ''')
        for flags in ([],['-O']):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable,*flags,'-c',code],cwd=Path(__file__).resolve().parents[1],
                                        capture_output=True,text=True)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('VerificationError: fresh temporary build unexpectedly reused artifacts',result.stderr)
