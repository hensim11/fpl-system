# Project state

Last updated: 2026-09-02

## Current milestone

Milestone 2 — Reproducible historical data foundation.

Status: in progress. Milestone 1 remains complete; the 2024/25 vertical slice and its Milestone 2 closure hardening are implemented and verified. Multi-season expansion has not started.

## What currently works

- The zero-runtime-dependency Milestone 1 CLI still retrieves current FPL bootstrap and fixture data into timestamped raw JSON and processed CSV snapshots.
- `python -m fpl_ai historical --season 2024-25 --output-dir data` processes only the configured commit-pinned 2024/25 sources.
- Immutable historical raw files carry requested season, repository, configured ref, resolved commit SHA, source path/URL, retrieval time, SHA-256, and byte-size provenance. The hashed source identity now includes the exact immutable artifact hashes.
- A separate deterministic build identity covers the explicit transformation contract version, canonical schemas, season checks, selected source schema, snapshot-selection contract, and reconciliation configuration. Build time and local paths are excluded; different builds over the same source use different directories.
- Seven leakage-classified CSV tables and five metadata artifacts are generated deterministically (12 processed artifacts total), including standalone points-reconciliation and frozen source-inventory artifacts.
- Every new processed build owns an atomic `source_inventory.json` with its exact source identity and file inventory. Catalogue schema v2 retains all discovered build versions; pre-v5 builds remain explicitly readable as `legacy_shared_raw_inventory` without rewriting their metadata.
- `data/historical/catalogue.json` provides an atomic latest-successful lookup without a filesystem symlink.
- Snapshot selection requires `is_next`, an exact deadline match, and capture strictly before the deadline. Missing values remain null; every fixture in a double gameweek shares the deadline cutoff.
- Each player deadline row takes team ID/code/names and position ID/labels from that accepted snapshot. It never falls back to end-of-season identity; 31 live elements correctly show more than one team across deadline snapshots.
- Deadline-safe fixture context is allowlisted to season, target gameweek, and deadline. Final fixture identity, assignment, teams/opponent, home/away, kickoff, difficulty, status, minutes, and results remain only in post-event tables.
- Vaastav fixture-level `total_points` is canonical. Player/Gameweek sums are reconciled against settled `fplcache` `event_points`; 2024/25 requires 100% eligible-row coverage, and no usable comparison, sub-threshold coverage, or any mismatch is a hard quality failure.
- Vaastav input shape is selected through the season's `vaastav-2024-25-v1` schema. Its field categories are disjoint, mappings are validated against supported source fields and unique canonical targets, and forbidden fields cannot populate trusted output. `xP` is structurally forbidden; drift remains visible under the tracked policy.
- Current and historical CLI option destinations are independent. Conflicting duplicate values before and after `historical` produce an argparse error instead of silent overwriting.
- Prediction models, feature engineering, optimisation, and FPL decision rules have intentionally not been started.

### Verified current-state run

- Command: `.venv/bin/python -m fpl_ai --output-dir data`
- Snapshot: `20260829T214120Z`
- Result: 623 players, 20 teams, and 380 fixtures
- Verification date: 2026-08-29

The local python.org installation has an empty default CA store. Both download paths securely fall back to the macOS system CA file when needed; certificate verification is never disabled.

### Verified historical 2024/25 run

- Command: `python3 -m fpl_ai historical --season 2024-25 --output-dir data --timeout 120`
- Source version: `v3-9779cdbc0c07-33dac28d1895`
- Processed build: `v3-9779cdbc0c07-33dac28d1895-build-105600b4135e`
- Source identity: `4c1896a6a9f9c26b739a490bea2553d9568f7f4549a2688ebe75bf76e18e880e`
- Build identity: `105600b4135e2b69ffcd0e07343f2998ebe5fa8e1e3156e049bd8bbda9f42296`
- Frozen source inventory: `source_inventory.json`, SHA-256 `f8bbf7daf5fa54c881473560843c15acaecab86ef911bbf06c79c79f1b78ec40`
- Sources: Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`; fplcache `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`
- Result: 38 gameweeks, 804 elements, 20 teams, 380 fixtures, 27,605 player-fixture facts, and 27,479 player-deadline snapshot rows
- Snapshot coverage: 38/38 gameweeks; no post-deadline, backfilled, or interpolated snapshot
- Quality: all hard checks passed; 38 fixture-bearing gameweeks, no duplicate fact keys, and every configured audit count matched
- Points reconciliation: required at threshold `1.0`; 27,231 eligible, 27,231 compared/matching, zero unmatched or mismatching, coverage `1.0`
- Deadline identity: all 27,479 snapshot rows have team and position IDs plus labels; no post-event fixture/result field appears in the snapshot table
- Exclusions: no Vaastav `xP` or `mng_*` field exists in an output table
- Identity audit: 10 accepted snapshot rows show the documented Assistant Manager person-code change for element 748; football-player code consistency passed
- Output preservation: all seven CSV files are byte-identical to the preceding `build-50b4c45a5abf`; the provenance-contract correction creates a v5 build identity and frozen inventory without overwriting earlier builds or modifying cached raw files
- Idempotency: an immediate second command reused the same identity- and checksum-verified build without network or file rewrites
- Legacy verification: the preceding `build-50b4c45a5abf` manifest stayed byte-identical and was resolved twice as `legacy_shared_raw_inventory`; it remains readable while its recorded shared-inventory checksum matches
- Failed-run lifecycle: the stale AM report from the corrected v1 attempt was removed; future failures use unique attempt-stamped metadata and never update the latest catalogue
- Tests: 41 deterministic `unittest` tests passed before final commit verification; package compilation and diff whitespace checks passed

## Architecture

Milestone 1 remains unchanged:

```text
FPL public endpoints -> FPLClient -> validation -> transforms
                                      |             |
                                      |             +-> data/processed/<snapshot>/
                                      +----------------> data/raw/<snapshot>/
```

Historical processing is a parallel path:

```text
pinned source catalogue
        |
        v
immutable Vaastav CSV + fplcache .json.xz inputs
        |
        v
strict source schema / deadline snapshot selection
        |
        v
canonical transforms -> cross-table quality contract
        |                         |
        |                         +-> failure: no latest update
        v
versioned CSV + schemas + report + manifest
        |
        v
atomic catalogue latest-successful entry
```

## Known limitations

- Historical support is intentionally limited to 2024/25. The four other agreed seasons are not configured or verified.
- Current ingestion responses are not atomic with each other and have no retry/backoff, retention policy, or schedule.
- CSV is portable and inspectable but requires downstream readers to apply the published schema.
- The source APIs and datasets are not guaranteed versioned developer contracts. Raw preservation makes corrections and revision changes auditable.
- Assistant Manager elements are club-manager slots rather than stable person identities and must not be treated as cross-season football-player IDs.
- The pinned inputs do not contain per-deadline fixture-list snapshots. Consequently fixture schedule/difficulty fields are intentionally post-event context and unavailable in the deadline table.
- Points can be reconciled only when a later snapshot marks the event `finished` and `data_checked` and provides integer `event_points`. Required reconciliation cannot publish as unavailable; optional skipping exists only as an explicit future-season policy and is not used for 2024/25.
- The existing `notebooks/exploration.ipynb` remains an empty placeholder.

## Recommended next step

Define and validate the 2023/24 catalogue entry plus its Vaastav source-schema definition, then run that one season through the unchanged generic importer before adding another season.
