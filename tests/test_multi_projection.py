"""Projection features and later targets have distinct temporal roles."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fpl_ai import multi_projection as mp
from fpl_ai.modelling_contract import FEATURES, NULLABLE_FEATURES


def rows():
    result=[]
    for season in ('2024-25','2025-26'):
        for gw in (1,2,3,37,38):
            f={n:0 for n in FEATURES}
            f.update(deadline_position_id=3,status='a',price=50)
            for n in NULLABLE_FEATURES: f[n+'_missing']=int(f[n] is None)
            result.append({'season':season,'target_gameweek':gw,'element':1,'split':'validation' if season=='2024-25' else 'test',
                           'features':f,'target_points':gw*2,'label_available_at':f'{season[:4]}-09-{gw:02d}T00:00:00Z' if gw<4 else f'{int(season[:4])+1}-05-{gw-15:02d}T00:00:00Z',
                           'audit':{'capture_time_utc':f'{season[:4]}-08-01T00:00:00Z'}})
    return result


class ProjectionTests(unittest.TestCase):
    def test_freeze_rejects_actual_clock_at_deadline_without_publication(self):
        from datetime import datetime, timezone
        source={'manifest':{'metadata':{'publication_started_at':'2026-09-18T00:00:00Z',
                                        'deadline':'2026-10-10T10:00:00Z'}}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.object(mp,'load_models',return_value=({},{})), \
                 patch.object(mp,'projection_rows',return_value=([],source)), \
                 patch.object(mp,'publish') as publish:
                with self.assertRaisesRegex(ValueError,'precede deadline'):
                    mp.freeze(root/'forecast',root/'m4e',root/'model',root/'out',
                              clock=lambda:datetime(2026,10,10,10,tzinfo=timezone.utc))
                publish.assert_not_called()

    def test_live_matrix_has_historical_preprocessing_parity(self):
        from fpl_ai.experiments import matrix, MODEL_FEATURES
        source=rows()
        fs=[{n:r['features'][n] for n in MODEL_FEATURES} for r in source]
        self.assertEqual(mp.direct_matrix(fs).tolist(),matrix(source).tolist())
        fs[0]['future_minutes']=90
        with self.assertRaises(ValueError): mp.direct_matrix(fs)

    def test_later_labels_never_future_features(self):
        source=rows(); future=source[1]
        future['features']['price']=999
        joined=mp.targets(source,1)
        first=joined[0]
        self.assertIs(first['features'],source[0]['features'])
        self.assertIs(first['audit'],source[0]['audit'])
        self.assertEqual(first['features']['price'],50)
        self.assertEqual(first['target_points'],4)
        self.assertEqual(first['outcome_gameweek'],2)
        before=copy.deepcopy(first['features'])
        future['target_points']=99999
        self.assertEqual(mp.targets(source,1)[0]['features'],before)
        self.assertEqual(mp.targets(source,1)[0]['target_points'],99999)

    def test_missing_blank_zero_double_and_season_end(self):
        source=rows()
        source[1]['target_points']=None; source[1]['label_available_at']=''
        source[2]['target_points']=0
        joined=mp.targets(source,1)
        self.assertIsNone(joined[0]['target_points'])
        self.assertEqual(joined[1]['target_points'],0)
        self.assertIsNone(joined[2]['target_points'])  # absent GW4
        self.assertFalse(any(r['target_gameweek']==38 for r in joined))
        # A reconciled double is already the full individual-GW sum, never split/scaled.
        source[1]['target_points']=19; source[1]['label_available_at']='2024-09-02T00:00:00Z'
        self.assertEqual(mp.targets(source,1)[0]['target_points'],19)
        self.assertEqual(mp.targets(source,0)[-1]['target_points'],76)

    def test_missing_future_registration_stays_missing(self):
        source=rows(); source[1]['element']=2
        self.assertIsNone(mp.targets(source,1)[0]['target_points'])

    def test_duplicate_invalid_settlement_and_horizon_rejected(self):
        source=rows()
        with self.assertRaises(ValueError): mp.targets(source+source,1)
        for h in (-1,5,True):
            with self.assertRaises(ValueError): mp.targets(source,h)
        source[1]['label_available_at']='2020-01-01T00:00:00Z'
        with self.assertRaises(ValueError): mp.targets(source,1)

    def test_training_cutoff_and_preprocessing_population(self):
        from unittest.mock import MagicMock
        source=mp.targets(rows(),1)
        training=[r for r in source if r['season']=='2024-25']
        model=MagicMock(); model.fit.return_value=model
        with patch.object(mp,'make_pipeline',return_value=model):
            _, evidence, selected=mp.fit_one(training,'2025-08-01T00:00:00Z')
        self.assertEqual(len(model.fit.call_args.args[0]),len(selected))
        self.assertEqual(evidence['counts'],{'2024-25':3})
        self.assertTrue(all(r['target_points'] is not None for r in selected))
        with self.assertRaises(ValueError): mp.fit_one(source,'2025-08-01T00:00:00Z')

    def test_artifact_closed_set_and_checksum(self):
        from fpl_ai.experiment_io import publish,verify_bundle
        from fpl_ai.historical_io import atomic_write_json
        with tempfile.TemporaryDirectory() as tmp:
            def writer(folder):
                for n in ('projections.json','h0_comparison.json','source.json'): atomic_write_json(folder/n,[])
            out,reused=publish(tmp,{'kind':'multi-horizon-forecast'},writer)
            self.assertFalse(reused)
            self.assertEqual(publish(tmp,{'kind':'multi-horizon-forecast'},writer),(out,True))
            (out/'projections.json').write_text('[]')
            with self.assertRaises(ValueError): verify_bundle(out,'multi-horizon-forecast')


if __name__=='__main__': unittest.main()
