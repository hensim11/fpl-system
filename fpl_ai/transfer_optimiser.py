"""M5A: offline one-Gameweek decisions over verified, immutable M4E evidence."""
import itertools
import json
import math
import tempfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from fpl_ai import prospective_xpts as xp
from fpl_ai.experiment_io import digest, publish, verify_bundle
from fpl_ai.fpl_rules import Rules, integer, require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.modelling import read_csv

CONTRACT = 'm5a-one-gw-transfers-v2'
SQUAD_CONTRACT = 'current-squad-v1'
OBJECTIVE = 'sum(starting XI base xPts) + captain base xPts - transfer hit; bench excluded'
TOLERANCE = 1e-6
# Numerical row feasibility only; never an additional semantic tie allowance.
FEASIBILITY_TOLERANCE = 1e-6
TIE_CONSTRAINT_SCALE = 1e4
TIE_POLICY = ('loss from best remaining net xPts <= 1e-6 inclusive; exact sums of binary64 inputs; fewer transfers; lexicographically '
              'smallest sorted squad IDs; XI and captain use unrounded xPts then ascending IDs')


def load_json(path):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key: ' + k)
            result[k] = v
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda v: (_ for _ in ()).throw(ValueError('invalid JSON number: ' + v)))


def load_forecast(forecast_dir, model_dir, model):
    """Replay production verification; extract only facts from its bound snapshot."""
    require(model in ('control', 'v2'), 'explicit control or v2 model required')
    manifest = xp.verify_forecast(forecast_dir, model_dir)
    evidence = load_json(Path(forecast_dir) / 'evidence.json')
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = xp.restore(Path(tmp), 'snapshot', evidence['snapshot'])
        bootstrap, _, sm = xp.live.load_snapshot(snapshot)
    meta = manifest['metadata']
    require(all(sm['metadata'][k] == meta[k] for k in ('season', 'target_gameweek', 'deadline')),
            'forecast snapshot decision mismatch')
    raw = xp.players(bootstrap)
    raw = {e: p for e, p in raw.items() if p['element_type'] in (1, 2, 3, 4)}
    teams = {t['id'] for t in bootstrap['teams']}
    predictions = xp.indexed(read_csv(Path(forecast_dir) / 'predictions.csv'))
    require(set(predictions) == {(meta['season'], meta['target_gameweek'], e) for e in raw},
            'forecast player population mismatch')
    column = 'control' if model == 'control' else 'xpts_v2'
    population = []
    for e, p in sorted(raw.items()):
        integer(e, 'element', 1)
        integer(p.get('team'), 'team', 1)
        integer(p['element_type'], 'position', 1, 4)
        integer(p.get('now_cost'), 'purchase price', 1)
        require(type(p.get('web_name')) is str, 'missing player name')
        require(p['team'] in teams, 'unknown player club')
        require(type(p.get('can_select')) is bool, 'missing or malformed snapshot can_select')
        value = float(predictions[(meta['season'], meta['target_gameweek'], e)][column])
        require(math.isfinite(value), 'nonfinite xPts')
        population.append({'element': e, 'position': p['element_type'], 'team': p['team'],
                           'purchase_price': p['now_cost'], 'name': p['web_name'], 'xpts': value,
                           'can_select': p['can_select']})
    source = {'manifest': manifest, 'manifest_sha256': sha256_file(Path(forecast_dir) / 'manifest.json'),
              'selected_model': model, 'selected_model_identity': meta['model_identities'][column],
              'snapshot_manifest_sha256': None}
    # Hash exact embedded bytes, not a newly serialized snapshot manifest.
    source['snapshot_manifest_sha256'] = xp.sha256_bytes(evidence['snapshot']['files']['manifest.json'].encode())
    return population, source


def validate_population(population):
    require(type(population) is list and bool(population), 'empty candidate population')
    ids = []
    for p in population:
        require(type(p) is dict and set(p) == {'element', 'position', 'team', 'purchase_price', 'name', 'xpts', 'can_select'},
                'invalid candidate columns')
        require(type(p['can_select']) is bool, 'invalid candidate can_select')
        ids.append(integer(p['element'], 'element', 1))
        integer(p['position'], 'position', 1, 4)
        integer(p.get('team'), 'team', 1)
        integer(p['purchase_price'], 'purchase price', 1)
        require(type(p['name']) is str and type(p['xpts']) in (float, int) and math.isfinite(p['xpts']),
                'invalid candidate name/xPts')
    require(len(ids) == len(set(ids)), 'duplicate candidate element')
    return {p['element']: p for p in population}


