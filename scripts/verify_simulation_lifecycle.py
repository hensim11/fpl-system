"""Real offline M5D fresh/reuse/replay, evaluation and corruption probes."""
import argparse
import copy
import tempfile
from pathlib import Path
from time import perf_counter

from fpl_ai import joint_simulation as js, simulation_plans as sp
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json
from scripts.verify_joint_simulation import CALIBRATION, UNCERTAINTY, M4E, PLAN, check
from tests.test_prospective import fingerprint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--simulation-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('docs/M5D_LIFECYCLE.json'))
    args = parser.parse_args()
    common = (UNCERTAINTY, CALIBRATION, js.uc.MODEL, M4E)
    source = args.simulation_dir
    original = verify_bundle(source, 'joint-simulation')
    before = fingerprint(source)
    actions = []
    def run(name, fn):
        print('Running '+name, flush=True)
        start = perf_counter(); value = fn()
        actions.append({'action': name, 'seconds': perf_counter()-start,
                        'completed_at': js.live.stamp(js.live.now_utc), 'passed': True})
        print('Passed '+name, flush=True)
        return value
    (rows, donor, config), _ = run('existing_full_replay', lambda: js.verify(source, *common))
    candidates, _ = sp.load_plans(PLAN, rows, original['metadata']['binding']['projection'])
    run('default_count_plan_computation_only', lambda: sp.compute(rows, donor, config, candidates))
    evaluation, reused = run('evaluate_accepted_top_three', lambda: sp.evaluate(source, PLAN, *common))
    evaluation_before = fingerprint(evaluation)
    again, used = run('evaluation_reuse', lambda: sp.evaluate(source, PLAN, *common))
    check(again == evaluation and used and fingerprint(evaluation) == evaluation_before, 'evaluation reuse changed bytes/mtimes')
    run('evaluation_verifier', lambda: sp.verify(evaluation, source, PLAN, *common))
    _, used = run('simulation_reuse', lambda: js.freeze(*common, source.parent, count=config['scenario_count'], seed=config['seed']))
    check(used and fingerprint(source) == before, 'simulation reuse changed publication')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fresh, used = run('fresh_actual_clock_publication', lambda: js.freeze(*common, root/'fresh', count=config['scenario_count'], seed=config['seed']))
        check(not used, 'fresh unexpectedly reused')
        fresh_manifest = verify_bundle(fresh, 'joint-simulation')
        check(fresh_manifest['metadata']['simulation_key'] == original['metadata']['simulation_key'], 'fresh deterministic simulation key changed')
        check(fresh_manifest['artifacts'] == original['artifacts'], 'fresh deterministic output hashes changed')
        check(fresh.name != source.name, 'new runtime publication did not bind new timestamps')
        restored, used = run('offline_attestation_replay', lambda: js.replay(source, *common, root/'replay'))
        check(not used and restored.name == source.name, 'replay redated original')
        metadata = copy.deepcopy(original['metadata'])
        metadata['config']['seed'] += 1
        metadata['simulation_key'] = js.identity(metadata['binding'], metadata['config'])
        def writer(out):
            for name in original['artifacts']:
                (out/name).write_bytes((source/name).read_bytes())
        corrupt, _ = publish(root/'rehashed-corruption', metadata, writer)
        def reject():
            try: js.verify(corrupt, *common)
            except ValueError as error:
                check('replay mismatch' in str(error), 'unexpected rejection path')
                return str(error)
            raise ValueError('rehashed seed and key with stale scenarios admitted')
        rejection = run('real_rehashed_seed_key_stale_scenarios_rejected', reject)
    check(fingerprint(source) == before and fingerprint(evaluation) == evaluation_before, 'real artifact changed')
    atomic_write_json(args.report, {'simulation_identity': source.name, 'simulation_key': original['metadata']['simulation_key'],
        'publication': original['metadata'], 'evaluation_identity': evaluation.name,
        'synthetic_squad_not_user_team': True, 'realised_outcomes_consumed': 0,
        'fresh_publication': fresh_manifest, 'fresh_same_key_and_all_product_hashes': True,
        'offline_replay_same_identity': True, 'reuse_bytes_and_mtimes_unchanged': True,
        'real_rehashed_corruption_rejection': rejection, 'actions': actions})
    print(args.report, flush=True)


if __name__ == '__main__': main()
