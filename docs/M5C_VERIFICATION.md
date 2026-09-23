# M5C — Prospective multi-GW scoring and frozen uncertainty

M5C is implemented and verified within its fixed empirical-interval scope.
**279 tests pass normally and under optimized Python**, including 18 focused M5C
tests. The accepted M5B models, forecasts, ranking implementation and decisions
are unchanged. No commit, merge or push was performed.

## Architecture and evidence

`fpl_ai/multi_uncertainty.py` reconstructs prior residuals, freezes calibration,
attaches intervals and replays the resulting forecast. `fpl_ai/multi_outcomes.py`
settles one target independently and builds immutable reports over explicit evidence
sets. The existing artifact publisher has four additional closed families:

| Directory under `data/multi_uncertainty/` | Family | Products |
| --- | --- | --- |
| `calibrations/<identity>` | `multi-uncertainty-calibration` | contract, source identities/hashes/fits, keyed residuals/exclusions, quantiles/counts |
| `forecasts/<identity>` | `multi-uncertainty-forecast` | exact original projection archive, unchanged points with marginal/cumulative intervals, runtime/provenance manifest |
| `settlements/<identity>` | `multi-target-settlement` | raw bootstrap, fixtures, target live response; identity/state/timing contract |
| `scores/<identity>` | `multi-uncertainty-score` | scored rows, cumulative eligibility/outcomes, fixed metrics and source references |

Calibration and score publication is deterministic and content-addressed. Reuse
verifies rather than rewrites. A new current freeze records actual runtime timestamps
and therefore receives a new identity; offline verification preserves the original
attestation. New publication has start, completion and final pre-deadline gates.
There is no timestamp CLI override. Local timestamps are not external attestations.

[Machine verification](M5C_VERIFICATION.json), [regression/preservation](M5C_REGRESSION.json),
[actual live observation](M5C_LIVE.json), and [planner profile](M5C_PROFILE.json)
record the executed evidence. Decisions 053–056 define the contracts.

## Exact historical calibration population

Only the accepted **2025/26 historical OOS predictions** supply residuals. Their
M5B evaluation pipelines fit 2021/22–2024/25. M5C never retrains them or the separate
production pipelines, which already fit all five prior seasons. Each target joins
to the exact M3 label at original as-of GW plus horizon and original player ID.
The latest calibration label settled **2026-05-25 10:23 UTC**, before the fixed
**2026-07-01** information cutoff and every supported operational state.

| Source | Exact identity |
| --- | --- |
| M3 | `57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a` |
| M5B models/predictions | `b0e9cf270c6524278ddb6c288c393aef580159c2a36a02b9a01e81cfadf4235b` |
| M5B separate historical outcomes | `15330198b278c5b82eca1b756d46236ac998a573ce755022957c89d0c7394c4f` |
| Frozen M5C calibration | `782bf10333f482f4ff2a1e19a2c438c4bc9d04b27b237779b1e71dbb8bc6d699` |

All **139,857** marginal residual rows are retained with keys, positions, point
forecasts, labels, availability times and exclusion fields. Original source
manifest/artifact hashes and historical/production fitting evidence are recorded.
Verification reconstructs the population and quantiles from these exact sources;
rehashed semantic corruption also fails. No current-season label can enter this API.

## Interval methodology

For sorted signed residuals `r = outcome - point forecast`, an interval at nominal
level L uses 1-based order statistics `floor((n+1)*(1-L)/2)` and
`ceil((n+1)*(1+L)/2)`, added to the unchanged point forecast. Levels are fixed at
50%, 80%, 90%, inclusive at both ends. There is no Gaussian assumption,
interpolation, rounding, clipping or adjustment of the point estimate.

For example, GW+0's nominal 80% interval is **forecast − 1.610682 to forecast +
1.345170 points**. It describes a range for future realised FPL points using the
historical residual distribution. It does not mean this particular player's
outcome has a verified 80% conditional probability of falling inside it.

| Pool | Labelled windows | As-of GWs | 80% width | 90% width |
| --- | ---: | ---: | ---: | ---: |
| GW+0 | 29,645 | 38 | 2.955853 | 5.975721 |
| GW+1 | 28,805 | 37 | 3.261896 | 6.202923 |
| GW+2 | 27,967 | 36 | 3.400752 | 6.386118 |
| GW+3 | 27,135 | 35 | 3.461403 | 6.437373 |
| GW+4 | 26,305 | 34 | 3.523229 | 6.520569 |
| Cumulative 3 | 27,967 | 36 | 8.205303 | 12.985954 |
| Cumulative 5 | 26,305 | 34 | 12.601393 | 19.037216 |

