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

- Decide the target season range and permitted historical sources.
- Add season-aware configuration for rules and source metadata.
- Define explicit schemas and data-quality reports.
- Add idempotent snapshot/catalog handling and a stable `latest` lookup.
- Ingest player match history and gameweek-level facts without adding modelling.

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
