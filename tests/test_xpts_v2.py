"""Focused downstream leakage boundaries, missingness and ranking semantics."""
import pickle
import unittest

import numpy as np
from threadpoolctl import threadpool_limits

from fpl_ai.experiments import MODEL_FEATURES, matrix as m4_matrix, make_pipeline, CONFIGS
from fpl_ai.modelling_contract import FEATURES
from fpl_ai.xpts_v2 import (EXTRA, STATE_FIELDS, fit_models, indexed, join_rows,
                            labels_for, model_bytes, model_matrix, pipeline, top10)


def fixture(n=60):
    rows, forecasts, audits = [], {}, {}
    for e in range(1,n+1):
        a = {f:'' for f in STATE_FIELDS}
        a.update(capture_time_utc='2024-08-16T12:38:00Z',deadline_time_utc='2024-08-16T17:30:00Z')
        f = {name:0 for name in FEATURES}
        f.update(deadline_position_id=1+e%4, status='a', price=45+e%30, points_mean_3=e%7)
        r = {'season':'2024-25','target_gameweek':1,'element':e,'features':f,'audit':a,
             'target_points':e%8,'label_available_at':'2024-08-20T06:00:00Z'}
        k = ('2024-25',1,e)
        rows.append(r);audits[k]=a.copy()
        forecasts[k] = dict(zip(('season','target_gameweek','element'),k),
            prediction_class='chronological_oos', downstream_training_allowed='True', unavailable_reason='',
            prediction_capture=a['capture_time_utc'], training_cutoff='2024-05-20T06:25:00Z',
            selection_cutoff='2024-05-20T06:25:00Z',expected_minutes=str(e%91),model_identity='model',feature_identity='features')
    return rows,forecasts,audits


