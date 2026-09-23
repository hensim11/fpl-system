# M5D — Joint simulation and plan evaluation verification

M5D meets its implementation acceptance criteria within the declared empirical
simulation scope; **recommend acceptance**. All verification below completed.
Independent prospective calibration and decision utility remain unproven.

## Contract and architecture

`joint-simulation-v1` is a complete-trajectory empirical bootstrap with a shared
historical as-of block. `m5d-plan-evaluation-v1` compares existing legal paths with
common random numbers. See [the exact law and limitations](M5D_DESIGN.md) and
Decisions 057–060. There are no new dependencies, point-model changes, marginal
recalibration or optimiser/tie-semantic changes.

New production modules: `fpl_ai/joint_simulation.py` and
`fpl_ai/simulation_plans.py`. CLI and the shared closed artifact registry are
extended; accepted M5B/M5C implementation and data remain unchanged. Raw cubes
are reproducible from source identities, configuration, RNG and software. The
published simulation occupies 10,410,648 bytes versus
431,882,240 bytes for one raw 16,384 × 5 × 659 float64 cube.

## Exact real state and identities

| Product | Identity |
| --- | --- |
| M5B model | `b0e9cf270c6524278ddb6c288c393aef580159c2a36a02b9a01e81cfadf4235b` |
| M5B historical scores | `15330198b278c5b82eca1b756d46236ac998a573ce755022957c89d0c7394c4f` |
| M3 | `57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a` |
| M5B projection | `03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b` |
| M5C calibration | `782bf10333f482f4ff2a1e19a2c438c4bc9d04b27b237779b1e71dbb8bc6d699` |
| M5C uncertainty | `c0a759479365bb0ee8676b355926ab2fdbd4a84bdca0d496d41c07189a471f2d` |
| M5D simulation | `0a4dceb30cd0fba3c4ef50c8f09b4c89e74eeb3a4b3704dc70baa69ac5029a62` |
| Deterministic simulation key | `355559e361d9721b598900f2507ccf73a71c7bb40fdf9dc551235de235e9b1dd` |
| M5D plan evaluation | `36a266e775e124a6d36bfb813e0aedf364c200a394a82d9b25e0b48a75902c3f` |
| Accepted M5B top-three plan | `0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8` |

Original as-of: **2026/27 GW6**; capture `2026-09-18T21:07:27.274412Z`;
M5B computation `2026-09-21T22:51:47.767427Z`. The bound first target deadline remains
**`2026-10-10T10:00:00Z`**. M5D started `2026-09-23T10:15:48.340036Z` and completed
its initial computation `2026-09-23T10:18:25.273024Z`. The actual-clock publisher
also completed full replay verification and its final deadline gate successfully.
No timestamp override and no newer news/state/outcome fetch occurred. Publication
is prospective; later verification/reuse retains this attestation without redating.

**The demonstration squad is synthetic, not the user's actual squad.** There are
no realised M5D outcomes or proven FPL decision gains. The simulation is conditional
on the retained early state, not nearer-deadline confirmation.

## Historical population and dependence diagnostics

Exact M5C reconstruction covers 139,857 prediction rows. Five-GW donors comprise
26,305 complete trajectories across 34 as-of blocks, with 3,340 explicitly keyed
season-end exclusions and no missing-label exclusion in this retained five-GW pool.
The latest prior-season settlement is May 25, 2026; the cutoff is July 1, 2026.
Historical rows/windows are dependent and 2025/26 is consumed evidence.

For GW+0 versus GW+4, complete historical donor correlation is 0.070354. Joint
simulated correlation is 0.070945; the independent null gives −0.000514. GW+0
distinct-player residual covariance is 0.014992 against the block-law reference
0.014920; the null is approximately zero (−0.000116). Aggregate GW+0 residual-sum
SD is 94.58 under the joint law and 48.92 under the null. These verify declared
semantics descriptively; they do not select a model or validate future calibration.

Every player/horizon has forecast and simulation mean, population SD, percentiles,
negative-point frequency and simulated coverage of the unchanged M5C intervals.
Both full M5C marginal and complete-window donor distributions are retained. Raw
residual means are positive here, so simulated plan means exceed unchanged M5B
objectives. Analytical expectation and Monte Carlo error are separately reported.

## Plan distributions at 16,384 scenarios, seed 1729

Joint model; total five-GW points including captain bonuses and transfer hits.

