# M4C — Chronological OOS minutes and live prospective validation

Verified 2026-09-18. M4C's in-run acceptance criteria pass, including the conditional
live requirement: a real forecast exists; its event is not settled, so no live score
is claimed. No commit or merge was performed. Evidence files are prepared in the
working tree. No xPts v2, optimiser, scheduler, service or new dependency was added.

## Architecture and exact protocol

`fpl_ai/minutes_oos.py` adds `chronological-minutes-oos-v1`, a separate artifact family,
annual refits, a narrowly bound minutes-evidence policy and `load_downstream`.
`minutes.py` exposes its unchanged train-only fitter; `playing_time.py` shares the
existing raw/settlement/schedule validation with a separate explicit policy callback.
Their M4B entry points, contracts and outputs retain the old defaults and identities.
`experiment_io.py` adds two closed artifact sets. `cli.py` adds `minutes oos`.
New focused tests and two scripts independently investigate and verify the work.
README, project state, roadmap and Decisions 042–043 describe the resulting boundary.

The bounded M4B candidates/features/hyperparameters remain fixed. Its selection used
2023/24 development evidence, available through **2024-05-20 06:25 UTC**. That is the
selection information cutoff for both OOS folds. All earlier development/fitting
rows remain unavailable: a retrospectively selected 2023/24 forecast is not OOS.
2024/25 is the earliest legitimate season under this retained selection history.

| Forecast season | Expanding fit seasons | Fit labels | Latest fitting label (UTC) | First forecast capture (UTC) |
| --- | --- | ---: | --- | --- |
| 2024/25 | 2021/22–2023/24 | 80,234 | 2024-05-20 06:25 | 2024-08-16 12:38 |
| 2025/26 | 2021/22–2024/25 | 107,392 | 2025-05-26 02:06 | 2025-08-15 12:52 |

Refit the selected `hist_15` **once before the first capture of each forecast season**.
Fit numeric imputation, categorical encoding, model parameters, position means and
overall fallbacks exclusively on that population. Require every fitting label and
feature capture, plus the full prior selection cutoff, strictly earlier than the
first forecast capture. Every individual forecast also proves these cutoffs strictly
precede its capture, which strictly precedes its authoritative deadline.
No within-season refit or re-selection. Only explicitly evidenced, already-settled,
earlier-GW observations update recent player history. Blank GWs never become zero.

These are reconstructed historical information cutoffs, **not fabricated timestamps
of actual historical model execution**. Only the separately frozen 2026/27 artifact
is prospective evidence. Neither OOS season is claimed as a new untouched holdout;
2025/26 was already consumed by the frozen M4 points experiment.

## Coverage and outcomes

| Season | Retained keyed rows | Downstream-safe forecasts | Scored minutes outcomes | GWs |
| --- | ---: | ---: | ---: | --- |
| 2021/22 | 25,150 | 0 | — | 1–38 |
| 2022/23 | 26,198 | 0 | — | 1–38 |
| 2023/24 | 29,510 | 0 | — | 1–38 |
| 2024/25 | 27,159 | 27,159 | 27,158 | 1–38 |
| 2025/26 | 29,645 | 29,645 | 29,645 | 1–38 |

Total: **137,662 rows; 56,804 downstream-safe forecasts; 80,858 explicitly unavailable
early rows**. Early predictions are null with `insufficient_prior_selection_history`.
The unresolved Ferguson GW27 minutes outcome is null, not zero. Its pre-GW27 OOS
forecast remains eligible: downstream feature safety is separate from target evidence.
Assistant Managers are excluded by the unchanged football-position population rule.

Prediction rows contain keys, capture, expected minutes, class/eligibility/reason,
model, feature, protocol and historical source identities, cutoffs and exception flags.
Full freshness metadata remains in `row_audit.csv`. `training.csv` records every
fitting key, capture, label-availability time and exact row hash; `folds.json` binds
population hashes, fitted fallback parameters and model identity. Saved per-season
model bytes, complete source evidence, M4B selection manifests and the explicit
protocol complete the closed, checksum-verified prediction bundle. Outcomes and
metrics live in a **separate** `minutes-oos-score` bundle linked to the forecast.

`load_downstream` rejects development/prospective artifact kinds, verifies all files,
contracts, model states, fitting populations and cutoffs, and rederives eligibility.
The immutable producer is trusted local code; hashes are integrity checks, not an
external signature. Only trusted locally produced pickle files may be loaded.
Changing semantic protocol/policy changes identity. Fresh builds reproduce exact
bytes; reuse verifies without writing. Forecast-year outcomes do not enter the
feature identity or predictor projection; a focused test mutates all final-season
labels and proves the prediction bundle stays identical.

## Discrepancy investigation

