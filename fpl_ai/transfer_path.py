"""Multi-period MILP with exact transfer-state arcs and static-price sale rights."""
import math
from fractions import Fraction
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from fpl_ai import prospective_xpts as xp
from fpl_ai.experiment_io import publish
from fpl_ai.fpl_rules import Rules, integer, require
from fpl_ai.historical_io import atomic_write_json, sha256_file
from fpl_ai.transfer_optimiser import (SquadMILP, validate_population, validate_state,
    make_plan, load_json, TOLERANCE, TIE_CONSTRAINT_SCALE, FEASIBILITY_TOLERANCE)

CONTRACT = 'm5b-transfer-path-v1'
TIE_ENUMERATION_LIMIT = 32
ASSUMPTIONS = {
    'objective': 'equal-weight sum of optimal XI plus captain bonus minus hits; no bench or terminal value',
    'prices': 'static purchase prices; exact initial sale rights until first sale; bought players sell at purchase price',
    'eligibility': 'strict as-of can_select held fixed; owned unselectable may remain',
    'tie': 'inclusive exact binary64 loss <=1e-6 from best remaining path; fewer paid transfers, fewer total transfers, lexicographic GW-ordered squads; optimal XI/captain by exact points then IDs',
    'scope': 'no chips, uncertainty, fixture effects, future news or price forecasts; projections are not realised utility evidence',
}


def validate_projections(rows, state, horizon, rules):
    integer(horizon, 'planning horizon', 1, 5)
    require(type(rows) is list and bool(rows), 'empty projections')
    g = state.get('target_gameweek')
    integer(g, 'Gameweek', 1, rules.gameweeks)
    horizon = min(horizon, rules.gameweeks-g+1)
    keys, populations = set(), {}
    fields = {'season', 'as_of_gameweek', 'target_gameweek', 'horizon'}
    for r in rows:
        require(type(r) is dict, 'invalid projection row')
        h = integer(r.get('horizon'), 'horizon offset', 0, 4)
        integer(r.get('as_of_gameweek'), 'as-of Gameweek', 1, 38)
        integer(r.get('target_gameweek'), 'target Gameweek', 1, 38)
        require(r['season'] == rules.season == state['season'] and r['as_of_gameweek'] == g and r['target_gameweek'] == g+h, 'projection state mismatch')
        k = (h, r.get('element'))
        require(k not in keys, 'duplicate projection key')
        keys.add(k)
        populations.setdefault(h, []).append({n: v for n, v in r.items() if n not in fields})
    require(set(populations) == set(range(len(populations))) and len(populations) >= horizon, 'incomplete projection horizon')
    reference = None
    for h, pop in populations.items():
        players = validate_population(pop)
        static = {e: {k: v for k, v in p.items() if k != 'xpts'} for e, p in players.items()}
        if reference is None: reference = static
        require(static == reference, 'projection population/static eligibility differs between horizons')
    state = validate_state(state, populations[0], rules.season, g, rules)
    return [sorted(populations[h], key=lambda p: p['element']) for h in range(horizon)], state


def path_plan(squads, populations, state, rules):
    current = state
    weeks, exact = [], Fraction()
    for t, ids in enumerate(squads):
        players = {p['element']: p for p in populations[t]}
        p = make_plan(ids, current, players, rules)
        score = sum((Fraction(players[e]['xpts']) for e in p['starting_xi']), Fraction())
        score += Fraction(players[p['captain']]['xpts']) * (rules.captain_multiplier-1) - p['transfer_hit']
        exact += score
        p.update(gameweek=state['target_gameweek']+t, free_transfers_before=current['free_transfers'],
                 free_transfers_used=min(current['free_transfers'], p['transfer_count']),
                 free_transfers_rolled=max(0, current['free_transfers']-p['transfer_count']),
                 cumulative_points=float(exact))
        weeks.append(p)
        held = {q['element']: q['selling_price'] for q in current['players']}
        current = {**current, 'target_gameweek': current['target_gameweek']+1,
                   'players': [{'element': e, 'selling_price': held.get(e, players[e]['purchase_price'])} for e in p['squad']],
                   'bank': p['resulting_bank'], 'free_transfers': p['next_free_transfers']}
    return {'weeks': weeks, 'total_points': float(exact), 'total_hit_cost': sum(w['transfer_hit'] for w in weeks),
            'transfer_count': sum(w['transfer_count'] for w in weeks)}, exact


