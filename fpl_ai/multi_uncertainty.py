"""Frozen M5C empirical residual calibration over the accepted M5B boundary."""
import math
import shutil
import tempfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

from fpl_ai import multi_projection as mp
from fpl_ai import prospective as live
from fpl_ai import prospective_xpts as xp
from fpl_ai.experiment_io import key, load_rows, publish, verify_bundle, verify_m3
from fpl_ai.fpl_rules import require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv
from fpl_ai.transfer_optimiser import load_json

MODEL_ID = 'b0e9cf270c6524278ddb6c288c393aef580159c2a36a02b9a01e81cfadf4235b'
HISTORY_ID = '15330198b278c5b82eca1b756d46236ac998a573ce755022957c89d0c7394c4f'
MODEL = Path('data/multi_projection/models') / MODEL_ID
HISTORY = Path('data/multi_projection/scores') / HISTORY_ID
M3 = Path('data/modelling') / xp.M3_ID
LEVELS = (50, 80, 90)
CONTRACT = {
    'version': 'm5c-residual-intervals-v1', 'season': '2026-27',
    'm3_identity': xp.M3_ID, 'model_identity': MODEL_ID, 'history_identity': HISTORY_ID,
    'information_cutoff': xp.CUTOFF, 'levels_percent': list(LEVELS),
    'population': 'all labelled 2025-26 M5B historical OOS predictions; football players visible at original as-of state',
    'segmentation': 'horizon only; positions audited, not selected or tuned; no position fallback needed',
    'minimum_pool_rows': 100,
    'insufficient_pool': 'unavailable; never substitute another horizon or a shorter cumulative window',
    'interval': 'signed residual y-p; equal tails; 1-based floor((n+1)*(1-level)/2), ceil((n+1)*(1+level)/2); no interpolation or clipping',
    'cumulative': 'sum outcomes minus sum original direct forecasts, for complete offsets 0..2 and 0..4 only',
    'interpretation': 'empirical prediction intervals for realised points; not coefficient confidence intervals or guaranteed conditional coverage',
    'limitations': 'dependent players/GWs, overlapping windows, season shift and production refit prevent an exchangeability/finite-sample coverage guarantee',
    'evidence': '2025-26 consumed for calibration, not independent calibration validation; prospective 2026-27 evidence only',
    'frozen': 'no prospective input, automatic recalibration, model selection or optimiser change; new calibration needs explicit version/batch',
}


def reference(folder, manifest):
    return {'identity': manifest['identity_sha256'], 'manifest_sha256': sha256_file(Path(folder)/'manifest.json'),
            'artifacts': manifest['artifacts']}


def historical_residuals(model_dir=MODEL, history_dir=HISTORY, m3_dir=M3):
    """Rejoin the accepted separate predictions/labels; never fit a point model."""
    model = verify_bundle(model_dir, 'multi-horizon-model')
    history = verify_bundle(history_dir, 'multi-horizon-score')
    m3 = verify_m3(m3_dir)
    require((model['identity_sha256'], history['identity_sha256'], m3['identity_sha256']) ==
            (MODEL_ID, HISTORY_ID, xp.M3_ID), 'unaccepted calibration source identity')
    require(model['metadata']['protocol'] == mp.PROTOCOL and history['metadata']['protocol'] == mp.PROTOCOL and
            history['metadata']['model_identity'] == MODEL_ID, 'historical model/score mismatch')
    rows, _ = load_rows(m3_dir, ('test',))
    lookup = {key(r): r for r in rows}
    saved = read_csv(Path(model_dir)/'predictions.csv')
    labels = read_csv(Path(history_dir)/'outcomes.csv')
    index = lambda r: (int(r['horizon']), key(r))
    predictions = {index(r): r for r in saved}
    outcomes = {index(r): r for r in labels}
    expected = {(h, key(r)) for h in range(5) for r in rows if r['target_gameweek']+h <= 38}
    require(len(predictions) == len(saved) and len(outcomes) == len(labels) and
            set(predictions) == set(outcomes) == expected, 'historical calibration population mismatch')
    fit = load_json(Path(model_dir)/'fit.json')
    residuals = []
    for (h, k), pred in sorted(predictions.items()):
        r = lookup[k]
        target = k[1]+h
        future = lookup.get((k[0], target, k[2]))
        y = future['target_points'] if future else None
        stamp = future['label_available_at'] if y is not None else ''
        outcome = outcomes[h, k]
        require(int(pred['outcome_gameweek']) == int(outcome['outcome_gameweek']) == target and
                (int(outcome['target_points']) if outcome['target_points'] else None) == y and
                outcome['label_available_at'] == stamp, 'historical outcome join mismatch')
        require(live.before(fit[str(h)]['historical']['latest_settlement'], r['audit']['capture_time_utc']),
                'historical forecast uses future training labels')
        require(y is None or (live.before(r['audit']['capture_time_utc'], stamp) and live.before(stamp, xp.CUTOFF)),
                'calibration label beyond information cutoff')
        p = float(pred['direct'])
        require(math.isfinite(p), 'nonfinite historical prediction')
        residuals.append({'season': k[0], 'as_of_gameweek': k[1], 'element': k[2], 'horizon': h,
                          'target_gameweek': target, 'position': r['features']['deadline_position_id'],
                          'xpts': p, 'outcome': y, 'residual': y-p if y is not None else None,
                          'label_available_at': stamp, 'capture': r['audit']['capture_time_utc'],
                          'exclusion': None if y is not None else 'missing_target_label_or_registration'})
    sources = {'model': reference(model_dir, model), 'history': reference(history_dir, history),
               'm3': reference(m3_dir, m3), 'historical_fits': fit,
               'latest_calibration_settlement': max(r['label_available_at'] for r in residuals)}
    return residuals, sources


