"""Independent M5C residual/order-statistic, raw settlement and metric audit.

Production builds the artifacts; this verifier separately reconstructs their
arithmetic from M3 CSVs, saved M5B predictions and raw live fixture explanations.
No assert statements: checks execute under optimized Python too.
"""
import argparse
import math
import tempfile
from collections import defaultdict
from pathlib import Path
from statistics import mean

from scipy.stats import spearmanr

from fpl_ai import multi_uncertainty as uc, multi_outcomes as mo
from fpl_ai.experiment_io import verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv
from fpl_ai.transfer_optimiser import load_json
from scripts.profile_multi_planner import PROJECTION
from scripts.verify_multi_gameweek import MODEL
from tests.test_multi_uncertainty import UncertaintyTests, republish
from tests.test_prospective import fingerprint


def check(value, message):
    if not value: raise ValueError(message)


def close(a, b):
    check((a is None and b is None) or (a is not None and b is not None and abs(a-b) < 1e-12), 'independent metric differs')


def history_audit(calibration):
    preds = read_csv(uc.MODEL/'predictions.csv')
    labels = {(r['season'], int(r['target_gameweek']), int(r['element'])): r for r in read_csv(uc.M3/'labels.csv')}
    positions = {(r['season'], int(r['target_gameweek']), int(r['element'])): int(r['deadline_position_id']) for r in read_csv(uc.M3/'features.csv')}
    residuals = load_json(calibration/'residuals.json')
    pools = defaultdict(list)
    windows = defaultdict(dict)
    saved = {(r['horizon'], r['as_of_gameweek'], r['element']): r for r in residuals}
    check(len(saved) == len(preds) == len(residuals), 'historical residual key counts')
    for p in preds:
        h, g, e = int(p['horizon']), int(p['target_gameweek']), int(p['element'])
        label = labels.get((p['season'], g+h, e))
        y = int(label['target_points']) if label and label['target_points'] else None
        prediction = float(p['direct'])
        r = saved[h, g, e]
        check(r['xpts'] == prediction and r['outcome'] == y and r['position'] == positions[p['season'], g, e], 'residual source join')
        check(r['residual'] == (y-prediction if y is not None else None), 'signed residual reconstruction')
        if y is not None:
            check(label['label_available_at'] == r['label_available_at'] < '2026-07-01T00:00:00Z', 'prior-only evidence')
            pools['h'+str(h)].append(y-prediction)
        windows[g, e][h] = (prediction, y)
    expected_cumulative = {}
    for length in (3, 5):
        values = []
        reasons = defaultdict(int)
        for (g, e), entries in windows.items():
            if 0 not in entries: continue
            if g+length-1 > 38:
                reasons['season_end'] += 1
            elif any(h not in entries or entries[h][1] is None for h in range(length)):
                reasons['missing_horizon_or_label'] += 1
            else:
                values.append(sum(entries[h][1] for h in range(length))-sum(entries[h][0] for h in range(length)))
        pools['c'+str(length)] = values
        expected_cumulative[str(length)] = dict(reasons)
    calibration_table = load_json(calibration/'calibration.json')
    evidence = {}
    for name, values in pools.items():
        table = calibration_table['horizons' if name[0] == 'h' else 'cumulative'][name[1:]]
        values.sort(); n = len(values)
        check(table['calibration_rows'] == n and n >= 100, 'calibration pool count')
        levels = {}
        for level in (50, 80, 90):
            # Integer arithmetic independently implements the fixed 1-based order statistics.
            low = ((n+1)*(100-level))//200
            high = ((n+1)*(100+level)+199)//200
            q = table['intervals'][str(level)]
            check((q['lower_rank'], q['upper_rank'], q['lower_residual'], q['upper_residual']) ==
                  (low, high, values[low-1], values[high-1]), 'independent residual order statistic')
            coverage = sum(values[low-1] <= v <= values[high-1] for v in values)/n
            levels[str(level)] = {'lower_residual': q['lower_residual'], 'upper_residual': q['upper_residual'],
                                  'width': q['upper_residual']-q['lower_residual'],
                                  'calibration_reuse_coverage_not_validation': coverage}
        evidence[name] = {'rows': n, 'as_of_gameweeks': table['as_of_gameweeks'], 'position_counts': table['position_counts'], 'levels': levels}
    for length, reasons in expected_cumulative.items():
        check(calibration_table['cumulative'][length]['exclusions'] == reasons, 'independent cumulative eligibility')
    return {'source_identities': {'model': uc.MODEL_ID, 'score': uc.HISTORY_ID, 'm3': uc.xp.M3_ID},
            'residual_rows': len(residuals), 'pools': evidence, 'cumulative_exclusions': expected_cumulative,
            'historical_residuals_and_quantiles_independently_reconstructed': True,
            'calibration_reuse_coverage_is_not_independent_validation': True}


