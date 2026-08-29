# Project state

Last updated: 2026-08-29

## Current milestone

Milestone 1 — Project foundation and current FPL ingestion.

Status: complete and verified locally on 2026-08-29.

## What currently works

- A zero-runtime-dependency Python CLI retrieves FPL bootstrap and fixture data.
- Minimum schema, unique-ID, and cross-entity reference validation runs before persistence.
- Timestamped raw JSON is kept separate from processed player, team, and fixture CSV files.
- Each processed snapshot includes provenance and row counts in `manifest.json`.
- Deterministic tests cover important validation, enrichment, table-shape, and persistence behavior.
- Prediction models and FPL decision rules have intentionally not been started.

### Latest verified run

- Command: `.venv/bin/python -m fpl_ai --output-dir data`
- Snapshot: `20260829T214120Z`
- Result: 623 players, 20 teams, and 380 fixtures
- Tests: 9 passed with `unittest`; package compilation also passed

The first network attempt was correctly blocked inside the restricted sandbox. An approved live retry then exposed that the local python.org Python installation had loaded zero certificate authorities. The client now securely falls back to the macOS system CA file when necessary (verification is never disabled), and the plain command above completed successfully.

## Current architecture

```text
FPL public endpoints
        |
        v
     FPLClient
        |
        v
 validate_payloads  ---- failure ----> non-zero CLI exit; no snapshot
        |
        v
 transform_players / transform_teams / transform_fixtures
        |
        +----> data/raw/<snapshot>/       (full JSON responses)
        |
        +----> data/processed/<snapshot>/ (CSV tables + manifest)
```

The boundaries are intentionally plain functions and a small client class. Local files are the only persistence layer.

## Known problems and limitations

- The upstream endpoints are public but unversioned and not guaranteed as a supported developer API.
- A run is a current snapshot; no historical ingestion, data catalogue, retention policy, or `latest` pointer exists.
- The two endpoint reads are not atomic with each other.
- There is no retry/backoff or automated schedule.
- CSV does not preserve a formal type schema.
- No season-specific rules configuration exists because no rule-backed logic is implemented yet.
- The existing `notebooks/exploration.ipynb` is an empty placeholder and was preserved as found.

## Recommended next step

Define Milestone 2's historical scope and data-quality contract before adding modelling. In particular, choose supported seasons and sources, then introduce season-aware configuration and gameweek/player-history tables with explicit schemas and leakage-safe timestamps.