def pool(rows):
    usable = [r for r in rows if r['residual'] is not None]
    values = sorted(r['residual'] for r in usable)
    require(all(math.isfinite(v) for v in values), 'nonfinite calibration residual')
    n = len(values)
    available = n >= CONTRACT['minimum_pool_rows']
    intervals = {}
    for level in LEVELS:
        tail = Fraction(100-level, 200)
        lower_rank = math.floor((n+1)*tail)
        upper_rank = math.ceil((n+1)*(1-tail))
        require(not available or 1 <= lower_rank <= upper_rank <= n, 'unsupported finite residual quantile')
        intervals[str(level)] = {'lower_residual': values[lower_rank-1] if available else None,
                                'upper_residual': values[upper_rank-1] if available else None,
                                'lower_rank': lower_rank, 'upper_rank': upper_rank}
    return {'population_rows': len(rows), 'calibration_rows': n, 'excluded_rows': len(rows)-n,
            'position_counts': dict(sorted(Counter(str(r['position']) for r in usable).items())),
            'as_of_gameweeks': len({r['as_of_gameweek'] for r in usable}),
            'available': available, 'segment': 'all_positions', 'fallback': None,
            'unavailable_reason': None if available else 'fewer_than_100_labelled_windows', 'intervals': intervals}


def calibration_tables(residuals):
    indexed = {(r['as_of_gameweek'], r['element'], r['horizon']): r for r in residuals}
    require(len(indexed) == len(residuals), 'duplicate residual key')
    marginal = {str(h): pool([r for r in residuals if r['horizon'] == h]) for h in range(5)}
    cumulative = {}
    for length in (3, 5):
        windows = []
        exclusions = Counter()
        for first in (r for r in residuals if r['horizon'] == 0):
            rs = [indexed.get((first['as_of_gameweek'], first['element'], h)) for h in range(length)]
            reason = ('season_end' if first['as_of_gameweek']+length-1 > 38 else
                      'missing_horizon_or_label' if any(r is None or r['outcome'] is None for r in rs) else None)
            if reason: exclusions[reason] += 1
            windows.append({**first, 'residual': None if reason else sum(r['outcome'] for r in rs)-sum(r['xpts'] for r in rs)})
        cumulative[str(length)] = {**pool(windows), 'exclusions': dict(exclusions)}
    return {'horizons': marginal, 'cumulative': cumulative}


def build_calibration(output_dir=Path('data/multi_uncertainty/calibrations'), *, model_dir=MODEL, history_dir=HISTORY, m3_dir=M3):
    live.safe_output(output_dir, model_dir, history_dir, m3_dir)
    residuals, sources = historical_residuals(model_dir, history_dir, m3_dir)
    tables = calibration_tables(residuals)
    def writer(folder):
        for name, value in [('contract.json', CONTRACT), ('sources.json', sources), ('residuals.json', residuals), ('calibration.json', tables)]:
            atomic_write_json(folder/name, value)
    return publish(output_dir, {'kind': 'multi-uncertainty-calibration', 'contract': CONTRACT}, writer)


def load_calibration(folder, *, model_dir=MODEL, history_dir=HISTORY, m3_dir=M3):
    manifest = verify_bundle(folder, 'multi-uncertainty-calibration')
    require(manifest['metadata'] == {'kind': 'multi-uncertainty-calibration', 'contract': CONTRACT} and
            load_json(Path(folder)/'contract.json') == CONTRACT, 'incompatible calibration contract')
    residuals, sources = historical_residuals(model_dir, history_dir, m3_dir)
    tables = calibration_tables(residuals)
    require(load_json(Path(folder)/'sources.json') == sources and load_json(Path(folder)/'residuals.json') == residuals and
            load_json(Path(folder)/'calibration.json') == tables, 'calibration reconstruction mismatch')
    return tables, manifest


def bounds(point, selected):
    return {'segment': selected['segment'], 'fallback': selected['fallback'],
            'calibration_rows': selected['calibration_rows'], 'unavailable_reason': selected['unavailable_reason'],
            'intervals': {level: {'lower': point+q['lower_residual'] if selected['available'] else None,
                                  'upper': point+q['upper_residual'] if selected['available'] else None}
                          for level, q in selected['intervals'].items()}}


