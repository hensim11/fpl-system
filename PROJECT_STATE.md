# Project state

Last updated: 2026-09-17

## Current milestone

Milestone 2 — Reproducible historical data foundation.

Status: **complete**. All five agreed seasons, 2021/22–2025/26, are accepted and published. The full-range identity, availability, temporal-integrity and offline reproducibility audit passes. Milestone 1 remains complete; Milestone 3 is not implemented. The exact authorized 2021/22 GW18 freshness exception remains applicable.

## What currently works

- The zero-runtime-dependency Milestone 1 CLI still retrieves current FPL bootstrap and fixture data into timestamped raw JSON and processed CSV snapshots.
- `python -m fpl_ai historical --season 2024-25 --output-dir data` processes configured commit-pinned 2024/25 sources; `--season 2023-24`, `--season 2022-23` and `--season 2021-22` process the separately validated older seasons; `--season 2025-26` completes the agreed range.
- Immutable historical raw files carry requested season, repository, configured ref, resolved commit SHA, source path/URL, retrieval time, SHA-256, and byte-size provenance. The hashed source identity includes only materially consumed records, with deterministic consumption roles; rejected discovery candidates and unrelated cache entries are audit-only.
- A separate deterministic build identity covers the explicit transformation contract version, canonical schemas, season checks, selected source schema, snapshot-selection contract, and reconciliation configuration. Build time and local paths are excluded; different builds over the same source use different directories.
- Seven leakage-classified CSV tables and five metadata artifacts are generated deterministically (12 processed artifacts total), including standalone points-reconciliation and frozen source-inventory artifacts.
- Every new processed build owns an atomic `source_inventory.json` with its exact source identity and canonicalised consumed-file inventory. Actual consumption must equal the resolved dependency set; exact duplicates merge safely and conflicts fail. Catalogue schema v2 retains all discovered build versions; pre-v5 builds remain explicitly readable as `legacy_shared_raw_inventory` without rewriting their metadata.
- `data/historical/catalogue.json` provides an atomic latest-successful lookup without a filesystem symlink.
- Snapshot selection requires `is_next`, an exact deadline match, and capture strictly before the deadline, except for the single authorized, hash-bound 2021/22 GW18 superseded-deadline policy described below. Missing values remain null; every fixture in a double gameweek shares the deadline cutoff.
- Each player deadline row takes team ID/code/names and position ID/labels from that accepted snapshot. It never falls back to end-of-season identity; 29, 23 and 31 elements show more than one deadline team in 2022/23, 2023/24 and 2024/25 respectively.
- Deadline-safe fixture context is allowlisted to season, target gameweek, and deadline. Final fixture identity, assignment, teams/opponent, home/away, kickoff, difficulty, status, minutes, and results remain only in post-event tables.
- Vaastav fixture-level `total_points` is canonical. Player/Gameweek sums are reconciled against settled `fplcache` `event_points`; all five seasons require 100% eligible-row coverage, and no usable comparison, sub-threshold coverage, or any mismatch is a hard quality failure.
- Vaastav input shape is selected through the season's `vaastav-2024-25-v1`, `vaastav-2023-24-v1`, `vaastav-2022-23-v1`, `vaastav-2021-22-v1` or `vaastav-2025-26-v1` schema. Its declarative mappings execute at one typed normalisation boundary, after which generic transforms consume only canonical names. Integer, decimal, boolean, string/enumeration, nullability, and UTC timestamp contracts are enforced. Optional-column reporting is category-accurate, quarantine targets are unique, and `xP` remains structurally forbidden.
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

### Verified historical 2022/23 and cross-season audit (2026-09-16)

- Command: `.venv/bin/python -m fpl_ai historical --season 2022-23 --output-dir data`.
- Build: `v3-9779cdbc0c07-33dac28d1895-build-9227d246d371`.
- Source identity: `12c000cd16399629ccfb762581e479906651834ca1f377234b98e5f26fb0c3c3`.
- Build identity: `9227d246d3718724d8118898b6548077c8963837bdf49e9bc6bf64b30a7762a0`.
- Same immutable provider revisions; observed schema `vaastav-2022-23-v1`.
- Counts: 38 gameweeks, 778 players, 20 teams, 380 fixtures, 26,505 facts,
  26,198 deadline rows and 26,505 quarantine rows.
- All 44 quality checks pass. All 24,957 eligible player/Gameweek totals match,
  with coverage `1.0`, zero missing comparisons and zero mismatches.