def metric_audit(rows, report):
    pairs = [r for r in rows if r['outcome'] is not None and r['xpts'] is not None]
    check(report['population_rows'] == len(rows) and report['scored_rows'] == len(pairs), 'scored row counts')
    close(report['mae'], mean(abs(r['outcome']-r['xpts']) for r in pairs) if pairs else None)
    close(report['rmse'], math.sqrt(mean((r['outcome']-r['xpts'])**2 for r in pairs)) if pairs else None)
    groups = defaultdict(list)
    for r in pairs: groups[r['projection_identity'], r['target_gameweek'], r.get('horizon', r.get('length'))].append(r)
    correlations = []
    for rs in groups.values():
        if len(rs) > 1 and len({r['outcome'] for r in rs}) > 1 and len({r['xpts'] for r in rs}) > 1:
            correlations.append(float(spearmanr([r['outcome'] for r in rs], [r['xpts'] for r in rs]).statistic))
    close(report['mean_within_gameweek_spearman'], mean(correlations) if correlations else None)
    for level in (50, 80, 90):
        valid = [r for r in pairs if all(v is not None for v in r['intervals'][str(level)].values())]
        covered = sum(r['intervals'][str(level)]['lower'] <= r['outcome'] <= r['intervals'][str(level)]['upper'] for r in valid)
        interval = report['intervals'][str(level)]
        check(interval['covered_rows'] == covered and interval['missing_unscorable_rows'] == len(rows)-len(valid), 'interval counts')
        close(interval['coverage'], covered/len(valid) if valid else None)
        close(interval['average_width'], mean(r['intervals'][str(level)]['upper']-r['intervals'][str(level)]['lower'] for r in valid) if valid else None)


def score_audit(folder):
    verify_bundle(folder, 'multi-uncertainty-score')
    rows = load_json(folder/'rows.json')
    cumulative = load_json(folder/'cumulative.json')
    report = load_json(folder/'metrics.json')
    metric_audit(rows, report['aggregate'])
    for group, metric in report['targets'].items():
        identity, gw = group.split(':')
        metric_audit([r for r in rows if r['projection_identity'] == identity and r['target_gameweek'] == int(gw)], metric)
    for h in range(5): metric_audit([r for r in rows if r['horizon'] == h], report['horizons'][str(h)])
    for p in range(1, 5):
        metric_audit([r for r in rows if r['position'] == p], report['positions'][str(p)])
        for h in range(5):
            metric_audit([r for r in rows if r['horizon'] == h and r['position'] == p], report['horizon_positions'][f'{h}:{p}'])
    index = {(r['projection_identity'], r['element'], r['horizon']): r for r in rows}
    for r in cumulative:
        parts = [index.get((r['projection_identity'], r['element'], h)) for h in range(r['length'])]
        eligible = all(p is not None and p['outcome'] is not None for p in parts) and r['xpts'] is not None
        check((r['outcome'] is not None) == eligible, 'cumulative score eligibility')
        if eligible:
            check(r['outcome'] == sum(p['outcome'] for p in parts) and r['xpts'] == sum(p['xpts'] for p in parts), 'cumulative arithmetic')
    for length in (3, 5): metric_audit([r for r in cumulative if r['length'] == length], report['cumulative'][str(length)])
    return {'scored_player_rows': report['scored_player_rows'], 'settled_target_gameweeks': report['settled_target_gameweeks'],
            'pending_targets': len(report['pending_targets']), 'mae': report['aggregate']['mae'], 'rmse': report['aggregate']['rmse'],
            'cumulative_scored_rows': {str(n): report['cumulative'][str(n)]['scored_rows'] for n in (3, 5)}}


