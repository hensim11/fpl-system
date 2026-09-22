# M5B — Multi-Gameweek projections and transfer paths

## Scope and contracts

M5B adds a separate expected-points planning layer. M4E control/v2, M5A, and
all earlier artifacts retain their contracts. Decisions 050–052 record the new
contracts. No retrospective model winner or realised FPL improvement is claimed.

`fpl_ai/multi_projection.py` constructs future individual-GW labels, fits five
fixed direct models, publishes historical predictions with separate outcomes,
and publishes/replays current projections. `fpl_ai/transfer_path.py` implements
the sparse multi-period MILP and human-readable decisions. The existing artifact
publisher has four new closed artifact families; CLI commands are `project` and
`plan`. There is no live fetch during planning or replay.

The target is points in GW g+h for h=0..4, using only the accepted state at g.
Later labels join by season/GW/element from the verified M3 evidence. They never
supply features. Doubles use their full canonical sum; verified explicit player
zeros remain zero; missing future registration/evidence and the genuine historical
blank remain unlabelled. GW38 is the boundary, not a wrap into another season.
The 2021/22 GW18 exception keeps its original freshness limitation. Historical
final fixtures remain unavailable as predictors (Decision 014).

## Fixed model protocol and historical results

Each horizon uses M4 hist_15: squared error, 15 leaves, 150 iterations, learning
rate 0.05, minimum leaf size 50, L2 10, no early stopping, seed 1729 and one thread.
The same 25 inputs, median imputation/missingness, scaling and one-hot encoding
are fitted only on the permitted training rows. There is no per-horizon search.

Historical training is 2021/22–2024/25; the latest permitted settlement precedes
the first 2025/26 capture. **2025/26 is consumed historical evidence, not an
untouched holdout.** Production then refits the frozen design on all five prior
seasons, with settlement strictly before 2026-07-01. No result-driven tuning.

| Offset | Historical fit | Evaluation rows | Production fit | RMSE | MAE | Within-GW Spearman | Recent-points RMSE |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | 107,393 | 29,645 | 137,038 | 1.913756 | 0.948185 | 0.742163 | 2.207706 |
| 1 | 104,241 | 28,805 | 133,046 | 1.988073 | 1.020859 | 0.698757 | 2.257511 |
| 2 | 101,122 | 27,967 | 129,089 | 2.022014 | 1.062055 | 0.674297 | 2.302047 |
| 3 | 97,998 | 27,135 | 125,133 | 2.044444 | 1.085815 | 0.657168 | 2.351696 |
| 4 | 94,877 | 26,305 | 121,182 | 2.065064 | 1.103883 | 0.643678 | 2.368194 |

All eligible evaluation rows have predictions and labels. Earlier-season missing
labels remain excluded: respectively 624, 623, 603, 594 and 589 across the five
horizons. Full evidence includes position-mean and recent-points baselines,
position segments, prediction distributions, residual quantiles, and cumulative
three/five-GW diagnostics over complete horizon labels.

GW+0 is explicitly different from M4E because it uses the full prior-season M3
population. In the retained real state its mean difference is +0.017890 versus
control and +0.201082 versus v2; maximum absolute differences are 1.038406 and
1.715765. These forecast differences do not establish model superiority. Both
M4E models remain frozen; later horizons are independently fitted targets, never
copies or rescalings of M4E.

## Planning formulation

For each GW, binary variables select the squad, legal XI, captain, purchases,
sales and surviving initial selling-price rights. Integer bank balances and
one-hot `(FT before, transfer count, FT after, paid count)` arcs connect weeks.
Squad/position/club constraints are structural, as are buy/sell membership,
integer budget, starting-XI formation and captain membership.

Free transfers evolve as `min(cap, max(0, FT - transfers) + weekly accrual)`;
hits are `hit_cost * max(0, transfers - FT)`. The registered 2026/27 rules provide
all constants. Default maximum transfers is two **per GW**, explicitly recorded
in the search contract. The objective sums optimal XI and captain points minus
hits with equal GW weights. It contains no bench or terminal value.

