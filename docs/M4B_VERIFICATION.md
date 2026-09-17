# M4B — Playing-time evidence, expected minutes and prospective evaluation

Verified 2026-09-17. The original M4 xPts experiment is preserved as a frozen
reference. This batch adds a separate versioned playing-time contract and one
bounded minutes experiment. It does not select against 2025/26, refit M4, produce
stacked xPts training features, or add an optimiser.

## Evidence and scope

Inspected the project vision, roadmap, state, decisions, M3/M4 verification,
historical source/schema/settlement/ingestion code, features, experiment publication
and temporal/freezing tests before implementation. No M2/M3 transformation or
published contract was changed. Decisions 014 and 032 remain authoritative.

[Machine source audit](M4B_SOURCE_AUDIT.json) records every candidate's classification,
raw field types, exact accepted capture paths/hashes/times, settlement paths/hashes,
source/build identities and observed disagreements. The model-development audit
covers 2021/22–2023/24. 2024/25 was inspected for source evidence only; it has no new
minutes predictions or metrics. 2025/26 was not opened by the new minutes pipeline.
Unchanged historical/M3/M4 regression replays still cover their original seasons.

| Candidate | Conclusion |
| --- | --- |
| Cumulative minutes | Directly observable in accepted bootstrap captures. GW1 values are stale prior-season totals and are excluded from current-season predictors. |
| Cumulative starts | Directly observable when present. Entirely absent in 2021/22; 9,301 missing raw player observations in 2022/23; complete in 2023/24. GW1 excluded. |
| Previous/rolling GW minutes | Accepted only after independently selected settlement and exact agreement between observed cumulative change and canonical fixture-minute sum. |
| Appearance history | Derive `minutes > 0` from those evidenced earlier GW totals. This means appearance in a GW, not number of fixture appearances or starts. |
| Status / chance next round | Direct accepted-capture observations; retain nulls. Consecutive observed states support changes without final identity joins. |
| Consecutive cumulative changes | Observable differences, but cannot be labelled GW minutes without settlement and reconciliation. |
| Chance this round / news timestamp | Observable, but omitted: no extra current/next-event interpretation or news model. |
| Form / minutes per game / starts per 90 | Form aggregation not independently specified; minutes per game absent; starts per 90 partial and redundant. Not selected. |
| Historical fixture schedule / opponent / home-away / kickoff / count / difficulty | Unavailable as deadline features. No fixture snapshots found in the complete pinned fplcache tree (9,867 entries, not truncated) or accepted bootstrap payloads. Final Vaastav fixtures remain post-event only. |
| Vaastav quarantine / xP / FPL ep_next | No engineered inputs. Existing restrictions unchanged. |

GW1 has 372, 396 and 400 nonzero stale cumulative-minute observations in the three
development seasons. For GW1 targets, the *post-reset settled* cumulative total is
checked against the full GW1 fixture sum. No stale opening cumulative value is
subtracted and no fictitious observed starting zero is claimed. For later target
GWs, subtract that GW's accepted pre-deadline cumulative observation from its
independently selected settled cumulative observation. Settlement requires the
existing `finished`/`data_checked` evidence, occurs after the target deadline and
before the next GW deadline, and every result must equal the canonical target sum.
Missing player/minute evidence, non-integers (including booleans) and discrepancies
fail; no-fact players require explicit matching zero differences. This extends
Decision 032 through separate evidence, not the assumption that all final statistics
were available once points settled. Existing points evidence checks also still run.

All three development seasons' settled cumulative totals agree with canonical
season-to-date fixture sums. The additional 2024/25 audit finds **element 123, GW27**:
observed cumulative change **34 minutes**, canonical fixture sum **17**. The
cumulative discrepancy remains +17 through GW38 (12 cumulative disagreements).
No source was corrected or alternative settlement selected to fit the desired
value. 2024/25 is not admitted to this v1 minutes build. It was already used in M4
and could not be called a new untouched holdout even if this discrepancy were resolved.

## Fixture-evidence hardening (Decision 041)

The initial implementation had two evidence gaps: an empty full-season current
fixture response could masquerade as a blank target GW, and historical target
classification plus the verifier derived fixture-bearing GWs from player facts.
The checks below supersede those behaviours; the modelling problem is unchanged.