class XptsTests(unittest.TestCase):
    def test_exact_state_required_beyond_keys(self):
        for field in STATE_FIELDS:
            rows,ps,aa=fixture(1);aa[('2024-25',1,1)][field]='different'
            with self.assertRaisesRegex(ValueError,'decision-time'):join_rows(rows,ps,aa)

    def test_duplicate_keys_rejected(self):
        rows,_,_=fixture(1)
        with self.assertRaisesRegex(ValueError,'duplicate'):indexed(rows+rows)

    def test_missing_minutes_excluded_without_fallback(self):
        rows,ps,aa=fixture(2);del ps[('2024-25',1,1)]
        f,a=join_rows(rows,ps,aa)
        self.assertIsNone(f[0][EXTRA]);self.assertFalse(a[0]['eligible'])
        self.assertEqual(a[0]['unavailable_reason'],'missing_oos_minutes')
        with self.assertRaisesRegex(ValueError,'cannot fall back'):model_matrix(f,'xpts_v2')
        models,state,_=fit_models(f,labels_for(rows),a,'2025-08-15T12:52:00Z')
        self.assertEqual(state['training_rows'],1)

    def test_missing_points_independent_of_prediction(self):
        rows,ps,aa=fixture(1);rows[0]['target_points']=None;rows[0]['label_available_at']=''
        f,a=join_rows(rows,ps,aa)
        self.assertEqual(f[0][EXTRA],1)
        self.assertEqual(a[0]['unavailable_reason'],'missing_points_label')
        self.assertNotIn('target_points',f[0]);self.assertNotIn('target_minutes',f[0])

    def test_wrong_prediction_class_and_eligibility_rejected(self):
        for field,value in [('prediction_class','development'),('prediction_class','prospective'),
                            ('downstream_training_allowed','False'),('unavailable_reason','no_history')]:
            rows,ps,aa=fixture(1);ps[('2024-25',1,1)][field]=value
            with self.assertRaisesRegex(ValueError,'ineligible'):join_rows(rows,ps,aa)

    def test_cutoffs_strict_and_values_finite(self):
        for field in ('training_cutoff','selection_cutoff'):
            rows,ps,aa=fixture(1);ps[('2024-25',1,1)][field]=rows[0]['audit']['capture_time_utc']
            with self.assertRaisesRegex(ValueError,'chronology'):join_rows(rows,ps,aa)
        for value in ('nan','inf','-1'):
            rows,ps,aa=fixture(1);ps[('2024-25',1,1)]['expected_minutes']=value
            with self.assertRaisesRegex(ValueError,'invalid OOS'):join_rows(rows,ps,aa)
        rows,ps,aa=fixture(1);rows[0]['audit']['deadline_time_utc']=rows[0]['audit']['capture_time_utc']
        aa[('2024-25',1,1)]=rows[0]['audit'].copy()
        with self.assertRaisesRegex(ValueError,'chronology'):join_rows(rows,ps,aa)

    def test_forbidden_features_rejected(self):
        for field in ('target_points','target_minutes','minutes','xP','ep_next','opponent','kickoff_time','actual_future_minutes','m4b_prediction'):
            rows,ps,aa=fixture(1);f,a=join_rows(rows,ps,aa);f[0][field]=0
            with self.assertRaisesRegex(ValueError,'allowlist'):model_matrix(f,'xpts_v2')
            rows[0]['features'][field]=0
            with self.assertRaisesRegex(ValueError,'allowlist'):join_rows(rows,ps,aa)

    def test_only_fit_season_and_prior_labels(self):
        rows,ps,aa=fixture(1);f,a=join_rows(rows,ps,aa);ys=labels_for(rows)
        for table in (f,a,ys):table[0]['season']='2025-26'
        with self.assertRaisesRegex(ValueError,'only 2024-25'):fit_models(f,ys,a,'2025-08-15T12:52:00Z')
        for table in (f,a,ys):table[0]['season']='2024-25'
        ys[0]['label_available_at']='2025-08-15T12:52:00Z'
        with self.assertRaisesRegex(ValueError,'cutoff'):fit_models(f,ys,a,'2025-08-15T12:52:00Z')

    def test_control_exact_m4_projection_and_preprocessing(self):
        rows,ps,aa=fixture();f,_=join_rows(rows,ps,aa)
        self.assertEqual(len(MODEL_FEATURES),25)
        self.assertTrue(np.array_equal(model_matrix(f,'control'),m4_matrix(rows)))
        with threadpool_limits(limits=1):
            old=make_pipeline(CONFIGS['hist_15']).fit(m4_matrix(rows),[r['target_points'] for r in rows])
            new=pipeline('control').fit(model_matrix(f,'control'),[r['target_points'] for r in rows])
        self.assertEqual(pickle.dumps(old,protocol=5),pickle.dumps(new,protocol=5))
        self.assertFalse(pipeline('xpts_v2').named_steps['model'].early_stopping)

    def test_evaluation_outcomes_do_not_enter_fit(self):
        rows,ps,aa=fixture();f,a=join_rows(rows,ps,aa)
        models,state,_=fit_models(f,labels_for(rows),a,'2025-08-15T12:52:00Z')
        before={n:pickle.dumps(m,protocol=5) for n,m in models.items()}
        # Fitting interface does not accept evaluation outcomes at all.
        for r in rows:r['target_points']=1000000
        with threadpool_limits(limits=1):
            for n,m in models.items():m.predict(model_matrix(f,n))
        self.assertEqual(before,{n:pickle.dumps(m,protocol=5) for n,m in models.items()})

    def test_top10_fixed_ties_and_equal_gw_weight(self):
        rows,_,_=fixture(12)
        ps={('2024-25',1,r['element']):{'v2':1.0} for r in rows}
        result=top10(rows,ps,'v2')
        self.assertEqual(result['gameweeks']['2024-25:1']['elements'],list(range(1,11)))
        self.assertEqual(result['mean_top10_realised_points'],sum(r['target_points'] for r in rows[:10])/10)

    def test_serialization_stable_after_load_and_refit(self):
        rows,ps,aa=fixture();f,a=join_rows(rows,ps,aa)
        models,_,_=fit_models(f,labels_for(rows),a,'2025-08-15T12:52:00Z')
        before={n:model_bytes(m) for n,m in models.items()}
        for n,m in models.items():
            restored=pickle.loads(before[n])
            self.assertEqual(model_bytes(restored),before[n])
            with threadpool_limits(limits=1):
                self.assertTrue(np.array_equal(m.predict(model_matrix(f,n)),restored.predict(model_matrix(f,n))))
        refitted,_,_=fit_models(f,labels_for(rows),a,'2025-08-15T12:52:00Z')
        self.assertEqual(before,{n:model_bytes(m) for n,m in refitted.items()})
        cyclic=[];cyclic.append(cyclic)
        with self.assertRaisesRegex(ValueError,'acyclic'):model_bytes(cyclic)


if __name__=='__main__':unittest.main()
