# Project state

Last updated: 2026-09-02

## Current milestone

Milestone 2 — Reproducible historical data foundation.

Status: in progress. Milestone 1 remains complete; the hardened 2024/25 Milestone 2 vertical slice is complete and live-verified. Multi-season expansion has not started.

## What currently works

- The zero-runtime-dependency Milestone 1 CLI still retrieves current FPL bootstrap and fixture data into timestamped raw JSON and processed CSV snapshots.
- `python -m fpl_ai historical --season 2024-25 --output-dir data` processes only the configured commit-pinned 2024/25 sources.
- Immutable historical raw files carry requested season, repository, configured ref, resolved commit SHA, source path/URL, retrieval time, SHA-256, and byte-size provenance. Manifests and the latest catalogue preserve the complete hashed source identity.
- Six leakage-classified canonical CSV tables, explicit schemas, a quality report, and a processed manifest are generated deterministically.
- `data/historical/catalogue.json` provides an atomic latest-successful lookup without a filesystem symlink.
- Snapshot selection requires `is_next`, an exact deadline match, and capture strictly before the deadline. Missing values remain null; every fixture in a double gameweek shares the deadline cutoff.
- Each player deadline row takes team ID/code/names and position ID/labels from that accepted snapshot. It never falls back to end-of-season identity; 31 live elements correctly show more than one team across deadline snapshots.
- Deadline-safe fixture context is allowlisted to season, target gameweek, and deadline. Final fixture identity, assignment, teams/opponent, home/away, kickoff, difficulty, status, minutes, and results remain only in post-event tables.
- Vaastav fixture-level `total_points` is canonical. Player/Gameweek sums are reconciled against settled `fplcache` `event_points`; any mismatch is a hard quality failure with both values recorded.
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
- Version: `v3-9779cdbc0c07-33dac28d1895`
- Sources: Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`; fplcache `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`
- Result: 38 gameweeks, 804 elements, 20 teams, 380 fixtures, 27,605 player-fixture facts, and 27,479 player-deadline snapshot rows
- Snapshot coverage: 38/38 gameweeks; no post-deadline, backfilled, or interpolated snapshot
- Quality: all hard checks passed; 38 fixture-bearing gameweeks, no duplicate fact keys, and every configured audit count matched
- Points reconciliation: 27,231 compared player/Gameweeks, 27,231 matching, zero mismatching, zero unavailable
- Deadline identity: all 27,479 snapshot rows have team and position IDs plus labels; no post-event fixture/result field appears in the snapshot table
- Exclusions: no Vaastav `xP` or `mng_*` field exists in an output table
- Identity audit: 10 accepted snapshot rows show the documented Assistant Manager person-code change for element 748; football-player code consistency passed
- Idempotency: an immediate second live command reused the same checksum-verified version without network or file rewrites
- Failed-run lifecycle: the stale AM report from the corrected v1 attempt was removed; future failures use unique attempt-stamped metadata and never update the latest catalogue
- Tests: 23 deterministic `unittest` tests passed; package `compileall` and diff whitespace checks passed

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
- Points can be reconciled only when a later snapshot marks the event `finished` and `data_checked` and provides `event_points`; missing comparison state remains explicitly unavailable, while any actual disagreement fails quality validation.
- The existing `notebooks/exploration.ipynb` remains an empty placeholder.

## Recommended next step

Add 2023/24 as the next single season using the same deadline-identity, fixture-availability, points-reconciliation, and immutable-provenance contract; validate it fully before adding another season.