Static prices are an assumption. Exact initial selling prices apply until first
sale. New purchases, including repurchases, subsequently sell at their fixed
purchase price. Frozen strict boolean `can_select` controls transfer-in eligibility
throughout the horizon. Owned unselectable players may remain. V1 rejects changing
price/eligibility assumptions across projection rows rather than silently treating
them as forecasts.

Top-N refers to unique complete GW-ordered squad paths. Each rank admits only
exact Fraction-sum loss <=1e-6 from its own best remaining primary objective;
priorities then minimise paid transfers, total transfers and lexicographic squads.
Every GW's XI/captain is chosen independently. Structural checks and semantic tie
acceptance are separate; objective conditioning never enlarges the tie band.
Time-limited/unproven solves fail closed. The time limit is per solver call; a
ranked full-population run can take many calls and several minutes.

Reports contain a legal no-transfer baseline and sequential greedy comparison.
Projected gains measure the stated objective, not realised decision utility.

## Reproducible commands

```bash
M3=data/modelling/57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a
MODEL=data/multi_projection/models/b0e9cf270c6524278ddb6c288c393aef580159c2a36a02b9a01e81cfadf4235b
M4E_MODEL=data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230
M4E_FORECAST=data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527
PROJECTIONS=data/multi_projection/forecasts/03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b

.venv/bin/python -m fpl_ai project fit --m3-dir "$M3"
# A NEW runtime publication; only while the actual target deadline permits it:
.venv/bin/python -m fpl_ai project freeze --forecast-dir "$M4E_FORECAST" \
  --m4e-model-dir "$M4E_MODEL" --model-dir "$MODEL" --horizon 5
# Offline replay of the original timestamped evidence:
.venv/bin/python -m fpl_ai project verify --projections-dir "$PROJECTIONS" \
  --m4e-model-dir "$M4E_MODEL" --model-dir "$MODEL"
.venv/bin/python -m fpl_ai plan --projections-dir "$PROJECTIONS" \
  --model-dir "$MODEL" --m4e-model-dir "$M4E_MODEL" \
  --squad tests/fixtures/optimiser/demo_gw6_squad.json --horizon 5 --top-n 3
```

The demonstration squad is synthetic, not the user's team. Forecasts are real
659-player GW6–10 predictions from the retained September 18 state, computed and
verified on September 21 before the October 10 deadline. They are early-state
projections with missing retained recent history, not near-deadline confirmation.
Re-running `freeze` produces a new actual timestamp; replaying an existing bundle
retains its original timestamp and predictions without backdating.

## Verification and limitations

`tests/test_multi_projection.py` exercises feature/label separation, missing
registration, zero/double/blank conventions, season boundaries, fitting cutoffs,
live/historical matrix parity and immutable artifact corruption. Historical
source semantics also remain covered by the unchanged M2–M4 suites.

`tests/test_transfer_path.py` enumerates all legal small-population squads and
ALL legal XIs in a separate oracle, then enumerates every feasible complete path
without production rules, lineup or economics helpers. It tests rolling, immediate
transfers, profitable/unprofitable hits, greedy regret, initial selling-price
rights and repurchases, bank/cap, club/position limits, unselectable players,
three-GW retention, negative forecasts, exact tie boundaries, rank determinism,
invalid horizon/populations and solver failure. `scripts/verify_multi_oracle.py`
extends this to 22 deterministic cases and 82 feasible ranked paths, including
near-tie seeds 26 and 1596; normal and optimized output must match exactly.
Top-N requests at most five paths per case: 15 cases return five and seven return
only one, so the checked total is 15 × 5 + 7 × 1 = 82. The one-path cases
(seeds 2, 6, 7, 10, 15, 18 and 19) have banks below 6 units; either available
replacement costs 55 while an owned player sells for 49. No first transfer is
affordable, and rolling does not change the bank, so the no-transfer path is the
only feasible complete path. This is intended exhaustive-oracle behaviour, not
an optimiser correctness failure. The report sums emitted paths rather than
assuming every case reaches the requested maximum.