- 38/38 accepted snapshots, captured 5 minutes–6 hours 9 minutes before deadline.
  GW7 retains its September 10 deadline and 06:33 UTC capture but no fixture facts.
- All deadline team/position identity and prices populated; 29 elements change
  deadline team. Two GW1 person-code changes are exact, source-path-scoped audited
  exceptions; original snapshot codes remain intact. See Decision 024.
- All 778 player season sums also match Vaastav final aggregates. Every club has
  38 fixtures, with each directed home/away pairing exactly once.
- All three seasons freshly rebuild offline with identical source/build identities
  and seven byte-identical CSVs. Published canonical schemas match across seasons;
  reuse preserves hashes and modification times. Both newer builds stay unchanged.
- 68 network-free tests pass; compilation, CLI help and whitespace checks pass.
  No dedicated lint/type-check tool is configured.
- Reproducible command: `PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/historical-audit.json`.
- Full evidence: [2022/23 verification](docs/M2_2022_23_VERIFICATION.md) and
  [machine-readable cross-season audit](docs/M2_CROSS_SEASON_AUDIT.json).


### Verified historical 2021/22 (2026-09-17)

- Normal command: `.venv/bin/python -m fpl_ai historical --season 2021-22 --output-dir data`.
- **Published successfully**: 38 Gameweeks, 737 players, 20 teams, 380 fixtures,
  25,447 facts, **25,150** deadline rows and 25,447 audit-only quarantine rows.
- **43/43 quality checks pass; 38/38 deadline snapshots**. All **23,230** eligible
  totals match independently selected settlement captures, coverage **1.0**, zero
  unmatched rows or mismatches. GW17 has 460 comparisons; James GW3 remains 1.
- Version: `v3-9779cdbc0c07-33dac28d1895-build-5644015b364e`.
- Source identity: `c4045c8739a4dfd0d3d47115f23d8a0c6ee211b510e8572ab6315f699542f863`.
- Build identity: `5644015b364e43177485c5d5c3f520efe64b7a17d4113b84b56c400bab2c57d8`.
- Frozen inventory: **134** materially consumed artifacts; SHA-256
  `4c094e22593ebfd61b77602720ec3b00309bdc75b5468acf16503b4ac4c57137`.
- User-authorized policy v1 admits only GW18's exact pinned `cache/2021/12/18/1233.json.xz`
  capture, hash `9c8fbad59eecb978494d98425e0dadcfa16fbb3a3954f99b4263c65277e2eed1`.
  It retains the observed payload deadline 13:30 and authoritative deadline 16:00.
  State is **as of 12:33**, with a **3h27 freshness limitation**. Capture is strictly
  before both deadlines; the 18:25 post-deadline capture remains forbidden.
- Exact season/GW/path/hash/revision/time/deadline matching and one unambiguous
  upcoming event are mandatory. The policy enters build identity and quality/audit
  evidence. No raw rewrite, interpolation, outcome backfill or global mismatch switch.
- Earlier compatibility and independent settlement policies remain intact. The new
  snapshot eligibility does not change settlement paths, fixture facts or points.
- All four seasons pass fresh offline builds, deterministic identities/CSV hashes
  and checksum-verified reuse without byte/mtime changes. The three prior seasons'
  complete audit entries remain identical to their pre-batch baseline.
- Default and explicit `--season 2021-22` audits pass. Status is now `published`
  solely because the successful catalogue entry exists. Earlier failures are retained.
- **102 tests pass**, including eight focused exception regressions on top of the
  94-test baseline; compilation, pipeline/audit help, dependency and whitespace
  checks pass. No new runtime dependency, commit or merge.
- [Acceptance record](docs/M2_2021_22_VERIFICATION.md),
  [cross-season audit](docs/M2_CROSS_SEASON_AUDIT.json), and historical
  [source-search record](docs/M2_2021_22_SOURCE_SEARCH.json).


### Verified historical 2025/26 and Milestone 2 closure (2026-09-17)

- Published build: `v3-9779cdbc0c07-33dac28d1895-build-0fa66b641643`.
- Source identity: `1bcdf1b685588c462bfd6b04a7c546a15d7ed295d85d33efedb9370b5a8a26ea`.
- Build identity: `0fa66b6416438b1149992ed4b8cae7d0cf8914bb47e48a08302f91d891c581e0`.
- Same immutable Vaastav/fplcache pins; schema `vaastav-2025-26-v1`; v6 canonical
  transformation contract unchanged. No existing season configuration changed.
