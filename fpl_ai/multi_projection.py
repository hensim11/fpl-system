"""M5B direct, nonrecursive multi-horizon points models and immutable evidence."""
import pickle
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from statistics import mean

import numpy as np
from threadpoolctl import threadpool_limits

from fpl_ai import prospective_xpts as xp
from fpl_ai.evaluation import metrics
from fpl_ai.experiment_io import digest, key, load_rows, publish, verify_bundle, verify_m3
from fpl_ai.experiments import CONFIGS, CATEGORICAL, MODEL_FEATURES, PROTOCOL as M4, environment, make_pipeline, matrix
from fpl_ai.fpl_rules import integer, require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv
from fpl_ai.transfer_optimiser import load_forecast, load_json
from fpl_ai.xpts_v2 import model_bytes, write_table

PROTOCOL = {
    'version': 'm5b-direct-points-v1', 'horizons': list(range(5)),
    'features': M4['features'], 'preprocessing': M4['preprocessing'],
    'model': {**CONFIGS['hist_15'], **M4['nonlinear']},
    'target': 'individual GW g+h points from verified M3 labels joined by season/element; absent future population or unlabelled GW stays missing',
    'state': 'one accepted M3 state at g; no future features, fixtures, minutes or recursive predictions',
    'historical_fit': '2021-22 through 2024-25; fixed design before 2025-26 evaluation; no selection',
    'evaluation': '2025-26 is already consumed historical evidence, not an untouched holdout',
    'production_fit': 'all five prior seasons; settlements strictly before 2026-07-01',
    'h0': 'distinct all-prior-season direct model; not identical to M4E matched-OOS-population control or v2; both remain frozen',
    'season_end': 'truncate at GW38; no labels beyond season end',
    'prices': 'static current purchase prices; exact initial selling prices until sold; repurchased players sell at purchase price',
    'eligibility': 'strict snapshot can_select frozen across horizon; owned unselectable may remain',
    'uncertainty': 'descriptive residual quantiles only; no risk penalty',
}


def targets(rows, horizon):
    """Attach later labels only; retain the exact earlier feature/audit objects."""
    integer(horizon, 'horizon offset', 0, 4)
    lookup = {key(r): r for r in rows}
    require(len(lookup) == len(rows), 'duplicate historical key')
    result = []
    for r in rows:
        g = r['target_gameweek'] + horizon
        if g > 38:
            continue
        future = lookup.get((r['season'], g, r['element']))
        y = future['target_points'] if future else None
        stamp = future['label_available_at'] if y is not None else ''
        require(y is None or xp.live.before(r['audit']['capture_time_utc'], stamp), 'future target settlement invalid')
        result.append({**r, 'target_points': y, 'label_available_at': stamp,
                       'outcome_gameweek': g, 'horizon': horizon})
    return result


def fit_one(rows, cutoff):
    selected = [r for r in rows if r['target_points'] is not None]
    require(bool(selected) and all(xp.live.before(r['label_available_at'], cutoff) for r in selected), 'training chronology violated')
    with threadpool_limits(limits=1):
        model = make_pipeline(CONFIGS['hist_15']).fit(matrix(selected), [r['target_points'] for r in selected])
    evidence = {'rows': len(selected), 'counts': dict(Counter(r['season'] for r in selected)),
                'keys_sha256': digest([key(r) for r in selected]),
                'features_sha256': digest([r['features'] for r in selected]),
                'labels_sha256': digest([(r['outcome_gameweek'], r['target_points'], r['label_available_at']) for r in selected]),
                'latest_settlement': max(r['label_available_at'] for r in selected), 'cutoff': cutoff}
    return model, evidence, selected


