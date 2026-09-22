"""Deterministic multi-period exhaustive oracle sweep, normal/-O comparable."""
import argparse
import copy
import random
from pathlib import Path

from fpl_ai.experiment_io import digest
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.transfer_path import optimise_paths
from tests.test_transfer_optimiser import fixture
from tests.test_transfer_path import oracle, projection


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report',type=Path,default=Path('docs/M5B_ORACLE.json'))
    args=parser.parse_args()
    cases=[]
    for seed in [*range(20),26,1596]:
        rng=random.Random(seed)
        p,s=fixture(); q=copy.deepcopy(p)
        s['free_transfers']=rng.randrange(6); s['bank']=rng.randrange(26)
        for pop in (p,q):
            for player in pop:
                player['xpts']=(1+rng.randint(-3,3)*1e-6/3) if seed in (26,1596) else rng.uniform(-2,10)
        if seed%3==0:
            p[15]['can_select']=q[15]['can_select']=False
        expected=oracle([p,q],s,2,5)
        actual=optimise_paths(projection([p,q]),s,horizon=2,max_transfers=2,top_n=5)
        paths=[tuple(tuple(w['squad']) for w in a['weeks']) for a in actual['plans']]
        if paths != [e[3] for e in expected]: raise ValueError(f'oracle ranking mismatch seed {seed}')
        if any(a['total_points']!=float(e[0]) or a['total_hit_cost']!=4*e[1] for a,e in zip(actual['plans'],expected)):
            raise ValueError(f'oracle arithmetic mismatch seed {seed}')
        cases.append({'seed':seed,'plans':len(paths),'path_digest':digest(paths),'points':[a['total_points'] for a in actual['plans']]})
    atomic_write_json(args.report,{'independent_full_XI_and_path_enumeration':True,'cases':cases,'case_count':len(cases),
                                  'ranked_paths_checked':sum(c['plans'] for c in cases),'no_production_rules_or_lineup_in_oracle':True})
    print(args.report,flush=True)


if __name__=='__main__': main()
