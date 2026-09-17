import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits

from fpl_ai.experiment_io import load_rows, publish, verify_bundle, verify_m3
from fpl_ai.experiments import (CONFIGS, MODEL_FEATURES, NUMERIC, PROTOCOL, fit_candidates,
                                make_pipeline, matrix, run_holdout, run_validation, select_model)
from fpl_ai.features import build_rows
from fpl_ai.modelling import run_modelling
from fpl_ai.modelling_contract import SPLITS
from tests.test_modelling import sample


def adapter(season,version,data_dir):
    s,f,e = sample(season)
    year = str(int(season[:4])+1)
    for r in s:
        for name in ('capture_time_utc','deadline_time_utc'): r[name] = year+r[name][4:]
    for r in e.values(): r['capture_time_utc'] = year+r['capture_time_utc'][4:]
    return build_rows(season,s,f,e), {'version':version}


class ExperimentTests(unittest.TestCase):
    def rows(self):
        return sum([adapter(s,'synthetic',None)[0] for s in SPLITS if SPLITS[s] != 'test'],[])

    def m3(self,root):
        with patch('fpl_ai.modelling.load_season',side_effect=adapter):
            return run_modelling(output_dir=root,builds=dict.fromkeys(SPLITS,'synthetic'))[0]

    def test_matrix_is_closed_and_audit_target_keys_are_excluded(self):
        rows = self.rows()
        before = matrix(rows)
        for r in rows:
            r['target_points'] = 999999
            r['element'] = 88888
            r['audit']['observed_player_code'] = 'future'
        np.testing.assert_array_equal(before.astype(str),matrix(rows).astype(str))
        rows[0]['features']['ep_next'] = 999
        with self.assertRaisesRegex(ValueError,'allowlist'): matrix(rows)
        self.assertNotIn('deadline_team_id',MODEL_FEATURES)

    def test_validation_cannot_change_fits_and_test_is_rejected(self):
        rows = self.rows()
        a = fit_candidates(rows)
        changed = copy.deepcopy(rows)
        for r in changed:
            if r['split']=='validation':
                r['target_points'] = -100000
                r['features']['price'] = 100000
                r['features']['status'] = 'unseen'
        b = fit_candidates(changed)
        x = matrix(rows)
        with threadpool_limits(limits=1):
            for n in a: np.testing.assert_array_equal(a[n].predict(x),b[n].predict(x))
        with self.assertRaisesRegex(ValueError,'test rows'):
            fit_candidates(rows+adapter('2025-26','synthetic',None)[0])

    def test_training_settlement_and_unlabelled_fit_boundaries(self):
        rows = self.rows()
        rows[0]['label_available_at'] = '2099-01-01T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'settled'): fit_candidates(rows)
        rows[0]['target_points'] = None
        models = fit_candidates(rows)
        pre = models['ridge_10']['preprocess']['numeric']['scale']
        self.assertEqual(pre.n_samples_seen_,41)

    def test_imputation_scaling_unknown_category_and_flags(self):
        rows = self.rows()[:14]
        rows[0]['features']['price'] = None
        rows[0]['features']['price_missing'] = 1
        x = matrix(rows)
        with threadpool_limits(limits=1):
            model = make_pipeline(CONFIGS['ridge_10']).fit(x,np.arange(len(x)))
            imputer = model['preprocess']['numeric']['impute']
            self.assertEqual(imputer.statistics_[NUMERIC.index('price')],50)
            # Chance is all-null in this train fixture: retained, not silently dropped.
            self.assertEqual(imputer.statistics_[NUMERIC.index('chance_of_playing_next_round')],0)
            altered = copy.deepcopy(rows[:1])
            altered[0]['features']['status'] = 'unseen'
            transformed = model['preprocess'].transform(matrix(altered))
            self.assertTrue(np.isfinite(transformed.astype(float)).all())
            self.assertEqual(transformed[0,len(NUMERIC)+list(f for f in MODEL_FEATURES if f.endswith('_missing')).index('price_missing')],1)
            self.assertTrue(np.isfinite(model.predict(matrix(altered))).all())
            self.assertNotIn('unseen',model['preprocess']['categorical'].categories_[1])

    def test_primary_selection_is_rmse_with_deterministic_ties(self):
        report = {'overall':{n:{'rmse':2,'mae':0} for n in CONFIGS}}
        report['overall']['ridge_100']['rmse'] = 1
        self.assertEqual(select_model(report),'ridge_100')
        report['overall']['ridge_10']['rmse'] = 1
        self.assertEqual(select_model(report),'ridge_10')
        self.assertFalse(PROTOCOL['nonlinear']['early_stopping'])

    def test_m3_integrity_and_population_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.m3(tmp)
            verify_m3(path)
            rows,preds = load_rows(path,('validation',))
            self.assertEqual(len(rows),14)
            self.assertEqual(set(preds),{(r['season'],r['target_gameweek'],r['element']) for r in rows})
            with (path/'labels.csv').open('a') as f: f.write('corrupt\n')
            with self.assertRaisesRegex(ValueError,'checksum'): verify_m3(path)

    def test_stage_filter_does_not_parse_test_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.m3(tmp)
            p=path/'labels.csv'
            lines=p.read_text().splitlines()
            # Deliberately unverified fixture tests the adapter's stage boundary.
            p.write_text('\n'.join(line.replace(',test,',',test,not-a-number') if line.startswith('2025-26,') else line for line in lines)+'\n')
            load_rows(path,('train','validation'))
            with self.assertRaises(ValueError): load_rows(path,('test',))

    def test_artifact_reuse_corruption_and_exact_set(self):
        for mode in ('extra','missing','corrupt','manifest'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
                def writer(folder): (folder/'result.txt').write_text('stable')
                path,reused = publish(tmp,{'kind':'fixture'},writer)
                before = {p.name:p.stat().st_mtime_ns for p in path.iterdir()}
                self.assertTrue(publish(tmp,{'kind':'fixture'},writer)[1])
                self.assertEqual(before,{p.name:p.stat().st_mtime_ns for p in path.iterdir()})
                if mode=='extra': (path/'unexpected').write_text('x')
                elif mode=='missing': (path/'result.txt').unlink()
                elif mode=='corrupt': (path/'result.txt').write_text('changed')
                else:
                    m=json.loads((path/'manifest.json').read_text());m['metadata']['kind']='changed'
                    (path/'manifest.json').write_text(json.dumps(m))
                with self.assertRaises(ValueError): publish(tmp,{'kind':'fixture'},writer)

    def test_complete_freeze_holdout_reproduction_and_no_refit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); m3=self.m3(root/'m3')
            freeze,_=run_validation(m3,root/'validation')
            again,_=run_validation(m3,root/'fresh')
            self.assertEqual(freeze.name,again.name)
            frozen=json.loads((freeze/'frozen.json').read_text())
            self.assertFalse(frozen['holdout_evaluated'])
            self.assertEqual(frozen['training_rows'],42)
            with patch('fpl_ai.experiments.fit_candidates',side_effect=AssertionError('holdout must never fit')):
                holdout,_=run_holdout(m3,freeze,root/'holdout')
                repeat,_=run_holdout(m3,freeze,root/'repeat')
            self.assertEqual(holdout.name,repeat.name)
            scores=json.loads((holdout/'holdout.json').read_text())['overall']
            self.assertEqual(set(scores)&set(CONFIGS),{frozen['selected']})
            with self.assertRaises(ValueError): run_holdout(m3,holdout,root/'bad')

    def test_changed_content_gets_different_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,_=publish(tmp,{'kind':'fixture'},lambda p:(p/'x').write_text('a'))
            b,_=publish(tmp,{'kind':'fixture'},lambda p:(p/'x').write_text('b'))
            self.assertNotEqual(a,b)

    def test_closed_stage_artifacts_and_directory_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'artifact set'):
                publish(tmp,{'kind':'frozen-holdout'},lambda p:(p/'holdout.json').write_text('{}'))
        with tempfile.TemporaryDirectory() as tmp:
            path,_=publish(tmp,{'kind':'fixture'},lambda p:(p/'x').write_text('a'))
            renamed=path.with_name('wrong');path.rename(renamed)
            with self.assertRaisesRegex(ValueError,'directory identity'): verify_bundle(renamed)

    def test_cli_requires_freeze_and_rejects_ingestion_options(self):
        from fpl_ai.cli import main
        import contextlib
        import io
        for args in (['experiment','holdout','--m3-dir','missing'],
                     ['--output-dir','wrong','experiment','validate','--m3-dir','missing'],
                     ['experiment','validate','--m3-dir','missing','--frozen-dir','wrong']):
            with self.subTest(args=args),contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc: main(args)
                self.assertEqual(exc.exception.code,2)

    def test_verification_checks_remain_active_under_optimization(self):
        import subprocess
        import sys
        for flags in ([],['-O']):
            completed=subprocess.run([sys.executable,*flags,'-c',
                "from scripts.verify_experiments import require; require(False, 'deliberate failure')"],
                capture_output=True,text=True)
            self.assertNotEqual(completed.returncode,0)
            self.assertIn('deliberate failure',completed.stderr)
