# Roadmap

The platform will grow in small, testable milestones. Dates are intentionally omitted until priorities and operating constraints are agreed.

## Milestone 1 — Project foundation and current FPL ingestion

Status: implemented; verification details are recorded in `PROJECT_STATE.md`.

- Establish a small Python package and command-line entry point.
- Retrieve current public player, team, and fixture data.
- Validate minimum schemas and entity relationships.
- Store immutable raw JSON separately from processed CSV tables.
- Add deterministic tests and working-state documentation.

## Milestone 2 — Reproducible historical data foundation

Status: **complete**. All five seasons, 2021/22–2025/26, are published and verified, including the full-range identity, availability, temporal-integrity and offline reproducibility audit. Evidence: `docs/M2_2025_26_VERIFICATION.md`.

- [x] Set the eventual target range to 2021/22–2025/26 and pin the permitted historical sources.
- [x] Add a machine-readable 2024/25 source catalogue and season audit expectations.
- [x] Define explicit nullable schemas, information classes, and a data-quality report.
- [x] Add immutable raw provenance, idempotent version handling, atomic manifests/catalogue, and a stable latest-successful lookup.
- [x] Ingest 2024/25 player-fixture outcomes and strict pre-deadline snapshots without modelling.
- [x] Harden 2024/25 with deadline-time team/position identity, an explicit fixture availability allowlist, cross-source points reconciliation, complete source-pin identity, and unambiguous CLI arguments.
- [x] Close the 2024/25 architecture slice with enforced reconciliation coverage, validated season-specific Vaastav schemas, separate source/build identities, frozen per-build source inventories, and build-safe processed versioning.
- [x] Make 2024/25 schema mappings/types executable and scope frozen provenance to materially consumed records, with byte-identical canonical outputs.
- [x] Verify 2023/24 through its own observed schema/catalogue entry, 38/38 deadline coverage, complete points reconciliation, deterministic rebuilds, and byte-identical 2024/25 regression checks.
- [x] Verify 2022/23 end-to-end, preserving fixture-empty GW7 and observed person-code changes; require complete points reconciliation and cross-season schema/rebuild checks.
- [x] Investigate 2021/22 schema differences, implement strict label/kickoff compatibility, and reproduce source blockers without publishing invalid data.
- [x] Implement independently selected, pinned settled-event comparisons for 2021/22: 23,230/23,230 exact matches, including GW3/GW17; preserve accepted-season identities.
- [x] Make the default audit verify published seasons and route unpublished attempts through explicit investigation mode.
- [x] Complete 2021/22 publication with 43/43 passing checks, 38/38 snapshots and complete settlement reconciliation, using one authorized, pinned GW18 superseded-deadline exception (state as of 12:33; 3h27 freshness limitation).
- [x] Add and verify 2025/26 through the proven pipeline, with exact duplicate-source evidence and complete settled points coverage.
- [x] Re-run cross-season identity and availability audits over all five seasons; preserve all earlier outputs and identities.

Exit criterion: **satisfied** — a documented, reproducible dataset suitable for exploratory analysis across all five agreed seasons.

## Milestone 3 — Feature and evaluation design

Status: **complete** against the current exit criterion. Five-season deterministic features and non-ML evaluation verified; see `docs/M3_VERIFICATION.md`. No trained model or recommendation claim.

- [x] Define prediction targets and guard against future-data leakage.
- [x] Create time-aware train/validation/test splits.
- [x] Build deterministic feature tables from versioned inputs.
- [x] Establish simple non-ML baselines and evaluation metrics.

Exit criterion: **satisfied** — an evaluation harness that can compare approaches honestly. 132 tests pass; five-season fresh rebuild/reuse, temporal protections and source traces are verified. No product recommendation claims yet.

## Milestone 4 — First predictive experiments

Status: **first substantial batch complete; current exit criterion satisfied**.
See `docs/M4_VERIFICATION.md` for the separate validation and frozen holdout evidence.

- [x] Train transparent Ridge and bounded nonlinear models for the frozen M3 target.
- [x] Track exact upstream identity, preprocessing, models, predictions and evaluation.
- [x] Select with validation RMSE, publish the fitted winner, then evaluate holdout.
- [x] Compare all five non-ML baselines, positions, history segments and uncertainty.
- [x] Verify fit boundaries, source anomalies, exact replay and upstream preservation.

Exit criterion: **satisfied for the agreed prediction problem** — held-out RMSE
1.9164 versus 2.0880 scoring rate and 2.1234 external ep_next, with MAE/ranking gains,
full coverage and lower squared error in all 38 test GWs. This does not establish
squad/transfer/captain utility or universal superiority. 145 tests pass.

Recommended next modelling batch: targeted independently proven point-in-time
feature expansion, position calibration investigation and prospective evaluation.
Preserve M4's frozen results; do not retune against the now-reported 2025/26 holdout.

## Later milestones

Only after the data and evaluation foundations are reliable:

- configurable squad/transfer optimisation;
- user-specific decision support;
- scheduled ingestion and monitoring;
- service or UI layers;
- deployment and operational controls.

These are directions, not commitments. Frameworks, databases, hosted services, and prediction models should be introduced only when a concrete requirement justifies them.