def attach(rows, tables):
    require(rows and len({(r['horizon'], r['element']) for r in rows}) == len(rows), 'duplicate/empty projection population')
    horizons = {r['horizon'] for r in rows}
    require(horizons == set(range(len(horizons))) and len(horizons) <= 5, 'incompatible horizons')
    populations = [{r['element'] for r in rows if r['horizon'] == h} for h in sorted(horizons)]
    require(all(p == populations[0] for p in populations), 'incomplete player keys')
    require(all(type(r['horizon']) is int and r['target_gameweek'] == r['as_of_gameweek']+r['horizon'] and
                r['target_gameweek'] <= 38 and math.isfinite(r['xpts']) for r in rows), 'invalid projection target')
    marginal = [{**r, **bounds(r['xpts'], tables['horizons'][str(r['horizon'])])} for r in rows]
    indexed = {(r['element'], r['horizon']): r for r in rows}
    cumulative = []
    for length in (3, 5):
        for first in (r for r in rows if r['horizon'] == 0):
            rs = [indexed.get((first['element'], h)) for h in range(length)]
            reason = ('season_end' if first['as_of_gameweek']+length-1 > 38 else
                      'projection_horizon_too_short' if any(r is None for r in rs) else None)
            point = None if reason else sum(r['xpts'] for r in rs)
            cumulative.append({k: first[k] for k in ('season', 'as_of_gameweek', 'element', 'position')} |
                              {'length': length, 'xpts': point, 'window_unavailable_reason': reason,
                               **bounds(point if point is not None else 0, tables['cumulative'][str(length)])})
            if reason:
                cumulative[-1]['intervals'] = {str(l): {'lower': None, 'upper': None} for l in LEVELS}
    return {'rows': marginal, 'cumulative': cumulative}


def freeze(projections_dir, calibration_dir, model_dir, m4e_model_dir,
           output_dir=Path('data/multi_uncertainty/forecasts'), *, clock=live.now_utc, history_dir=HISTORY, m3_dir=M3):
    live.safe_output(output_dir, projections_dir, calibration_dir, model_dir, m4e_model_dir, history_dir, m3_dir)
    started = live.stamp(clock)
    tables, calibration = load_calibration(calibration_dir, model_dir=model_dir, history_dir=history_dir, m3_dir=m3_dir)
    rows, projection = mp.verify_projection(projections_dir, model_dir, m4e_model_dir)
    p = projection['metadata']
    require(p['season'] == CONTRACT['season'] and p['model_identity'] == MODEL_ID and
            live.before(xp.CUTOFF, p['capture']), 'incompatible uncertainty state/model')
    require(live.not_after(p['computed_at'], started) and live.before(started, p['deadline']), 'uncertainty must precede original deadline')
    product = attach(rows, tables)
    completed = live.stamp(clock)
    require(live.not_after(started, completed), 'uncertainty clock reversed')
    metadata = {'kind': 'multi-uncertainty-forecast', 'contract': CONTRACT,
                'projection': reference(projections_dir, projection), 'calibration': reference(calibration_dir, calibration),
                'state': p, 'started_at': started, 'computed_at': completed}
    def writer(folder):
        atomic_write_json(folder/'uncertainty.json', product)
        atomic_write_json(folder/'projection.json', xp.archive(projections_dir))
    def guard():
        stamp = live.stamp(clock)
        require(live.not_after(completed, stamp) and live.before(stamp, p['deadline']), 'uncertainty publication reached deadline or clock reversed')
    out, reused = publish(output_dir, metadata, writer, publication_guard=guard)
    try:
        verify_uncertainty(out, calibration_dir, model_dir, m4e_model_dir, history_dir=history_dir, m3_dir=m3_dir)
        guard()
    except BaseException:
        if not reused: shutil.rmtree(out)
        raise
    return out, reused


def verify_uncertainty(folder, calibration_dir, model_dir, m4e_model_dir, *, history_dir=HISTORY, m3_dir=M3):
    folder = Path(folder)
    manifest = verify_bundle(folder, 'multi-uncertainty-forecast')
    m = manifest['metadata']
    tables, calibration = load_calibration(calibration_dir, model_dir=model_dir, history_dir=history_dir, m3_dir=m3_dir)
    require(m['contract'] == CONTRACT and m['calibration'] == reference(calibration_dir, calibration), 'uncertainty calibration mismatch')
    with tempfile.TemporaryDirectory() as tmp:
        projection_dir = xp.restore(Path(tmp), 'projection', load_json(folder/'projection.json'))
        rows, projection = mp.verify_projection(projection_dir, model_dir, m4e_model_dir)
        require(m['projection'] == reference(projection_dir, projection) and m['state'] == projection['metadata'], 'uncertainty projection/state mismatch')
    p = m['state']
    require(p['season'] == CONTRACT['season'] and p['model_identity'] == MODEL_ID and live.before(xp.CUTOFF, p['capture']) and
            live.not_after(p['computed_at'], m['started_at']) and live.not_after(m['started_at'], m['computed_at']) and
            live.before(m['computed_at'], p['deadline']), 'invalid uncertainty timing/model')
    product = load_json(folder/'uncertainty.json')
    require(product == attach(rows, tables), 'uncertainty replay mismatch')
    return product, manifest
