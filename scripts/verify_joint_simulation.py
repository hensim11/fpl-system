"""Independent M5D source, sampling, dependence and plan arithmetic audit.

Does not call production donor selection, sampling, diagnostics, plan returns or
metric helpers for reference values. Checks stay enabled under python -O.
"""
import argparse
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

from fpl_ai import joint_simulation as js, simulation_plans as sp
from fpl_ai.experiment_io import verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json
from scripts.verify_multi_uncertainty import history_audit
from scripts.verify_multi_gameweek import audit_plan

CALIBRATION = Path('data/multi_uncertainty/calibrations/782bf10333f482f4ff2a1e19a2c438c4bc9d04b27b237779b1e71dbb8bc6d699')
UNCERTAINTY = Path('data/multi_uncertainty/forecasts/c0a759479365bb0ee8676b355926ab2fdbd4a84bdca0d496d41c07189a471f2d')
M4E = Path('data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230')
PLAN = Path('data/transfer_paths/0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8')


def check(condition, message):
    if not condition: raise ValueError(message)


def close(actual, expected, label):
    check(math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-10), f'{label}: {actual} != {expected}')


def quantile(values, probability):
    ordered = sorted(float(v) for v in values)
    offset = (len(ordered)-1)*probability
    low = math.floor(offset)
    return ordered[low]+(offset-low)*(ordered[min(low+1, len(ordered)-1)]-ordered[low])


def audit_summary(saved, values):
    avg = math.fsum(values)/len(values)
    close(saved['mean'], avg, 'mean')
    close(saved['sd'], math.sqrt(math.fsum((v-avg)**2 for v in values)/len(values)), 'population SD')
    for field, q in [('p05', .05), ('p10', .1), ('median', .5), ('p90', .9), ('p95', .95)]:
        close(saved[field], quantile(values, q), field)
    close(saved['min'], min(values), 'min'); close(saved['max'], max(values), 'max')


def reconstruct(folder, calibration):
    manifest = verify_bundle(folder, 'joint-simulation')
    m = manifest['metadata']
    source = load_json(calibration/'residuals.json')
    h = m['binding']['state']['horizon']
    windows = defaultdict(dict)
    for r in source:
        windows[r['as_of_gameweek'], r['element']][r['horizon']] = r
    keys, donors, excluded = [], [], []
    for key, entries in sorted(windows.items()):
        reason = ('season_end' if key[0]+h-1 > 38 else
                  'missing_horizon_or_label' if any(t not in entries or entries[t]['outcome'] is None for t in range(h)) else None)
        if reason:
            excluded.append({'as_of_gameweek': key[0], 'element': key[1], 'reason': reason})
        else:
            keys.append(list(key)); donors.append([entries[t]['outcome']-entries[t]['xpts'] for t in range(h)])
    pop = load_json(folder/'population.json')
    check(keys == pop['eligible_keys'] and excluded == pop['excluded'], 'independent complete-window selection')
    values = np.array(donors, dtype=float)
    check(hashlib.sha256(values.astype('<f8').tobytes()).hexdigest() == pop['donor_values_sha256'], 'donor value hash')
    return manifest, keys, values


def independent_samples(manifest, keys, values, players, model):
    config = manifest['metadata']['config']
    h = values.shape[1]
    rng = np.random.Generator(np.random.PCG64(config['seed']))
    # Membership reconstructed solely from the retained original keys.
    members = defaultdict(list)
    for i, (g, e) in enumerate(keys): members[g].append(i)
    samples = np.empty((config['scenario_count'], h, players))
    trace = hashlib.sha256()
    for s in range(len(samples)):
        if model == js.JOINT:
            anchor = int(rng.integers(len(keys), dtype=np.int64))
            block = members[keys[anchor][0]]
            chosen = np.array([block[int(j)] for j in rng.integers(len(block), size=players, dtype=np.int64)])
            for t in range(h): samples[s, t] = [values[j, t] for j in chosen]
            trace.update(np.array([anchor], dtype='<i8').tobytes())
        else:
            chosen = rng.integers(len(keys), size=(h, players), dtype=np.int64)
            for t in range(h): samples[s, t] = [values[j, t] for j in chosen[t]]
        trace.update(chosen.astype('<i8').tobytes())
    return samples, trace.hexdigest()


