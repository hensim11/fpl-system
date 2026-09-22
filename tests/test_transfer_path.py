"""Independent exhaustive path/XI oracle: no production economics/rules helpers."""
import copy
import itertools
import math
import random
import unittest
from collections import Counter
from fractions import Fraction
from unittest.mock import patch

from fpl_ai import transfer_path as tp
from tests.test_transfer_optimiser import fixture


def projection(populations, gameweek=6):
    return [{**p, 'season': '2026-27', 'as_of_gameweek': gameweek,
             'target_gameweek': gameweek+h, 'horizon': h} for h, pop in enumerate(populations) for p in pop]


def oracle(populations, state, max_transfers, top_n):
    """Enumerate legal squads, every XI and every reachable complete path."""
    ids = sorted(p['element'] for p in populations[0])
    players = [{p['element']: p for p in pop} for pop in populations]
    squads = []
    for squad in itertools.combinations(ids, 15):
        if Counter(players[0][e]['position'] for e in squad) != {1:2, 2:5, 3:5, 4:3}: continue
        if max(Counter(players[0][e]['team'] for e in squad).values()) > 3: continue
        squads.append(squad)
    lineups = []
    for ps in players:
        table = {}
        for squad in squads:
            options = []
            for xi in itertools.combinations(squad, 11):
                counts = Counter(ps[e]['position'] for e in xi)
                if not (counts[1]==1 and 3<=counts[2]<=5 and 2<=counts[3]<=5 and 1<=counts[4]<=3): continue
                captain = min(xi, key=lambda e: (-ps[e]['xpts'], e))
                total = sum((Fraction(ps[e]['xpts']) for e in xi), Fraction()) + Fraction(ps[captain]['xpts'])
                options.append((-total, xi, captain))
            table[squad] = min(options)
        lineups.append(table)
    all_paths = []
    def visit(t, held, bank, free, path, total, paid, transfers):
        if t==len(players):
            all_paths.append((total, paid, transfers, tuple(path)))
            return
        for squad in squads:
            incoming, outgoing = set(squad)-held.keys(), held.keys()-set(squad)
            count = len(incoming)
            if count>max_transfers or any(not players[t][e]['can_select'] for e in incoming): continue
            cash = bank + sum(held[e] for e in outgoing)-sum(players[t][e]['purchase_price'] for e in incoming)
            if cash<0: continue
            hit = max(0,count-free)
            holding = {e: held[e] if e in held else players[t][e]['purchase_price'] for e in squad}
            visit(t+1,holding,cash,min(5,max(0,free-count)+1),path+[squad],total-lineups[t][squad][0]-4*hit,paid+hit,transfers+count)
    visit(0,{p['element']:p['selling_price'] for p in state['players']},state['bank'],state['free_transfers'],[],Fraction(),0,0)
    ranked = []
    for _ in range(min(top_n,len(all_paths))):
        best = max(r[0] for r in all_paths)
        chosen = min((r for r in all_paths if best-r[0] <= Fraction(1e-6)),key=lambda r: (r[1],r[2],r[3]))
        ranked.append(chosen)
        all_paths.remove(chosen)
    return ranked