def validate_squad(ids, players, rules):
    require(len(ids) == rules.squad_size and len(set(ids)) == len(ids), 'wrong squad size or duplicate element')
    require(set(ids) <= set(players), 'unknown squad player')
    require(Counter(players[e]['position'] for e in ids) == dict(enumerate(rules.position_counts, 1)),
            'illegal squad positional composition')
    require(max(Counter(players[e]['team'] for e in ids).values()) <= rules.club_limit, 'club limit exceeded')


def validate_state(state, population, season, gameweek, rules=Rules()):
    rules.validate()
    players = validate_population(population)
    require(type(state) is dict and set(state) == {'contract', 'season', 'target_gameweek', 'players', 'bank', 'free_transfers'},
            'invalid squad-state fields')
    require(state['contract'] == SQUAD_CONTRACT and state['season'] == season == rules.season,
            'squad contract/season mismatch')
    integer(state['target_gameweek'], 'gameweek', 1, rules.gameweeks)
    require(state['target_gameweek'] == gameweek, 'squad Gameweek mismatch')
    integer(state['bank'], 'bank')
    integer(state['free_transfers'], 'free transfers', 0, rules.free_transfer_cap)
    require(type(state['players']) is list, 'players must be a list')
    ids = []
    for p in state['players']:
        require(type(p) is dict and set(p) == {'element', 'selling_price'}, 'invalid held player fields')
        e = integer(p['element'], 'element', 1)
        integer(p['selling_price'], 'selling price', 1)
        require(e in players, 'unknown squad player')
        require(p['selling_price'] <= players[e]['purchase_price'], 'selling price exceeds current purchase price')
        ids.append(e)
    validate_squad(ids, players, rules)
    return {**state, 'players': sorted(state['players'], key=lambda p: p['element'])}


def best_lineup(ids, players, rules):
    """Only a 15-player squad is enumerated: all legal formations, no transfer search."""
    by_position = {p: sorted((e for e in ids if players[e]['position'] == p),
                            key=lambda e: (-players[e]['xpts'], e)) for p in range(1, 5)}
    candidates = []
    for counts in itertools.product(*(range(lo, hi + 1) for lo, hi in zip(rules.xi_min, rules.xi_max))):
        if sum(counts) != rules.xi_size:
            continue
        xi = sorted(e for p, count in enumerate(counts, 1) for e in by_position[p][:count])
        captain = min(xi, key=lambda e: (-players[e]['xpts'], e))
        gross = math.fsum(players[e]['xpts'] for e in xi)
        bonus = players[captain]['xpts'] * (rules.captain_multiplier - 1)
        exact = sum((Fraction(players[e]['xpts']) for e in xi), Fraction()) + Fraction(players[captain]['xpts']) * (rules.captain_multiplier - 1)
        candidates.append((-exact, xi, captain, gross, bonus))
    _, xi, captain, gross, bonus = min(candidates)
    bench = sorted(set(ids) - set(xi), key=lambda e: (players[e]['position'] == 1, -players[e]['xpts'], e))
    vice = min((e for e in xi if e != captain), key=lambda e: (-players[e]['xpts'], e))
    return {'starting_xi': xi, 'captain': captain, 'vice_captain': vice, 'bench_order': bench,
            'gross_xi_points': gross, 'captain_bonus': bonus}


def make_plan(ids, state, players, rules):
    ids = sorted(ids)
    validate_squad(ids, players, rules)
    held = {p['element']: p['selling_price'] for p in state['players']}
    incoming, outgoing = sorted(set(ids) - held.keys()), sorted(held.keys() - set(ids))
    require(all(players[e]['can_select'] for e in incoming), 'unselectable incoming player')
    bank = state['bank'] + sum(held[e] for e in outgoing) - sum(players[e]['purchase_price'] for e in incoming)
    require(bank >= 0 and len(incoming) == len(outgoing), 'infeasible transfer economics')
    lineup = best_lineup(ids, players, rules)
    hit = rules.hit(len(incoming), state['free_transfers'])
    return {**lineup, 'squad': ids, 'transfers_in': incoming, 'transfers_out': outgoing,
            'transfer_count': len(incoming), 'resulting_bank': bank, 'transfer_hit': hit,
            'next_free_transfers': rules.next_free(len(incoming), state['free_transfers']),
            'net_points': lineup['gross_xi_points'] + lineup['captain_bonus'] - hit}