Position counts were inspected (smallest operational pool/position: 2,894 rows).
The fixed choice is horizon-only, avoiding coverage-driven selection of buckets.
It has no hidden position fallback; every row names the all-position pool and its
sample size. Pools below 100 labelled rows return unavailable intervals with a
reason, never another horizon's quantiles. Position diagnostics remain available.
These are broad population intervals: two players with the same point forecast
and horizon receive the same uncertainty offsets, even if their rotation risks differ.

Cumulative pools directly calibrate `sum(outcomes)-sum(original forecasts)` within
complete same-state windows. They do not sum marginal endpoints or assume independent
GWs. Three-GW windows exclude 1,678 season-end rows; five-GW windows exclude 3,340.
No additional missing-label exclusion occurs in the accepted 2025/26 calibration
population. Synthetic tests verify missing-label and short-horizon handling.

2025/26 is **consumed calibration evidence, not independent validation**. Reusing
its residuals yields roughly nominal empirical coverage by construction (ties can
increase it, particularly at 50%). Dependence among players, overlapping windows,
season drift and production refitting prevent a distribution-free coverage guarantee.
M5C provides empirical/conformal-style order statistics, not proven conditional
calibration or a parametric joint outcome distribution.

## Prospective settlement and accumulation

One target GW is adapted to the existing `prospective-settlement-v2` validator.
It requires the original target deadline, official endpoint capture times,
bootstrap `finished` and `data_checked`, all target fixtures finished, and live
minutes/points reconciling to fixture explanations. The full original forecast
player population needs explicit evidence. Missing players reject settlement;
they are never zero-filled. A valid full-season schedule with no target fixtures
produces null outcomes. Doubles preserve their full target totals. Deadline
revisions fail closed for investigation instead of silently changing the contract.

Each settlement binds the original projection bytes and state, target and horizon,
raw hashes and sequential request/receipt timestamps. Later uncompleted targets
never block an earlier legally completed target. The forecast stays immutable.

Scores report per-target, aggregate, horizon, position and horizon-position MAE,
RMSE, within-projection/GW Spearman, distributions, row/missing counts, interval
coverage, average width, signed deviation and under/overcoverage. Cumulative scores
require every labelled outcome in the same original 3/5-GW window. Reports list
unsettled targets and cumulative unscorable reasons.

Repeated identical input pairs are deduplicated. Competing settlements or uncertainty
versions for the same projection/target fail. Different projections of one target
remain different forecasts, with one distinct actual target counted separately;
conflicting realised values across projections fail. This prevents treating
repeated evidence as additional data without erasing valid forecast-horizon comparisons.

Fewer than 100 scored rows or five labelled target GWs triggers `small_sample`.
This threshold is descriptive, not a significance test or permission to declare
calibration after five GWs. Scoring cannot change calibration, models, levels,
segmentation or the optimiser. Recalibration needs an explicit new version/batch.

## Actual 2026/27 lifecycle and operator commands

The original early-state projection is
`03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b`:
659 players × GW6–10, September 18 capture and September 21 computation. Its M5C
uncertainty publication completed **2026-09-23 08:57:50.871098 UTC**, before GW6's
**October 10 10:00 UTC** deadline. It is early-state evidence, not near-deadline
confirmation. There was no reason to claim a nearer-deadline state on September 23.

An actual official bootstrap/fixture observation completed at **09:01:36 UTC on
September 23**. GW6–10 were unfinished/unchecked; GW5 was finished/checked. Raw
responses, hashes and request/receipt times are retained. M5C's real GW6 settlement
command fails with `target deadline has not passed`. There are **zero real settled
M5C targets and zero scored player rows**. The real pending report is
`502730c1d0de9f5b29c3786e58e2d058134e8e70e19cc937d3d50b6cb49a6053`.
No current M5C outcome or calibration-quality claim is fabricated.

```bash
export LOKY_MAX_CPU_COUNT=1
PY=.venv/bin/python
M4E=data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230
PROJECTION=data/multi_projection/forecasts/03a9f348378b8ad61a8eea3c58424fdb7bf689f5c1da46707c03e54c35f1427b
CALIBRATION=data/multi_uncertainty/calibrations/782bf10333f482f4ff2a1e19a2c438c4bc9d04b27b237779b1e71dbb8bc6d699
UNCERTAINTY=data/multi_uncertainty/forecasts/c0a759479365bb0ee8676b355926ab2fdbd4a84bdca0d496d41c07189a471f2d

$PY -m fpl_ai uncertainty calibrate   # verifies/reuses the exact fixed product
$PY -m fpl_ai uncertainty verify --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E"
# Only before the original first deadline; new actual-clock publication:
$PY -m fpl_ai uncertainty freeze --projections-dir "$PROJECTION" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E"
# Explicit zero-outcome/pending report:
$PY -m fpl_ai uncertainty score --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E"

# NEXT LEGAL STAGE: only once GW6 is authoritatively complete and checked:
$PY -m fpl_ai uncertainty settle --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E" --gameweek 6
# Set GW6_SETTLEMENT to the immutable directory printed by that successful command.
$PY -m fpl_ai uncertainty score --calibration-dir "$CALIBRATION" \
  --m4e-model-dir "$M4E" --settlement-pair "$UNCERTAINTY" "$GW6_SETTLEMENT"
# Later add --settlement-pair "$UNCERTAINTY" "$GW7_SETTLEMENT", etc.
```