Prospective validation extends the existing current-fixture minimum schema through
`validation.validate_fixture_schedule`. It requires a nonempty array, object rows
with the existing required fixture fields plus explicit `event`, unique positive
fixture IDs, valid distinct integer team references, boolean `finished`, valid
nullable kickoff timestamps, and known integer event assignments or explicit null.
At least one fixture must have an event assignment. Missing/empty evidence,
malformed rows and unusable all-unassigned schedules fail distinctly. No fixed
380-fixture assumption is added. Ordinary ingestion can still accept an empty
between-season response; the forecast/settlement evidence boundary cannot.

A valid nonempty schedule can have no fixtures assigned to the target GW, preserving
genuine blanks. This requirement runs at capture, snapshot read, settlement capture
and settlement read/scoring, including checksum-valid but semantically invalid
bundles. No blank settlement or score is published from an empty schedule.

Historical `playing-time-v2` uses the published processed **`fixtures.csv`** as the
independent post-event source of fixture-bearing GWs. It requires valid season/GW /
fixture identities, exact fact-to-schedule fixture/GW agreement, and football-player
facts for **every** scheduled fixture. Losing an entire ordinary GW or one fixture
of a double is a hard failure. An individual player's absent facts still yield zero
only with the unchanged explicit settlement evidence. No fixture row is fabricated.
The exact consumed `fixtures.csv` hash now enters `sources.json` and artifact identity.

The verifier separately reads that schedule, reconciles fact fixture coverage and
assignments, verifies its consumed checksum and reports schedule-supported blanks.
It does not call production reconciliation or derive fixture-bearing GWs from facts.
It checks **1,140 scheduled fixtures** across the three seasons; only 2022/23 GW7 is
blank, retaining all **624 null-target rows**. Schedule context is **label/evidence
validation only** and never enters the feature projection or model matrix.

Contract/identity transitions:

- `playing-time-v1` → `playing-time-v2`; initial feature artifact
  `fa3ddcc5fc3051aaad99e25da55e17b35801e69579cbaf37d4280c7e79b68af8` →
  `4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c`.
- Minutes freeze `802d25d83db3cf5ad0c38d8a036d9b035cda436eb6ac3251c2c2c72cb81cb169` →
  `e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc`, because its
  embedded contract and upstream feature identity changed. Model specification,
  saved model bytes, predictions and all development metrics are exactly unchanged.
- `prospective-fixtures-v2` and `prospective-settlement-v2` bind positive schedule
  evidence. Forecast identities also bind the new embedded feature contract.
  Older contracts are rejected by current readers rather than silently reinterpreted.

All original feature/label/audit CSVs are byte-identical. All prior immutable artifact
directories remain untouched; there is no in-place migration. This is not retuning.

Six new regression tests exercise the evidence contracts: empty current schedules
at capture/settlement/scoring, ten malformed/unusable schedule cases, a removed whole
historical GW, a missing double fixture, a schedule-supported GW7 blank with explicit
player zeros, and independent-verifier detection of a fact-derived false blank.
The existing prospective blank lifecycle now uses a valid nonempty schedule with
fixtures assigned to another GW. Normal and optimized suites both pass 176 tests.

Current fixture validation establishes structural schedule evidence; it cannot detect
a server response that silently omits rows while remaining structurally plausible.
No authoritative live completeness count is available in the existing contract, so
none is guessed. Live 2026/27 smoke testing/retention remains next work.

## Feature contract

`playing-time-v2` has **11 values plus 9 explicit missingness flags (20 inputs)**:

| Feature | Definition / boundary |
| --- | --- |
| `position`, `status`, `chance` | Raw accepted snapshot position, status, chance of playing next round. Position must be football 1–4. |
| `previous_minutes` | Previous calendar GW's evidenced total, only if settled at or before this capture. |
| `minutes_mean_3`, `minutes_count_3` | Mean and observed count over previous three calendar GWs; missing observations excluded, not replaced with zero. |
| `appearance_rate_3` | Fraction of those observed GWs with minutes > 0. Null with no observations. |
| `observed_season_minutes`, `observed_season_starts` | Exact accepted cumulative observations after GW1; GW1 null because prior-season meaning is unsafe. |
| `status_changed` | 0/1 comparison with immediately preceding GW's accepted status for the same season/element. Null if either side absent. |
| `chance_change` | Current minus previous accepted chance, in percentage points. Null if either side absent. |

