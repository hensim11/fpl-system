"""Independent M5E report arithmetic and retained synthetic comparison audit.

No report/decomposition builder is used as the oracle. M5B's exhaustive XI audit
and M5D's scalar RNG/return/metric audit verify the actual new dependency identities.
"""
import argparse
import json
import math
from fractions import Fraction
from datetime import datetime, timedelta
from pathlib import Path

from fpl_ai.experiment_io import verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import load_json
from scripts.verify_multi_gameweek import audit_plan
from scripts.verify_joint_simulation import audit as simulation_audit, PLAN


def check(value, message):
    if not value: raise ValueError(message)


def close(a, b):
    check(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-10), f'arithmetic mismatch {a} != {b}')


def audit(bundle, roots):
    manifest = verify_bundle(bundle, 'personal-decision')
    summary = load_json(bundle/'summary.json')
    attestation = manifest['metadata']['attestation']
    check(set(attestation) == {'imported_at','created_at','publication_checked_at'}, 'attestation fields')
    times = {k: datetime.fromisoformat(v.replace('Z','+00:00')) for k,v in attestation.items()}
    check(all(t.utcoffset() == timedelta(0) for t in times.values()), 'attestation UTC')
    check(times['imported_at'] <= times['created_at'] <= times['publication_checked_at'], 'attestation chronology')
    check(all(summary['timing'][k] == v for k,v in attestation.items()), 'summary attestation mismatch')
    observed = datetime.fromisoformat(summary['timing']['personal_observed_at'].replace('Z','+00:00'))
    capture = datetime.fromisoformat(summary['timing']['snapshot_capture'].replace('Z','+00:00'))
    check(observed <= times['imported_at'], 'observation after import')
    if summary['config']['mode'] == 'pre-deadline':
        deadline = datetime.fromisoformat(summary['timing']['first_target_deadline'].replace('Z','+00:00'))
        checked = times['publication_checked_at']
        check(capture <= observed and checked < deadline, 'pre-deadline attestation')
        check(checked-capture <= timedelta(hours=24) and checked-observed <= timedelta(hours=24), 'freshness attestation')
    refs = load_json(bundle/'dependencies.json')
    paths = {}
    for role, ref in refs.items():
        matches = {p.parent.resolve() for root in roots for p in root.rglob(ref['identity']+'/manifest.json')}
        check(len(matches) == 1, 'missing/ambiguous independent dependency '+role)
        paths[role] = matches.pop()
        check(sha256_file(paths[role]/'manifest.json') == ref['manifest_sha256'], 'dependency bytes changed')
    rows = load_json(paths['projection']/'projections.json')
    decision = load_json(paths['plan']/'decision.json')
    expected = {'no_transfer':decision['baseline'], 'greedy':decision['greedy'],
                **{f'exact_{i}':p for i,p in enumerate(decision['plans'],1)}}
    check(summary['plans'] == expected, 'summary changed M5B candidates')
    check(summary['returned_exact_paths'] == len(decision['plans']), 'emitted path count')
    independent = audit_plan(paths['plan'], rows)
    lookup = {(r['horizon'],r['element']): Fraction(r['xpts']) for r in rows}
    comparisons = 0
    for name, plan in expected.items():
        for baseline in ('no_transfer','greedy'):
            sums = [Fraction(),Fraction(),Fraction()]
            for h,(w,b) in enumerate(zip(plan['weeks'],expected[baseline]['weeks'])):
                delta_xi = sum((lookup[h,e] for e in w['starting_xi']),Fraction())-sum((lookup[h,e] for e in b['starting_xi']),Fraction())
                delta_captain = lookup[h,w['captain']]-lookup[h,b['captain']]
                delta_hits = b['transfer_hit']-w['transfer_hit']
                values = (delta_xi,delta_captain,delta_hits)
                actual = summary['decomposition'][name][baseline]['weeks'][h]
                for key,v in zip(('xi_change','captain_bonus_change','hit_change'),values): close(actual[key],float(v))
                close(actual['net_change'],float(sum(values)))
                for i,v in enumerate(values): sums[i]+=v
                comparisons += 1
            total = summary['decomposition'][name][baseline]['horizon']
            for key,v in zip(('xi_change','captain_bonus_change','hit_change'),sums): close(total[key],float(v))
            close(total['net_change'],float(sum(sums)))
            close(total['net_change'],plan['total_points']-expected[baseline]['total_points'])
    archive = load_json(paths['projection']/'source.json')
    evidence = json.loads(archive['files']['evidence.json'])
    bootstrap = json.loads(evidence['snapshot']['files']['bootstrap.json'])
    raw = {p['id']:p for p in bootstrap['elements']}
    for element, player in summary['population'].items():
        p = raw[int(element)]
        check((player['name'],player['team'],player['position'],player['purchase_price'],player['can_select']) ==
              (p['web_name'],p['team'],p['element_type'],p['now_cost'],p['can_select']), 'summary metadata not from original snapshot')
    check(summary['personal']['squad'] == load_json(paths['plan']/'squad.json'), 'personal account economics mismatch')
    check(summary['simulation'] == load_json(paths['evaluation']/'evaluation.json'), 'simulation fields changed')
    check(summary['empirical_player_intervals'] == load_json(paths['uncertainty']/'uncertainty.json'), 'M5C intervals changed')
    # This demonstration deliberately shares the synthetic squad/account values with M5B/D.
    check(summary['personal']['provenance']['kind'] == 'synthetic', 'this script audits only the synthetic demonstration')
    check((paths['plan']/'decision.json').read_bytes() == (PLAN/'decision.json').read_bytes(), 'existing equivalent M5B decision differs')
    original_evaluation = Path('data/simulation_evaluations/36a266e775e124a6d36bfb813e0aedf364c200a394a82d9b25e0b48a75902c3f')
    check((paths['evaluation']/'evaluation.json').read_bytes() == (original_evaluation/'evaluation.json').read_bytes(), 'existing equivalent M5D evaluation differs')
    stochastic = simulation_audit(paths['simulation'], paths['evaluation'], calibration=paths['calibration'],
                                 uncertainty=paths['uncertainty'], plan_dir=paths['plan'], m4e=paths['m4e_model'])
    return {'bundle_identity':manifest['identity_sha256'], 'synthetic_not_user_advice':True, 'retained_attestation_independently_checked':True,
        'attestation':attestation,
        'exact_paths':len(decision['plans']), 'candidate_entries':len(expected),
        'candidate_gameweeks':sum(len(p['weeks']) for p in expected.values()), 'per_gw_baseline_decompositions':comparisons,
        'objectives':{n:p['total_points'] for n,p in expected.items()},
        'independent_XI_economics_FT_and_totals':independent['independent_XI_economics_FT_and_totals'],
        'all_baseline_decompositions_reconcile':True, 'bound_snapshot_metadata_exact':True,
        'empirical_intervals_unchanged':True, 'equivalent_existing_M5B_decision_bytes':True,
        'equivalent_existing_M5D_evaluation_bytes':True, 'independent_actual_new_path_simulation_audit':stochastic,
        'report_sha256':{name:sha256_file(bundle/name) for name in ('summary.json','report.md','report.html')}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--evidence-root',type=Path,action='append')
    parser.add_argument('--report',type=Path,default=Path('docs/M5E_VERIFICATION.json'))
    args=parser.parse_args()
    atomic_write_json(args.report,audit(args.bundle,args.evidence_root or [Path('data')]))
    print(args.report)


if __name__=='__main__': main()