def diagnostics(rows, predictions):
    groups = {'overall': rows, **{f'position:{p}': [r for r in rows if r['features']['deadline_position_id'] == p] for p in range(1, 5)}}
    names = ('direct', 'position_mean', 'recent_points')
    report = {'segments': {g: {n: metrics(rs, predictions, n) for n in names} for g, rs in groups.items()}}
    values = [predictions[key(r)]['direct'] for r in rows]
    residuals = [r['target_points'] - predictions[key(r)]['direct'] for r in rows if r['target_points'] is not None]
    report['distribution'] = {'min': min(values), 'max': max(values), 'mean': mean(values),
                              'quantiles_05_25_50_75_95': np.quantile(values, [.05, .25, .5, .75, .95]).tolist()}
    report['residual_quantiles_05_25_50_75_95'] = np.quantile(residuals, [.05, .25, .5, .75, .95]).tolist() if residuals else []
    return report


def build_models(m3_dir, output_dir=Path('data/multi_projection/models')):
    xp.live.safe_output(output_dir, m3_dir)
    source = verify_m3(m3_dir)
    require(source['identity_sha256'] == xp.M3_ID, 'unaccepted M3 identity')
    rows, _ = load_rows(m3_dir, ('train', 'validation', 'test'))
    blobs, fits, predictions, outcomes, reports = {}, {}, [], [], {}
    by_horizon = {}
    for h in range(5):
        rs = targets(rows, h)
        evaluation = [r for r in rs if r['season'] == '2025-26']
        cutoff = min(r['audit']['capture_time_utc'] for r in evaluation)
        train = [r for r in rs if r['season'] != '2025-26']
        model, historical, selected = fit_one(train, cutoff)
        with threadpool_limits(limits=1):
            values = model.predict(matrix(evaluation))
        overall = mean(r['target_points'] for r in selected)
        positions = {p: mean([r['target_points'] for r in selected if r['features']['deadline_position_id'] == p]) for p in range(1, 5)}
        preds = {}
        for r, v in zip(evaluation, values):
            base = positions.get(r['features']['deadline_position_id'], overall)
            preds[key(r)] = {'direct': float(v), 'position_mean': base,
                            'recent_points': r['features']['points_mean_3'] if r['features']['points_mean_3'] is not None else base}
            common = {**dict(zip(xp.KEYS, key(r))), 'horizon': h, 'outcome_gameweek': r['outcome_gameweek']}
            predictions.append({**common, **preds[key(r)]})
            outcomes.append({**common, 'target_points': r['target_points'], 'label_available_at': r['label_available_at']})
        reports[str(h)] = diagnostics(evaluation, preds)
        by_horizon[h] = (evaluation, preds)
        production, operational, _ = fit_one(rs, xp.CUTOFF)
        blobs[f'h{h}.pickle'] = model_bytes(production)
        blobs[f'eval_h{h}.pickle'] = model_bytes(model)
        fits[str(h)] = {'historical': historical, 'production': operational}
    cumulative = {}
    for length in (3, 5):
        maps = [{key(r): r for r in by_horizon[h][0]} for h in range(length)]
        common = sorted(set.intersection(*(set(m) for m in maps)))
        rs, ps = [], {}
        for k in common:
            labelled = all(m[k]['target_points'] is not None for m in maps)
            rs.append({**maps[0][k], 'target_points': sum(m[k]['target_points'] for m in maps) if labelled else None})
            ps[k] = {n: sum(by_horizon[h][1][k][n] for h in range(length)) for n in ('direct', 'position_mean', 'recent_points')}
        cumulative[str(length)] = diagnostics(rs, ps)
    def writer(folder):
        for n, b in blobs.items(): (folder/n).write_bytes(b)
        atomic_write_json(folder/'protocol.json', PROTOCOL)
        atomic_write_json(folder/'fit.json', fits)
        write_table(folder, 'predictions.csv', predictions)
    meta = {'kind': 'multi-horizon-model', 'protocol': PROTOCOL, 'm3_identity': source['identity_sha256'], 'environment': environment()}
    out, reused = publish(output_dir, meta, writer)
    def score_writer(folder):
        atomic_write_json(folder/'metrics.json', {'horizons': reports, 'cumulative': cumulative})
        write_table(folder, 'outcomes.csv', outcomes)
    score, score_reused = publish(Path(output_dir).parent/'scores', {'kind': 'multi-horizon-score', 'model_identity': out.name, 'protocol': PROTOCOL}, score_writer)
    return out, reused, score, score_reused