class SquadMILP:
    """Binary squad/XI/captain plus paid-transfer count; exact no-good squad cuts."""
    def __init__(self, population, state, rules, max_transfers):
        self.state, self.rules = state, rules
        held_ids = {p['element'] for p in state['players']}
        self.population = sorted((p for p in population if p['can_select'] or p['element'] in held_ids),
                                 key=lambda p: p['element'])
        self.players = {p['element']: p for p in self.population}
        self.n = n = len(self.population)
        self.width = 3 * n + 1
        self.rows, self.lower, self.upper, self.row_scales = [], [], [], []
        self.row_roles = []
        held = {p['element']: p['selling_price'] for p in state['players']}
        self.transfers = {i: 1 for i, p in enumerate(self.population) if p['element'] not in held}
        self.add({i: 1 for i in range(n)}, rules.squad_size, rules.squad_size)
        self.add({n+i: 1 for i in range(n)}, rules.xi_size, rules.xi_size)
        self.add({2*n+i: 1 for i in range(n)}, 1, 1)
        for pos in range(1, 5):
            indices = [i for i, p in enumerate(self.population) if p['position'] == pos]
            self.add({i: 1 for i in indices}, rules.position_counts[pos-1], rules.position_counts[pos-1])
            self.add({n+i: 1 for i in indices}, rules.xi_min[pos-1], rules.xi_max[pos-1])
        for team in sorted({p['team'] for p in self.population}):
            self.add({i: 1 for i, p in enumerate(self.population) if p['team'] == team}, 0, rules.club_limit)
        for i in range(n):
            self.add({n+i: 1, i: -1}, -np.inf, 0)
            self.add({2*n+i: 1, n+i: -1}, -np.inf, 0)
        self.add({i: held.get(p['element'], p['purchase_price']) for i, p in enumerate(self.population)},
                 -np.inf, state['bank'] + sum(held.values()))
        self.add(self.transfers, 0, max_transfers)
        self.add({**self.transfers, 3*n: -1}, -np.inf, state['free_transfers'])
        self.bounds = Bounds(np.zeros(self.width), np.array([1.] * (3*n) + [float(rules.squad_size)]))
        self.objective = np.zeros(self.width)
        for i, p in enumerate(self.population):
            self.objective[n+i] = -p['xpts']
            self.objective[2*n+i] = -p['xpts'] * (rules.captain_multiplier - 1)
        self.objective[3*n] = rules.hit_cost

    def add(self, coefficients, lo, hi, *, scale=1.0, role='structural'):
        require(role in ('structural', 'objective_band'), 'invalid constraint role')
        require(math.isfinite(scale) and scale > 0, 'invalid constraint scale')
        self.rows.append(coefficients.copy()); self.lower.append(lo); self.upper.append(hi)
        self.row_scales.append(scale)
        self.row_roles.append(role)

    def solve(self, objective, *, presolve=True):
        matrix = np.zeros((len(self.rows), self.width))
        for j, row in enumerate(self.rows):
            for i, value in row.items(): matrix[j, i] = value
        result = milp(objective, integrality=np.ones(self.width), bounds=self.bounds,
                      constraints=LinearConstraint(csr_matrix(matrix), self.lower, self.upper),
                      options={'mip_rel_gap': 0.0, 'time_limit': 120, 'presolve': presolve})
        if result.status == 2:
            return None
        require(result.success and result.status == 0, 'optimisation did not prove optimality: ' + result.message)
        rounded = np.rint(result.x)
        require(np.max(np.abs(result.x - rounded)) < 1e-5, 'nonintegral solver result')
        values = matrix @ rounded
        # Structural rows remain independently validated after rounding. The
        # conditioned objective row is a search hint, never a second tie-band
        # authority: all its candidates must reach solve_tied's exact check.
        require(np.isfinite(values).all() and np.all(rounded >= self.bounds.lb) and
                np.all(rounded <= self.bounds.ub), 'invalid solver vector')
        structural = np.array([role == 'structural' for role in self.row_roles])
        scales = np.array(self.row_scales)[structural]
        require(np.all((np.array(self.lower)[structural] - values[structural]) / scales <= FEASIBILITY_TOLERANCE) and
                np.all((values[structural] - np.array(self.upper)[structural]) / scales <= FEASIBILITY_TOLERANCE),
                'solver constraint violation')
        return rounded

    def exact_net(self, result):
        ids = [p['element'] for i, p in enumerate(self.population) if result[i] == 1]
        plan = make_plan(ids, self.state, self.players, self.rules)
        return (sum((Fraction(self.players[e]['xpts']) for e in plan['starting_xi']), Fraction())
                + Fraction(self.players[plan['captain']]['xpts']) * (self.rules.captain_multiplier - 1)
                - plan['transfer_hit'])

    def solve_tied(self, objective, best):
        # HiGHS feasibility tolerance can admit a squad a few ULPs outside
        # the objective bound. Check exact input-float sums, exclude that squad
        # only for this rank, and retry. Do not widen the contractual tolerance.
        while True:
            result = self.solve(objective)
            if result is None:
                # A known in-band witness survives each secondary fixing. Near
                # a tight scaled row, presolve can incorrectly remove it. Retry
                # the unchanged model without presolve; still require optimality
                # and the identical numerical and exact semantic validations.
                result = self.solve(objective, presolve=False)
            require(result is not None, 'lost optimal solution during tie break')
            if best - self.exact_net(result) <= Fraction(TOLERANCE):
                return result
            indices = [i for i in range(self.n) if result[i] == 1]
            self.add({i: 1 for i in indices}, -np.inf, len(indices) - 1)

    def next_squad(self):
        original = len(self.rows)
        result = self.solve(self.objective * 1e6)
        if result is None: return None
        best = self.exact_net(result)
        optimum = -float(best)
        # Scale the primary bound to prevent the solver feasibility tolerance
        # from erasing small point differences. Raw predictions are never rounded.
        self.add({i: float(v * TIE_CONSTRAINT_SCALE) for i, v in enumerate(self.objective) if v},
                 -np.inf, (optimum + TOLERANCE) * TIE_CONSTRAINT_SCALE, scale=TIE_CONSTRAINT_SCALE, role='objective_band')
        secondary = np.zeros(self.width)
        for i in self.transfers: secondary[i] = 1
        result = self.solve_tied(secondary, best)
        require(result is not None, 'lost optimal solution during tie break')
        count = int(secondary @ result)
        self.add(self.transfers, count, count)
        # Binary blocks implement a unique lexicographic squad tie break without
        # an epsilon perturbation to the primary objective or giant coefficients.
        for start in range(0, self.n, 16):
            indices = range(start, min(start + 16, self.n))
            coefficients = {i: -(2 ** (len(indices)-j-1)) for j, i in enumerate(indices)}
            tie = np.zeros(self.width)
            for i, v in coefficients.items(): tie[i] = v
            result = self.solve_tied(tie, best)
            require(result is not None, 'lost optimal squad during lexicographic tie break')
            value = int(tie @ result)
            self.add(coefficients, value, value)
        require(best - self.exact_net(result) <= Fraction(TOLERANCE), 'primary objective changed in tie break')
        self.row_roles = self.row_roles[:original]
        self.row_scales = self.row_scales[:original]
        self.rows = self.rows[:original]; self.lower = self.lower[:original]; self.upper = self.upper[:original]
        indices = [i for i in range(self.n) if result[i] == 1]
        self.add({i: 1 for i in indices}, -np.inf, len(indices)-1)
        return [self.population[i]['element'] for i in indices]


