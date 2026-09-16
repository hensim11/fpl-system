# FPL AI Platform

Data foundation for an AI-powered Fantasy Premier League analytics platform. Milestone 1 downloads current public FPL data; Milestone 2 builds reproducible, leakage-classified historical tables for 2023/24 and 2024/25. The project does **not** contain feature engineering, prediction models, optimisation, or recommendations.

## Quick start

Python 3.11 or newer is required. The pipelines and tests have no third-party runtime dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate

# Existing Milestone 1 current snapshot
python -m fpl_ai --output-dir data

# Pinned Milestone 2 historical seasons
python -m fpl_ai historical --season 2023-24 --output-dir data
python -m fpl_ai historical --season 2024-25 --output-dir data

python -m unittest discover -v
```

The compatibility entry point remains equivalent for current ingestion:

```bash
python main.py --output-dir data
```

An optional editable installation exposes `fpl-ingest`:

```bash
python -m pip install -e .
fpl-ingest --output-dir data
fpl-ingest historical --season 2024-25 --output-dir data
```

TLS certificate verification is always enabled. If a python.org macOS installation has not loaded its optional certificate bundle, both download paths use the operating-system CA bundle when available.

## Repository structure

```text
.
├── data/
│   ├── raw/                       # Current untouched API JSON (ignored)
│   ├── processed/                 # Current CSV snapshots (ignored)
│   └── historical/                # Pinned raw/canonical versions (ignored)
├── fpl_ai/
│   ├── client.py                  # Current FPL HTTP client
│   ├── validation.py              # Current payload validation
│   ├── transform.py               # Current transformations
│   ├── pipeline.py                # Current snapshot persistence
│   ├── historical_sources.json    # Pinned source and season catalogue
│   ├── historical_schema.py       # Explicit canonical/source schemas
│   ├── historical_transform.py    # Historical transformations
│   ├── historical_validation.py   # Cross-table quality contract
│   ├── historical_io.py           # Immutable and atomic file helpers
│   ├── historical_pipeline.py     # Historical orchestration/catalogue
│   └── cli.py                     # Backward-compatible CLI
├── tests/                         # Network-free deterministic tests
├── DATA_NOTICE.md                 # Data-use and affiliation notice
├── DECISIONS.md                   # Architecture decision record
├── PROJECT_STATE.md               # Verified status and next handoff
├── PROJECT_VISION.md              # Long-term product vision
├── ROADMAP.md                     # Incremental delivery plan
├── main.py                        # Compatibility entry point
└── pyproject.toml
```

Generated current and historical data is intentionally ignored by Git.

## Data sources

### Current FPL state

Milestone 1 makes two unauthenticated requests to the public endpoints used by the official FPL website:

| Endpoint | Use |
| --- | --- |
| `https://fantasy.premierleague.com/api/bootstrap-static/` | Current players, teams, positions, availability, and aggregate statistics. |
| `https://fantasy.premierleague.com/api/fixtures/` | Current fixture schedule, gameweeks, kickoff, teams, results, and difficulty. |

These are public but not guaranteed as a versioned developer API.

### Historical 2023/24 and 2024/25

Both seasons use the same two immutable repository revisions, inspected for their respective season files:

