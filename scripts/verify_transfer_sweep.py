"""Independent exhaustive small-population ranking oracle and deterministic sweep.

Only the fixture generator and optimiser invocation use production/test helpers.
The oracle enumerates legal squads and ALL legal XIs, with integer-scaled exact
binary64 arithmetic, and implements the rank-specific inclusive Fraction band.
"""
import argparse
import itertools
import random
from collections import Counter
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

from fpl_ai import transfer_optimiser as opt
from fpl_ai.historical_io import atomic_write_json
from fpl_ai.experiment_io import digest
from tests.test_transfer_optimiser import fixture

BAND = Fraction(1e-6)


def reviewed_fixture(seed):
    rng = random.Random(seed)
    population, state = fixture()
    for player in population:
        player['xpts'] = rng.randint(0, 20) / 3 + rng.choice([0.0, 1e-6 / 2, 1e-6, 2 * 1e-6])
        if player['element'] > 15:
            player['can_select'] = rng.choice([True, True, False])
    state['bank'] = rng.randint(0, 20)
    state['free_transfers'] = rng.randint(0, 3)
    return population, state, rng.randint(0, 2)


@lru_cache(maxsize=16)
def topology(facts):
    players = {e: (pos, team) for e, pos, team in facts}
    result = []
    for ids in itertools.combinations(sorted(players), 15):
        if Counter(players[e][0] for e in ids) != {1:2, 2:5, 3:5, 4:3}: continue
        if max(Counter(players[e][1] for e in ids).values()) > 3: continue
        xis = []
        for xi in itertools.combinations(ids, 11):
            c = Counter(players[e][0] for e in xi)
            if c[1] == 1 and c[2] >= 3 and c[3] >= 2 and c[4] >= 1: xis.append(xi)
        result.append((ids, tuple(xis)))
    return result


def exhaustive(population, state, maximum):
    players = {p['element']:p for p in population}
    fractions = {e:Fraction(p['xpts']) for e,p in players.items()}
    denominator = max(v.denominator for v in fractions.values())  # powers of two
    weights = {e:v.numerator * (denominator // v.denominator) for e,v in fractions.items()}
    held = {p['element']:p['selling_price'] for p in state['players']}
    outcomes = {}
    for ids, xis in topology(tuple((e,p['position'],p['team']) for e,p in sorted(players.items()))):
        incoming = set(ids) - held.keys(); outgoing = held.keys() - set(ids)
        if len(incoming) > maximum or any(not players[e]['can_select'] for e in incoming): continue
        bank = state['bank'] + sum(held[e] for e in outgoing) - sum(players[e]['purchase_price'] for e in incoming)
        if bank < 0: continue
        hit = 4 * max(0, len(incoming) - state['free_transfers'])
        # Independently enumerate every XI; captain is its greatest exact weight.
        score = max(sum(weights[e] for e in xi) + max(weights[e] for e in xi) for xi in xis)
        outcomes[ids] = {'score':Fraction(score,denominator)-hit, 'count':len(incoming), 'bank':bank, 'hit':hit}
    return outcomes


def check_case(seed, depth):
    population, state, maximum = reviewed_fixture(seed)
    reference = exhaustive(population, state, maximum)
    rejected = []
    # Wrap the production exact_net instead of replacing its tie-loop: captures
    # rank reference via solve_tied and all out-of-band candidates checked there.
    original_tied = opt.SquadMILP.solve_tied
    def observe_tied(solver, objective, best):
        original_net = solver.exact_net
        def observe_net(vector):
            score = original_net(vector)
            if best-score > BAND: rejected.append(str(best-score))
            return score
        with patch.object(solver, 'exact_net', side_effect=observe_net):
            return original_tied(solver, objective, best)
    with patch.object(opt.SquadMILP, 'solve_tied', new=observe_tied):
        result = opt.optimise(population, state, max_transfers=maximum, top_n=depth)
    if len(result['plans']) != min(depth,len(reference)): raise ValueError('wrong result count')
    remaining = dict(reference)
    players = {p['element']:p for p in population}
    losses = []
    for plan in result['plans']:
        best = max(r['score'] for r in remaining.values())
        tied_ids = [ids for ids,r in remaining.items() if best-r['score'] <= BAND]
        expected = min(tied_ids, key=lambda ids:(remaining[ids]['count'], ids))
        actual = tuple(plan['squad'])
        if actual != expected: raise ValueError(f'ranking differs: seed={seed}, depth={depth}, expected={expected}, actual={actual}')
        xi = plan['starting_xi']; captain = plan['captain']
        c = Counter(players[e]['position'] for e in xi)
        if not (len(set(xi))==len(xi)==11 and set(xi)<=set(actual) and captain in xi and
                c[1]==1 and c[2]>=3 and c[3]>=2 and c[4]>=1): raise ValueError('illegal XI/captain')
        exact = sum((Fraction(players[e]['xpts']) for e in xi), Fraction()) + Fraction(players[captain]['xpts']) - plan['transfer_hit']
        row = remaining.pop(actual)
        if exact != row['score'] or best-exact > BAND: raise ValueError('exact objective/band mismatch')
        if (plan['resulting_bank'],plan['transfer_hit'],plan['transfer_count']) != (row['bank'],row['hit'],row['count']):
            raise ValueError('economics mismatch')
        losses.append(str(best-exact))
    return {'seed':seed,'depth':depth,'maximum_transfers':maximum,'plans':len(result['plans']),
            'squads_sha256':digest([p['squad'] for p in result['plans']]),
            'exact_rank_losses':losses,'out_of_band_candidates_rejected':len(rejected)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds',type=int,default=400)
    parser.add_argument('--report',type=Path,default=Path('docs/M5A_EXHAUSTIVE_VERIFICATION.json'))
    args = parser.parse_args()
    seeds = [1596,26]
    seed = 0
    while len(seeds) < args.seeds:
        if seed not in seeds and all(p['xpts'] > 0 for p in reviewed_fixture(seed)[0]): seeds.append(seed)
        seed += 1
    rows = []
    for i,seed in enumerate(seeds):
        for depth in (1,3,10,20): rows.append(check_case(seed,depth))
        if (i+1)%50 == 0: print(f'{i+1} seeds verified',flush=True)
    atomic_write_json(args.report, {'generator':'review snippet: random.Random, randint(0,20)/3 plus micro offsets; eligibility/bank/free/max draws unchanged',
                      'seed_count':len(seeds),'seeds':seeds,'depths':[1,3,10,20],'cases':len(rows),
                      'all_squads_match_independent_exhaustive_ranking':True,
                      'all_rank_losses_within_exact_inclusive_band':True,
                      'out_of_band_candidates_rejected':sum(r['out_of_band_candidates_rejected'] for r in rows),
                      'results':rows})


if __name__ == '__main__': main()