def optimise(population, state, *, max_transfers=2, top_n=3, rules=Rules()):
    rules.validate()
    integer(max_transfers, 'maximum transfers', 0, rules.squad_size)
    integer(top_n, 'top-N', 1, 20)
    require(type(state) is dict, 'invalid squad state')
    state = validate_state(state, population, rules.season, state.get('target_gameweek'), rules)
    players = validate_population(population)
    baseline = make_plan([p['element'] for p in state['players']], state, players, rules)
    baseline['gain_vs_no_transfer'] = 0.0
    solver = SquadMILP(population, state, rules, max_transfers)
    plans = []
    for _ in range(top_n):
        ids = solver.next_squad()
        if ids is None: break
        plan = make_plan(ids, state, players, rules)
        require(plan['transfer_count'] <= max_transfers, 'transfer limit violated')
        plan['gain_vs_no_transfer'] = plan['net_points'] - baseline['net_points']
        plans.append(plan)
    require(bool(plans), 'no feasible solution')
    owned = {p['element'] for p in state['players']}
    counts = {'forecast_population': len(population),
              'transfer_in_eligible_population': sum(p['can_select'] for p in population),
              'eligible_not_owned': sum(p['can_select'] and p['element'] not in owned for p in population),
              'owned_population': len(owned),
              'owned_unselectable': sum(not players[e]['can_select'] for e in owned),
              'optimisation_population': len(solver.population)}
    return {'baseline': baseline, 'plans': plans, 'available_plans_returned': len(plans),
            'population_counts': counts}