def synthetic_audit():
    # Only upstream evidence generation is synthetic; calibration/forecast/settle/
    # score publication and all settlement authority checks execute production code.
    fixture = UncertaintyTests()
    fixture.setUp()
    try:
        before = fingerprint(fixture.calibration), fingerprint(fixture.forecast)
        settlements = []
        stages = []
        for gw in range(2, 7):
            settlement = fixture.settle(gw)
            settlements.append(settlement)
            raw = load_json(settlement/'live.json')
            bootstrap = load_json(settlement/'bootstrap.json')
            fixtures = load_json(settlement/'fixtures.json')
            event = next(e for e in bootstrap['events'] if e['id'] == gw)
            check(event['finished'] is True and event['data_checked'] is True, 'raw event flags')
            target = {f['id'] for f in fixtures if f['event'] == gw and f['finished'] is True}
            check(len(target) == 2, 'complete double evidence')
            totals = {}
            for r in raw['elements']:
                check(all(e['fixture'] in target for e in r['explain']), 'explanation fixture membership')
                totals[r['id']] = sum(s['points'] for e in r['explain'] for s in e['stats'])
                check(totals[r['id']] == r['stats']['total_points'], 'independent raw target-GW total')
            score = fixture.score(settlements)
            for r in load_json(score/'rows.json'):
                if r['target_gameweek'] == gw: check(r['outcome'] == totals[r['element']], 'independent score/raw outcome join')
            stages.append(score_audit(score))
        repeated = fixture.score(settlements+settlements)
        check(repeated.name == score.name, 'repeated evidence counted twice')
        check(before == (fingerprint(fixture.calibration), fingerprint(fixture.forecast)), 'prospective evidence altered calibration/forecast')
        blank = fixture.settle(client=fixture.client(2, settled=True, empty=True))
        blank_score = fixture.score([blank])
        check(load_json(blank_score/'metrics.json')['aggregate']['scored_rows'] == 0, 'blank became zero')
        blank_evidence = score_audit(blank_score)
        return {'synthetic_not_real_outcomes': True, 'stages': stages, 'blank': blank_evidence,
                'raw_outcomes_point_errors_ranks_coverage_widths_cumulative_eligibility_independent': True,
                'duplicate_reuse_same_identity': True, 'frozen_calibration_and_forecast_preserved': True}
    finally:
        fixture.doCleanups()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--calibration-dir', type=Path, required=True)
    parser.add_argument('--uncertainty-dir', type=Path, required=True)
    parser.add_argument('--report', type=Path, default=Path('docs/M5C_VERIFICATION.json'))
    args = parser.parse_args()
    calibration = args.calibration_dir
    uc.load_calibration(calibration)
    history = history_audit(calibration)
    product, forecast = uc.verify_uncertainty(args.uncertainty_dir, calibration, uc.MODEL, MODEL)
    originals = load_json(PROJECTION/'projections.json')
    check(len(originals) == len(product['rows']) and all(all(r[k] == v for k, v in p.items()) for p, r in zip(originals, product['rows'])), 'original points/keys changed')
    synthetic = synthetic_audit()
    before = fingerprint(calibration), fingerprint(args.uncertainty_dir)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        fresh, reused = uc.build_calibration(root/'calibrations')
        check(not reused and fresh.name == calibration.name, 'fresh calibration identity differs')
        captured = fingerprint(fresh)
        check(uc.build_calibration(root/'calibrations')[1] and captured == fingerprint(fresh), 'calibration reuse rewrote artifact')
        # Exact offline restoration verifies original runtime timestamps; never backdate a new freeze.
        restored = uc.xp.restore(root, 'forecast', uc.xp.archive(args.uncertainty_dir))
        restored_product, _ = uc.verify_uncertainty(restored, fresh, uc.MODEL, MODEL)
        check(restored_product == product, 'offline restored uncertainty differs')
        bad = republish(calibration, root/'bad', lambda m, v: v['calibration.json']['horizons']['0']['intervals']['90'].update(upper_residual=999))
        try: uc.load_calibration(bad)
        except ValueError: pass
        else: raise ValueError('corrupt rehashed calibration admitted')
        empty, _ = mo.score([args.uncertainty_dir], [], calibration, uc.MODEL, MODEL, root/'scores')
        captured = fingerprint(empty)
        check(mo.score([args.uncertainty_dir], [], calibration, uc.MODEL, MODEL, root/'scores')[1] and fingerprint(empty) == captured, 'score reuse modified evidence')
        real = score_audit(empty)
    check(before == (fingerprint(calibration), fingerprint(args.uncertainty_dir)), 'read-only verification altered evidence')
    report = {'contract': uc.CONTRACT, 'calibration_identity': calibration.name, 'uncertainty_identity': args.uncertainty_dir.name,
              'uncertainty_manifest': forecast, 'historical': history, 'synthetic_lifecycle': synthetic,
              'current_real_evidence': real, 'original_projection_fields_exact': True,
              'fresh_calibration_and_offline_uncertainty_replay_identical': True,
              'calibration_score_reuse_bytes_and_mtimes_preserved': True, 'rehashed_calibration_corruption_rejected': True,
              'source_sha256': {str(p): sha256_file(p) for p in (Path('fpl_ai/multi_uncertainty.py'), Path('fpl_ai/multi_outcomes.py'))}}
    atomic_write_json(args.report, report)
    print(args.report)


if __name__ == '__main__': main()