class PathMILP(SquadMILP):
    """x/XI/captain/buy/sell/initial-right binaries, integer bank, FT transition arcs.

    Inherit only row construction and numerical/semantic tie principles from M5A.
    M5A's one-GW formulation and behaviour remain unchanged.
    """
    def __init__(self, populations, state, rules, max_transfers, time_limit=120):
        self.state, self.rules, self.populations = state, rules, populations
        self.time_limit, self.max_transfers = time_limit, max_transfers
        owned = {p['element']: p['selling_price'] for p in state['players']}
        self.population = [p for p in populations[0] if p['can_select'] or p['element'] in owned]
        self.n, self.h = len(self.population), len(populations)
        self.arcs = [(f, k, rules.next_free(k, f), max(0, k-f))
                     for f in range(rules.free_transfer_cap+1) for k in range(max_transfers+1)]
        self.stride = 6*self.n + 1 + len(self.arcs)
        self.width = self.h*self.stride
        self.rows, self.lower, self.upper, self.row_scales, self.row_roles = [], [], [], [], []
        self.objective = np.zeros(self.width)
        self.paid, self.transfers = {}, {}
        upper = np.ones(self.width)
        wealth = state['bank'] + sum(p['purchase_price'] for p in self.population if p['element'] in owned)
        self.squad_indices = [self.idx(t, 0, i) for t in range(self.h) for i in range(self.n)]
        for t in range(self.h):
            bank = self.bank(t); upper[bank] = wealth
            values = {p['element']: p['xpts'] for p in populations[t]}
            for b, count in ((0, rules.squad_size), (1, rules.xi_size), (2, 1)):
                self.add({self.idx(t,b,i): 1 for i in range(self.n)}, count, count)
            for pos in range(1,5):
                indices = [i for i,p in enumerate(self.population) if p['position']==pos]
                self.add({self.idx(t,0,i): 1 for i in indices}, rules.position_counts[pos-1], rules.position_counts[pos-1])
                self.add({self.idx(t,1,i): 1 for i in indices}, rules.xi_min[pos-1], rules.xi_max[pos-1])
            for club in sorted({p['team'] for p in self.population}):
                self.add({self.idx(t,0,i): 1 for i,p in enumerate(self.population) if p['team']==club}, 0, rules.club_limit)
            cash = {bank: 1}
            if t: cash[self.bank(t-1)] = -1
            rhs = state['bank'] if t==0 else 0
            for i,p in enumerate(self.population):
                x, xi, c, buy, sell, right = [self.idx(t,b,i) for b in range(6)]
                old = int(p['element'] in owned)
                self.add({xi: 1, x: -1}, -np.inf, 0)
                self.add({c: 1, xi: -1}, -np.inf, 0)
                self.add({buy: 1, sell: 1}, 0, 1)  # prohibit same-week round trips
                transition = {x: 1, buy: -1, sell: 1}
                if t: transition[self.idx(t-1,0,i)] = -1
                self.add(transition, old if t==0 else 0, old if t==0 else 0)
                if not p['can_select']: upper[buy] = 0
                self.add({right: 1, x: -1}, -np.inf, 0)
                if t:
                    prev = self.idx(t-1,5,i)
                    self.add({right: 1, prev: -1}, -np.inf, 0)
                    self.add({right: 1, prev: -1, x: -1}, -1, np.inf)
                else:
                    upper[right] = old
                    self.add({right: 1, x: -1}, old-1, np.inf)
                price = p['purchase_price']
                delta = price-owned.get(p['element'], price)
                cash[buy], cash[sell], cash[right] = price, -price, -delta
                if t: cash[self.idx(t-1,5,i)] = delta
                else: rhs -= delta*old
                self.objective[xi] = -values[p['element']]
                self.objective[c] = -values[p['element']]*(rules.captain_multiplier-1)
                self.transfers[buy] = 1
            self.add(cash, rhs, rhs)
            self.add({self.arc(t,a): 1 for a in range(len(self.arcs))}, 1, 1)
            transfer_count = {self.idx(t,3,i): 1 for i in range(self.n)}
            for a,(free,k,next_free,paid) in enumerate(self.arcs):
                v = self.arc(t,a)
                transfer_count[v] = -k
                self.objective[v] = paid*rules.hit_cost
                self.paid[v] = paid
                if t==0 and free != state['free_transfers']: upper[v] = 0
            self.add(transfer_count, 0, 0)
            if t:
                for free in range(rules.free_transfer_cap+1):
                    flow = {self.arc(t,a): 1 for a,v in enumerate(self.arcs) if v[0]==free}
                    flow.update({self.arc(t-1,a): -1 for a,v in enumerate(self.arcs) if v[2]==free})
                    self.add(flow, 0, 0)
        self.bounds = Bounds(np.zeros(self.width), upper)

    def idx(self,t,b,i): return t*self.stride+b*self.n+i
    def bank(self,t): return t*self.stride+6*self.n
    def arc(self,t,a): return self.bank(t)+1+a

    def solve(self, objective, *, presolve=True):
        rr, cc, vv = [], [], []
        for j,row in enumerate(self.rows):
            for i,v in row.items(): rr.append(j); cc.append(i); vv.append(v)
        matrix = coo_matrix((vv,(rr,cc)), shape=(len(self.rows),self.width)).tocsr()
        result = milp(objective, integrality=np.ones(self.width), bounds=self.bounds,
                      constraints=LinearConstraint(matrix, self.lower, self.upper),
                      options={'mip_rel_gap': 0.0, 'time_limit': self.time_limit, 'presolve': presolve})
        if result.status == 2: return None
        require(result.success and result.status==0, 'path optimisation did not prove optimality: '+result.message)
        require(result.x is not None and np.isfinite(result.x).all(), 'nonfinite solver result')
        rounded = np.rint(result.x)
        require(np.max(np.abs(result.x-rounded)) < 1e-5, 'nonintegral path solution')
        require(np.all(rounded>=self.bounds.lb) and np.all(rounded<=self.bounds.ub), 'invalid path bounds')
        structural = np.array([r=='structural' for r in self.row_roles])
        values = matrix @ rounded
        scales = np.array(self.row_scales)[structural]
        require(np.isfinite(values).all() and
                np.all((np.array(self.lower)[structural]-values[structural])/scales <= FEASIBILITY_TOLERANCE) and
                np.all((values[structural]-np.array(self.upper)[structural])/scales <= FEASIBILITY_TOLERANCE), 'path structural violation')
        # Independently replay integer economics and FT transitions, not just Ax.
        plan, _ = path_plan(self.squads(rounded), self.populations, self.state, self.rules)
        for t,w in enumerate(plan['weeks']):
            require(w['resulting_bank']==rounded[self.bank(t)] and w['transfer_count']<=self.max_transfers, 'path cash/transfer mismatch')
            a = next(a for a in range(len(self.arcs)) if rounded[self.arc(t,a)]==1)
            free,k,nxt,paid = self.arcs[a]
            require((free,k,nxt,paid*self.rules.hit_cost)==(w['free_transfers_before'],w['transfer_count'],w['next_free_transfers'],w['transfer_hit']), 'path transfer-state mismatch')
        return rounded

    def squads(self,result):
        return [[p['element'] for i,p in enumerate(self.population) if result[self.idx(t,0,i)]==1] for t in range(self.h)]

    def exact_net(self,result):
        return path_plan(self.squads(result), self.populations, self.state, self.rules)[1]

    def exclude(self,result):
        self.add({i: 1 for i in self.squad_indices if result[i]==1}, -np.inf, self.h*self.rules.squad_size-1)

    def solve_tied(self, objective, best):
        while True:
            result = self.solve(objective)
            if result is None: result = self.solve(objective, presolve=False)
            require(result is not None, 'lost path during tie break')
            if best-self.exact_net(result) <= Fraction(TOLERANCE): return result
            self.exclude(result)

    def next_path(self):
        original = len(self.rows)
        result = self.solve(self.objective*1e6)
        if result is None:
            result = self.solve(self.objective*1e6, presolve=False)
        if result is None: return None
        best = self.exact_net(result)
        # Prove discrete secondary priorities through unrestricted primary
        # solves with progressively smaller integer counts. This avoids asking
        # HiGHS to find a fresh witness inside a very narrow floating-point band.
        # Exact Fraction admission remains the only definition of a tie.
        for coefficients in (self.paid, self.transfers):
            result = self.minimize_count(coefficients, result, best)
        band_index = len(self.rows)
        self.add({i: float(v*TIE_CONSTRAINT_SCALE) for i,v in enumerate(self.objective) if v},
                 -np.inf, (-float(best)+TOLERANCE)*TIE_CONSTRAINT_SCALE, scale=TIE_CONSTRAINT_SCALE, role='objective_band')
        # Most realistic optima have very few tied complete paths. Prove this
        # by primary-objective enumeration before paying for every binary block.
        # A bounded enumeration is only a shortcut: on overflow restore the
        # unchanged model and perform the full lexicographic proof below.
        chosen = self.enumerate_tied(result, best, band_index)
        if chosen is not None:
            for name in ('rows','lower','upper','row_scales','row_roles'):
                setattr(self,name,getattr(self,name)[:original])
            self.exclude(chosen)
            return self.squads(chosen)
        priorities = []
        for start in range(0,len(self.squad_indices),16):
            indices = self.squad_indices[start:start+16]
            priorities.append({i: -2**(len(indices)-j-1) for j,i in enumerate(indices)})
        for coefficients in priorities:
            objective = np.zeros(self.width)
            for i,v in coefficients.items(): objective[i] = v
            result = self.solve_tied(objective,best)
            value = int(objective @ result)
            self.add(coefficients,value,value)
        for name in ('rows','lower','upper','row_scales','row_roles'):
            setattr(self,name,getattr(self,name)[:original])
        self.exclude(result)
        return self.squads(result)

    def minimize_count(self, coefficients, result, best):
        count = int(sum(v*result[i] for i,v in coefficients.items()))
        while count:
            original = len(self.rows)
            self.add(coefficients, -np.inf, count-1)
            candidate = self.solve(self.objective*1e6)
            if candidate is None: candidate = self.solve(self.objective*1e6,presolve=False)
            for n in ('rows','lower','upper','row_scales','row_roles'):
                setattr(self,n,getattr(self,n)[:original])
            if candidate is None or best-self.exact_net(candidate)>Fraction(TOLERANCE): break
            result = candidate
            count = int(sum(v*result[i] for i,v in coefficients.items()))
        self.add(coefficients, count, count)
        return result

    def enumerate_tied(self, first, best, band_index):
        names = ('rows','lower','upper','row_scales','row_roles')
        saved = {n:getattr(self,n)[:] for n in names}
        candidates = [first]
        try:
            # Remove only the numerical objective band. Each query proves the
            # best remaining objective under the fixed paid/total priorities;
            # exact semantic admission still uses the same rank-specific best.
            for n in names: del getattr(self,n)[band_index]
            for _ in range(TIE_ENUMERATION_LIMIT):
                self.exclude(candidates[-1])
                result = self.solve(self.objective*1e6)
                if result is None: result = self.solve(self.objective*1e6,presolve=False)
                if result is None or best-self.exact_net(result)>Fraction(TOLERANCE):
                    return min(candidates,key=lambda r: tuple(tuple(s) for s in self.squads(r)))
                candidates.append(result)
            return None
        finally:
            for n in names: setattr(self,n,saved[n])