def build_decision(forecast_dir, model_dir, model, squad_path, output_dir=Path('data/decisions'), *,
                   max_transfers=2, top_n=3, rules=Rules()):
    xp.live.safe_output(output_dir, forecast_dir, model_dir, squad_path)
    population, source = load_forecast(forecast_dir, model_dir, model)
    meta = source['manifest']['metadata']
    state = validate_state(load_json(squad_path), population, meta['season'], meta['target_gameweek'], rules)
    result = optimise(population, state, max_transfers=max_transfers, top_n=top_n, rules=rules)
    config = {'max_transfers': max_transfers, 'top_n': top_n, 'objective': OBJECTIVE,
              'tie_break': TIE_POLICY, 'solver': 'scipy.optimize.milp/HiGHS', 'mip_rel_gap': 0.0,
              'time_limit_per_solve_seconds': 120, 'objective_tolerance': TOLERANCE,
              'constraint_feasibility_tolerance_unscaled': FEASIBILITY_TOLERANCE,
              'tie_constraint_scale': TIE_CONSTRAINT_SCALE,
              'tie_constraint_validation': 'exact Fraction squad objective only; numerical admission is not semantic acceptance',
              'secondary_infeasibility_retry': 'same model with presolve disabled',
              'transfer_eligibility': 'bound snapshot elements.can_select must be boolean; true required only for incoming players'}
    metadata = {'kind': 'one-gw-transfer-decision', 'contract': CONTRACT,
                **{k: meta[k] for k in ('season', 'target_gameweek', 'deadline')},
                'model': model, 'forecast_identity': source['manifest']['identity_sha256'],
                'forecast_manifest_sha256': source['manifest_sha256'], 'squad_sha256': digest(state),
                'rules': rules.as_dict(), 'config': config, 'environment': xp.environment(),
                'implementation_sha256': {p.name: sha256_file(p) for p in
                                          (Path(__file__), Path(__file__).with_name('fpl_rules.py'))}}
    def writer(folder):
        for name, value in [('squad.json', state), ('population.json', population), ('source.json', source),
                            ('decision.json', result), ('rules.json', rules.as_dict()), ('config.json', config)]:
            atomic_write_json(folder / name, value)
        lines = [f'# One-Gameweek transfer optimiser v1: {meta["season"]} GW{meta["target_gameweek"]}',
                 f'Model explicitly selected: {model}. Snapshot deadline: {meta["deadline"]}.',
                 f'Population counts: {result["population_counts"]}.',
                 f'No-transfer net xPts: {result["baseline"]["net_points"]:.6f}.',
                 'Ranked by XI + captain bonus - hits. Bench points excluded.',
                 'No value for rolling transfers, future fixtures, uncertainty, chips or multi-GW flexibility.',
                 'Frozen evidence replay; this report does not establish current deadline freshness.', '']
        for rank, plan in enumerate(result['plans'], 1):
            lines += [f'## Plan {rank}: net {plan["net_points"]:.6f}; gain {plan["gain_vs_no_transfer"]:+.6f}',
                      f'In: {[(e, players_name(population, e)) for e in plan["transfers_in"]]}',
                      f'Out: {[(e, players_name(population, e)) for e in plan["transfers_out"]]}',
                      f'Hit: {plan["transfer_hit"]}; bank (tenths): {plan["resulting_bank"]}',
                      f'XI: {plan["starting_xi"]}; captain: {plan["captain"]}; squad: {plan["squad"]}', '']
        (folder / 'report.md').write_text('\n'.join(lines) + '\n')
    return publish(output_dir, metadata, writer)


def players_name(population, element):
    return next(p['name'] for p in population if p['element'] == element)