- Counts: 38 Gameweeks, 841 players, 20 teams, 380 fixtures, **29,747 fixture facts**,
  **29,645 deadline observations**, 29,747 quarantine rows. **43/43 checks pass**.
- All **29,338** eligible player/Gameweek totals compare and match: required coverage
  **1.0**, zero unmatched/mismatching. Every final aggregate also matches fixture sums.
- 38/38 snapshots satisfy exact deadlines and strictly earlier capture, with ages
  22 minutes–5h35. GW38 uses May 24 08:39 before 13:30; the stale 13:49 `is_next`
  capture is rejected. Final settlement is May 25 10:23; 04:38 is still unsettled.
- 27 elements change observed team, none changes position, and no new person-code
  anomaly occurs. Sillah (841) is absent from the last deadline snapshot; no backfill.
- The raw merged file has 29,757 rows. Ten identical repeats from overlapping renamed
  player directories are handled by a season/commit/file-hash/key/count-bound policy.
  All raw fields must agree; conflicts, changed hashes and undeclared/stale rules fail.
  Raw bytes and original record numbers remain auditable. See Decision 029.
- Frozen inventory: 44 consumed records; SHA-256
  `1b1cf8b00991fab11caf0a2ba2ff2ae415787c607f9e6cae364700bcd15e6fd1`.
- All five seasons freshly rebuild offline with identical identities and seven CSVs,
  then reuse without byte/mtime changes. All 112 pre-existing processed files and
  all earlier catalogue/configuration/audit season entries remain unchanged.
- Expanded audit: 190 deadline captures rechecked against raw payloads, settlement
  timing, field presence/types, blanks/doubles, code/position/team changes. 1,777
  non-AM final codes, 1,016 across multiple seasons, 51 cross-season position changes;
  no duplicate final football-player codes within a season. All prior cases preserved.
- **112 tests pass**; compilation, four help commands, invalid CLI arguments, dependency
  consistency, pinned acquisition, offline inspection/build/reuse and diff hygiene pass.
  No configured lint/type checker, new runtime dependency, features or models.
- Evidence: [2025/26 acceptance](docs/M2_2025_26_VERIFICATION.md),
  [source inspection](docs/M2_2025_26_SOURCE_AUDIT.json),
  [five-season audit](docs/M2_CROSS_SEASON_AUDIT.json),
  [availability guide](docs/M2_FIVE_SEASON_AVAILABILITY.md),
  [prior-season preservation](docs/M2_2025_26_REGRESSION.json).

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

- Luke Harris (546) and Hugo Bueno (558) have documented 2022/23 GW1 person-code
  changes. Downstream identity linking must account for these; earlier observations
  are not rewritten with later codes.
- An additional 2024/25 final-aggregate diagnostic finds Ferguson's fixture sum
  is 27 versus cumulative 28. Settled event points match every canonical Gameweek;
  the archive itself exhibits this cumulative inconsistency. No arbitrary point
  adjustment was made. Details and precise captures are in the 2022/23 verification.

- Historical support covers the complete 2021/22–2025/26 range. GW18 2021/22 state is as of 12:33, 3h27 before its final deadline, under the exact superseded-deadline exception. New 2025/26 defensive statistics and partial-season metadata remain raw-only; they are not consistently available across all five seasons.
- Current ingestion responses are not atomic with each other and have no retry/backoff, retention policy, or schedule.
- CSV is portable and inspectable but requires downstream readers to apply the published schema.
- The source APIs and datasets are not guaranteed versioned developer contracts. Raw preservation makes corrections and revision changes auditable.
- Assistant Manager elements are club-manager slots rather than stable person identities and must not be treated as cross-season football-player IDs.
- The pinned inputs do not contain per-deadline fixture-list snapshots. Consequently fixture schedule/difficulty fields are intentionally post-event context and unavailable in the deadline table.
- Points can be reconciled only when a later snapshot marks the event `finished` and `data_checked` and provides integer `event_points`. Required reconciliation cannot publish as unavailable; optional skipping exists only as an explicit future-season policy and is not used for any verified season.
- The existing `notebooks/exploration.ipynb` remains an empty placeholder.

## Recommended next step

Begin the first substantial Milestone 3 batch: feature and evaluation design.
Use the five-season availability/identity audit to define targets, permissible inputs,
identity linking and time-aware evaluation before implementing features or models.
Preserve the explicit 2021/22 GW18 freshness limitation and all documented anomalies.
