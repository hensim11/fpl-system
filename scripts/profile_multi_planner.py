"""Observe unchanged full-population exact M5B search; never weaken the solver."""
import argparse
import inspect
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from fpl_ai import transfer_path as planner
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_optimiser import load_json
from scripts.verify_multi_gameweek import MODELS, MODEL, SQUAD

PROJECTION = Path('data/multi_projection/forecasts/03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b')
PLAN = Path('data/transfer_paths/0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=Path('docs/M5C_PROFILE.json'))
    args = parser.parse_args()
    calls = []
    original = planner.milp
    def measured(*a, **kw):
        stack = {f.function for f in inspect.stack()}
        stage = ('count_proof' if 'minimize_count' in stack else
                 'tie_enumeration' if 'enumerate_tied' in stack else
                 'lexicographic_proof' if 'solve_tied' in stack else 'primary_search')
        scope = 'greedy' if 'greedy_path' in stack else 'top_three'
        started = time.perf_counter()
        result = original(*a, **kw)
        calls.append({'scope': scope, 'stage': stage, 'seconds': time.perf_counter()-started,
                      'status': int(result.status), 'nodes': int(result.mip_node_count) if getattr(result, 'mip_node_count', None) is not None else None,
                      'presolve': kw['options']['presolve'], 'mip_rel_gap': kw['options']['mip_rel_gap']})
        return result
    with tempfile.TemporaryDirectory() as tmp, patch.object(planner, 'milp', measured):
        start = time.perf_counter()
        fresh, reused = planner.build_plan(PROJECTION, MODELS, MODEL, SQUAD, Path(tmp)/'plans')
        elapsed = time.perf_counter()-start
        if reused or fresh.name != PLAN.name or load_json(fresh/'decision.json') != load_json(PLAN/'decision.json'):
            raise ValueError('profiled decision differs from accepted M5B plan')
        if any((fresh/p.name).read_bytes() != p.read_bytes() for p in PLAN.iterdir()):
            raise ValueError('profiled plan bytes differ')
    groups = defaultdict(lambda: {'calls': 0, 'seconds': 0})
    for call in calls:
        g = groups[call['scope']+':'+call['stage']]
        g['calls'] += 1
        g['seconds'] += call['seconds']
    atomic_write_json(args.report, {'wall_seconds': elapsed, 'milp_seconds': sum(c['seconds'] for c in calls),
                                   'solve_count': len(calls), 'groups': dict(groups), 'calls': calls,
                                   'population': 659, 'selectable': 554, 'solver_candidates': 555,
                                   'horizon': 5, 'top_n': 3, 'max_transfers_per_gw': 2,
                                   'decision_identity': PLAN.name, 'all_decision_bytes_identical': True,
                                   'production_planner_changed': False,
                                   'timing_note': 'one local instrumented run; wall time includes validation/publication/greedy; MILP times exclude Python matrix/replay overhead'})
    print(args.report)


if __name__ == '__main__': main()