def optimise_paths(rows, state, *, horizon=5, max_transfers=2, top_n=3, rules=Rules(), time_limit=120):
    rules.validate()
    integer(max_transfers,'maximum transfers per GW',0,rules.squad_size)
    integer(top_n,'top-N',1,20)
    require(type(time_limit) in (int,float) and math.isfinite(time_limit) and time_limit>0, 'invalid time limit')
    require(type(state) is dict,'invalid squad state')
    populations,state = validate_projections(rows,state,horizon,rules)
    initial = [p['element'] for p in state['players']]
    baseline,_ = path_plan([initial]*len(populations),populations,state,rules)
    solver = PathMILP(populations,state,rules,max_transfers,time_limit)
    plans = []
    for _ in range(top_n):
        squads = solver.next_path()
        if squads is None: break
        p,_ = path_plan(squads,populations,state,rules)
        p['gain_vs_no_transfer'] = p['total_points']-baseline['total_points']
        plans.append(p)
    require(bool(plans),'no proven feasible path')
    return {'contract': CONTRACT, 'horizon': len(populations), 'baseline': baseline, 'plans': plans,
            'assumptions': ASSUMPTIONS, 'max_transfers_per_gameweek': max_transfers}


def greedy_path(rows, state, *, horizon=5, max_transfers=2, rules=Rules(), time_limit=120):
    """Sequential one-GW decisions on exactly the same projections and state rules."""
    rules.validate()
    integer(max_transfers, 'maximum transfers per GW', 0, rules.squad_size)
    populations, state = validate_projections(rows, state, horizon, rules)
    current, squads = state, []
    for population in populations:
        solver = PathMILP([population], current, rules, max_transfers, time_limit)
        selected = solver.next_path()
        require(selected is not None, 'no proven greedy action')
        squad = selected[0]
        squads.append(squad)
        players = {p['element']: p for p in population}
        step = make_plan(squad, current, players, rules)
        held = {p['element']: p['selling_price'] for p in current['players']}
        current = {**current, 'target_gameweek': current['target_gameweek']+1,
                   'players': [{'element': e, 'selling_price': held.get(e, players[e]['purchase_price'])} for e in squad],
                   'bank': step['resulting_bank'], 'free_transfers': step['next_free_transfers']}
    plan, _ = path_plan(squads, populations, state, rules)
    return plan


