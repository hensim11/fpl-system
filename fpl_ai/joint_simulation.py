"""M5D empirical joint scenarios; M5B points and M5C calibration remain frozen.

The executable law is a size-weighted as-of block bootstrap of complete donor
trajectories. There is no fitted covariance matrix, recentering or Gaussian law.
"""
import hashlib
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from fpl_ai import multi_uncertainty as uc
from fpl_ai import prospective as live
from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.experiments import environment
from fpl_ai.fpl_rules import integer, require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json

DEFAULT_COUNT = 16384
DEFAULT_SEED = 1729
JOINT = 'as-of-block-trajectories-v1'
NULL = 'independent-residual-null-v1'
CONTRACT = {
    'version': 'joint-simulation-v1', 'dependency_model': JOINT,
    'null_model': NULL, 'supported_horizons': [1, 2, 3, 4, 5],
    'source': 'exact reconstructed M5C calibration; 2025-26 residual y-p only; no prospective outcomes',
    'eligibility': 'complete offsets 0..H-1 at one original as-of/player; season-end and missing labels excluded explicitly',
    'joint_law': 'uniform anchor among sorted complete trajectories selects as-of block (probability block size / total); each current player independently draws one donor uniformly WITH replacement within that block and keeps all H residuals',
    'dependence': 'within-player donor trajectory; common historical as-of block induces cross-player covariance of block means across target offsets; conditional on block, donor trajectories are independent',
    'unsupported': 'specific current player identity, position, club, opponent, match, pairwise competition and conditional rotation risk; no cross-publication scenario coupling',
    'exchangeability': 'current players exchangeable with complete historical donors; overlaps and one consumed season are not independent validation',
    'null_law': 'each player/horizon independently samples the corresponding component of a uniform complete donor; same marginal population as joint, deliberately removes both dependencies',
    'points': 'original binary64 forecast plus raw signed residual; no centering, clipping, rounding, retraining or recursive state',
    'rng': 'NumPy Generator(PCG64(seed)); sorted (as_of_gameweek, element) donors and ascending current IDs; scenario-major calls: joint integers(N) anchor then integers(block_size,size=P); null integers(N,size=(H,P)); int64 draws; separate RNG restarted with same seed for each model; count extensions preserve prefixes',
    'storage': 'no raw cube; exact little-endian float64 C-order (scenario,horizon,ascending element) SHA256 of residual and points plus donor-index trace SHA256; reconstruct from bound sources/seed/software',
    'statistics': 'population SD ddof=0; linear percentiles; inclusive M5C interval coverage; negative points retained; covariance uses population denominator',
    'default_count': DEFAULT_COUNT, 'information_cutoff': uc.CONTRACT['information_cutoff'],
    'interpretation': 'projected simulation diagnostics, not realised benefit, conditional calibration or model selection',
}


def configuration(count=DEFAULT_COUNT, seed=DEFAULT_SEED):
    integer(count, 'scenario count', 2, 131072)
    integer(seed, 'seed', 0, 2**64-1)
    return {'scenario_count': count, 'seed': seed}


