# M5A — Rules-aware current-squad transfer optimiser v1

M5A is a deterministic **one-Gameweek optimiser v1**, consuming the accepted M4E
forecast family. It neither fits nor selects a model. The operator chooses
`control` or `v2`, and supplies their current squad and exact selling prices.

## Boundaries and rules

`fpl_ai/fpl_rules.py` defines the immutable validated `fpl-2026-27-one-gw-v1`
contract. Only this registered version is executable; altered constants or an
unsupported season fail closed. The engine reads rules through this boundary so
future registered rules and planning contracts can extend it separately.

The encoded squad is 15 players: 2 GK, 5 DEF, 5 MID, 3 FWD, at most three from a
club. XI size is 11, with exactly one GK, 3–5 DEF, 2–5 MID and 1–3 FWD. The captain
must start and receives twice base xPts. A separate vice-captain and deterministic
outfield bench order are provided, with the reserve goalkeeper last; neither
changes the objective. The input free-transfer count is 0–5. Additional transfers
cost four points each. The next ordinary-GW balance is
`min(5, max(0, free_transfers - transfers) + 1)` and has **no objective value**.
The rules describe an established team without an active chip, not the initial
unlimited-transfer squad-selection stage. No chip strategy or special event top-up
is implemented. Squad market value is not capped at the initial £100m: this is
current-team transfer economics, with exact selling prices and available bank.