Every value except mandatory position and the observation count has a corresponding
`_missing` flag. Season-local identity resets each season; no final person/team or
cross-season identity backfill. Team numbers, price, points, transfers, opaque
forecasts and final fixture context are not inputs to this compact minutes model.
Historical rows retain original M3 audit fields including observed person codes,
source path/hash, label status and full GW18 freshness metadata. The 2021/22 GW18
exception remains **12:33 state / superseded 13:30 payload deadline / authoritative
16:00 deadline / 207-minute age**, for all 656 rows.

Products live in `data/playing_time/<identity>/`: `features.csv`, `labels.csv`,
`row_audit.csv`, `contract.json`, `evidence.json`, `sources.json`, `manifest.json`.
Feature and target files are separate. Exact serialized hashes, contracts and raw
provenance identify the bundle; no build timestamp or local path enters identity.

Feature identity:
`4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c`.

## Expected-minutes v1

Target is **total realised minutes in the target GW**, summing every target-GW
fixture. Doubles may exceed 90; there is no upper prediction cap. A registered
nonplayer has an evidenced zero. Globally fixture-empty 2022/23 GW7 retains its
624 prediction rows with null targets and does not enter fitting, history or metrics.

Train: **2021/22–2022/23**, **50,724 labelled rows** (51,348 total).
Development/selection: **2023/24**, **29,510 rows**.
Latest training settlement: **2023-05-29 06:23 UTC**.
First development capture: **2023-08-11 12:31 UTC**.
No 2024/25 or 2025/26 selection, calibration, threshold fitting or performance check.
The training fit is not refreshed during development. Earlier independently settled
observations can update a player's feature history without refitting the model.

Before scoring, fixed three baselines and one sklearn candidate:

- Training position mean, with overall training mean fallback.
- Recent three-calendar-GW observed minutes, falling back to that training mean.
- Availability-aware recent minutes: multiply by observed chance/100 only when
  chance exists; otherwise leave the recent baseline unadjusted. This is a declared
  baseline rule, not conversion of a missing observation to “healthy”.
- One squared-error histogram gradient booster: 15 leaves, 150 iterations, rate
  .05, minimum leaf 50, L2 10, seed 1729, no early stopping. No search grid.

Preprocessing is fitted only on training rows: median numerical fills, all-null
computational fill zero with original missingness retained, and one-hot position /
status with unknown categories ignored. Forecasts are lower-bounded at zero;
nonfinite raw model outputs fail before bounding. There is no fixture-count scaling
or upper clip. Overall development RMSE selects the winner, with name tie-breaking.

| Approach | Development MAE | Development RMSE | Rows |
| --- | ---: | ---: | ---: |
| Training position mean | 35.231586 | 39.024999 | 29,510 |
| Recent minutes | 13.758681 | 27.010578 | 29,510 |
| Availability-aware recent | 12.302370 | 25.346981 | 29,510 |
| **hist_15** | **12.659552** | **23.292082** | **29,510** |

The model improves RMSE but **does not beat the availability-aware baseline on MAE**.
This is a development result, not untouched confirmation evidence. Forecast range:
0–105.3973 minutes; target range across the three seasons: 0–180.

| Segment | Rows | Model MAE | Model RMSE | Availability baseline RMSE |
| --- | ---: | ---: | ---: | ---: |
| Actual appearance (target > 0; diagnostic only) | 11,073 | 22.154692 | 30.754754 | 35.242576 |
| Useful history (pre-capture three-GW mean >= 60) | 6,731 | 20.711570 | 31.336580 | 33.602790 |
| No observed recent history | 861 | 28.514627 | 33.810157 | 35.817208 |
| Missing chance | 9,995 | 14.369293 | 24.131959 | 25.554056 |

Segments overlap. The fixed 60-minute diagnostic is not a tuned player-selection
threshold. Position metrics, full precision scores and all baselines are in
[M4B_VERIFICATION.json](M4B_VERIFICATION.json).