[Report](M4C_DISCREPANCY.md), [pinned observations](M4C_DISCREPANCY.json).
56 date-selected neighbouring captures identify a later upstream aggregate change:
Ferguson had 287 cumulative minutes while GW27 was already finished/checked, then
304 between March 2 18:29 and March 3 01:52 UTC. Total points also increased by one,
while GW event points stayed unchanged. The accepted before/settled values remain
270 and 304; the canonical fixture remains 17 minutes. No historical live payload
is available in the pinned tree, and cause remains unresolved.

The exact source/hash-bound policy excludes **one target** from fitting, history
and metrics, and masks **11 cumulative-feature values**, GW28–38 for that player.
Later individually reconciled deltas and unrelated evidence remain available.
There is no guessed correction or value-selected replacement settlement. All other
mismatches fail. M4B's earlier season exclusion remains frozen evidence.

Independent checks cover **1,900 scheduled fixtures**, **137,037 reconciled targets**,
**4,553 explicit no-fact player zeros**, **5,476 double rows**, **624 blank GW7 rows**,
and **656 GW18 freshness rows**. Every historical fixture is still post-event
label/evidence context only; it never enters the model matrix. Missingness, GW18's
12:33 state/207-minute age, double-GW sums and current fixture contract v2 remain.

## Walk-forward diagnostics

All values are minutes; the existing three baselines are reported without new tuning.

| Season | Model MAE | Model RMSE | Availability baseline MAE | Availability baseline RMSE |
| --- | ---: | ---: | ---: | ---: |
| 2024/25 | 13.304010 | 22.944441 | 12.603902 | 24.818716 |
| 2025/26 | 12.114528 | 21.776158 | 11.410267 | 23.873513 |

Model RMSE improves; MAE remains worse. Useful-history RMSE is 28.485497 / 28.448476;
actual-appearance RMSE is 28.432179 / 28.296428. Registered-player zeros still weigh
heavily in overall metrics. [Machine evidence](M4C_VERIFICATION.json) reports full
precision metrics for all four approaches, every GW, positions, useful/absent recent
history, actual appearance, missing/known chance, available/other/missing status,
and missing cumulative minutes. Segments overlap; there is no decision-utility claim.

## Real 2026/27 operation

The existing CLI, real official API responses and real runtime clock produced:

- Bootstrap: **659 players, 20 teams**, GW1 deadline August 21 17:30 UTC.
- Full fixture response: **380 fixtures**, structurally accepted under fixture v2.
- Observed GW4: current, finished and data_checked. GW5: unique next event,
  unfinished/unchecked; authoritative deadline **2026-09-18 17:30 UTC**.
- A separate immutable snapshot and **659-row forecast**, completed
  **2026-09-18 08:27:13.598395 UTC**, before that deadline.
- Successful CLI verification without rewriting. Actual CLI settlement attempt
  rejected with `target event not authoritatively settled`; no settlement or score
  bundle was published. A settled earlier GW cannot retroactively get a forecast.

[Live evidence](M4C_LIVE.json) records response intervals, contracts, exact hashes,
event state, feature missingness and immutable identities. Bootstrap/fixtures are
sequential, not atomic. No previous live snapshot or settled forecast history was
available; all recent history and availability-change features are missing. The
frozen M4B model is used for this operational smoke test, not the new annual OOS fits.
Expected points remains null. No model superiority or prospective score is claimed.
Successful live settlement/scoring schema compatibility remains pending its legal stage.

```bash
# Executed with real runtime timestamps; no override:
.venv/bin/python -m fpl_ai --output-dir data/m4c_live_inspection
.venv/bin/python -m fpl_ai prospective capture --season 2026-27 --gameweek 5
SNAPSHOT=data/prospective_snapshots/ffcdc756331c67fa780f2bec92237f28486032416b80a6f843ed6d9161fef0ce
MINUTES=data/minutes/e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc
.venv/bin/python -m fpl_ai prospective freeze --snapshot-dir "$SNAPSHOT" --model-dir "$MINUTES"
PREDICTION=data/prospective_predictions/19622ab3d853222513b977fac4ae6c11d6f8e160ad9dd48f66a064892b078e24
.venv/bin/python -m fpl_ai prospective verify --prediction-dir "$PREDICTION"
# Attempted now and correctly rejected. Re-run only after authoritative settlement:
.venv/bin/python -m fpl_ai prospective settle --prediction-dir "$PREDICTION"
# Then use the actual returned settlement directory (not executed yet):
.venv/bin/python -m fpl_ai prospective score --prediction-dir "$PREDICTION" --settlement-dir RETURNED_SETTLEMENT_DIR
```

The sandbox initially prevented DNS access; the authorized network retry succeeded
with normal certificate verification. No data or clock substitution was used.
Generated raw/live/model artifacts remain ignored; compact evidence is in `docs/`.

## Identities and verification commands

- OOS predictions: `3550ded6a2aff16fa9f799b9c993b8799726d0243a3b1e643e6249af475867be`.
- Separate OOS score: `6b469d61feac7cf9f37f0d222c9587bc840ef848e38d3dfa8013672621b61728`.
- Frozen M4B features: `4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c`.
- Frozen M4B model: `e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc`.

