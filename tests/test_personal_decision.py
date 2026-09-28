"""M5E hand-checkable input, arithmetic, binding, time and lifecycle contracts."""
import copy
import json
import shutil
import socket
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from fpl_ai import personal_decision as pd, decision_report as report
from fpl_ai.experiment_io import publish, verify_bundle, STAGE_ARTIFACTS
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json
from tests.test_transfer_optimiser import fixture
from tests.test_transfer_path import projection
from tests.test_multi_uncertainty import residual_fixture
from tests.test_prospective import clock, fingerprint

OBSERVED = '2026-09-23T09:00:00Z'
IMPORTED = '2026-09-23T10:00:00Z'


def personal_fixture():
    p, s = fixture()
    return projection([p, p]), {'contract': pd.CONTRACT['input'], 'squad': s,
        'provenance': {'kind': 'synthetic', 'source': 'Hand-checkable synthetic fixture', 'observed_at': OBSERVED, 'confirmed': True},
        'account_state': {'transfers_already_made': 0, 'hits_already_incurred': 0, 'active_chip': None}}


def state_fixture():
    return {'as_of_gameweek': 6, 'season': '2026-27', 'horizon': 2, 'capture': '2026-09-23T08:00:00Z',
            'computed_at': '2026-09-23T08:30:00Z', 'deadline': '2026-09-24T10:00:00Z', 'model_identity': pd.js.uc.MODEL_ID}


def config_fixture():
    return {'mode': 'snapshot', 'planning': {'horizon': 2, 'effective_horizon': 2, 'max_transfers': 2, 'top_n': 3, 'scenario_count': 32, 'seed': 4}}