| Path | M5B objective | Simulation mean | Median | SD | P10 | P90 | Lower 10% mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| no_transfer | 164.065 | 165.745 | 164.334 | 20.713 | 140.847 | 192.737 | 132.392 |
| greedy | 188.020 | 189.770 | 188.367 | 20.458 | 165.110 | 216.464 | 156.798 |
| exact_1 | 194.178 | 195.990 | 194.471 | 20.363 | 171.580 | 222.738 | 163.111 |
| exact_2 | 194.046 | 195.847 | 194.359 | 20.339 | 171.510 | 222.349 | 163.076 |
| exact_3 | 193.924 | 195.745 | 194.281 | 20.334 | 171.395 | 222.361 | 162.846 |

Paired comparisons use identical scenarios for every candidate.

| Path | Mean gain vs no transfer | Beat no transfer | Beat greedy | Highest, split ties |
| --- | ---: | ---: | ---: | ---: |
| no_transfer | 0.000 | 0.00% | 3.25% | 0.99% |
| greedy | 24.024 | 96.75% | 0.00% | 25.80% |
| exact_1 | 30.245 | 96.53% | 67.40% | 20.91% |
| exact_2 | 30.102 | 96.36% | 66.36% | 22.62% |
| exact_3 | 30.000 | 96.11% | 67.49% | 29.68% |

Independent null comparison (same marginals, dependencies removed):

| Path | Mean | SD | P10 | P90 | Beat no transfer | Beat greedy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| no_transfer | 166.020 | 16.915 | 145.573 | 188.708 | 0.00% | 1.77% |
| greedy | 189.908 | 16.944 | 169.324 | 212.092 | 98.23% | 0.00% |
| exact_1 | 196.107 | 16.896 | 175.397 | 218.483 | 98.51% | 69.12% |
| exact_2 | 195.979 | 16.907 | 175.317 | 218.451 | 98.32% | 68.27% |
| exact_3 | 195.929 | 16.927 | 175.402 | 218.241 | 98.21% | 69.63% |

Path 1 has the highest forecast objective, while path 3 has the largest probability
of being highest among this specific supplied set. These are different criteria,
not permission to select a risk attitude. Top-three distributions are very close.
The existing optimiser remains unchanged. Full P05/P95, paired gain quantiles,
win/tie/loss, extrema and Monte Carlo standard errors are in `evaluation.json`.

## Scenario-count choice and runtime

[Three-seed convergence evidence](M5D_CONVERGENCE.json) uses fixed seeds 1729,
2718 and 31415, with 1,024/4,096/16,384/32,768 prefixes. Doubling the operational
16,384 across both laws and all candidates changes means by at most 0.166 points,
P05/P10/P90/P95 by 0.684 points, lower-tail means by 0.368 points, paired win
probabilities by 0.00593 and highest-return probabilities by 0.00709. This is below
explicit practical targets of 0.5 mean points, 1 tail point and 0.015 paired
probability. Sampling error is much smaller than the unvalidated model assumptions.

Both-law 32,768-scenario generation and plan metric runs took 12.30, 23.59 and
80.11 seconds while other verification jobs competed for resources. These are
observed runtimes, not guarantees. Full-source verification and marginal diagnostics
add cost. The [real lifecycle record](M5D_LIFECYCLE.json) measures **4.88 seconds**
for both-law default-count plan computation and **44.82 seconds** for a fresh
publication including source verification, all diagnostics and final replay.
Other contended full replay/reuse operations took 50–182 seconds. The default halves cube memory relative to 32,768
while meeting the stated broad-comparison precision. It is not sufficient to infer
the superiority of nearly identical top-N plans.

## Operator commands

```bash
export LOKY_MAX_CPU_COUNT=1
PY=.venv/bin/python
M4E_MODEL=data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230
CALIBRATION=data/multi_uncertainty/calibrations/782bf10333f482f4ff2a1e19a2c438c4bc9d04b27b237779b1e71dbb8bc6d699
UNCERTAINTY=data/multi_uncertainty/forecasts/c0a759479365bb0ee8676b355926ab2fdbd4a84bdca0d496d41c07189a471f2d
SIMULATION=data/simulations/0a4dceb30cd0fba3c4ef50c8f09b4c89e74eeb3a4b3704dc70baa69ac5029a62
EVALUATION=data/simulation_evaluations/36a266e775e124a6d36bfb813e0aedf364c200a394a82d9b25e0b48a75902c3f
PLAN=data/transfer_paths/0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8

$PY -m fpl_ai simulate freeze --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL" --count 16384 --seed 1729
$PY -m fpl_ai simulate verify --simulation-dir "$SIMULATION" \
  --uncertainty-dir "$UNCERTAINTY" --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL"
$PY -m fpl_ai simulate evaluate --simulation-dir "$SIMULATION" --plan-dir "$PLAN" \
  --uncertainty-dir "$UNCERTAINTY" --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL"
$PY -m fpl_ai simulate verify-evaluation --evaluation-dir "$EVALUATION" \
  --simulation-dir "$SIMULATION" --plan-dir "$PLAN" --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL"
PYTHONPATH=. $PY scripts/verify_joint_simulation.py \
  --simulation-dir "$SIMULATION" --evaluation-dir "$EVALUATION"
# The same independent audit also runs with $PY -O and a separate --report path.
PYTHONPATH=. $PY scripts/profile_joint_simulation.py
```