def donor_population(residuals, horizon):
    """Select complete keyed windows without modifying any M5C residual value."""
    integer(horizon, 'simulation horizon', 1, 5)
    indexed = {}
    for r in residuals:
        k = r['as_of_gameweek'], r['element'], r['horizon']
        require(k not in indexed, 'duplicate residual key')
        require(r['season'] == '2025-26' and r['target_gameweek'] == k[0]+k[2] and
                type(k[2]) is int and 0 <= k[2] <= 4, 'residual season/target/horizon mismatch')
        if r['residual'] is not None:
            require(r['outcome'] is not None and r['residual'] == r['outcome']-r['xpts'] and
                    np.isfinite(r['residual']) and live.before(r['label_available_at'], CONTRACT['information_cutoff']),
                    'invalid residual/cutoff')
        else:
            require(r['outcome'] is None, 'missing residual with observed label')
        indexed[k] = r
    keys, values, excluded = [], [], []
    for g, e in sorted({(g, e) for g, e, h in indexed}):
        require((g, e, 0) in indexed, 'trajectory lacks original horizon')
        parts = [indexed.get((g, e, h)) for h in range(horizon)]
        reason = ('season_end' if g+horizon-1 > 38 else
                  'missing_horizon_or_label' if any(r is None or r['residual'] is None for r in parts) else None)
        if reason:
            excluded.append({'as_of_gameweek': g, 'element': e, 'reason': reason})
        else:
            keys.append([g, e])
            values.append([r['residual'] for r in parts])
    require(bool(values), 'no complete residual evidence; cannot substitute zero')
    groups = defaultdict(list)
    for i, (g, _) in enumerate(keys): groups[g].append(i)
    array = np.array(values, dtype=np.float64)
    record = {'horizon': horizon, 'residual_population_sha256': digest(residuals),
              'eligible_keys': keys, 'excluded': excluded,
              'exclusion_counts': dict(Counter(r['reason'] for r in excluded)),
              'complete_trajectories': len(keys), 'as_of_blocks': len(groups),
              'block_counts': {str(g): len(ids) for g, ids in groups.items()},
              'donor_values_sha256': array_hash(array),
              'M5C_full_marginal_reference': {str(t): {
                  'labelled_rows': sum(r['horizon'] == t and r['residual'] is not None for r in residuals),
                  'residual': summary([r['residual'] for r in residuals if r['horizon'] == t and r['residual'] is not None])}
                  for t in range(horizon)}}
    return array, keys, dict(groups), record


def array_hash(values):
    return hashlib.sha256(memoryview(np.asarray(values, dtype='<f8', order='C'))).hexdigest()


def generate(donors, keys, groups, players, config, model=JOINT):
    """Pure scenario kernel; output axes S,H,P, trace never includes current labels."""
    require(model in (JOINT, NULL), 'unsupported dependence model')
    require(config == configuration(**{'count': config['scenario_count'], 'seed': config['seed']}), 'invalid simulation configuration')
    integer(players, 'player count', 1)
    rng = np.random.Generator(np.random.PCG64(config['seed']))
    n, h = donors.shape
    integer(h, 'simulation horizon', 1, 5)
    require(n > 0 and np.isfinite(donors).all(), 'missing/nonfinite donor evidence')
    result = np.empty((config['scenario_count'], h, players), dtype=np.float64)
    trace = hashlib.sha256()
    group_arrays = {g: np.array(ids, dtype=np.int64) for g, ids in groups.items()}
    for s in range(config['scenario_count']):
        if model == JOINT:
            anchor = int(rng.integers(n, dtype=np.int64))
            block = group_arrays[keys[anchor][0]]
            chosen = block[rng.integers(len(block), size=players, dtype=np.int64)]
            result[s] = donors[chosen].T
            trace.update(np.array([anchor], dtype='<i8').tobytes())
        else:
            chosen = rng.integers(n, size=(h, players), dtype=np.int64)
            result[s] = donors[chosen, np.arange(h)[:, None]]
        trace.update(np.asarray(chosen, dtype='<i8').tobytes())
    return result, trace.hexdigest()


def summary(values):
    values = np.asarray(values, dtype=np.float64)
    qs = np.quantile(values, [.05, .1, .5, .9, .95], method='linear')
    return {'mean': float(values.mean()), 'sd': float(values.std()),
            **{k: float(v) for k, v in zip(('p05', 'p10', 'median', 'p90', 'p95'), qs)},
            'min': float(values.min()), 'max': float(values.max())}


def covariance(values):
    centered = values-values.mean(axis=0)
    return centered.T @ centered / len(values)


def correlation(cov):
    scales = np.sqrt(np.diag(cov))
    return [[float(cov[i, j]/(scales[i]*scales[j])) if scales[i]*scales[j] > 0 else None
             for j in range(len(scales))] for i in range(len(scales))]


