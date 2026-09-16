# Project state

Last updated: 2026-09-16

## Current milestone

Milestone 2 — Reproducible historical data foundation.

Status: in progress. Milestone 1 remains complete; the 2024/25 vertical slice and its Milestone 2 closure hardening are implemented and verified. The first cross-season expansion, 2023/24, is now implemented and fully verified.

## What currently works

- The zero-runtime-dependency Milestone 1 CLI still retrieves current FPL bootstrap and fixture data into timestamped raw JSON and processed CSV snapshots.
- `python -m fpl_ai historical --season 2024-25 --output-dir data` processes configured commit-pinned 2024/25 sources; `--season 2023-24` processes the separately validated older season.
- Immutable historical raw files carry requested season, repository, configured ref, resolved commit SHA, source path/URL, retrieval time, SHA-256, and byte-size provenance. The hashed source identity includes only materially consumed records, with deterministic consumption roles; rejected discovery candidates and unrelated cache entries are audit-only.
- A separate deterministic build identity covers the explicit transformation contract version, canonical schemas, season checks, selected source schema, snapshot-selection contract, and reconciliation configuration. Build time and local paths are excluded; different builds over the same source use different directories.
- Seven leakage-classified CSV tables and five metadata artifacts are generated deterministically (12 processed artifacts total), including standalone points-reconciliation and frozen source-inventory artifacts.
- Every new processed build owns an atomic `source_inventory.json` with its exact source identity and canonicalised consumed-file inventory. Actual consumption must equal the resolved dependency set; exact duplicates merge safely and conflicts fail. Catalogue schema v2 retains all discovered build versions; pre-v5 builds remain explicitly readable as `legacy_shared_raw_inventory` without rewriting their metadata.
- `data/historical/catalogue.json` provides an atomic latest-successful lookup without a filesystem symlink.
- Snapshot selection requires `is_next`, an exact deadline match, and capture strictly before the deadline. Missing values remain null; every fixture in a double gameweek shares the deadline cutoff.
- Each player deadline row takes team ID/code/names and position ID/labels from that accepted snapshot. It never falls back to end-of-season identity; 31 live elements correctly show more than one team across deadline snapshots.
- Deadline-safe fixture context is allowlisted to season, target gameweek, and deadline. Final fixture identity, assignment, teams/opponent, home/away, kickoff, difficulty, status, minutes, and results remain only in post-event tables.
- Vaastav fixture-level `total_points` is canonical. Player/Gameweek sums are reconciled against settled `fplcache` `event_points`; 2024/25 requires 100% eligible-row coverage, and no usable comparison, sub-threshold coverage, or any mismatch is a hard quality failure.
- Vaastav input shape is selected through the season's `vaastav-2024-25-v1` or `vaastav-2023-24-v1` schema. Its declarative mappings execute at one typed normalisation boundary, after which generic transforms consume only canonical names. Integer, decimal, boolean, string/enumeration, nullability, and UTC timestamp contracts are enforced. Optional-column reporting is category-accurate, quarantine targets are unique, and `xP` remains structurally forbidden.
- Current and historical CLI option destinations are independent. Conflicting duplicate values before and after `historical` produce an argparse error instead of silent overwriting.
- Prediction models, feature engineering, optimisation, and FPL decision rules have intentionally not been started.

### Verified current-state run

- Command: `.venv/bin/python -m fpl_ai --output-dir data`
- Snapshot: `20260829T214120Z`
- Result: 623 players, 20 teams, and 380 fixtures
- Verification date: 2026-08-29

The local python.org installation has an empty default CA store. Both download paths securely fall back to the macOS system CA file when needed; certificate verification is never disabled.

### Verified historical 2024/25 run

