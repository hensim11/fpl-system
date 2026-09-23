"""Common-scenario evaluation of verified M5B paths; no stochastic optimisation."""
from pathlib import Path

import numpy as np

from fpl_ai import joint_simulation as js, transfer_path as tp
from fpl_ai.experiment_io import publish, verify_bundle
from fpl_ai.fpl_rules import Rules, integer, require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json

# Already independently accepted exact M5B products; all other identities must
# reproduce the unchanged exact solver. Never infer acceptance from a new hash.
ACCEPTED_PLANS = frozenset({
    '0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8',
    '26b900fe844835296b1a20f9a32c54092fb031bb2255eac0ec3d84ee5d03dd24',
})
CONTRACT = {
    'version': 'm5d-plan-evaluation-v1',
    'returns': 'fixed M5B XI and captain for each GW; add captain_multiplier-1 copies; subtract that GW transfer hit; equal-weight horizon sum; no scenario hindsight, substitutions, vice-captain or chips',
    'comparison': 'same scenario cube for no-transfer, sequential greedy and each exact top-N path; no new objective or risk attitude',
    'ties': 'strict greater-than wins and exact binary64 equality ties; highest-return probability splits unit credit equally across ALL supplied candidate entries tied for maximum; also report inclusive highest and sole winner; duplicate paths retained and disclosed',
    'shortfall': 'lower-tail expected shortfall at 10% = integral of empirical quantile over [0,0.1]/0.1; fractional boundary observation gives exactly 10% mass',
    'numerics': 'ascending XI IDs then extra captain, subtract hit each GW, sequential binary64 horizon sum; plan comparisons have no optimiser tolerance',
    'interpretation': 'simulation diagnostics conditional on frozen assumptions; not realised FPL return or decision utility',
}


def load_plans(folder, rows, projection_reference):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'multi-gw-transfer-path')
    m = manifest['metadata']
    source = load_json(folder/'source.json')
    require(source['identity_sha256'] == projection_reference['identity'] and
            js.digest(source) == projection_reference['manifest_sha256'], 'plan projection source mismatch')
    require(m['contract'] == tp.CONTRACT and m['rules'] == Rules().as_dict() and m['assumptions'] == tp.ASSUMPTIONS and
            m['implementation_sha256'] == sha256_file(Path(tp.__file__)) and
            m['projection_identity'] == source['identity_sha256'] and m['model_identity'] == js.uc.MODEL_ID,
            'plan source/rules/implementation mismatch')
    state = load_json(folder/'squad.json')
    integer(m['horizon'], 'plan horizon', 1, 5)
    require(m['horizon'] <= max(r['horizon'] for r in rows)+1, 'plan exceeds simulation horizon')
    integer(m['max_transfers'], 'max transfers', 0, 15)
    integer(m['top_n'], 'top N', 1, 20)
    populations, valid_state = tp.validate_projections(rows, state, m['horizon'], Rules())
    decision = load_json(folder/'decision.json')
    require(decision['contract'] == tp.CONTRACT and decision['assumptions'] == tp.ASSUMPTIONS and
            decision['horizon'] == m['horizon'] and decision['max_transfers_per_gameweek'] == m['max_transfers'] and
            1 <= len(decision['plans']) <= m['top_n'], 'plan configuration mismatch')
    candidates = {'no_transfer': decision['baseline'], 'greedy': decision['greedy'],
                  **{f'exact_{i}': p for i, p in enumerate(decision['plans'], 1)}}
    initial = sorted(p['element'] for p in valid_state['players'])
    require(all(w['squad'] == initial for w in decision['baseline']['weeks']), 'no-transfer path made transfers')
    for name, plan in candidates.items():
        require(len(plan['weeks']) == m['horizon'], 'incomplete plan horizon')
        rebuilt, _ = tp.path_plan([w['squad'] for w in plan['weeks']], populations, valid_state, Rules())
        if name.startswith('exact_'):
            rebuilt['gain_vs_no_transfer'] = rebuilt['total_points']-decision['baseline']['total_points']
        require(plan == rebuilt and all(w['transfer_count'] <= m['max_transfers'] for w in plan['weeks']),
                'plan legal XI/captain/economics replay mismatch')
    if manifest['identity_sha256'] not in ACCEPTED_PLANS:
        exact = tp.optimise_paths(rows, state, horizon=m['horizon'], max_transfers=m['max_transfers'], top_n=m['top_n'])
        exact['greedy'] = tp.greedy_path(rows, state, horizon=m['horizon'], max_transfers=m['max_transfers'])
        require(exact == decision, 'unaccepted plan did not reproduce exact M5B ranking/greedy')
    return candidates, manifest


def scenario_returns(residuals, rows, candidates, rules=Rules()):
    rules.validate()
    h, p = residuals.shape[1:]
    ordered = sorted(rows, key=lambda r: (r['horizon'], r['element']))
    require(len(ordered) == h*p, 'scenario population shape mismatch')
    lookup = {(r['horizon'], r['element']): (j % p, r['xpts']) for j, r in enumerate(ordered)}
    result = {}
    for name, plan in candidates.items():
        require(0 < len(plan['weeks']) <= h, 'unsupported plan horizon')
        total = np.zeros(len(residuals))
        for t, week in enumerate(plan['weeks']):
            require(week['captain'] in week['starting_xi'], 'captain outside XI')
            week_return = np.zeros(len(residuals))
            for e in sorted(week['starting_xi']):
                j, point = lookup[t, e]
                week_return += residuals[:, t, j]+point
            j, point = lookup[t, week['captain']]
            week_return += (residuals[:, t, j]+point)*(rules.captain_multiplier-1)
            week_return -= week['transfer_hit']
            total += week_return
        result[name] = total
    return result