The model/history/M3 defaults are the exact pinned products listed above. Optional
path overrides support copies of those identities, not source/model reselection.
Retain original uncertainty artifacts when adding evidence; re-running `freeze`
creates another runtime attestation, not a score update. Source artifacts remain
necessary for strict full reconstruction.

## Independent verification and regression

`scripts/verify_multi_uncertainty.py` separately joins saved M5B predictions to M3
CSVs, reconstructs all signed residuals, computes order statistics with integer
arithmetic, and checks complete-window eligibility. The synthetic lifecycle runs
production calibration, publication, settlement and scoring with explicitly mocked
upstream evidence/clock; the independent audit sums raw fixture explanation points
and separately recomputes errors, SciPy rank correlations, coverage and widths.
It checks every accumulation stage through five targets, explicit zero and blank,
all report breakdowns, duplicate reuse and frozen calibration/forecast hashes/mtimes.
This is deterministic lifecycle proof, not real prospective performance evidence.

```bash
$PY -m unittest tests.test_multi_uncertainty -v
$PY -O -m unittest tests.test_multi_uncertainty -v
$PY -m unittest discover -v
$PY -O -m unittest discover -v
PYTHONPATH=. $PY scripts/verify_multi_uncertainty.py \
  --calibration-dir "$CALIBRATION" --uncertainty-dir "$UNCERTAINTY"
PYTHONPATH=. $PY -O scripts/verify_multi_uncertainty.py \
  --calibration-dir "$CALIBRATION" --uncertainty-dir "$UNCERTAINTY" \
  --report /tmp/m5c-verification-optimized.json
PYTHONPATH=. $PY scripts/profile_multi_planner.py
PYTHONPATH=. $PY scripts/verify_multi_gameweek.py --projections-dir "$PROJECTION" \
  --plan-dir data/transfer_paths/0df6760a8e32dd269d381c1a7298769522900520f841e8d3b2e5c848398f1bd8 \
  --report /tmp/m5c-m5b.json
PYTHONPATH=. $PY scripts/verify_multi_oracle.py --report /tmp/m5c-oracle.json
# Both preceding commands also ran under -O, with separate report paths.
PYTHONPATH=. $PY scripts/verify_uncertainty_regression.py --before /tmp/m5c-before.json
```

The regression record includes exact executed prior M5B audit/oracle and M2/M3/M4E
commands, log hashes and results. M5B normal/optimized reports and exhaustive
22-case/82-path oracle reproduce the accepted reports byte-for-byte. All 951
pre-batch data files retain SHA-256 bytes and nanosecond mtimes. No dependency,
accepted model, projection, optimiser or prior acceptance-evidence file changed.
Compilation, dependency checks, CLI help and tracked/new-file whitespace checks pass.

## Runtime and remaining limits

The representative full-population five-GW top-three run took **110.84 seconds**,
including verification, greedy and publication; **110.02s** was inside 29 MILP calls.
Top-three primary search used 3 calls/20.98s, count proof 6/63.30s and tie enumeration
3/22.61s. Greedy used 17 calls/3.13s. No binary-block fallback occurred in this case.
All regenerated decision bytes matched M5B. Count proof dominates; no production
performance change was justified. Full populations, exact ranking and zero solver
gap remain intact.

There is no automatic scheduling, deadline-revision reconciliation, outcome-version
selection, player-conditional calibration or prospective quality claim. Frozen
source re-verification costs more than simply reading cached bounds. Historical
players/windows are dependent, and the operational refit differs from evaluation
fits. Missing future registrations remain unscorable, not invented observations.
Real GW6–10 settlement awaits authoritative future evidence, not more code.

The keyed historical residuals preserve cross-horizon alignment for future research.
They do not specify a joint law across players, fixtures or GWs, and interval widths
are not standard deviations. A later Monte Carlo/risk-aware batch must address those
dependencies and evaluate prospective utility explicitly. M5B still optimises its
unchanged expected-points objective; M5C supplies no risk penalty.