class InputTests(unittest.TestCase):
    def setUp(self): self.rows, self.personal = personal_fixture()

    def validate(self, value=None):
        return pd.validate_personal(value or self.personal, self.rows, 2, IMPORTED)

    def test_incomplete_template_rejected(self):
        self.personal['provenance']['confirmed'] = False
        with self.assertRaisesRegex(ValueError, 'unfinished template'): self.validate()
        self.personal['provenance']['confirmed'] = True
        self.personal['squad']['bank'] = None
        with self.assertRaisesRegex(ValueError, 'bank'): self.validate()

    def test_duplicate_and_unknown_ids(self):
        for value, match in ((1, 'duplicate'), (999, 'unknown')):
            p = copy.deepcopy(self.personal); p['squad']['players'][-1]['element'] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, match): self.validate(p)

    def test_wrong_season_gameweek(self):
        for k, v in (('season', '2025-26'), ('target_gameweek', 7), ('target_gameweek', True)):
            p = copy.deepcopy(self.personal); p['squad'][k] = v
            with self.subTest(k=k, v=v), self.assertRaises(ValueError): self.validate(p)

    def test_strict_money_free_transfer_types(self):
        for field in ('bank', 'free_transfers', 'selling_price', 'element'):
            for bad in (None, True, -1, 1.5, '1'):
                p = copy.deepcopy(self.personal)
                target = p['squad']['players'][0] if field in ('selling_price', 'element') else p['squad']
                target[field] = bad
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError): self.validate(p)

    def test_unsupported_account_state_and_provenance(self):
        for key, bad in (('transfers_already_made', 1), ('transfers_already_made', False), ('hits_already_incurred', 4), ('active_chip', 'wildcard')):
            p = copy.deepcopy(self.personal); p['account_state'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(p)
        for key, bad in (('source', ''), ('kind', 'official'), ('confirmed', 1), ('observed_at', None), ('observed_at', '2027-01-01T00:00:00Z')):
            p = copy.deepcopy(self.personal); p['provenance'][key] = bad
            with self.subTest(key=key), self.assertRaises(ValueError): self.validate(p)

    def test_exact_sales_and_canonical_order(self):
        self.personal['squad']['players'].reverse()
        self.personal['squad']['players'][0]['selling_price'] = 41
        valid = self.validate()
        self.assertEqual(valid['squad']['players'][-1], {'element': 15, 'selling_price': 41})
        self.assertEqual(valid['squad']['bank'], 12)
        self.assertEqual(valid['squad']['free_transfers'], 1)

    def test_owned_unselectable_and_newcomer(self):
        for r in self.rows:
            if r['element'] in (1, 16): r['can_select'] = False
        valid = self.validate()
        decision = pd.tp.optimise_paths(self.rows, valid['squad'], horizon=2, top_n=1)
        self.assertIn(1, decision['plans'][0]['weeks'][0]['squad'])
        self.assertNotIn(16, decision['plans'][0]['weeks'][0]['squad'])
        self.rows[0]['can_select'] = 1
        with self.assertRaisesRegex(ValueError, 'can_select'): self.validate()

    def test_closed_fields_and_duplicate_json_keys(self):
        self.personal['account_id'] = 'unneeded'
        with self.assertRaisesRegex(ValueError, 'fields'): self.validate()
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'bad.json'; p.write_text('{"bank": 1, "bank": 2}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): load_json(p)

    def test_settings_strict_types_and_scenario_mismatch(self):
        raw = {k:v for k,v in config_fixture()['planning'].items() if k != 'effective_horizon'}
        for k, v in (('horizon', True), ('max_transfers', False), ('top_n', 0), ('scenario_count', 16), ('seed', 5)):
            with self.subTest(k=k), self.assertRaises(ValueError): pd.settings({**raw, k:v}, state_fixture(), {'scenario_count':32, 'seed':4})
        result = pd.settings({**raw, 'horizon':5}, {**state_fixture(), 'as_of_gameweek':38, 'horizon':1}, {'scenario_count':32, 'seed':4})
        self.assertEqual(result['effective_horizon'], 1)


class TimeTests(unittest.TestCase):
    def setUp(self):
        _, self.personal = personal_fixture()
        self.state = state_fixture()
        self.sim = {'computed_at': '2026-09-23T08:45:00Z'}

    def check(self, mode='snapshot', imported=IMPORTED, created=IMPORTED, final=IMPORTED):
        pd.time_check(self.personal, {'mode':mode}, self.state, self.sim, imported, created, final)

    def test_after_deadline_snapshot_allowed_not_predeadline(self):
        self.check(imported='2026-10-01T10:00:00Z', created='2026-10-01T10:00:00Z', final='2026-10-01T10:00:00Z')
        with self.assertRaisesRegex(ValueError, 'reached deadline'):
            self.check('pre-deadline', '2026-10-01T10:00:00Z', '2026-10-01T10:00:00Z', '2026-10-01T10:00:00Z')

    def test_stale_snapshot_predeadline_gate(self):
        self.state['capture'] = '2026-09-20T08:00:00Z'
        self.check()
        with self.assertRaisesRegex(ValueError, '24-hour'): self.check('pre-deadline')

    def test_mixed_age_allowed_explicitly_within_gate(self): self.check('pre-deadline')

    def test_no_backdated_personal_or_reversed_clock(self):
        for kwargs in ({'imported':'2026-09-23T07:00:00Z'}, {'final':'2026-09-23T09:00:00Z'}):
            with self.assertRaisesRegex(ValueError, 'chronology'): self.check(**kwargs)
        self.personal['provenance']['observed_at'] = '2026-09-23T07:00:00Z'
        with self.assertRaisesRegex(ValueError, 'predates snapshot'): self.check('pre-deadline')

    def test_final_deadline_and_freshness_gate(self):
        with self.assertRaisesRegex(ValueError, 'reached deadline'):
            self.check('pre-deadline', final=self.state['deadline'])
        with self.assertRaisesRegex(ValueError, '24-hour'):
            self.check('pre-deadline', final='2026-09-24T09:00:00Z')

    def test_exact_boundaries(self):
        self.check('pre-deadline', final='2026-09-24T08:00:00Z')
        with self.assertRaisesRegex(ValueError, '24-hour'):
            self.check('pre-deadline', final='2026-09-24T08:00:00.000001Z')
        self.state['deadline']='2026-09-23T11:00:00Z'
        self.check('pre-deadline', final='2026-09-23T10:59:59.999999Z')
        for t in ('2026-09-23T11:00:00Z','2026-09-23T11:00:00.000001Z'):
            with self.assertRaisesRegex(ValueError,'reached deadline'): self.check('pre-deadline',final=t)


class BindingTests(unittest.TestCase):
    def test_missing_ambiguous_override_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); identity = 'a'*64
            with self.assertRaisesRegex(ValueError, 'missing model prerequisite'): pd.resolve_one(identity, [root], 'model')
            for name in ('a', 'b'):
                p = root/name/identity; p.mkdir(parents=True); (p/'manifest.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'ambiguous'): pd.resolve_one(identity, [root], 'model')
            selected = root/'a'/identity
            self.assertEqual(pd.resolve_one(identity, [root], 'model', {'model':selected}), selected)
            with self.assertRaisesRegex(ValueError, 'conflicts'): pd.resolve_one(identity, [root], 'model', {'model':root/'wrong'})

    def test_no_missing_simulation_training(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, 'ordinary decision runs never train'):
            pd.resolve(Path(tmp)/'missing', [Path(tmp)])

    def test_settings_wrong_squad_and_projection(self):
        _, personal = personal_fixture(); effective = config_fixture()
        meta = {'kind':'multi-gw-transfer-path', 'projection_identity':'x', 'horizon':2, 'max_transfers':2, 'top_n':3}
        with tempfile.TemporaryDirectory() as tmp:
            def writer(out):
                for name in STAGE_ARTIFACTS['multi-gw-transfer-path']:
                    atomic_write_json(out/name, personal['squad'] if name == 'squad.json' else {})
            out, _ = publish(tmp, meta, writer)
            pd.check_plan(out, personal, effective, {'identity':'x'})
            def reordered_writer(target):
                for name in STAGE_ARTIFACTS['multi-gw-transfer-path']:
                    value = {**personal['squad'], 'players':list(reversed(personal['squad']['players']))} if name=='squad.json' else {}
                    atomic_write_json(target/name,value)
            reordered,_ = publish(Path(tmp)/'reordered',meta,reordered_writer)
            pd.check_plan(reordered,personal,effective,{'identity':'x'})
            with self.assertRaisesRegex(ValueError, 'projection/planning'): pd.check_plan(out, personal, effective, {'identity':'y'})
            personal['squad']['bank'] += 1
            with self.assertRaisesRegex(ValueError, 'different squad'): pd.check_plan(out, personal, effective, {'identity':'x'})


class WorkflowTests(unittest.TestCase):
    """Only upstream forecasts/calibration are mocked; real small exact M5B/M5D work."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.rows, self.personal = personal_fixture()
        # Exercise supplied text escaping on both report surfaces.
        for r in self.rows:
            if r['element'] == 1: r['name'] = '<script>alert("x")</script>|[link]'
        self.effective = config_fixture(); self.state = state_fixture()
        self.donor = pd.js.donor_population(residual_fixture(), 2)
        self.simconfig = {'scenario_count':32, 'seed':4}
        self.tables = pd.js.uc.calibration_tables(residual_fixture())
        def artifact(kind, meta, products, root):
            def writer(out):
                for name in STAGE_ARTIFACTS[kind]: atomic_write_json(out/name, products.get(name, {}))
            return publish(root, {'kind':kind, **meta}, writer)[0]
        projection_dir = artifact('multi-horizon-forecast', self.state, {'projections.json':self.rows}, self.root/'projections')
        pm = verify_bundle(projection_dir)
        uncertainty = artifact('multi-uncertainty-forecast', {}, {'uncertainty.json':pd.js.uc.attach(self.rows, self.tables)}, self.root/'uncertainty')
        simulation_dir = artifact('joint-simulation', {'binding':{'state':pm['metadata'], 'projection':pd.js.uc.reference(projection_dir, pm)},
              'config':self.simconfig, 'started_at':'2026-09-23T08:40:00Z', 'computed_at':'2026-09-23T08:45:00Z'}, {'projections.json':self.rows}, self.root/'simulations')
        self.sim = verify_bundle(simulation_dir)
        self.paths = {'projection':projection_dir, 'uncertainty':uncertainty, 'simulation':simulation_dir,
                      **{k:self.root/k for k in ('calibration','model','m4e_model','history','m3')}}
        for k in ('calibration','model','m4e_model','history','m3'):
            self.paths[k] = publish(self.root/k, {'kind':'synthetic-source', 'role':k}, lambda out: atomic_write_json(out/'fixture.json', {}))[0]
        self.refs = {k:pd.reference(p, verify_bundle(p)) if (p/'manifest.json').exists() else {'identity':k, 'artifacts':{}, 'manifest_sha256':k} for k,p in self.paths.items()}
        self.context = {'projection_metadata':pm['metadata'], 'simulation_metadata':self.sim['metadata'], 'forecast_metadata':{},
                        'snapshot_metadata':{}, 'clubs':{str(i):f'Club {i}' for i in range(1,7)}, 'retained_history_count':0}
        self.config_path = self.root/'config.json'
        config = {'contract':pd.CONTRACT['config'], 'personal_state':'personal.json', 'simulation_dir':str(simulation_dir), 'evidence_roots':[str(self.root)],
                  'dependencies':{}, 'plan_dir':None, 'output_dir':str(self.root/'decisions'), 'mode':'snapshot',
                  'planning':{k:v for k,v in self.effective['planning'].items() if k!='effective_horizon'}}
        atomic_write_json(self.config_path, config); atomic_write_json(self.root/'personal.json', self.personal)
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(pd, 'resolve', return_value=(self.paths, self.refs)))
        stack.enter_context(patch.object(pd.js, 'verify', return_value=((self.rows,self.donor,self.simconfig),self.sim)))
        stack.enter_context(patch.object(pd.js.uc.mp, 'verify_projection', return_value=(self.rows,pm)))
        stack.enter_context(patch.object(pd, 'context_for', return_value=self.context))
        stack.enter_context(patch.object(pd, 'bound_context', return_value=self.context))
        stack.enter_context(patch.object(pd.live, 'now_utc', clock(IMPORTED)))
        stack.enter_context(patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')))

    def run_workflow(self): return pd.run(self.config_path, progress=lambda text:None)

    def test_fresh_reuse_replay_deterministic_and_upstream_preserved(self):
        before = {k:fingerprint(p) for k,p in self.paths.items() if p.exists()}
        out, reused, summary, _ = self.run_workflow()
        self.assertFalse(reused); self.assertEqual(summary['returned_exact_paths'], 3)
        self.assertNotIn(summary['dependencies']['plan']['identity'], pd.sp.ACCEPTED_PLANS)
        fingerprint_before = fingerprint(out)
        with patch.object(pd.live, 'now_utc', clock('2026-10-01T10:00:00Z')):
            again, used, reused_summary, _ = self.run_workflow()
        self.assertEqual(again,out); self.assertTrue(used); self.assertEqual(summary,reused_summary)
        self.assertEqual(fingerprint(out),fingerprint_before)
        manifest, verified = pd.verify(out,[self.root])
        replayed, used, _ = pd.replay(out,[self.root],self.root/'replay')
        self.assertFalse(used); self.assertEqual(out.name,replayed.name)
        self.assertEqual(manifest, verify_bundle(replayed)); self.assertEqual(verified,summary)
        for k, v in before.items(): self.assertEqual(fingerprint(self.paths[k]),v)
        self.assertEqual(report.render(summary),report.render(verified))

    def test_independent_objective_economics_and_decomposition(self):
        _, _, s, _ = self.run_workflow()
        # All original players score 1; stars score 10 and 8. Independently known optimum.
        self.assertEqual(s['plans']['no_transfer']['total_points'],24)
        self.assertEqual(s['plans']['greedy']['total_points'],70)
        self.assertEqual(s['plans']['exact_1']['total_points'],70)
        self.assertEqual(s['decomposition']['exact_1']['no_transfer']['horizon'],
                         {'xi_change':32.,'captain_bonus_change':18.,'hit_change':-4.,'net_change':46.})
        points={(r['horizon'],r['element']):r['xpts'] for r in self.rows}
        for name, plan in s['plans'].items():
            bank=12; free=1; held={e:49 for e in range(1,16)}; total=0
            for h,w in enumerate(plan['weeks']):
                incoming=set(w['squad'])-held.keys(); outgoing=held.keys()-set(w['squad'])
                bank += sum(held[e] for e in outgoing)-sum(55 if e>15 else 50 for e in incoming)
                hit=4*max(0,len(incoming)-free)
                free=min(5,max(0,free-len(incoming))+1)
                score=sum(points[h,e] for e in w['starting_xi'])+points[h,w['captain']]-hit
                self.assertEqual((bank,free,hit,score),(w['resulting_bank'],w['next_free_transfers'],w['transfer_hit'],w['net_points']))
                held={e:held[e] if e in held else (55 if e>15 else 50) for e in w['squad']}; total+=score
            self.assertEqual(total,plan['total_points'])
            for b in ('no_transfer','greedy'):
                self.assertEqual(s['decomposition'][name][b]['horizon']['net_change'],total-s['plans'][b]['total_points'])

    def test_faithful_simulation_fields_duplicate_ties_and_html_escaping(self):
        config=load_json(self.config_path); config['planning']['max_transfers']=0; atomic_write_json(self.config_path,config)
        out,_,s,_=self.run_workflow()
        self.assertEqual(s['returned_exact_paths'],1)
        self.assertEqual(len(s['simulation']['duplicate_path_entries']),3)
        for m in s['simulation']['models'].values():
            for metric in m['metrics'].values():
                self.assertAlmostEqual(metric['probability_highest_split_ties'],1/3)
                self.assertEqual(metric['vs_no_transfer']['probability_tie'],1)
        html=(out/'report.html').read_text()
        self.assertNotIn('<script>',html); self.assertIn('&lt;script&gt;',html)
        self.assertIn('Club 1',html); self.assertIn('snapshot',html)
        self.assertEqual(s['simulation'],load_json(next((self.root/'decisions'/'evaluations').glob('*/evaluation.json'))))

    def test_rehashed_false_summary_render_and_personal_rejected(self):
        out,_,s,_=self.run_workflow(); original=verify_bundle(out)
        for filename in ('summary.json','personal.json','report.html','dependencies.json'):
            def writer(target):
                for n in original['artifacts']: shutil.copyfile(out/n,target/n)
                if filename=='report.html': (target/filename).write_text('false report')
                else:
                    value=load_json(target/filename)
                    if filename=='summary.json': value['decomposition']['exact_1']['no_transfer']['horizon']['net_change']+=10
                    elif filename=='personal.json': value['squad']['bank']+=1
                    else: value['projection']['manifest_sha256']='0'*64
                    atomic_write_json(target/filename,value)
            corrupt,_=publish(self.root/'corrupt'/filename,original['metadata'],writer)
            with self.subTest(filename=filename), self.assertRaises(ValueError): pd.verify(corrupt,[self.root])

    def test_explicit_path_identity_cannot_be_silently_replaced_by_cached_path(self):
        out,_,summary,_=self.run_workflow()
        plan=next((self.root/'decisions'/'paths').glob('*/manifest.json')).parent
        original=verify_bundle(plan)
        def writer(target):
            for n in original['artifacts']: shutil.copyfile(plan/n,target/n)
            state=load_json(target/'squad.json'); state['players'].reverse()
            atomic_write_json(target/'squad.json',state)
        equivalent,_=publish(self.root/'equivalent-path',original['metadata'],writer)
        pd.sp.load_plans(equivalent,self.rows,self.sim['metadata']['binding']['projection'])
        config=load_json(self.config_path); config['plan_dir']=str(equivalent); atomic_write_json(self.config_path,config)
        with self.assertRaisesRegex(ValueError,'explicit path identity conflicts'): self.run_workflow()

    def test_rehashed_boolean_integer_substitution_in_saved_artifacts(self):
        out,_,_,_=self.run_workflow(); original=verify_bundle(out)
        for filename in ('summary.json','squad.json'):
            def writer(target):
                for n in original['artifacts']: shutil.copyfile(out/n,target/n)
                value=load_json(target/filename)
                if filename=='summary.json': value['personal']['squad']['free_transfers']=True
                else: value['free_transfers']=True
                atomic_write_json(target/filename,value)
            bad,_=publish(self.root/'boolean-substitution'/filename,original['metadata'],writer)
            with self.subTest(filename=filename),self.assertRaises(ValueError): pd.verify(bad,[self.root])

    def test_partial_failure_leaves_no_personal_bundle(self):
        with patch.object(pd.sp, 'verify', side_effect=ValueError('evaluation failure')):
            with self.assertRaisesRegex(ValueError,'evaluation failure'): self.run_workflow()
        self.assertFalse(list((self.root/'decisions').glob('*/summary.json')))
        self.assertFalse(list((self.root/'decisions').glob('.building-*')))

    def test_publication_boundary_cleanup_after_creation_and_after_retained_check(self):
        config=load_json(self.config_path); config['mode']='pre-deadline'; atomic_write_json(self.config_path,config)
        for boundary, message in (('2026-09-24T08:00:00.000001Z', '24-hour'),
                                  ('2026-09-24T10:00:00Z', 'reached deadline')):
            for stage in ('retained', 'final'):
                times = [IMPORTED, IMPORTED, boundary] if stage == 'retained' else [IMPORTED, IMPORTED, IMPORTED, boundary]
                with self.subTest(boundary=boundary, stage=stage), patch.object(pd.live, 'now_utc', side_effect=[clock(t)() for t in times]):
                    with self.assertRaisesRegex(ValueError, message): self.run_workflow()
                self.assertFalse(list((self.root/'decisions').glob('*/summary.json')))
                self.assertFalse(list((self.root/'decisions').glob('.building-*')))

    def test_retained_check_is_later_than_creation_and_reconstructed(self):
        times = [IMPORTED, '2026-09-23T10:01:00Z', '2026-09-23T10:02:00Z', '2026-09-23T10:03:00Z']
        with patch.object(pd.live, 'now_utc', side_effect=[clock(t)() for t in times]):
            out, _, summary, _ = self.run_workflow()
        m, reconstructed = pd.verify(out, [self.root])
        self.assertEqual(m['metadata']['attestation'], dict(zip(('imported_at','created_at','publication_checked_at'), times[:3])))
        self.assertEqual(summary, reconstructed)
        self.assertIn(times[2], (out/'report.md').read_text())

    def test_rehashed_false_attestation_rejected(self):
        config=load_json(self.config_path); config['mode']='pre-deadline'; atomic_write_json(self.config_path,config)
        out,_,_,_=self.run_workflow(); original=verify_bundle(out)
        for checked, message in ((None, 'attestation fields'), (True, 'timestamp'),
                                 ('2026-09-23T09:59:59Z', 'chronology'),
                                 ('2026-09-24T08:00:00.000001Z', '24-hour'),
                                 ('2026-09-24T10:00:00Z', 'reached deadline'),
                                 ('2026-09-23T10:01:00Z', 'summary semantic')):
            metadata=copy.deepcopy(original['metadata'])
            if checked is None: del metadata['attestation']['publication_checked_at']
            else: metadata['attestation']['publication_checked_at']=checked
            def writer(target):
                for n in original['artifacts']: shutil.copyfile(out/n,target/n)
            bad,_=publish(self.root/'bad-attestations',metadata,writer)
            with self.subTest(checked=checked), self.assertRaisesRegex(ValueError,message): pd.verify(bad,[self.root])

    def test_final_guard_clock_regression_cleanup(self):
        times=[IMPORTED, IMPORTED, '2026-09-23T10:02:00Z', '2026-09-23T10:01:00Z']
        with patch.object(pd.live,'now_utc',side_effect=[clock(t)() for t in times]):
            with self.assertRaisesRegex(ValueError,'precedes retained'): self.run_workflow()
        self.assertFalse(list((self.root/'decisions').glob('*/summary.json')))
        self.assertFalse(list((self.root/'decisions').glob('.building-*')))

    def test_incomplete_artifact_set_and_rehashed_path(self):
        out,_,_,_=self.run_workflow(); manifest=verify_bundle(out)
        (out/'report.md').unlink()
        with self.assertRaises(ValueError): pd.verify(out,[self.root])
        # A rehashed legal but non-optimal exact result still requires actual solver replay.
        plan=next((self.root/'decisions'/'paths').glob('*/manifest.json')).parent
        pm=verify_bundle(plan)
        def writer(target):
            for n in pm['artifacts']: shutil.copyfile(plan/n,target/n)
            decision=load_json(target/'decision.json')
            decision['plans']=[{**decision['baseline'],'gain_vs_no_transfer':0.}]
            atomic_write_json(target/'decision.json',decision)
        bad,_=publish(self.root/'bad-path',pm['metadata'],writer)
        with self.assertRaisesRegex(ValueError,'exact M5B'):
            pd.sp.load_plans(bad,self.rows,self.sim['metadata']['binding']['projection'])

    def test_init_invalid_template_and_non_overwrite(self):
        config, personal, catalog=pd.init(self.root/'new.json',self.paths['simulation'],[self.root])
        self.assertEqual(len(load_json(catalog)),17)
        self.assertIsNone(load_json(personal)['squad']['bank'])
        with self.assertRaisesRegex(ValueError,'unfinished template'): pd.validate(config)
        with self.assertRaisesRegex(ValueError,'overwrite'): pd.init(config,self.paths['simulation'],[self.root])

    def test_predeadline_reuse_preserves_original_attestation_after_deadline(self):
        config=load_json(self.config_path); config['mode']='pre-deadline'; atomic_write_json(self.config_path,config)
        times=[IMPORTED, '2026-09-24T07:59:59Z', '2026-09-24T08:00:00Z', '2026-09-24T08:00:00Z']
        with patch.object(pd.live,'now_utc',side_effect=[clock(t)() for t in times]):
            out,_,summary,_=self.run_workflow()
        before=fingerprint(out)
        with patch.object(pd.live,'now_utc',clock('2026-10-01T00:00:00Z')):
            again,reused,current,_=self.run_workflow()
            replayed,_,replayed_summary=pd.replay(out,[self.root],self.root/'replay')
        self.assertEqual(out,again); self.assertTrue(reused); self.assertEqual(summary,current)
        self.assertEqual(summary,replayed_summary)
        self.assertEqual(verify_bundle(out),verify_bundle(replayed))
        self.assertEqual(fingerprint(out),before)
        self.assertEqual(summary['timing']['publication_checked_at'],times[2])

    def test_catalog_returns_all_ambiguous_matches(self):
        for r in self.rows:
            if r['element'] in (1,2): r['name']='Same name'
        matches=pd.catalog(self.paths['simulation'],[self.root],'Same name')
        self.assertEqual([p['element'] for p in matches],[1,2])
        self.assertEqual([p['element'] for p in pd.catalog(self.paths['simulation'],[self.root],'2')],[2,12])

    def test_rehashed_evaluation_arithmetic_fails_m5d_reader(self):
        out,_,summary,_=self.run_workflow()
        evaluation=next((self.root/'decisions'/'evaluations').glob('*/manifest.json')).parent
        original=verify_bundle(evaluation)
        def writer(target):
            value=load_json(evaluation/'evaluation.json')
            value['analytical_simulation_expectation']['exact_1']+=1
            atomic_write_json(target/'evaluation.json',value)
        bad,_=publish(self.root/'bad-evaluation',original['metadata'],writer)
        plan=next((self.root/'decisions'/'paths').glob('*/manifest.json')).parent
        with self.assertRaisesRegex(ValueError,'evaluation replay mismatch'):
            pd.sp.verify(bad,self.paths['simulation'],plan,*pd.common(self.paths),**pd.sources(self.paths))

    def test_offline_after_deadline_label_and_stale_mixed_age(self):
        with patch.object(pd.live,'now_utc',clock('2026-10-01T00:00:00Z')):
            _,_,summary,_=self.run_workflow()
        self.assertTrue(summary['timing']['created_after_deadline'])
        self.assertIn('snapshot',summary['label'])
        self.assertTrue(any('STALE INPUT' in v for v in summary['limitations']))
        self.assertTrue(any('MIXED-AGE' in v for v in summary['limitations']))


if __name__=='__main__': unittest.main()