def dependency_reference(donors, groups, players):
    means = np.array([donors[ids].mean(axis=0) for ids in groups.values()])
    weights = np.array([len(ids)/len(donors) for ids in groups.values()])
    centered = means-donors.mean(axis=0)
    common = (centered*weights[:, None]).T @ centered
    total = covariance(donors)
    return {'donor_covariance': total.tolist(), 'donor_correlation': correlation(total),
            'cross_player_covariance_from_shared_block': common.tolist(),
            'aggregate_mean_covariance_joint': (common+(total-common)/players).tolist(),
            'aggregate_mean_covariance_null': (np.diag(np.diag(total))/players).tolist(),
            'block_means': means.tolist(), 'block_probabilities': weights.tolist()}


def diagnostics(residuals, rows, tables, donors, groups):
    s, h, p = residuals.shape
    points = np.array([r['xpts'] for r in rows]).reshape(h, p)
    per_player, per_horizon = [], {}
    for offset in range(h):
        for j in range(p):
            r = rows[offset*p+j]
            vs = residuals[:, offset, j]+r['xpts']
            intervals = tables['horizons'][str(offset)]['intervals']
            per_player.append({**r, 'simulation': summary(vs),
                               'negative_frequency': float(np.mean(vs < 0)),
                               'm5c_fixed_intervals': {level: {'lower': r['xpts']+q['lower_residual'],
                                   'upper': r['xpts']+q['upper_residual'],
                                   'simulated_coverage': float(np.mean((residuals[:, offset, j] >= q['lower_residual']) &
                                                                     (residuals[:, offset, j] <= q['upper_residual'])))}
                                   for level, q in intervals.items()}})
        per_horizon[str(offset)] = {'forecast_mean': float(points[offset].mean()),
                                    'residual': summary(residuals[:, offset].reshape(-1)),
                                    'simulated_points': summary((residuals[:, offset]+points[offset]).reshape(-1)),
                                    'aggregate_GW_residual_sum': summary(residuals[:, offset].sum(axis=1)),
                                    'complete_donor_residual': summary(donors[:, offset])}
    # A random player trajectory's covariance, and the mean covariance over
    # ordered distinct player pairs, computed without a P x P covariance matrix.
    means = residuals.mean(axis=2)
    marginal_means = means.mean(axis=0)
    within = np.array([[float(np.mean(residuals[:, a]*residuals[:, b]))-marginal_means[a]*marginal_means[b]
                        for b in range(h)] for a in range(h)])
    aggregate = covariance(means)
    cross = (p*aggregate-within)/(p-1) if p > 1 else None
    return {'player_horizons': per_player, 'horizons': per_horizon,
            'dependence': {'pooled_player_covariance': within.tolist(), 'pooled_player_correlation': correlation(within),
                           'aggregate_mean_covariance': aggregate.tolist(),
                           'distinct_player_pair_covariance': cross.tolist() if cross is not None else None},
            'historical_reference': dependency_reference(donors, groups, p)}