Minutes freeze identity:
`e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc`.
`frozen.json`, `development.json`, development-only `predictions.csv`, the fitted
`model.pickle` and manifest are published atomically. The fitted state and all
baseline means are frozen. Only trusted locally produced model files may be loaded.

No training-row predictions are exported and no xPts adapter accepts these minutes
predictions. `downstream_training_allowed: false` is explicit. Future stacking needs
expanding chronological fits, with fitted parameters and model-selection decisions
based only on information available before each row's deadline. Selection using the
whole 2023/24 development season does not retroactively make its forecasts safe
stacked training features. Integration is deliberately deferred.

## Prospective contracts and commands

`prospective capture` uses the current official bootstrap and fixture endpoints.
It checks the season against GW1's authoritative deadline year, a unique upcoming
event, no started/scored target fixtures, and request start/response completion
clocks for both responses. Both must complete before the authoritative target
deadline. The two responses are **not an atomic API snapshot**. Exact JSON hashes,
request intervals and the observed deadline are retained in a separate immutable
snapshot. Fixture IDs, assignment, teams, home/away, kickoff (nullable) and difficulty
are available as observed context; the v1 model does not consume them.

`prospective freeze` loads a checksum-verified snapshot and minutes model, projects
only the feature allowlist, and publishes keys, expected minutes and nullable
expected points with no outcomes. It records prediction start/completion UTC,
season/GW/deadline, source identity and hashes, feature-contract identity, fitted
model/freeze identity and hashes, fixture snapshot identity, and optional history
identities. It checks the real runtime clock again immediately before atomic
publication. There is **no CLI backdating option**. Prediction timestamps are
semantic observations and intentionally enter identity; incidental build timestamps
do not. Existing forecasts can be verified later without re-dating or rewriting.

`--previous-dir` supplies the previous GW's accepted prospective snapshot for
availability changes. Repeated `--history-pair PREDICTION_DIR SETTLEMENT_DIR` supplies
only earlier same-season GWs settled before the current source capture. No stored
history means explicit missing inputs; the first live freezes therefore have a
history warm-up limitation. Unknown minutes/availability never becomes an observed
zero or healthy state. Expected points remains null: the frozen M4 xPts pipeline
has no current-season feature adapter in this batch.

`prospective settle` retrieves bootstrap, fixtures and `event/<GW>/live/` separately
after the deadline. It requires settled event flags, finished target fixtures,
integer explicit player outcomes, full forecast-player coverage and agreement
between live minutes/points and their per-fixture `explain` totals. Doubles sum;
empty-GW outcomes remain null. The entire outcome capture is another immutable
bundle. `prospective score` verifies both inputs, creates separate outcomes/metrics,
and references both identities/checksums. It cannot alter the original freeze.
Missing/corrupt/extra files, wrong contracts, incompatible populations and changed
outcomes fail loudly. Same-identity reuse verifies hashes and preserves mtimes.

```bash
FEATURES=data/playing_time/4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c
MINUTES=data/minutes/e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc
.venv/bin/python -m fpl_ai minutes features
.venv/bin/python -m fpl_ai minutes train --features-dir "$FEATURES"

# Operational examples: use the actual upcoming GW and returned artifact directories.
.venv/bin/python -m fpl_ai prospective capture --season 2026-27 --gameweek GW_NUMBER
.venv/bin/python -m fpl_ai prospective freeze --snapshot-dir SNAPSHOT_DIR --model-dir "$MINUTES"
.venv/bin/python -m fpl_ai prospective verify --prediction-dir PREDICTION_DIR
# After settlement:
.venv/bin/python -m fpl_ai prospective settle --prediction-dir PREDICTION_DIR
.venv/bin/python -m fpl_ai prospective score --prediction-dir PREDICTION_DIR --settlement-dir SETTLEMENT_DIR
```

These operational examples were **not run against the live 2026/27 endpoints**.
The complete capture→freeze→settle→score lifecycle is verified with deterministic
network-free doubles, blanks, missingness, corruption, timing and history fixtures.
No actual 2026/27 clean confirmation result or live schema compatibility is claimed.
Local clock evidence is not an externally witnessed signature. Capture and retain
real pre-deadline artifacts from now on to accumulate new confirmation data.