def shortfall(values, alpha=.1):
    ordered = np.sort(values)
    mass = len(ordered)*alpha
    whole = int(mass)
    return float((ordered[:whole].sum() + (mass-whole)*ordered[min(whole, len(ordered)-1)])/mass)


def paired(values, baseline):
    delta = values-baseline
    return {**js.summary(delta), 'probability_win': float(np.mean(delta > 0)),
            'probability_tie': float(np.mean(delta == 0)), 'probability_loss': float(np.mean(delta < 0)),
            'mean_mc_standard_error': float(delta.std()/np.sqrt(len(delta))),
            'win_probability_mc_standard_error': float(np.sqrt(np.mean(delta > 0)*(1-np.mean(delta > 0))/len(delta)))}


def metrics(returns):
    require({'no_transfer', 'greedy'} <= set(returns), 'missing plan baselines')
    names = list(returns)
    matrix = np.stack([returns[n] for n in names])
    require(np.isfinite(matrix).all(), 'nonfinite plan return')
    highest = matrix == matrix.max(axis=0)
    tied_count = highest.sum(axis=0)
    return {name: {**js.summary(matrix[j]), 'lower_tail_mean_10pct': shortfall(matrix[j]),
                    'mean_mc_standard_error': float(matrix[j].std()/np.sqrt(matrix.shape[1])),
                    'vs_no_transfer': paired(matrix[j], returns['no_transfer']),
                    'vs_greedy': paired(matrix[j], returns['greedy']),
                    'probability_highest_split_ties': float(np.mean(highest[j]/tied_count)),
                    'probability_highest_including_ties': float(np.mean(highest[j])),
                    'probability_sole_highest': float(np.mean(highest[j] & (tied_count == 1)))}
            for j, name in enumerate(names)}


def compute(rows, donor, config, candidates):
    donors, keys, groups, _ = donor
    report = {'contract': CONTRACT, 'scenario_count': config['scenario_count'],
              'M5B_forecast_objectives': {n: p['total_points'] for n, p in candidates.items()},
              'models': {}, 'duplicate_path_entries': []}
    names = list(candidates)
    for j, n in enumerate(names):
        for other in names[:j]:
            if candidates[n]['weeks'] == candidates[other]['weeks']:
                report['duplicate_path_entries'].append([other, n])
    for model in (js.JOINT, js.NULL):
        residuals, _ = js.generate(donors, keys, groups, len(rows)//donors.shape[1], config, model)
        returns = scenario_returns(residuals, rows, candidates)
        del residuals
        report['models'][model] = {'metrics': metrics(returns),
            'return_sha256': {name: js.array_hash(v) for name, v in returns.items()},
            'convergence_prefixes': {str(n): metrics({k: v[:n] for k, v in returns.items()})
                                    for n in sorted({min(config['scenario_count'], c) for c in (1024, 4096, 16384, config['scenario_count'])})}}
    # Analytical expectation exposes raw residual bias; no hidden recentering.
    report['analytical_simulation_expectation'] = {
        n: p['total_points']+sum(float(donors[:, h].mean())*(Rules().xi_size+Rules().captain_multiplier-1)
                               for h in range(len(p['weeks']))) for n, p in candidates.items()}
    return report


def evaluate(simulation_dir, plan_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir,
             output_dir=Path('data/simulation_evaluations'), **sources):
    js.live.safe_output(output_dir, simulation_dir, plan_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, *sources.values())
    (rows, donor, config), simulation = js.verify(simulation_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    candidates, plan = load_plans(plan_dir, rows, simulation['metadata']['binding']['projection'])
    report = compute(rows, donor, config, candidates)
    metadata = {'kind': 'simulation-plan-evaluation', 'contract': CONTRACT,
                'simulation': js.uc.reference(simulation_dir, simulation), 'plan': js.uc.reference(plan_dir, plan),
                'implementation_sha256': sha256_file(Path(__file__))}
    def writer(folder): atomic_write_json(folder/'evaluation.json', report)
    return publish(output_dir, metadata, writer)


def verify(folder, simulation_dir, plan_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources):
    manifest = verify_bundle(folder, 'simulation-plan-evaluation')
    (rows, donor, config), simulation = js.verify(simulation_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    candidates, plan = load_plans(plan_dir, rows, simulation['metadata']['binding']['projection'])
    expected = {'kind': 'simulation-plan-evaluation', 'contract': CONTRACT,
                'simulation': js.uc.reference(simulation_dir, simulation), 'plan': js.uc.reference(plan_dir, plan),
                'implementation_sha256': sha256_file(Path(__file__))}
    require(manifest['metadata'] == expected and load_json(Path(folder)/'evaluation.json') == compute(rows, donor, config, candidates),
            'plan evaluation replay mismatch')
    return manifest