`freeze` reuses an existing matching run in its output root. A fresh root creates a
new actual-clock prospective publication and is disallowed after the bound deadline.
Use `simulate replay --simulation-dir ... --artifact-dir ...` with the same source
arguments for a verified copy retaining the original attestation. Source directory
overrides accept copies of the pinned identities, not arbitrary new calibration.

## Verification evidence

- **20 focused M5D tests and 299 full tests pass normally and under `python -O`.**
- The [independent M5D audit](M5D_VERIFICATION.json) is byte-identical across modes
  (SHA-256 `8d92dd2cc3324687eda28843374c277325c053ad544de15424b9cbf552e52a62`).
  It separately reconstructs historical joins and complete donor windows, every
  scenario and donor-index trace, every scalar scenario plan return, paired and
  tail metrics, prefix convergence and declared dependence moments.
- Known positive/negative horizon dependence, shared GW shocks, donor-specific
  persistence and independent behaviour pass deterministic synthetic tests.
- [Real lifecycle evidence](M5D_LIFECYCLE.json) proves fresh build, reuse,
  evaluation reuse, independent publication/evaluation replay and rehashed
  corruption rejection. Changing both seed and simulation key while retaining
  stale scenarios fails `simulation deterministic replay mismatch`.
- Fresh actual-clock publication
  `92d0f90a2a8fbd753d61e019bc305fcfc2e0f780353ab5d8503e40b32d9fd800`
  shares the original simulation key and **every product hash**, but correctly
  has a distinct timestamped publication identity. It started at
  `2026-09-23T10:29:53.272213Z`; computation completed at
  `2026-09-23T10:30:07.794542Z`; final verification completed by
  `2026-09-23T10:30:38.091611Z`, before the original deadline. This temporary
  fresh-build fixture was cleaned up; its full manifest is retained in the
  lifecycle report and the identical products remain in the primary artifact.
- Offline replay preserves original identity; reuse preserves bytes and nanosecond
  mtimes. Missing/corrupt upstreams, rehashed calibration changes, invalid keys and
  horizons, unavailable donors, stale hashes and deadline/clock reversals fail.
- M5B's historical/model/plan audit and **22-case/82-path exhaustive oracle**,
  plus M5C's independent verification, reproduce accepted reports byte-for-byte
  in both modes. No solver proof or tie semantics are weakened.
- A preservation check confirms **all 1,015 pre-batch evidence files**, including
  **965 data files**, retain SHA-256 bytes and nanosecond mtimes.
- [Final regression evidence](M5D_REGRESSION.json) records successful M2 five-season
  offline rebuilds, M3 reconstruction and retained M4E verification, compilation,
  dependency/CLI checks, unchanged upstream implementation and final preservation.
- [Acceptance summary](M5D_ACCEPTANCE.json) binds all reports, mode comparisons,
  convergence maxima, source hashes and the final preservation/whitespace checks.
  All 20 implementation criteria are met; genuine prospective quality remains pending.

## Limits and next batch

One consumed season, overlapping windows, complete-window selection, exchangeable
donor assignment, production refit drift and unmodelled football/team/match
structure limit interpretation. Block means also mix donor composition and forecast
bias; they do not identify causal Gameweek shocks. There is no independent prospective calibration
or proven risk-aware decision utility. No current result has been used to choose
a dependency model. Simulation does not make a new optimisation objective safe.

Recommend a **personalised FPL decision workflow** next: explicit real squad and
prices/FT state, state freshness checks, legal alternatives and transparent paired
comparisons, alongside fixed-contract prospective retention and settlement. Defer
production stochastic/risk-aware optimisation until prospective evidence and an
explicit user utility contract justify it. No commit, merge or push was performed.