## Verification and regression

[Verification JSON](M4B_VERIFICATION.json) independently checks **80,858 feature rows**,
**80,234 targets**, **3,784 explicit no-fact zeros**, **4,705 multi-fixture rows**,
**624 fixture-empty rows**, and **656 GW18 freshness rows**, directly against raw
captures and canonical fixture minutes. It rechecks availability/cumulative state,
recent-window means/counts, checksums, exact feature/model rebuilds, reuse and cleanup.

176 automated tests pass: 145 original tests, 25 initial M4B tests and 6 hardening regressions. New coverage includes target /
future mutations, delayed settlement, strict earlier-GW history, missingness,
doubles/blanks, stale GW1, availability identity, forbidden fields, target evidence,
train-only fits, split rejection, category compatibility, nonfinite outputs,
closed artifact sets, future/late captures, publication failure cleanup, settled
fixture explanations, missing players, scoring immutability and prospective history.
All 176 also pass under `python -O`; explicit verification guards remain active.

Fresh M4B feature/model/prediction/metric files reproduce exactly. Normal and optimized
real-data verification reports are identical. All five historical seasons pass the
existing offline rebuild/audit; M3 reproduces all 137,662 rows; the original M4
validation fit and frozen holdout replay remain byte/checksum compatible. The original batch preserved 179 pre-batch files. The focused hardening additionally
fingerprints and preserves all 638 pre-existing data files, including historical raw
sources and prior M4B artifacts, in bytes and mtimes. See [regression record](M4B_REGRESSION.json).

Executed commands include:

```bash
export LOKY_MAX_CPU_COUNT=1
.venv/bin/python -m unittest discover -v
.venv/bin/python -O -m unittest discover
PYTHONPATH=. .venv/bin/python scripts/verify_minutes.py --features-dir "$FEATURES" --model-dir "$MINUTES" --report docs/M4B_VERIFICATION.json --source-report docs/M4B_SOURCE_AUDIT.json
PYTHONPATH=. .venv/bin/python -O scripts/verify_minutes.py --features-dir "$FEATURES" --model-dir "$MINUTES" --report /tmp/m4bh-verify-O.json
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/m4bh-historical.json
PYTHONPATH=. .venv/bin/python scripts/verify_modelling.py --report /tmp/m4bh-m3.json
PYTHONPATH=. .venv/bin/python scripts/verify_experiments.py --m3-dir data/modelling/57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a --frozen-dir data/experiments/09eb67bd0fc9198073c28f921e3ba0ffd67876f341d32a97dc0f76743e0d411c --holdout-dir data/experiment_holdouts/21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd --report /tmp/m4bh-m4.json
.venv/bin/python -m compileall -q fpl_ai scripts tests main.py
.venv/bin/python -m pip check
.venv/bin/python -m fpl_ai minutes --help
.venv/bin/python -m fpl_ai prospective --help
git diff --check
```

All scoped acceptance criteria pass. Optional stacked xPts, additional 2024/25
performance reporting and live confirmation are not claimed. No new dependency,
scheduler, hosted service, optimisation, transfer/captaincy system, commit or push.

## Limitations and next batch

Missing historical fixture schedules prevent opportunity-aware blank/double
forecasts. Starts are unevenly available and cumulative; v1 does not estimate start
probabilities or match-level rotations. Registered-player zeros dominate metrics;
useful-player and appearance errors remain substantial. Development improvement
does not establish future calibration or product decision value. The first live
forecasts lack prior prospective history, and the live endpoint contract still
needs an operational smoke test. The 2024/25 minutes discrepancy blocks an honest
complete comparable historical check until independently resolved.

Next substantial batch: operate the 2026/27 capture/freeze/settle workflow, retain
real prospective evidence, and implement a separately versioned chronological
out-of-sample minutes prediction artifact for xPts v2. Include training-label,
model-selection and prediction-availability cutoffs for every row; then compare a
bounded xPts integration on earlier-season development only. Investigate the
2024/25 source discrepancy without changing accepted sources or treating 2025/26
as fresh confirmation. Optimisation remains downstream of these checks.