def audit_metrics(saved, totals):
    names = list(totals)
    for name, vs in totals.items():
        record = saved[name]
        audit_summary(record, vs)
        close(record['mean_mc_standard_error'], record['sd']/math.sqrt(len(vs)), 'mean MC SE')
        ordered = sorted(vs); mass = len(vs)/10; whole = math.floor(mass)
        close(record['lower_tail_mean_10pct'], (math.fsum(ordered[:whole])+(mass-whole)*ordered[min(whole, len(vs)-1)])/mass, 'tail mean')
        for field, baseline in [('vs_no_transfer', 'no_transfer'), ('vs_greedy', 'greedy')]:
            delta = [a-b for a, b in zip(vs, totals[baseline])]
            audit_summary(record[field], delta)
            close(record[field]['mean_mc_standard_error'], record[field]['sd']/math.sqrt(len(delta)), 'paired mean MC SE')
            win = sum(d > 0 for d in delta)/len(delta)
            close(record[field]['win_probability_mc_standard_error'], math.sqrt(win*(1-win)/len(delta)), 'paired win MC SE')
            for key, fn in [('win', lambda d: d > 0), ('tie', lambda d: d == 0), ('loss', lambda d: d < 0)]:
                close(record[field]['probability_'+key], sum(fn(d) for d in delta)/len(delta), 'paired '+key)
        credit, inclusive, sole = 0., 0, 0
        for i, value in enumerate(vs):
            top = max(totals[n][i] for n in names)
            n_top = sum(totals[n][i] == top for n in names)
            if value == top: credit += 1/n_top; inclusive += 1; sole += int(n_top == 1)
        close(record['probability_highest_split_ties'], credit/len(vs), 'split ties')
        close(record['probability_highest_including_ties'], inclusive/len(vs), 'inclusive ties')
        close(record['probability_sole_highest'], sole/len(vs), 'sole highest')