- Command: `.venv/bin/python -m fpl_ai historical --season 2024-25 --output-dir data`
- Source version: `v3-9779cdbc0c07-33dac28d1895`
- Processed build: `v3-9779cdbc0c07-33dac28d1895-build-1fbdcc84c93d`
- Source identity: `d94912c4423cd0f7ffb8b1fbaf4ff4493450f772af7d1258f9cfe5bea5a89f69`
- Build identity: `1fbdcc84c93d92367c3f6f2a0b39d039dc04403980bb100491410523c62f9d86`
- Transformation contract: `historical-transform-v6`
- Frozen consumed-source inventory: 44 records; `source_inventory.json` SHA-256 `ccee8444e994e81cf4d1d0dc1bde04c4bbeb9eeace50c570dd1d007a3169840c`
- Sources: Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`; fplcache `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`
- Result: 38 gameweeks, 804 elements, 20 teams, 380 fixtures, 27,605 player-fixture facts, and 27,479 player-deadline snapshot rows
- Snapshot coverage: 38/38 gameweeks; no post-deadline, backfilled, or interpolated snapshot
- Quality: all hard checks passed; 38 fixture-bearing gameweeks, no duplicate fact keys, and every configured audit count matched
- Points reconciliation: required at threshold `1.0`; 27,231 eligible, 27,231 compared/matching, zero unmatched or mismatching, coverage `1.0`
- Deadline identity: all 27,479 snapshot rows have team and position IDs plus labels; no post-event fixture/result field appears in the snapshot table
- Exclusions: no Vaastav `xP` or `mng_*` field exists in an output table
- Identity audit: 10 accepted snapshot rows show the documented Assistant Manager person-code change for element 748; football-player code consistency passed
- Source-schema validation: all real rows passed executable mapping and declared type/format validation; the quality report distinguishes required, optional, unexpected, ignored, quarantined, and forbidden-source columns
- Output preservation: all seven CSV files are byte-identical to baseline `build-105600b4135e`; v6 changes source/build identities and metadata semantics without changing canonical output
- Idempotency: an immediate second command reused the same identity- and checksum-verified build without network or file rewrites
- Compatibility: baseline `build-105600b4135e` remained checksum-readable and unmodified after the rebuild
- Failed-run lifecycle: the stale AM report from the corrected v1 attempt was removed; future failures use unique attempt-stamped metadata and never update the latest catalogue
- Tests: 53 deterministic `unittest` tests passed; package compilation, CLI help, cached rebuild/reuse, manifest checksum verification, and diff whitespace checks passed

### Verified historical 2023/24 run (2026-09-16)

- Command: `.venv/bin/python -m fpl_ai historical --season 2023-24 --output-dir data`
- Build: `v3-9779cdbc0c07-33dac28d1895-build-7886af1a34dd`
- Source identity: `adfc64c1be2725e4ccc68b3366e615f1b007a8f7583698b0f58e9f2335e2cb9a`
- Build identity: `7886af1a34dd6293e9ea8bfb8c4b94eedd3bcee2c75f7f93d4a98eef390e35e8`
- Same immutable provider revisions as 2024/25; schema `vaastav-2023-24-v1`, transformation contract unchanged at v6.
- Counts: 38 gameweeks, 865 players, 20 teams, 380 fixtures, 29,725 fixture facts, 29,510 deadline rows, 29,725 quarantine rows.
- Coverage: 38/38 deadlines; captures strictly earlier by 8 minutes–6 hours 10 minutes; no backfill. All deadline team/position identity fields populated; 23 elements change deadline team.
- Reconciliation: required at `1.0`; 28,742 eligible, compared, and matching; zero unmatched or mismatching.
- All 40 quality checks passed, including keys, relationships, deadline safety, source schema drift, executable source types, and audit counts.
- Frozen inventory: 44 consumed records; SHA-256 `1774f4b05981a9b5ff03af0c2979faf4ae7d276fe69a90bb73a550d2a1d1366b`. The earlier unsettled GW38 capture remains only in the 45-record raw cache.
- Fresh offline rebuilds of both seasons reproduced their source/build identities and all seven CSVs byte-for-byte. Immediate reruns were checksum-verified, network-free, and left hashes and modification times unchanged.
- The existing 2024/25 v6 build and v5 compatibility build remained readable and unmodified.
- 60 network-free tests passed (53 existing plus seven new); compilation, both CLI help commands, manifest verification, and whitespace checks passed.
- No generic ingestion, validation, reconciliation, canonical schema, or compatibility changes were necessary.
- Detailed source observations, artifact checksums, and limitations: [verification record](docs/M2_2023_24_VERIFICATION.md).

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
typed source normalisation / deadline snapshot selection
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

- Historical support covers 2023/24 and 2024/25. The three other agreed seasons are not configured or verified.
- Current ingestion responses are not atomic with each other and have no retry/backoff, retention policy, or schedule.
- CSV is portable and inspectable but requires downstream readers to apply the published schema.
- The source APIs and datasets are not guaranteed versioned developer contracts. Raw preservation makes corrections and revision changes auditable.
- Assistant Manager elements are club-manager slots rather than stable person identities and must not be treated as cross-season football-player IDs.
- The pinned inputs do not contain per-deadline fixture-list snapshots. Consequently fixture schedule/difficulty fields are intentionally post-event context and unavailable in the deadline table.
- Points can be reconciled only when a later snapshot marks the event `finished` and `data_checked` and provides integer `event_points`. Required reconciliation cannot publish as unavailable; optional skipping exists only as an explicit future-season policy and is not used for either verified season.
- The existing `notebooks/exploration.ipynb` remains an empty placeholder.

## Recommended next step

Add 2022/23 through the same evidence-first catalogue/schema workflow, including its fixture-empty GW7 and an explicit audit of archive and settlement coverage. Keep feature engineering and modelling deferred.
