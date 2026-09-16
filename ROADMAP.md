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

Status: in progress. The 2024/25 vertical slice is implemented and live-verified; expansion to the other agreed seasons remains.

- [x] Set the eventual target range to 2021/22–2025/26 and pin the permitted historical sources.
- [x] Add a machine-readable 2024/25 source catalogue and season audit expectations.
- [x] Define explicit nullable schemas, information classes, and a data-quality report.
- [x] Add immutable raw provenance, idempotent version handling, atomic manifests/catalogue, and a stable latest-successful lookup.
- [x] Ingest 2024/25 player-fixture outcomes and strict pre-deadline snapshots without modelling.
- [x] Harden 2024/25 with deadline-time team/position identity, an explicit fixture availability allowlist, cross-source points reconciliation, complete source-pin identity, and unambiguous CLI arguments.
- [x] Close the 2024/25 architecture slice with enforced reconciliation coverage, validated season-specific Vaastav schemas, separate source/build identities, frozen per-build source inventories, and build-safe processed versioning.
- [x] Make 2024/25 schema mappings/types executable and scope frozen provenance to materially consumed records, with byte-identical canonical outputs.
- [ ] Expand the proven pipeline and season-specific schema mappings to 2021/22–2023/24 and 2025/26.
- [ ] Re-run cross-season identity and availability audits over the full supported range.

Exit criterion: a documented, reproducible dataset suitable for exploratory analysis across agreed seasons.

## Milestone 3 — Feature and evaluation design

- Define prediction targets and guard against future-data leakage.
- Create time-aware train/validation/test splits.
- Build deterministic feature tables from versioned inputs.
- Establish simple non-ML baselines and evaluation metrics.

Exit criterion: an evaluation harness that can compare approaches honestly. No product recommendation claims yet.

## Milestone 4 — First predictive experiments

- Train transparent baseline models for the agreed target.
- Track data snapshot, features, configuration, and evaluation results.
- Compare against non-ML baselines and document uncertainty.

Exit criterion: a reproducible experiment with evidence that modelling adds value.

## Later milestones

Only after the data and evaluation foundations are reliable:

- configurable squad/transfer optimisation;
- user-specific decision support;
- scheduled ingestion and monitoring;
- service or UI layers;
- deployment and operational controls.

These are directions, not commitments. Frameworks, databases, hosted services, and prediction models should be introduced only when a concrete requirement justifies them.
