"""M5A independent plan arithmetic/formation audit over real frozen GW6 rows.

Uses production forecast verification and optimisation, but independently checks
all squad, transfer, XI and captain arithmetic and enumerates all legal squad XIs.
Never fetches a live API or reads target outcomes.
"""
import argparse
import itertools
import json
import math
import tempfile
from collections import Counter
from pathlib import Path

from fpl_ai.transfer_optimiser import build_decision
from fpl_ai.experiment_io import verify_bundle
from fpl_ai.historical_io import atomic_write_json, sha256_file

FORECAST = Path('data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527')
MODEL = Path('data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230')
SQUAD = Path('tests/fixtures/optimiser/demo_gw6_squad.json')


def check(value, message):
    if not value: raise ValueError(message)


def fingerprint(folder):
    return {p.name: [sha256_file(p), p.stat().st_mtime_ns] for p in folder.iterdir() if p.is_file()}


def audit(folder):
    manifest = verify_bundle(folder, 'one-gw-transfer-decision')
    data = json.loads((folder/'decision.json').read_text())
    state = json.loads((folder/'squad.json').read_text())
    population = json.loads((folder/'population.json').read_text())
    # Read independently from the original forecast and raw embedded bootstrap.
    import csv
    predictions = {int(r['element']): r for r in csv.DictReader((FORECAST/'predictions.csv').open())}
    evidence = json.loads((FORECAST/'evidence.json').read_text())
    raw = json.loads(evidence['snapshot']['files']['bootstrap.json'])
    players = {r['id']: r for r in raw['elements'] if r['element_type'] in (1, 2, 3, 4)}
    check(set(predictions) == set(players) == {r['element'] for r in population}, 'population mismatch')
    check(all(type(p.get('can_select')) is bool for p in players.values()), 'selectability missing/malformed')
    eligible = {e for e, p in players.items() if p['can_select']}
    check(len(players) == 659 and len(eligible) == 554, 'GW6 population counts changed')
    check(all(players[e]['can_select'] is True for e in (124, 449)), 'original winners unselectable')
    check(all(p['can_select'] == players[p['element']]['can_select'] for p in population), 'bound selectability mismatch')
    model = manifest['metadata']['model']; column = 'control' if model == 'control' else 'xpts_v2'
    points = {e: float(r[column]) for e, r in predictions.items()}
    held = {r['element']: r['selling_price'] for r in state['players']}
    check(len(held) == 15, 'initial squad size')
    population_counts = {'forecast_population': len(players), 'transfer_in_eligible_population': len(eligible),
              'eligible_not_owned': len(eligible - held.keys()), 'owned_population': len(held),
              'owned_unselectable': len(held.keys() - eligible),
              'optimisation_population': len(eligible | held.keys())}
    check(data['population_counts'] == population_counts, 'reported population counts differ')
    def legal(ids):
        check(len(set(ids)) == 15 and Counter(players[e]['element_type'] for e in ids) == {1:2, 2:5, 3:5, 4:3}, 'positions')
        check(max(Counter(players[e]['team'] for e in ids).values()) <= 3, 'clubs')
    legal(held)
    for plan in [data['baseline'], *data['plans']]:
        ids = plan['squad']; legal(ids)
        incoming, outgoing = set(ids)-held.keys(), held.keys()-set(ids)
        check(incoming <= eligible, 'unselectable incoming player')
        check(incoming == set(plan['transfers_in']) and outgoing == set(plan['transfers_out']), 'transfers')
        check(len(incoming) == len(outgoing) == plan['transfer_count'] <= 2, 'count')
        bank = state['bank'] + sum(held[e] for e in outgoing) - sum(players[e]['now_cost'] for e in incoming)
        check(bank == plan['resulting_bank'] and bank >= 0, 'budget')
        xi = plan['starting_xi']; captain = plan['captain']
        check(len(xi) == len(set(xi)) == 11 and set(xi) <= set(ids) and captain in xi, 'XI/captain')
        counts = Counter(players[e]['element_type'] for e in xi)
        check(counts[1] == 1 and counts[2] >= 3 and counts[3] >= 2 and counts[4] >= 1, 'formation')
        gross = math.fsum(points[e] for e in xi); bonus = points[captain]
        hit = 4 * max(0, len(incoming)-state['free_transfers'])
        net = gross + bonus - hit
        check(gross == plan['gross_xi_points'] and bonus == plan['captain_bonus'] and hit == plan['transfer_hit'] and net == plan['net_points'], 'objective')
        check(plan['gain_vs_no_transfer'] == net-data['baseline']['net_points'], 'gain')
        exhaustive = []
        for starting in itertools.combinations(ids, 11):
            c = Counter(players[e]['element_type'] for e in starting)
            if c[1] == 1 and c[2] >= 3 and c[3] >= 2 and c[4] >= 1:
                exhaustive.append(math.fsum(points[e] for e in starting) + max(points[e] for e in starting)-hit)
        check(net == max(exhaustive), 'XI not optimal')
    check(len({tuple(p['squad']) for p in data['plans']}) == len(data['plans']), 'duplicate squad')
    check(all(a['net_points'] >= b['net_points']-1e-6 for a,b in zip(data['plans'],data['plans'][1:])), 'ranking')
    return {'identity': folder.name, 'model': model, 'population_counts': population_counts,
            'original_winners_selectable': {str(e): players[e]['can_select'] for e in (124,449)},
            'all_incoming_players_selectable': True,
            'baseline': data['baseline'], 'plans': data['plans'],
            'all_squads_economics_formations_captains_objectives_exact': True,
            'all_XIs_independently_exhaustively_optimal': True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=Path('docs/M5A_VERIFICATION.json'))
    parser.add_argument('--prior-report', type=Path, default=Path('docs/M5A_PRE_HARDENING_VERIFICATION.json'), help='pre-hardening report for exact plan comparison')
    parser.add_argument('--artifact-dir', type=Path, default=Path('data/decisions'))
    args = parser.parse_args()
    result = {'demo_only_not_user_team': True, 'no_target_outcomes_or_network_required': True, 'models': {}}
    with tempfile.TemporaryDirectory() as tmp:
        for model in ('control', 'v2'):
            out, _ = build_decision(FORECAST, MODEL, model, SQUAD, args.artifact_dir)
            before = fingerprint(out)
            fresh, _ = build_decision(FORECAST, MODEL, model, SQUAD, Path(tmp)/model)
            check(verify_bundle(out) == verify_bundle(fresh), 'fresh content mismatch')
            reused, yes = build_decision(FORECAST, MODEL, model, SQUAD, args.artifact_dir)
            check(yes and reused == out and before == fingerprint(out), 'reuse changed bytes/mtime')
            result['models'][model] = {**audit(out), 'fresh_identity_and_content_equal': True,
                                       'reuse_preserves_bytes_mtimes': True}
            print(model, out, flush=True)
    if args.prior_report:
        prior = json.loads(args.prior_report.read_text())
        for model, report in result['models'].items():
            unchanged = all(report[k] == prior['models'][model][k] for k in ('baseline', 'plans'))
            check(unchanged, 'demo plans changed beyond population metadata: ' + model)
            report['baseline_and_all_plans_unchanged_from_pre_hardening'] = unchanged
        result['prior_report_sha256'] = sha256_file(args.prior_report)
    atomic_write_json(args.report, result)


if __name__ == '__main__': main()