def build_plan(projections_dir, model_dir, m4e_model_dir, squad_path, output_dir=Path('data/transfer_paths'), *, horizon=5, max_transfers=2, top_n=3, time_limit=120):
    from fpl_ai.multi_projection import verify_projection
    xp.live.safe_output(output_dir,projections_dir,model_dir,m4e_model_dir,squad_path)
    rows,manifest = verify_projection(projections_dir,model_dir,m4e_model_dir)
    state = load_json(squad_path)
    result = optimise_paths(rows,state,horizon=horizon,max_transfers=max_transfers,top_n=top_n,time_limit=time_limit)
    result['greedy'] = greedy_path(rows,state,horizon=horizon,max_transfers=max_transfers,time_limit=time_limit)
    metadata = {'kind':'multi-gw-transfer-path','contract':CONTRACT,'projection_identity':manifest['identity_sha256'],
                'model_identity':manifest['metadata']['model_identity'],'rules':Rules().as_dict(),
                'implementation_sha256':sha256_file(Path(__file__)), 'horizon':result['horizon'],
                'max_transfers':max_transfers,'top_n':top_n,'assumptions':ASSUMPTIONS}
    names = {r['element']:r['name'] for r in rows}
    lines = ['# Multi-Gameweek transfer paths', '', 'Projected expected points; no realised performance claim.',
             f"Frozen state: {manifest['metadata']['capture']}; horizon {result['horizon']} GWs.", '',
             *[f'{k}: {v}' for k,v in ASSUMPTIONS.items()], '',
             f"No-transfer baseline: {result['baseline']['total_points']:.3f}",
             f"Sequential greedy comparison: {result['greedy']['total_points']:.3f}"]
    for rank,p in enumerate(result['plans'],1):
        lines += ['',f'## Plan {rank}',f"Total {p['total_points']:.3f}; gain {p['gain_vs_no_transfer']:+.3f}; hits {p['total_hit_cost']}."]
        for w in p['weeks']:
            moves = ('Sell '+', '.join(names[e] for e in w['transfers_out'])+'; buy '+', '.join(names[e] for e in w['transfers_in'])) if w['transfer_count'] else 'Roll'
            lines += [f"- GW{w['gameweek']}: {moves}. Captain {names[w['captain']]}; projected {w['net_points']:.3f}; FT {w['free_transfers_before']} → {w['next_free_transfers']}; hit {w['transfer_hit']}; bank £{w['resulting_bank']/10:.1f}m."]
    def writer(folder):
        atomic_write_json(folder/'decision.json',result)
        atomic_write_json(folder/'squad.json',state)
        atomic_write_json(folder/'source.json',manifest)
        (folder/'report.md').write_text('\n'.join(lines)+'\n')
    return publish(output_dir,metadata,writer)