def load_models(folder):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'multi-horizon-model')
    require(manifest['metadata'] == {'kind': 'multi-horizon-model', 'protocol': PROTOCOL, 'm3_identity': xp.M3_ID, 'environment': environment()}, 'incompatible multi-horizon model')
    require(load_json(folder/'protocol.json') == PROTOCOL, 'model protocol mismatch')
    fits = load_json(folder/'fit.json')
    require(set(fits) == {str(h) for h in range(5)}, 'missing horizon fits')
    for fit in fits.values():
        require(fit['production']['cutoff'] == xp.CUTOFF and xp.live.before(fit['production']['latest_settlement'], xp.CUTOFF), 'unsafe model cutoff')
    models = {h: pickle.loads((folder/f'h{h}.pickle').read_bytes()) for h in range(5)}
    require(all(m.named_steps['model'].get_params() == make_pipeline(CONFIGS['hist_15']).named_steps['model'].get_params() for m in models.values()), 'model configuration mismatch')
    return models, manifest


def projection_rows(forecast_dir, m4e_model_dir, models, horizon):
    population, source = load_forecast(forecast_dir, m4e_model_dir, 'control')
    fs = read_csv(Path(forecast_dir)/'features.csv')
    typed = [{n: xp.number(f[n], xp.FEATURE_TYPES[n]) for n in MODEL_FEATURES} for f in fs]
    inputs = direct_matrix(typed)
    meta = source['manifest']['metadata']
    integer(horizon, 'horizon', 1, 5)
    horizon = min(horizon, 39-meta['target_gameweek'])
    values = {}
    with threadpool_limits(limits=1):
        for h in range(horizon):
            values[h] = models[h].predict(inputs)
    require(all(np.isfinite(v).all() for v in values.values()), 'nonfinite projection')
    lookup = {p['element']: p for p in population}
    result = []
    for h in range(horizon):
        for f, value in zip(fs, values[h]):
            e = int(f['element'])
            result.append({'season': meta['season'], 'as_of_gameweek': meta['target_gameweek'],
                           'target_gameweek': meta['target_gameweek']+h, 'horizon': h,
                           **lookup[e], 'xpts': float(value)})
    return result, source


def direct_matrix(features):
    require(all(set(f) == set(MODEL_FEATURES) for f in features), 'direct model feature allowlist violated')
    return np.array([[('__missing__' if f[n] is None else str(f[n])) if n in CATEGORICAL
                      else (np.nan if f[n] is None else f[n]) for n in MODEL_FEATURES] for f in features], dtype=object)