class PathTests(unittest.TestCase):
    def test_top_n_is_maximum_when_only_roll_path_is_feasible(self):
        p,s=fixture(); s['bank']=5
        minimum_purchase=min(r['purchase_price'] for r in p if r['element'] not in
                             {q['element'] for q in s['players']})
        maximum_sale=max(q['selling_price'] for q in s['players'])
        self.assertLess(s['bank'],minimum_purchase-maximum_sale)
        result=self.compare([p,p],s,max_transfers=2,top_n=5)
        self.assertEqual(len(result['plans']),1)
        self.assertEqual(result['plans'][0]['transfer_count'],0)
        self.assertTrue(all(w['resulting_bank']==s['bank'] for w in result['plans'][0]['weeks']))

    def test_oracle_report_counts_emitted_paths_not_requested_maximum(self):
        import json
        import sys
        import tempfile
        from pathlib import Path
        from scripts import verify_multi_oracle as verifier
        emitted=[]
        expected=[]
        sizes=itertools.cycle((1,3,5))
        def reference(populations,state,max_transfers,top_n):
            self.assertEqual(top_n,5)
            count=next(sizes)
            expected[:]=[(Fraction(i),0,0,((i,),)) for i in range(count)]
            emitted.append(count)
            return expected.copy()
        def solve(*args,**kwargs):
            self.assertEqual(kwargs['top_n'],5)
            return {'plans':[{'weeks':[{'squad':list(e[3][0])}],
                              'total_points':float(e[0]),'total_hit_cost':0} for e in expected]}
        with tempfile.TemporaryDirectory() as tmp:
            report=Path(tmp)/'oracle.json'
            with patch.object(verifier,'oracle',side_effect=reference), \
                 patch.object(verifier,'optimise_paths',side_effect=solve), \
                 patch.object(sys,'argv',['verify_multi_oracle','--report',str(report)]), \
                 patch('builtins.print'):
                verifier.main()
            data=json.loads(report.read_text())
        self.assertEqual(data['case_count'],len(emitted))
        self.assertEqual([c['plans'] for c in data['cases']],emitted)
        self.assertEqual([len(c['points']) for c in data['cases']],emitted)
        self.assertEqual(data['ranked_paths_checked'],sum(emitted))
        self.assertLess(data['ranked_paths_checked'],data['case_count']*5)

    def compare(self, populations, state, max_transfers=2, top_n=3):
        expected = oracle(populations,state,max_transfers,top_n)
        actual = tp.optimise_paths(projection(populations,state['target_gameweek']),state,horizon=len(populations),max_transfers=max_transfers,top_n=top_n)
        for a,e in zip(actual['plans'],expected):
            self.assertEqual(tuple(tuple(w['squad']) for w in a['weeks']), e[3])
            self.assertEqual(a['total_points'], float(e[0]))
            self.assertEqual(a['total_hit_cost'],4*e[1])
            self.assertEqual(a['transfer_count'],e[2])
        self.assertEqual(len(actual['plans']),len(expected))
        return actual

    def test_immediate_hit_pays_over_horizon(self):
        p,s=fixture()
        r=self.compare([p,p],s)
        self.assertEqual(r['plans'][0]['weeks'][0]['transfer_hit'],4)
        self.assertEqual(r['plans'][0]['weeks'][0]['transfers_in'],[16,17])

    def test_roll_then_use_two_free_transfers(self):
        p,s=fixture(); q=copy.deepcopy(p)
        p[15]['xpts']=p[16]['xpts']=0
        r=self.compare([p,q],s)
        self.assertEqual(r['plans'][0]['weeks'][0]['transfer_count'],0)
        self.assertEqual(r['plans'][0]['weeks'][1]['transfer_hit'],0)
        self.assertEqual(r['plans'][0]['weeks'][1]['transfer_count'],2)

    def test_small_gain_hit_not_worthwhile(self):
        p,s=fixture(); s['free_transfers']=0
        p[15]['xpts']=p[16]['xpts']=1.1
        r=self.compare([p,p],s)
        self.assertEqual(r['plans'][0]['weeks'][0]['transfer_count'],0)

    def test_greedy_first_move_loses(self):
        p,s=fixture(); q=copy.deepcopy(p); s['bank']=6
        p[15]['xpts']=4; p[16]['xpts']=3
        q[15]['xpts']=0; q[16]['xpts']=12
        r=self.compare([p,q],s,max_transfers=1)
        self.assertEqual(r['plans'][0]['weeks'][0]['transfers_in'],[17])
        one=tp.optimise_paths(projection([p]),s,horizon=1,max_transfers=1,top_n=1)
        self.assertEqual(one['plans'][0]['weeks'][0]['transfers_in'],[16])
        greedy=tp.greedy_path(projection([p,q]),s,horizon=2,max_transfers=1)
        self.assertGreater(r['plans'][0]['total_points'],greedy['total_points'])

    def test_three_week_path_with_squad_retention(self):
        p,s=fixture(); p=p[:16]; s['bank']=30
        q=copy.deepcopy(p); r=copy.deepcopy(p)
        p[15]['xpts']=0; q[15]['xpts']=5; r[15]['xpts']=9
        result=self.compare([p,q,r],s,max_transfers=1,top_n=3)
        weeks=result['plans'][0]['weeks']
        self.assertEqual(weeks[0]['transfer_count'],0)
        self.assertEqual(weeks[1]['transfers_in'],[16])
        self.assertEqual(weeks[2]['transfer_count'],0)

    def test_exact_tie_boundary_and_negative_scores(self):
        for bump in (1e-6/2, math.nextafter(1e-6/2,math.inf), 0.9e-6/2, 1.1e-6/2):
            p,s=fixture()
            for r in p: r['xpts']=0.0
            p[15]['xpts']=bump; p[16]['can_select']=False
            with self.subTest(bump=bump): self.compare([p],s,max_transfers=1,top_n=3)
        p,s=fixture()
        for r in p: r['xpts']=-float(r['element'])
        self.compare([p,p],s,max_transfers=1,top_n=3)

    def test_club_limit_blocks_high_scoring_incoming(self):
        p,s=fixture(); p[15]['team']=1
        r=self.compare([p,p],s,max_transfers=1,top_n=3)
        self.assertTrue(all(16 not in w['squad'] for a in r['plans'] for w in a['weeks']))

    def test_sale_repurchase_rights_bank_and_cap(self):
        p,s=fixture(); q=copy.deepcopy(p); s['free_transfers']=5; s['bank']=100
        q[11]['xpts']=100; q[15]['xpts']=-100
        r=self.compare([p,q],s,max_transfers=1,top_n=3)
        for plan in r['plans']:
            self.assertLessEqual(plan['weeks'][1]['next_free_transfers'],5)
        squads=[list(range(1,12))+[13,14,15,16],list(range(1,16))]
        plan,_=tp.path_plan(squads,[p,q],s,tp.Rules())
        self.assertEqual(plan['weeks'][0]['resulting_bank'],94)
        self.assertEqual(plan['weeks'][1]['resulting_bank'],99)

    def test_unselectable_owned_retained_and_incoming_rejected(self):
        p,s=fixture(); p[15]['can_select']=False; p[0]['can_select']=False
        r=self.compare([p,p],s,max_transfers=1)
        self.assertTrue(all(16 not in w['squad'] and 1 in w['squad'] for a in r['plans'] for w in a['weeks']))

    def test_random_signed_and_near_tie_paths(self):
        for seed in (26,1596,0,1):
            p,s=fixture(); q=copy.deepcopy(p); rng=random.Random(seed)
            for pop in (p,q):
                for r in pop: r['xpts']=1+rng.randint(-3,3)*1e-6/3
            with self.subTest(seed=seed): self.compare([p,q],s,max_transfers=1,top_n=5)

    def test_boundary_and_input_rejection(self):
        from dataclasses import replace
        p,s=fixture(); s['target_gameweek']=38
        r=tp.optimise_paths(projection([p],38),s,horizon=5,max_transfers=0)
        self.assertEqual(r['horizon'],1)
        rows=projection([p],38)
        for bad in (rows+rows, [{**r,'season':'2025-26'} for r in rows], [{**r,'target_gameweek':39} for r in rows]):
            with self.assertRaises(ValueError): tp.optimise_paths(bad,s)
        with self.assertRaises(ValueError): tp.optimise_paths(rows,s,horizon=True)
        with self.assertRaises(ValueError): tp.optimise_paths(rows,{**s,'contract':'unknown'},horizon=1)
        with self.assertRaises(ValueError): tp.optimise_paths(rows,s,horizon=1,rules=replace(tp.Rules(),hit_cost=3))
        s['target_gameweek']=6
        with self.assertRaises(ValueError): tp.optimise_paths(projection([p]),s)
        q=copy.deepcopy(p); q[0]['can_select']=True; q[1]['team']=9
        with self.assertRaises(ValueError): tp.optimise_paths(projection([p,q]),s,horizon=2)

    def test_unproven_solver_fails_closed(self):
        from types import SimpleNamespace
        p,s=fixture()
        with patch.object(tp,'milp',return_value=SimpleNamespace(status=1,success=False,message='time limit')):
            with self.assertRaisesRegex(ValueError,'prove optimality'):
                tp.optimise_paths(projection([p]),s,horizon=1)
        with patch.object(tp,'milp',return_value=SimpleNamespace(status=2,success=False,message='infeasible')):
            with self.assertRaisesRegex(ValueError,'no proven feasible'):
                tp.optimise_paths(projection([p]),s,horizon=1)

    def test_order_determinism(self):
        p,s=fixture(); rows=projection([p,p])
        a=tp.optimise_paths(rows,s,horizon=2,top_n=3)
        b=tp.optimise_paths(list(reversed(rows)),{**s,'players':list(reversed(s['players']))},horizon=2,top_n=3)
        self.assertEqual(a,b)
        with patch.object(tp,'TIE_ENUMERATION_LIMIT',0):
            fallback=tp.optimise_paths(rows,s,horizon=2,top_n=3)
        self.assertEqual(a,fallback)


if __name__=='__main__': unittest.main()