def audit(folder, evaluation_dir, calibration=CALIBRATION, uncertainty=UNCERTAINTY, plan_dir=PLAN, m4e=M4E):
    # Use upstream authority; independently reconstruct the M5C label joins too.
    js.uc.verify_uncertainty(uncertainty, calibration, js.uc.MODEL, m4e)
    historical = history_audit(calibration)
    manifest, keys, values = reconstruct(folder, calibration)
    original_archive = load_json(uncertainty/'projection.json')
    rows = sorted(js.uc.mp.load_json_from_text(original_archive['files']['projections.json']), key=lambda r: (r['horizon'], r['element']))
    check(rows == load_json(folder/'projections.json'), 'original binary64 points and keys')
    audit_plan(plan_dir, rows)
    decision = load_json(plan_dir/'decision.json')
    candidates = {'no_transfer': decision['baseline'], 'greedy': decision['greedy'],
                  **{f'exact_{i}': p for i, p in enumerate(decision['plans'], 1)}}
    evaluation_manifest = verify_bundle(evaluation_dir, 'simulation-plan-evaluation')
    check(evaluation_manifest['metadata']['simulation'] == js.uc.reference(folder, manifest), 'evaluation scenario binding')
    check(evaluation_manifest['metadata']['plan'] == js.uc.reference(plan_dir, verify_bundle(plan_dir)), 'evaluation plan binding')
    evaluation = load_json(evaluation_dir/'evaluation.json')
    diagnostics = load_json(folder/'diagnostics.json')
    hashes = load_json(folder/'scenario_hashes.json')
    h = values.shape[1]; p = len(rows)//h
    forecast = np.array([r['xpts'] for r in rows]).reshape(h, p)
    id_index = {r['element']: i for i, r in enumerate(rows[:p])}
    results = {}
    for model in (js.JOINT, js.NULL):
        samples, trace = independent_samples(manifest, keys, values, p, model)
        hasher = hashlib.sha256()
        for scenario in samples: hasher.update((scenario+forecast).astype('<f8').tobytes())
        check(hasher.hexdigest() == hashes[model]['points_sha256'], 'independent scenario point hash')
        check(hashlib.sha256(memoryview(samples)).hexdigest() == hashes[model]['residual_sha256'], 'independent residual hash')
        check(trace == hashes[model]['donor_trace_sha256'], 'independent donor trace hash')
        for i, saved in enumerate(diagnostics[model]['player_horizons']):
            t, j = divmod(i, p)
            vs = samples[:, t, j]+rows[i]['xpts']
            # All means/SD and interval/negative frequencies; all full percentiles
            # for a fixed spread of IDs keep this independent scalar audit practical.
            close(saved['simulation']['mean'], math.fsum(vs)/len(vs), 'player mean')
            close(saved['simulation']['sd'], float(np.std(vs)), 'player SD')
            if j in (0, p//2, p-1): audit_summary(saved['simulation'], vs)
            close(saved['negative_frequency'], sum(v < 0 for v in vs)/len(vs), 'negative frequency')
            for level, interval in saved['m5c_fixed_intervals'].items():
                q = load_json(calibration/'calibration.json')['horizons'][str(t)]['intervals'][level]
                check(interval['lower'] == rows[i]['xpts']+q['lower_residual'] and interval['upper'] == rows[i]['xpts']+q['upper_residual'], 'unchanged M5C endpoints')
                close(interval['simulated_coverage'], float(np.mean((samples[:, t, j] >= q['lower_residual']) & (samples[:, t, j] <= q['upper_residual']))), 'interval comparison')
        block_groups = defaultdict(list)
        for i, (g, e) in enumerate(keys): block_groups[g].append(i)
        avg = values.mean(axis=0)
        common = np.zeros((h, h))
        for ids in block_groups.values():
            delta = np.mean(values[ids], axis=0)-avg
            common += len(ids)/len(values)*np.outer(delta, delta)
        saved_ref = diagnostics[model]['historical_reference']
        check(np.allclose(common, saved_ref['cross_player_covariance_from_shared_block'], atol=1e-13), 'historical common covariance')
        aggregate = samples.mean(axis=2)
        empirical = np.cov(aggregate, rowvar=False, bias=True)
        check(np.allclose(empirical, diagnostics[model]['dependence']['aggregate_mean_covariance'], atol=1e-12), 'aggregate dependence diagnostic')
        check(np.allclose(np.cov(values, rowvar=False, bias=True), saved_ref['donor_covariance'], atol=1e-12), 'donor covariance diagnostic')
        totals = {name: [] for name in candidates}
        # Scalar FPL return arithmetic, no production plan-return helper.
        for scenario in samples:
            for name, candidate in candidates.items():
                total = 0.
                for t, week in enumerate(candidate['weeks']):
                    score = 0.
                    for e in sorted(week['starting_xi']):
                        j = id_index[e]; score += float(scenario[t, j]+forecast[t, j])
                    j = id_index[week['captain']]
                    score += float(scenario[t, j]+forecast[t, j])
                    score -= week['transfer_hit']; total += score
                totals[name].append(total)
        del samples
        for name, vs in totals.items():
            check(hashlib.sha256(np.array(vs, dtype='<f8').tobytes()).hexdigest() == evaluation['models'][model]['return_sha256'][name], 'independent exact scenario path totals')
        audit_metrics(evaluation['models'][model]['metrics'], totals)
        for n, saved in evaluation['models'][model]['convergence_prefixes'].items():
            audit_metrics(saved, {name: vs[:int(n)] for name, vs in totals.items()})
        results[model] = {'all_scenario_and_trace_hashes_exact': True, 'all_scalar_plan_returns_exact': True,
                          'all_plan_metrics_and_convergence_prefixes_independently_verified': True,
                          'marginal_interval_negative_and_dependence_diagnostics_verified': True}
    return {'simulation_identity': folder.name, 'evaluation_identity': evaluation_dir.name,
            'simulation_key': manifest['metadata']['simulation_key'], 'seed': manifest['metadata']['config']['seed'],
            'scenario_count': manifest['metadata']['config']['scenario_count'],
            'complete_donors': len(keys), 'as_of_blocks': len({g for g, e in keys}),
            'historical': historical, 'models': results,
            'source_sha256': {n: sha256_file(Path(n)) for n in ('fpl_ai/joint_simulation.py', 'fpl_ai/simulation_plans.py', 'scripts/verify_joint_simulation.py')}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--simulation-dir', type=Path, required=True)
    parser.add_argument('--evaluation-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('docs/M5D_VERIFICATION.json'))
    args = parser.parse_args()
    atomic_write_json(args.report, audit(args.simulation_dir, args.evaluation_dir))
    print(args.report)


if __name__ == '__main__': main()