The implemented subset agrees with the [official FPL rules](https://www.premierleague.com/es/news/4661029)
checked during this batch. The two-midfielder minimum also follows from XI size
and maximum available goalkeeper, defenders and forwards. Player scoring equations,
chips and autosub contingencies are outside this optimiser's rules subset.

`current-squad-v1` is a closed JSON object with exactly:

- `contract`: `current-squad-v1`;
- `season`: `2026-27` and `target_gameweek`: integer 1–38 matching the forecast;
- `players`: exactly 15 objects with `element` and `selling_price`;
- `bank`: nonnegative integer;
- `free_transfers`: integer 0–5, available **before this proposed plan**.

Prices and bank are integer £0.1m units (e.g. 55 means £5.5m). Each selling price
must be positive and no greater than the bound current purchase price. The user
provides it directly: no public-price reconstruction. Previously incurred transfer
hits are sunk and not included in incremental plan costs. Duplicate JSON keys,
extra fields, bools masquerading as integers, nonfinite numbers, duplicates,
unknown IDs, invalid composition/clubs and mismatching season/GW fail closed.
The [demo input](../tests/fixtures/optimiser/demo_gw6_squad.json) is **synthetic**,
including selling prices, and is not the user's team.

## Forecast and immutable artifact interfaces

`load_forecast` calls the unmodified M4E `verify_forecast` with a trusted local
operational model directory. It verifies the exact family, protocol, content
hashes, fitted model identities, season/GW/deadline and population, and replays
saved predictions. It restores the checksum-bound snapshot and extracts current
team, position, purchase price, display name and boolean `can_select`; missing or invalid decision facts
fail rather than falling back to live data. No network, target settlement, future
label or refit is needed. The replay does call production prediction functions;
it does not duplicate model logic or claim an independent prediction engine.
`v2` maps explicitly to M4E's `xpts_v2` column and model identity. Both remain
available, with no automatic selection, averaging, clipping or tuning.

`one-gw-transfer-decision` uses the established staged, atomic, content-addressed
publisher. Its closed files are `squad.json`, `population.json`, `source.json`,
`decision.json`, `rules.json`, `config.json`, `report.md`, plus `manifest.json`.
The source record preserves the original forecast manifest, its byte hash,
selected model identity, embedded snapshot manifest byte hash, and transitive
snapshot/minutes/model/protocol identities. Reproduction uses those immutable
upstream bundles; it does not duplicate their serialized models or raw archives.
The manifest retains canonical squad hash, full rules/config, season/GW/deadline,
implementation hashes and environment. The complete forecast population, exact `can_select` flags and selected unrounded
xPts are retained. Decision contract `m5a-one-gw-transfers-v2` adds explicit
forecast/selectable/owned/solver counts and the hardened tie policy. Input player order and JSON whitespace are
not semantic: the canonical sorted squad is hashed. Every serialized output has a
checksum. Reuse regenerates a candidate and verifies existing content without
rewriting it; corruption fails. Implementation changes deliberately change identity.

## Point-in-time transfer eligibility hardening

The sole selectability authority is `elements[].can_select` in the verified bound
bootstrap: it must be a JSON boolean for **every** forecast row, including owned
and excluded players. `true` admits a transfer in; `false` forbids a new acquisition.
The [provider data dictionary](https://github.com/vaastav/Fantasy-Premier-League/blob/master/DATA_DICTIONARY.md#position--status)
identifies this as the selection flag. In this snapshot, `can_transact` is true and
`removed` false for every row, so those fields cannot establish selectability.
Injury/suspension status is also not a replacement for the explicit permission.
No later/current player data is fetched or used. Corruption or changed embedded
flags without matching bound hashes fails at the existing M4E verification boundary.

Owned unselectable players can remain, start, captain, or be sold; this flag limits
new acquisition rather than mandating disposal of existing holdings. The original
squad contract, including all club and position checks, remains unchanged.
Unselectable non-owned rows stay in `population.json` for audit but have **no MILP
variables**. Plan construction independently rejects ineligible incoming IDs.
Every decision and its report distinguishes forecast, transfer-in-eligible,
eligible-not-owned, owned, owned-unselectable and optimisation populations.

Seven new regression tests cover a dominant unselectable newcomer and selectable
alternative; owned-player retention/captaincy/sale; malformed/missing flags;
bound-snapshot tampering and both model paths; just-below/exact/just-above tolerance
boundaries; fewer-transfers and lexicographic priorities; and non-chained tolerance.
Boundary cases use adjacent representable floats, including a case where ordinary
rounded totals can conceal the distinction. Repeated runs are deterministic.
See Decision 047; Decisions 046–047 remain unchanged historical records. The
subsequent numerical reliability correction is documented in Decision 048 below.

## Optimisation and ties

SciPy 1.16.2/HiGHS is already pinned; no dependency was added. The mixed-integer
formulation has squad, starting-XI and captain binary variables only for selectable
players union existing squad members,
and an integer paid-transfer count. Membership, formation, club, transfer-count
and budget constraints apply jointly, so simultaneous transfers can release both
money and club slots. Budget is expressed as retained players' selling value plus
incoming players' purchase cost, bounded by original selling value plus bank.
Incoming and outgoing sets are disjoint; unnecessary sell/rebuy cycles are absent.
Default maximum transfers is two; the operator can choose 0–15. Top-N defaults to
three, with supported range 1–20. Fewer results are returned if all legal outcomes
are exhausted. The no-transfer optimum is **always separately retained**, even
when it is outside the requested top-N.

The sole primary objective is:

`sum(starting-XI base xPts) + captain base xPts - 4 * paid transfers`

Bench points and the option value of remaining transfers are zero in the objective.
No whole-population transfer combinations are enumerated. Each additional ranked
plan excludes the previous complete squad with a no-good cut, yielding distinct
transfer outcomes. The solver must report optimality with zero relative MIP gap;
time limits (120 seconds per solve), errors and nonintegral/invalid results fail
closed. Results use floating-point optimisation, not a symbolic rational proof:
objective-equivalent ties have loss **<= 1e-6 points inclusive** from the fixed
best remaining objective at each rank. This corrects the original implementation's
`TOLERANCE / 10` (1e-7) constraint. The primary objective is uniformly scaled by
1e6; the full inclusive tie bound is scaled by 1e4. Neither changes predictions.
After every secondary solve, exact sums of binary64 input values (using `Fraction`)
check the loss against the exact binary64 `1e-6` literal. A solver-feasible squad
outside that band is excluded temporarily and retried, rather than broadening the
contract. Temporary exclusions reset at the next rank. All secondary stages use
the same primary reference, preventing chained tolerance. Report arithmetic retains
the existing floats; prediction rounding, clipping and quantisation remain absent.

Secondary priority is fewer transfers, then the lexicographically smallest sorted
squad-ID list. Sequential 16-bit objectives establish a unique squad order without
perturbing the primary objective with epsilon weights. Each fixed squad's legal
formations are solved directly using position-ranked players. XI/captain ties use
ascending IDs. This deterministic formation calculation also recomputes reported
XI/captain totals independently of the solver's selected binary lineup. Bench
ordering is descending base xPts then ascending ID (GK separate); vice-captain
uses the same starter ranking. No probabilistic autosub or captain fallback value
is included.

## Earlier scaled-constraint correction (Decision 048; superseded by 049)

The prior acceptance conclusion was premature: a supported valid input could
raise `solver constraint violation` before reaching the exact semantic tie check.
We reproduced this on the unmodified implementation using the existing legal
17-player fixture, setting all base xPts to 1, element 16 to
`1 + 1.001e-6 / 2`, and non-owned element 17 unselectable; max transfers 1, top-N 3.
The attachment did not supply a separate reviewer fixture; this deterministic
input reproduces the reported failure mechanism with actual HiGHS output.

At a secondary solve, the rounded vector's tie-row residual was approximately
**1.00000034e-5 scaled units**, or **1.00000034e-9 objective points** after dividing
by 1e4. The old validator compared the scaled residual directly against 1e-6.
That prematurely rejected the entire run instead of allowing the exact gate to
reject the inferior candidate and retry. The regression restores the old unit
handling locally to prove it still raises, then verifies the corrected run.

That correction gave each constraint its scale. Both upper and lower residuals were divided
by that scale before checking the separately named numerical feasibility allowance
of 1e-6 in original row units. Existing integer squad/budget/membership and
lexicographic rows retain scale 1. The tie row retains scale 1e4; the primary
objective retains scale 1e6. Row scales are restored along with temporary cuts
between ranks. No mathematical constraint or objective has changed.

**Numerical feasibility is not semantic tie membership.** The same exact
`Fraction` computation still rejects any squad with objective loss >1e-6 from
that rank's fixed best reference. The failing fixture's no-transfer squad is
slightly outside that band and is rejected; the returned three legal upgraded
squads all equal the independently computed exact optimum. Existing tests retain
one representable float below, at and above the boundary, equality, clearly larger
differences, fewer transfers, lexicographic ordering and no chained tolerance.

The nearby fixture with base xPts 3 exposed a secondary HiGHS presolve false
infeasibility. A single retry of that same model with presolve disabled proves
optimality. This narrowly scoped retry applies only to secondary infeasibility;
all normal solver-success, integrality, residual, legality and exact semantic
checks remain mandatory. Time-limited/unproven results are never accepted.

That pass added three tests covering the reproduced old-unit failure/successful top-three
exact replay, lower and upper normalized-residual validation (including rejected
excess residuals), and the real presolve retry. Verification assertions use
`unittest` methods or explicit runtime checks, so optimized Python retains them.
The original fixture's exact optimum is
`12 + 2 * (Fraction(1 + 1.001e-6 / 2) - 1)`; no rounding is used to test the loss.

## Final correction: structural checks versus exact tie admission (Decision 049)

Decision 048's normalised but global numerical guard was still too restrictive.
The reviewer supplied the exact generator: `random.Random(seed)`, each xPts is
`randint(0,20)/3 + choice([0,1e-6/2,1e-6,2e-6])`; non-owned selectability is drawn
from `[True,True,False]`, then bank 0–20, free transfers 0–3 and max transfers 0–2.
Seed **1596**, top-N **1**, yields bank 14/free 0/max 2; seed **26**, top-N **10**,
yields bank 13/free 3/max 2. Both reproduced `solver constraint violation` on the
saved pre-fix module, and both continue to fail when tests emulate its all-row
numeric guard. The corrected implementation completes both cases.

A candidate can have exact loss about 2.00000000028e-6 and a scaled tie-row residual
about 0.010000000009, yielding 1.00000000093e-6 after normalisation. The old guard
aborted before the exact gate could reject it. Increasing that global allowance
would merely move the failure threshold and confuse two distinct responsibilities.

Rows now explicitly distinguish **structural** from **objective-band** constraints.
The latter remains in the solver for search conditioning but has no generic
post-solve residual cutoff. All structural residuals are checked as before, along
with finite values, rounded variable bounds, integrality and proved optimality.
Budget, counts, positions, clubs, membership, transfer count/fixings, lexicographic
fixings and no-good cuts retain their structural classification. Scale and role
metadata are restored with temporary rows between ranks.

**Numerical admission is not semantic acceptance.** Every structurally valid
secondary candidate reaches the unchanged exact Fraction best-XI/net computation.
Only loss <=1e-6 inclusive from that rank's fixed best remaining objective is
accepted; greater loss excludes the squad and retries. Predictions, primary
objective, deterministic priorities and non-chaining semantics are unchanged.
The existing presolve-disabled retry remains subject to the same checks.

Two new tests cover the exact reviewer cases, prove actual out-of-band rejection,
and compare every returned squad and rank loss with an independently exhaustive
reference. Existing lower/upper structural-residual, equality/adjacent-float,
non-chaining, legality, economics and presolve regressions remain intact.

The [exhaustive sweep](../scripts/verify_transfer_sweep.py) enumerates every legal
small-fixture squad and every legal XI; exact binary64 sums use integer weights
with a shared power-of-two denominator. Reference ranking independently applies
the fixed best-at-rank band, fewer transfers and ascending squad IDs; it uses no
production plan/lineup helper. The supplied generator is unchanged. Starting with
the two reviewer seeds, it scans ascending seeds and keeps strictly positive-xPts
populations until **400 seeds** are included. It tests depths **1, 3, 10, 20**.
All **1,600 cases** match the exhaustive reference, including every exact rank loss.
**121 solver candidates were rejected as out of band and retried.** Seed 1596/top-1
records one rejection; seed 26/top-10 records two. Normal and optimized reports
are byte-identical: [machine sweep evidence](M5A_EXHAUSTIVE_VERIFICATION.json).

## Operator commands

```bash
export LOKY_MAX_CPU_COUNT=1
MODEL=data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230
FORECAST=data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527
# Synthetic demo only. Replace with your actual current-squad-v1 JSON for real use.
.venv/bin/python -m fpl_ai optimise --forecast-dir "$FORECAST" --model-dir "$MODEL" \
  --model control --squad tests/fixtures/optimiser/demo_gw6_squad.json \
  --max-transfers 2 --top-n 3
# A separate explicit run; no model comparison or selection is performed:
.venv/bin/python -m fpl_ai optimise --forecast-dir "$FORECAST" --model-dir "$MODEL" \
  --model v2 --squad tests/fixtures/optimiser/demo_gw6_squad.json \
  --max-transfers 2 --top-n 3
```

Each command prints its immutable directory and human-readable report. Override
`--artifact-dir` for another output root. The command performs frozen-evidence
replay and remains usable for reproduction after a deadline; it never re-dates a
forecast or promises the state is still current. This early GW6 snapshot is from
September 18, before the retained October 10 deadline, with missing history.
Use a legitimately retained nearer-deadline forecast for an actual decision.

## Verification

The focused hand fixture has 15 one-point players, bank 12, selling prices 49,
one free transfer, and two new players costing 55 with 10 and 8 base xPts.
Baseline is 11 + 1 = **12**. One transfer yields 20 + 10 = **30**, bank 6.
Two yield 27 + 10 − 4 = **33**, bank 0. With bank 5 neither upgrade is affordable;
changing the outgoing player's exact selling price from 49 to 50 enables one.
An exhaustive tiny-population reference checks top ten unique squads and tie order.

The executable [verification entry point](../scripts/verify_transfer_optimiser.py)
uses production optimisation and forecast verification, but independently reads
original prediction rows and embedded raw snapshot facts. For the original and
every returned squad it checks composition/clubs, integer money/hits, XI formation,
captain membership, objective and baseline gain. It independently enumerates all
legal starting XIs of each resulting 15-player squad to confirm optimality.
Fresh builds and verified reuse run separately for control and v2. See
[M5A_VERIFICATION.json](M5A_VERIFICATION.json) for full plans and identities, and
[M5A_REGRESSION.json](M5A_REGRESSION.json) for test and preservation evidence.

```bash
# Capture before starting a batch; never overwrite the pre-batch inventory:
PYTHONPATH=. .venv/bin/python scripts/verify_transfer_regression.py --capture /tmp/m5a-before.json
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m unittest tests.test_transfer_optimiser -v > /tmp/m5a-focused.log 2>&1
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -O -m unittest tests.test_transfer_optimiser -v > /tmp/m5a-focused-opt.log 2>&1
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m unittest discover -s tests -q > /tmp/m5a-normal.log 2>&1
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -O -m unittest discover -s tests -q > /tmp/m5a-opt.log 2>&1
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=. .venv/bin/python scripts/verify_transfer_optimiser.py
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=. .venv/bin/python -O scripts/verify_transfer_optimiser.py \
  --report /tmp/m5a-optimized.json
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=. .venv/bin/python scripts/verify_transfer_sweep.py
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=. .venv/bin/python -O scripts/verify_transfer_sweep.py \
  --report /tmp/m5a-sweep-optimized.json
PYTHONPATH=. .venv/bin/python scripts/verify_transfer_regression.py \
  --before /tmp/m5a-before.json --normal-log /tmp/m5a-normal.log \
  --optimized-log /tmp/m5a-opt.log --focused-log /tmp/m5a-focused.log \
  --focused-optimized-log /tmp/m5a-focused-opt.log \
  --prior-report docs/M5A_PRE_ADMISSION_VERIFICATION.json \
  --optimized-report /tmp/m5a-optimized.json \
  --optimized-sweep-report /tmp/m5a-sweep-optimized.json
```

## Recorded GW6 demo results

The bound forecast contains **659 rows**, of which **554** have `can_select=true`
and **105** have `can_select=false`. The demo owns 15 players, including one
unselectable player; 540 selectable players are not already owned. The MILP
therefore includes 555 players (554 selectable plus that retained owned player).
Maximum transfers was two,
with one available free transfer and synthetic bank £1.0m. Three distinct ranked
plans were returned for each explicitly chosen model, plus the separate baseline.

| Explicit model | No-transfer net | First-ranked net | Gain | Hit | Remaining bank |
| --- | ---: | ---: | ---: | ---: | ---: |
| control | 30.700207 | 34.090866 | +3.390659 | 0 | £0.1m |
| v2 | 28.014028 | 30.701324 | +2.687296 | 0 | £0.2m |

Control's first plan changes element 21 to 124, captaining 124. V2's first changes
33 to 449, captaining 4. These are different objective runs on a **demo team**, not
model-quality comparisons or recommendations for the user's team. Both happen to
prefer one transfer despite permission to make two; a second transfer would need
to justify its hit under this objective. All eight baseline/ranked-plan records
passed independent legal-squad, economics, formation, captain and exact objective
checks, including exhaustive XI verification. Fresh content and identities matched;
reuse preserved all decision bytes and nanosecond mtimes. Both original winners
(124 and 449) have `can_select=true` in the independently inspected bound snapshot.
**All baseline and top-three plan fields are unchanged** for both models. In this
admission fix the populations and semantic contract also stay unchanged; revised
implementation/config hashes produce new content-addressed decision identities. The verifier compares against a byte-for-byte retained copy of the original
[M5A pre-hardening report](M5A_PRE_HARDENING_VERIFICATION.json). That file is a
historical record of the earlier reporting schema, not current eligibility evidence.
The regression script additionally checks all plan fields, objectives, population
counts and selectability against the byte-for-byte preserved
[pre-admission-fix report](M5A_PRE_ADMISSION_VERIFICATION.json). The numerical fix changes
implementation/config hashes and publishes new decision identities; it changes
none of those GW6 results.

**238 tests pass in normal and optimized Python**: all 236 prior tests
plus two reviewer-seed regressions (28 focused tests pass in both modes). All
**904 pre-hardening data files retain their original bytes and nanosecond
mtimes**. Normal and optimized real-verifier reports are byte-identical. Exact
results, original preservation inventory and test logs are retained in the
regression report linked above. CLI help, compilation and diff-whitespace checks
also pass, including explicit checks of all nonignored untracked text artifacts.
M5A acceptance is restored within its one-Gameweek scope after the exact reviewer
regressions, exhaustive sweep and complete verification pass. No
commit, merge or push was performed.

## Limits and next objective

This is the best plan under a single frozen one-GW objective, not universally the
best transfer. It cannot value future fixtures, rolling a transfer, long-term
budget flexibility, uncertainty, chips or multi-GW paths. Point forecasts remain
uncertain; no simulation, calibrated decision confidence, account access, service,
scheduler or LLM-generated advice is added. No real-user recommendation is claimed
from the demo. Control/v2 prospective quality is still unresolved.

M4E remains frozen. Its separate operational work is nearer-deadline retention,
authoritatively settled scoring, and accumulating prospective evidence without
premature model selection. The next substantial decision-system objective is
**multi-Gameweek projections and transfer-path optimisation**, using these reusable
rules, squad-state and immutable decision boundaries.