def freeze(forecast_dir, m4e_model_dir, model_dir, output_dir=Path('data/multi_projection/forecasts'), *, horizon=5, clock=xp.live.now_utc):
    xp.live.safe_output(output_dir, forecast_dir, m4e_model_dir, model_dir)
    started = xp.live.stamp(clock)
    models, model = load_models(model_dir)
    rows, source = projection_rows(forecast_dir, m4e_model_dir, models, horizon)
    meta = source['manifest']['metadata']
    require(xp.live.not_after(meta['publication_started_at'], started) and xp.live.before(started, meta['deadline']), 'multi-horizon publication must precede deadline')
    evidence = load_json(Path(forecast_dir)/'evidence.json')
    snapshot = load_json_from_text(evidence['snapshot']['files']['manifest.json'])
    capture = snapshot['metadata']['bootstrap_timing']['requested_at']
    completed = xp.live.stamp(clock)
    require(xp.live.not_after(started, completed) and xp.live.before(completed, meta['deadline']), 'projection computation reached deadline')
    metadata = {'kind': 'multi-horizon-forecast', 'protocol': PROTOCOL,
                'model_identity': model['identity_sha256'], 'm4e_model_identity': source['manifest']['metadata']['model_identity'],
                'forecast_identity': source['manifest']['identity_sha256'], 'snapshot_identity': meta['snapshot_identity'],
                'season': meta['season'], 'as_of_gameweek': meta['target_gameweek'], 'capture': capture,
                'deadline': meta['deadline'], 'started_at': started, 'computed_at': completed,
                'horizon': max(r['horizon'] for r in rows)+1,
                'snapshot_age_minutes_at_deadline': meta['snapshot_age_minutes']}
    original = {int(r['element']): r for r in read_csv(Path(forecast_dir)/'predictions.csv')}
    comparison = {n: {'mean_direct_minus_m4e': mean(r['xpts']-float(original[r['element']][n]) for r in rows if r['horizon']==0),
                      'max_absolute_difference': max(abs(r['xpts']-float(original[r['element']][n])) for r in rows if r['horizon']==0)} for n in ('control', 'xpts_v2')}
    def writer(folder):
        atomic_write_json(folder/'projections.json', rows)
        atomic_write_json(folder/'h0_comparison.json', comparison)
        atomic_write_json(folder/'source.json', xp.archive(forecast_dir))
    def publication_guard():
        current = xp.live.stamp(clock)
        require(xp.live.not_after(completed, current) and xp.live.before(current, meta['deadline']),
                'projection publication reached deadline or clock reversed')
    out, reused = publish(output_dir, metadata, writer, publication_guard=publication_guard)
    try:
        verify_projection(out, model_dir, m4e_model_dir)
        publication_guard()
    except BaseException:
        if not reused: shutil.rmtree(out)
        raise
    return out, reused


def load_json_from_text(text):
    import json
    return json.loads(text)


def verify_projection(folder, model_dir, m4e_model_dir):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'multi-horizon-forecast')
    m = manifest['metadata']
    models, model = load_models(model_dir)
    require(m['protocol'] == PROTOCOL and m['model_identity'] == model['identity_sha256'], 'projection model mismatch')
    require(xp.live.not_after(m['capture'], m['started_at']) and xp.live.not_after(m['started_at'], m['computed_at']) and xp.live.before(m['computed_at'], m['deadline']), 'invalid projection timing')
    with tempfile.TemporaryDirectory() as tmp:
        forecast = xp.restore(Path(tmp), 'forecast', load_json(folder/'source.json'))
        rows, source = projection_rows(forecast, m4e_model_dir, models, m['horizon'])
        sm = source['manifest']['metadata']
        evidence = load_json(forecast/'evidence.json')
        snapshot = load_json_from_text(evidence['snapshot']['files']['manifest.json'])
        require(m['capture'] == snapshot['metadata']['bootstrap_timing']['requested_at'] and
                m['forecast_identity'] == forecast.name and m['m4e_model_identity'] == sm['model_identity'] and
                m['snapshot_identity'] == sm['snapshot_identity'] and m['season'] == sm['season'] and
                m['as_of_gameweek'] == sm['target_gameweek'] and m['deadline'] == sm['deadline'] and
                m['snapshot_age_minutes_at_deadline'] == sm['snapshot_age_minutes'], 'projection source state mismatch')
        require(m['horizon'] == max(r['horizon'] for r in rows)+1 and
                xp.live.not_after(sm['publication_started_at'], m['started_at']), 'projection horizon/publication mismatch')
        require(load_json(folder/'projections.json') == rows, 'projection replay mismatch')
        original = {int(r['element']): r for r in read_csv(forecast/'predictions.csv')}
        comparison = {n: {'mean_direct_minus_m4e': mean(r['xpts']-float(original[r['element']][n]) for r in rows if r['horizon']==0),
                          'max_absolute_difference': max(abs(r['xpts']-float(original[r['element']][n])) for r in rows if r['horizon']==0)} for n in ('control', 'xpts_v2')}
        require(load_json(folder/'h0_comparison.json') == comparison, 'h0 comparison mismatch')
    return rows, manifest
