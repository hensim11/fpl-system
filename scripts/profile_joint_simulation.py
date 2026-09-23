"""Numerical scenario-count convergence; never dependency-model selection."""
import argparse
from pathlib import Path
from time import perf_counter

from fpl_ai import joint_simulation as js, simulation_plans as sp
from fpl_ai.historical_io import atomic_write_json
from scripts.verify_joint_simulation import CALIBRATION, UNCERTAINTY, M4E, PLAN


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=Path('docs/M5D_CONVERGENCE.json'))
    args = parser.parse_args()
    started = perf_counter()
    rows, tables, donor, binding = js.inputs(UNCERTAINTY, CALIBRATION, js.uc.MODEL, M4E)
    candidates, _ = sp.load_plans(PLAN, rows, binding['projection'])
    source_seconds = perf_counter()-started
    runs = []
    for seed in (1729, 2718, 31415):
        t = perf_counter()
        report = sp.compute(rows, donor, js.configuration(32768, seed), candidates)
        elapsed = perf_counter()-t
        changes = {}
        for model, data in report['models'].items():
            a, b = data['convergence_prefixes']['16384'], data['convergence_prefixes']['32768']
            changes[model] = {
                'max_mean_change': max(abs(a[n]['mean']-b[n]['mean']) for n in a),
                'max_p05_p10_p90_p95_change': max(abs(a[n][k]-b[n][k]) for n in a for k in ('p05', 'p10', 'p90', 'p95')),
                'max_lower_tail_mean_change': max(abs(a[n]['lower_tail_mean_10pct']-b[n]['lower_tail_mean_10pct']) for n in a),
                'max_paired_win_probability_change': max(abs(a[n][k]['probability_win']-b[n][k]['probability_win']) for n in a for k in ('vs_no_transfer', 'vs_greedy')),
                'max_highest_probability_change': max(abs(a[n]['probability_highest_split_ties']-b[n]['probability_highest_split_ties']) for n in a),
            }
        runs.append({'seed': seed, 'seconds_both_models_and_plan_metrics': elapsed, 'default_to_double_changes': changes, 'evaluation': report})
    atomic_write_json(args.report, {'purpose': 'Monte Carlo precision/runtime only; fixed dependency law, no model selection',
        'default_count': js.DEFAULT_COUNT, 'source_verification_seconds': source_seconds, 'runs': runs,
        'precision_scope': 'broad path distribution comparisons; cannot resolve tiny top-N expectation differences; model error not included in Monte Carlo SE',
        'practical_precision_targets': {'mean_points': .5, 'tail_quantile_points': 1., 'paired_probability': .015}})
    print(args.report)


if __name__ == '__main__': main()