def inputs(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources):
    product, uncertainty = uc.verify_uncertainty(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    archive = load_json(Path(uncertainty_dir)/'projection.json')
    original = uc.mp.load_json_from_text(archive['files']['projections.json'])
    rows = sorted(original, key=lambda r: (r['horizon'], r['element']))
    tables = load_json(Path(calibration_dir)/'calibration.json')
    # attach checks all original keys, horizons and finite forecasts.
    uc.attach(rows, tables)
    h = uncertainty['metadata']['state']['horizon']
    require(len({r['horizon'] for r in rows}) == h, 'simulation horizon mismatch')
    require(all(tables['horizons'][str(t)]['available'] for t in range(h)), 'unavailable M5C residual pool')
    residuals = load_json(Path(calibration_dir)/'residuals.json')
    donor = donor_population(residuals, h)
    require(donor[3]['complete_trajectories'] >= uc.CONTRACT['minimum_pool_rows'], 'insufficient complete trajectory evidence')
    binding = {'uncertainty': uc.reference(uncertainty_dir, uncertainty),
               'projection': uncertainty['metadata']['projection'], 'calibration': uncertainty['metadata']['calibration'],
               'state': uncertainty['metadata']['state'], 'uncertainty_computed_at': uncertainty['metadata']['computed_at'],
               'residual_population_sha256': digest(residuals),
               'projection_population_sha256': digest(rows),
               'environment': environment(), 'numpy_version': np.__version__,
               'implementation_sha256': sha256_file(Path(__file__))}
    return rows, tables, donor, binding


def compute(rows, tables, donor, config):
    values, keys, groups, population = donor
    count = len(rows)//values.shape[1]
    reports, hashes = {}, {}
    for model in (JOINT, NULL):
        samples, trace = generate(values, keys, groups, count, config, model)
        point_hash = hashlib.sha256()
        forecasts = np.array([r['xpts'] for r in rows]).reshape(values.shape[1], count)
        for scenario in samples:
            point_hash.update(np.asarray(scenario+forecasts, dtype='<f8').tobytes())
        hashes[model] = {'residual_sha256': array_hash(samples), 'points_sha256': point_hash.hexdigest(), 'donor_trace_sha256': trace}
        reports[model] = diagnostics(samples, rows, tables, values, groups)
        del samples
    return {'population.json': population, 'projections.json': rows,
            'diagnostics.json': reports, 'scenario_hashes.json': hashes, 'contract.json': CONTRACT}


def identity(binding, config):
    return digest({'binding': binding, 'config': config, 'contract': CONTRACT})


def freeze(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir,
           output_dir=Path('data/simulations'), *, count=DEFAULT_COUNT, seed=DEFAULT_SEED, **sources):
    """New publication uses only the actual clock; matching existing runs replay."""
    live.safe_output(output_dir, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, *sources.values())
    started = live.stamp(live.now_utc)
    config = configuration(count, seed)
    rows, tables, donor, binding = inputs(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    run_key = identity(binding, config)
    for path in sorted(Path(output_dir).glob('*/manifest.json')):
        existing = load_json(path)
        if existing['metadata'].get('simulation_key') == run_key:
            verify(path.parent, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
            return path.parent, True
    state = binding['state']
    require(live.not_after(binding['uncertainty_computed_at'], started) and live.before(started, state['deadline']), 'simulation must precede original deadline')
    products = compute(rows, tables, donor, config)
    completed = live.stamp(live.now_utc)
    require(live.not_after(started, completed), 'simulation clock reversed')
    metadata = {'kind': 'joint-simulation', 'contract': CONTRACT, 'binding': binding,
                'config': config, 'simulation_key': run_key, 'started_at': started, 'computed_at': completed}
    def writer(folder):
        for name, value in products.items(): atomic_write_json(folder/name, value)
    def guard():
        current = live.stamp(live.now_utc)
        require(live.not_after(completed, current) and live.before(current, state['deadline']), 'simulation publication reached deadline or clock reversed')
    out, reused = publish(output_dir, metadata, writer, publication_guard=guard)
    try:
        verify(out, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
        guard()
    except BaseException:
        if not reused: shutil.rmtree(out)
        raise
    return out, reused


def verify(folder, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources):
    manifest = verify_bundle(folder, 'joint-simulation')
    m = manifest['metadata']
    rows, tables, donor, binding = inputs(uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    require(m['contract'] == CONTRACT and m['binding'] == binding and
            m['simulation_key'] == identity(binding, m['config']), 'simulation source/contract mismatch')
    require(live.not_after(binding['uncertainty_computed_at'], m['started_at']) and
            live.not_after(m['started_at'], m['computed_at']) and live.before(m['computed_at'], binding['state']['deadline']),
            'invalid simulation publication timing')
    products = compute(rows, tables, donor, m['config'])
    require(all(load_json(Path(folder)/name) == value for name, value in products.items()), 'simulation deterministic replay mismatch')
    return (rows, donor, m['config']), manifest


def replay(folder, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, output_dir, **sources):
    live.safe_output(output_dir, folder, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, *sources.values())
    _, manifest = verify(folder, uncertainty_dir, calibration_dir, model_dir, m4e_model_dir, **sources)
    def writer(out):
        for name in manifest['artifacts']: shutil.copyfile(Path(folder)/name, out/name)
    return publish(output_dir, manifest['metadata'], writer)