`scripts/verify_multi_gameweek.py` independently joins labels and fitting keys,
checks chronology and hashes, replays saved models, recomputes metrics, and audits
every real-demo XI, captain, transfer, bank and FT transition. Optional `--rebuild`
verifies fresh/reused model, score and decision identities, bytes and mtimes.
Machine evidence and regression logs record actual completed checks.

Limitations: no deadline-known historical fixture features; no future availability,
price, ownership, chip or risk forecasts; no calibrated intervals; no realised
transfer-path backtest or prospective utility claim. Price/eligibility policies are
static and versioned. Sparse MILP ranking has significant full-population runtime.
New settled prospective evidence and runtime profiling are the next substantial
work, followed by uncertainty calibration/risk-aware planning only after its
forecast and decision contracts are defensible.

## Real five-GW planning result

The full 659-player projection population (554 selectable; 555 solver candidates
including the owned unselectable player) is retained. Default search limits are
five GWs, two transfers per GW and top three complete paths. The verified decision
is `data/transfer_paths/0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8`.

| Path | Net projected total | Gain vs no transfer | Hit points |
|---|---:|---:|---:|
| 1 | 194.178 | +30.113 | 8 |
| 2 | 194.046 | +29.981 | 8 |
| 3 | 193.924 | +29.859 | 8 |
| Sequential greedy | 188.020 | +23.955 | 0 |
| No transfer | 164.065 | 0 | 0 |

Best path: two transfers in GW6, two in GW7, one in GW8, roll GW9, and two free
transfers in GW10. It uses seven transfers and eight hit points in total. The
report and machine evidence carry exact IDs, names, bank, FT transitions, XI and
captain. This is a demonstration on a synthetic squad, not a team recommendation.

A separate stricter one-transfer-per-GW/top-one run scores 190.338, with no hits;
it remains immutable under decision identity
`26b900fe844835296b1a20f9a32c54092fb031bb2255eac0ec3d84ee5d03dd24`.

Initial full-population secondary solves inside the narrow floating-point band
were too slow and were stopped without publishing decisions. The final formulation
proves minimal discrete counts with primary solves and uses exact enumeration of
small tie sets before falling back to binary-block ranking. It preserves the same
objective/tolerance and all candidates. The final default top-three demonstration
completed in approximately 110 seconds on this machine; the stricter top-one run
took approximately 30 seconds. These timings are observations, not runtime bounds.

Machine evidence: [historical/live/plan audit](M5B_VERIFICATION.json),
[22-case/82-feasible-path exhaustive sweep](M5B_ORACLE.json),
[full-suite, rebuild and preservation record](M5B_REGRESSION.json).

Final acceptance evidence: **261 tests pass normally and under `python -O`** after the evidence correction
(two focused regressions added to the reviewed 259-test baseline).
Normal/optimized independent audit and oracle reports are byte-identical. Fresh
model, score and full top-three decision builds reproduce original identities;
repeated builds reuse them without byte/mtime changes. All **920** pre-batch data
files retain bytes and nanosecond mtimes. Compilation, CLI help and tracked/new
text whitespace checks pass. M5B is recommended for acceptance within its stated
expected-points/static-assumption scope. No commit, merge or push was performed.

The evidence correction changes no projection, optimiser or oracle-generation
behaviour. Focused regressions cover a requested top-five with only one feasible
path and report totals derived from varying emitted counts. Original generated
reports remain unchanged; [correction verification](M5B_EVIDENCE_CORRECTION.json)
records the reruns, deterministic comparisons and preservation checks.