| Provider | Pinned revision | Use |
| --- | --- | --- |
| [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) | `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` | Player-fixture outcomes, season identities, teams, and fixtures. |
| [Randdalf/fplcache](https://github.com/Randdalf/fplcache) | `33dac28d18953bee5bc4bd56ddd8a5e32e169d68` | Compressed historical `bootstrap-static` captures. |

`fpl_ai/historical_sources.json` records repositories, configured refs, resolved immutable commit SHAs, required paths, expected gameweeks, season audit counts, the selected Vaastav source-schema ID/version, and the season's reconciliation policy. No moving `master` or `main` ref is accepted. Every downloaded file is retained byte-for-byte under `data/historical/raw/` and recorded with requested season, provider, repository, configured ref, resolved commit, source path and URL, retrieval time, SHA-256, and byte size.

Provenance has two deliberately separate hashes. `source_identity_sha256` identifies only pinned immutable artifacts that materially participated in the build, including their paths, content hashes, sizes, and deterministic consumption roles. Rejected snapshot candidates and unrelated cached files may remain in the mutable raw-cache manifest for operational audit, but they are excluded from the frozen consumed inventory and source identity. `build_identity_sha256` identifies the transformation contract, canonical schema contract, season expectations, snapshot-selection settings, selected source schema, and reconciliation policy. Timestamps, local output paths, cache contents, and discovery order are excluded from deterministic identities. This permits two semantic builds from the same sources without overwriting one another.

### Verified 2023/24 batch

The full command produces 38 gameweeks, 865 players, 20 teams, 380 fixtures,
29,725 fixture facts, 29,510 deadline rows, and 29,725 quarantine rows.
Coverage is 38/38 deadlines; accepted captures precede deadlines by 8 minutes to
6 hours 10 minutes. All 28,742 eligible player/Gameweek totals reconcile exactly
at the required `1.0` threshold. The absent `modified` source field remains null
in quarantine; no Assistant Manager fields or positions occur.

Build: `v3-9779cdbc0c07-33dac28d1895-build-7886af1a34dd`.
See [the batch verification record](docs/M2_2023_24_VERIFICATION.md) for full
identities, source evidence, checksums, limitations, and rebuild verification.

## Output datasets

### Current snapshots

For a current snapshot `<id>`:

- `data/raw/<id>/bootstrap-static.json` and `fixtures.json` preserve the API responses.
- `data/processed/<id>/players.csv`, `teams.csv`, and `fixtures.csv` are inspectable current-state tables.
- `data/processed/<id>/manifest.json` records sources and row counts.

### Historical versions

A successful historical version has this layout:

```text
data/historical/
├── raw/2024-25/<version>/
│   ├── vaastav/                    # Four immutable CSV inputs
│   ├── fplcache/                   # Tree response and tested .json.xz files
│   └── source_manifest.json
├── processed/2024-25/<source-version>-build-<build-hash>/
│   ├── gameweeks.csv
│   ├── players.csv
│   ├── teams.csv
│   ├── fixtures.csv
│   ├── player_fixture_facts.csv
│   ├── player_deadline_snapshots.csv
│   ├── quarantined_source_metadata.csv
│   ├── schemas.json
│   ├── data_quality_report.json
│   ├── total_points_reconciliation.json
│   ├── source_inventory.json
│   └── manifest.json
└── catalogue.json                  # Stable latest-successful lookup
```

Each successful build contains seven generated CSV tables and five metadata artifacts (12 processed artifacts total). `schemas.json` is the machine-readable column, type, nullability, information-class, transformation-version, and selected source-schema contract. The generated tables are:

- `gameweeks`: every scheduled gameweek, including a future fixture-empty gameweek; deadline, selected capture, hours before deadline, source path, and coverage flag.
- `players`: season-qualified `element`, FPL `player_code`, names, and explicitly named end-of-season team/position fields for identity auditing. `element` is never treated as cross-season identity.
- `teams`: season-qualified FPL team identity and names.
- `fixtures`: the season-end/post-event gameweek assignment, teams, UTC kickoff, difficulty, scores, and completion. It is not a deadline-time schedule snapshot.
- `player_fixture_facts`: one row per `(season, element, fixture)`, with explicitly post-event `team_id_at_fixture`, `opponent_team_id_at_fixture`, `position_at_fixture`, home/away context, and realised outcomes. Zero-minute rows are preserved.
- `player_deadline_snapshots`: one element per accepted gameweek capture, containing the team ID/code/name, position ID/labels, price, ownership, transfers, availability/news, FPL `ep_next`, set-piece orders, and provenance known at that capture. Snapshot identity is never filled from end-of-season metadata; unavailable source identity remains null.
- `quarantined_source_metadata`: Vaastav ownership, value, and transfer fields whose independent capture time is not proven. These are audit-only.

Vaastav `xP` is absent from every output table. The 2024/25 `mng_*` fields are also excluded. Assistant Manager position `AM` is retained to preserve the pinned 27,605-row/804-element contract, but those elements are club-manager slots: a real-manager change can change the person code within one element. The quality report audits this exception, and AM must not be treated as a normal cross-season football-player identity.

## Leakage boundary

Historical schema fields are separated into explicit information classes:

- realised outcomes are post-match facts and cannot predict the same gameweek;
- pre-deadline state comes only from an accepted archive snapshot;
- deadline context is restricted to season, target gameweek, and exact deadline;
- final fixture identity, assignment, teams, opponent, home/away, kickoff, difficulty and status remain post-event fixture context;
- unverified-timing fields stay quarantined.

For each gameweek, the selector accepts only the latest snapshot where the target event is `is_next`, its deadline exactly matches the recorded deadline, and capture is strictly before that deadline. A post-deadline capture is never accepted. Missing snapshots are not interpolated or backfilled, and missing values are never converted to zero. Because the pinned inputs do not preserve fixture-list snapshots at every deadline, no fixture ID, opponent, home/away flag, kickoff, difficulty, score, played minutes, started/finished flag, or rescheduling state is attached to `player_deadline_snapshots`.

All fixtures in a double gameweek share one gameweek-deadline information cutoff. The first fixture's outcomes therefore cannot become information for the second fixture. This milestone creates no modelling features.

## Validation and reproducibility

Current ingestion retains its required-field, unique-ID, and foreign-key validation. Historical processing additionally checks:

- the explicitly selected season-specific Vaastav schema and required types;
- unique season-qualified player, team, fixture, fact, and snapshot keys;
- player/fixture/team foreign keys and fixture-derived player team/opponent;
- UTC timestamps, exact deadlines, and capture strictly before deadline;
- expected, fixture-bearing, missing, and snapshot-covered gameweeks;
- null counts, duplicate counts, and source/processed row counts;
- configured expectations: 380 fixtures and 38 fixture-bearing gameweeks per season; 2023/24 has 29,725 facts and 865 fact elements, while 2024/25 has 27,605 and 804.
- Vaastav fixture-level `total_points`, summed by player/Gameweek, against `fplcache` `event_points` from a later snapshot where that event is both `finished` and `data_checked`.

Vaastav `merged_gw.csv` remains canonical for fixture-grain `total_points`; `fplcache` is the independent Gameweek-total check. Reconciliation coverage is `compared_row_count / eligible_row_count`: eligible rows are the unique `(season, gameweek, element)` totals obtained by summing canonical fixture rows, while compared rows additionally have an integer `event_points` in a later snapshot whose event is `finished` and `data_checked`. For both verified seasons reconciliation is required and the tracked minimum coverage is `1.0`. No eligible rows, no usable comparisons, coverage below the threshold, or any points mismatch fails the build. Only a season explicitly configured with optional reconciliation may record `skipped_optional`.

The standalone reconciliation artifact records coverage counts, unmatched reasons, policy, threshold, both identities, creation time, provider/repository/revision/path provenance, and its processed-file hash in the manifest. Gameweek 38 uses `cache/2024/5/20/0625.json.xz` for 2023/24 and `cache/2025/5/26/0206.json.xz` for 2024/25.

Vaastav schemas are registered by schema ID and restricted to declared seasons. The 2024/25 definition records disjoint required, optional, ignored, quarantined, and forbidden categories; executable trusted and quarantine mappings; expected types and metrics; and known exceptions. A small declarative normalisation adapter validates each source value and maps it to canonical names before generic transformations run. Integer, finite decimal, explicit `True`/`False`, string/enumeration, nullability, and UTC ISO-8601 rules are enforced with row-level diagnostics. Validation rejects duplicate or overlapping declarations, undeclared mapping sources, ambiguous canonical or quarantine targets, malformed schemas/adapters, and every mapping from a forbidden field. `xP` is structurally forbidden from mapping to any output. Reports separately list required-present/missing, optional-present/absent, unexpected, ignored, quarantined, and encountered-forbidden columns; an absent optional target remains null. The verified `vaastav-2023-24-v1` definition reuses the inspected common mappings, removes the absent manager and `modified` fields, and restricts fixture positions to GK/DEF/MID/FWD. No generic transformation or reconciliation change was needed.

Every new processed build owns `source_inventory.json`, an atomic frozen copy of its canonicalised, materially consumed records. Exact duplicate registrations merge their sorted roles; conflicting registrations or any mismatch between resolved dependencies and actual consumption fail. Its portable relative path, SHA-256, full source identity, and source-identity hash are recorded in the processed manifest and catalogue. Raw files remain shared without duplication, but later additions to the raw cache cannot change a successful build's provenance, identity, or CSVs. Catalogue schema v2 retains a version-indexed build history as well as the latest-successful lookup.

Builds created before this contract are readable as `legacy_shared_raw_inventory` only while their original shared raw inventory still matches the checksum recorded in their manifest. They are never rewritten or retroactively described as frozen. `load_historical_build(season, version, output_dir)` performs the explicit checksum-verified compatibility lookup.

A table-quality failure does not update `catalogue.json`. It is retained under `data/historical/failed/<season>/` with a unique attempt timestamp, failure status, dataset version, both identity hashes, and `catalogue_updated: false`. Manifest and catalogue writes are atomic. A successful rerun verifies both identities and all raw and processed checksums, then reuses the same build without network access or rewriting data. A same-path content collision fails instead of overwriting immutable raw data.

## Assumptions and limitations

- Historical support currently covers verified 2023/24 and 2024/25. The eventual range is 2021/22–2025/26.
- `fplcache` capture filenames are interpreted as UTC because the pinned archive is generated by GitHub Actions' UTC runner.
- Assistant Manager elements have club-slot rather than stable person identity semantics.
- CSV is retained for portability and zero dependencies; downstream readers must apply `schemas.json`.
- There is no retry/backoff, database, scheduler, orchestration framework, feature pipeline, model, prediction, or optimiser.
- Current endpoint responses are sequential rather than an atomic upstream snapshot.
- Data use and redistribution require a separate review; see [DATA_NOTICE.md](DATA_NOTICE.md).

For wider context, see [PROJECT_VISION.md](PROJECT_VISION.md), [ROADMAP.md](ROADMAP.md), [PROJECT_STATE.md](PROJECT_STATE.md), and [DECISIONS.md](DECISIONS.md).