Full per-file SHA-256 manifests and fold/model identities are retained in
[M4C_VERIFICATION.json](M4C_VERIFICATION.json); live hashes in [M4C_LIVE.json](M4C_LIVE.json).

```bash
export LOKY_MAX_CPU_COUNT=1
FEATURES=data/playing_time/4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c
MINUTES=data/minutes/e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc
OOS=data/minutes_oos/3550ded6a2aff16fa9f799b9c993b8799726d0243a3b1e643e6249af475867be
SCORE=data/minutes_oos/scores/6b469d61feac7cf9f37f0d222c9587bc840ef848e38d3dfa8013672621b61728
.venv/bin/python -m fpl_ai minutes oos --features-dir "$FEATURES" --model-dir "$MINUTES"
.venv/bin/python -m unittest discover
.venv/bin/python -O -m unittest discover
PYTHONPATH=. .venv/bin/python scripts/verify_minutes_oos.py --oos-dir "$OOS" --score-dir "$SCORE" --features-dir "$FEATURES" --model-dir "$MINUTES" --report docs/M4C_VERIFICATION.json
PYTHONPATH=. .venv/bin/python -O scripts/verify_minutes_oos.py --oos-dir "$OOS" --score-dir "$SCORE" --features-dir "$FEATURES" --model-dir "$MINUTES" --report /tmp/m4c-oos-O.json
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/m4c-historical.json
PYTHONPATH=. .venv/bin/python scripts/verify_modelling.py --report /tmp/m4c-m3.json
PYTHONPATH=. .venv/bin/python scripts/verify_experiments.py --m3-dir data/modelling/57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a --frozen-dir data/experiments/09eb67bd0fc9198073c28f921e3ba0ffd67876f341d32a97dc0f76743e0d411c --holdout-dir data/experiment_holdouts/21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd --report /tmp/m4c-m4.json
PYTHONPATH=. .venv/bin/python scripts/verify_minutes.py --features-dir "$FEATURES" --model-dir "$MINUTES" --report /tmp/m4c-m4b.json
PYTHONPATH=. .venv/bin/python -O scripts/verify_minutes.py --features-dir "$FEATURES" --model-dir "$MINUTES" --report /tmp/m4c-m4b-O.json
PYTHONPATH=. .venv/bin/python scripts/investigate_minutes.py --report /tmp/m4c-discrepancy.json
.venv/bin/python -m pip check
.venv/bin/python -m compileall -q fpl_ai scripts tests main.py
.venv/bin/python -m fpl_ai minutes oos --help
.venv/bin/python -m fpl_ai prospective --help
git diff --check
```

186 tests pass normally and under optimized Python. Ten focused M4C tests cover
strict fitting/selection boundaries, annual populations, unsupported early periods,
development rejection, exact fresh/reuse behavior, semantic protocol identity,
corruption/missing/extra files, checksum-valid tampering, forecast-label mutations,
and exception/history isolation. Existing tests cover doubles, explicit zeros,
blanks, freshness, fixture v2, actual-clock deadline enforcement and separate
settlement/forecast immutability. Production/verifier checks use explicit exceptions,
not `assert`. Normal and optimized real-data verification reports are identical.

The independent audit reads pinned raw captures and processed fixture evidence,
recomputes target deltas, recent history, observed state/availability, masks and
model metrics, and checks all fitting row hashes against the exact source rows.
Fresh builds and same-identity reuse reproduce model/prediction/metric bytes and
preserve mtimes. Five-season M2, 137,662-row M3, frozen M4 validation/holdout and M4B
replay all pass. [Regression evidence](M4C_REGRESSION.json) binds the complete
pre-batch inventory: **664 files preserved in both bytes and mtimes**, including
raw inventories, historical builds/catalogue, M3, original M4 and all prior M4B bundles.
Dependency consistency, compilation, CLI help and whitespace checks pass.

## Acceptance and next batch

Chronology, guarded downstream handoff, unavailable early rows, separate outcomes,
immutable identities/checksums, deterministic rebuild/reuse, narrow documented anomaly
handling, real pre-deadline capture/freeze and full regression protection pass.
The conditional live-scoring criterion is satisfied by recording its legal
unavailability and exact next commands; **successful live settlement/scoring is still
pending**. The broader roadmap item requiring retained live outcomes stays open.

Next: a bounded leakage-safe xPts v2 integration using verified OOS minutes and a
separately declared downstream evaluation protocol. Only two historical OOS seasons
are available; the consumed 2025/26 points holdout cannot become fresh evidence.
Continue manual prospective retention and score GW5 when settled. Historical fixture
predictors, cause of the aggregate anomaly, first-live-history warm-up, external
timestamp attestation and demonstrated FPL decision value remain unresolved limitations.
