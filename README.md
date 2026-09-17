# FPL AI Platform

Data foundation for an AI-powered Fantasy Premier League analytics platform. Milestone 1 downloads current public FPL data; Milestone 2 builds reproducible, leakage-classified historical tables for the complete 2021/22–2025/26 range. Milestones 2 and 3 are complete: deadline-safe features and chronological non-ML baseline evaluation now build offline from those historical inputs. The project does **not** contain trained predictive models, optimisation, or recommendations.

## Quick start

Python 3.11 or newer is required. The pipelines and tests have no third-party runtime dependencies.

```bash
python3 -m venv .venv
source .venv/bin/activate

# Existing Milestone 1 current snapshot
python -m fpl_ai --output-dir data

# Pinned Milestone 2 historical seasons
python -m fpl_ai historical --season 2021-22 --output-dir data
python -m fpl_ai historical --season 2022-23 --output-dir data
python -m fpl_ai historical --season 2023-24 --output-dir data
python -m fpl_ai historical --season 2024-25 --output-dir data
python -m fpl_ai historical --season 2025-26 --output-dir data

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

### Historical 2021/22–2025/26

All five seasons use the same two immutable repository revisions, inspected for their respective season files:

| Provider | Pinned revision | Use |
| --- | --- | --- |
| [vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League) | `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` | Player-fixture outcomes, season identities, teams, and fixtures. |
| [Randdalf/fplcache](https://github.com/Randdalf/fplcache) | `33dac28d18953bee5bc4bd56ddd8a5e32e169d68` | Compressed historical `bootstrap-static` captures. |

`fpl_ai/historical_sources.json` records repositories, configured refs, resolved immutable commit SHAs, required paths, expected gameweeks, season audit counts, the selected Vaastav source-schema ID/version, and the season's reconciliation policy. No moving `master` or `main` ref is accepted. Every downloaded file is retained byte-for-byte under `data/historical/raw/` and recorded with requested season, provider, repository, configured ref, resolved commit, source path and URL, retrieval time, SHA-256, and byte size.

Provenance has two deliberately separate hashes. `source_identity_sha256` identifies only pinned immutable artifacts that materially participated in the build, including their paths, content hashes, sizes, and deterministic consumption roles. Rejected snapshot candidates and unrelated cached files may remain in the mutable raw-cache manifest for operational audit, but they are excluded from the frozen consumed inventory and source identity. `build_identity_sha256` identifies the transformation contract, canonical schema contract, season expectations, snapshot-selection settings, selected source schema, and reconciliation policy. Timestamps, local output paths, cache contents, and discovery order are excluded from deterministic identities. This permits two semantic builds from the same sources without overwriting one another.

### Verified 2021/22 batch

The normal historical command publishes 38 Gameweeks, 737 players, 20 teams,
380 fixtures, 25,447 fixture facts and 25,150 deadline observations. All **43/43**
quality checks pass, with **38/38** snapshot coverage and **23,230/23,230** exact
settled-event points comparisons (coverage 1.0, zero unmatched or mismatching).
Unavailable starts and expected metrics remain null. The scoped `GKP -> GK` and
78-row delayed-kickoff normalization policies remain unchanged.

GW18 uses one explicitly authorized **superseded-deadline exception**:
`cache/2021/12/18/1233.json.xz`, SHA-256
`9c8fbad59eecb978494d98425e0dadcfa16fbb3a3954f99b4263c65277e2eed1`.
The payload still says **13:30**, while the authoritative deadline remains **16:00**.
Player state is observed **as of 12:33 UTC**, before both deadlines, with a
**3-hour-27-minute freshness gap**. This does not establish state immediately before
16:00. The 18:25 capture remains forbidden. Every other snapshot uses the normal
exact-deadline rule. Policy identity, hash, both deadlines, capture age and reason
are retained in quality and audit evidence; raw bytes are unchanged.

Independent settlement selection is separate from this eligibility exception.
It still reconciles every eligible total, including all 460 GW17 totals and Daniel
James's GW3 value of 1. The later settled-value mutation is diagnostic only.

Build: `v3-9779cdbc0c07-33dac28d1895-build-5644015b364e`.
See [the acceptance record](docs/M2_2021_22_VERIFICATION.md) and
[cross-season audit](docs/M2_CROSS_SEASON_AUDIT.json). The
[source-search log](docs/M2_2021_22_SOURCE_SEARCH.json) remains historical evidence;
no exact-final-deadline GW18 capture was discovered.

Default audits derive supported seasons from successful catalogue entries and now
include all five seasons. `--season` explicitly selects published seasons;
`--investigate-season` is for unpublished attempts and rejects published seasons.
Publication, not a hard-coded status, moved 2021/22 into normal verification.

```bash
PYTHONPATH=. python scripts/verify_historical_seasons.py --report /tmp/published-audit.json
PYTHONPATH=. python scripts/verify_historical_seasons.py --season 2021-22 --report /tmp/selected-audit.json
```

### Verified 2022/23 batch

The same pipeline produces 38 gameweeks, 778 players, 20 teams, 380 fixtures,
26,505 fixture facts and 26,198 deadline observations. All 44 quality checks pass;
24,957 eligible player/Gameweek totals reconcile exactly at required coverage `1.0`.
GW7 has deadline observations and no fixtures; zero fixture rows are invented.
The four source headers match 2023/24, including starts and expected metrics.

Two exact GW1 person-code exceptions preserve the observed codes for Luke Harris
and Hugo Bueno. The codes change by GW2; the pipeline does not backfill corrected
codes into GW1. Exceptions are versioned in build identity, require the exact
source path and code pair, and fail if missing or stale. Every other football-player
code mismatch remains a hard failure. Downstream cross-season identity joins must
account for these documented source code changes.

Build: `v3-9779cdbc0c07-33dac28d1895-build-9227d246d371`.
See [the verification record](docs/M2_2022_23_VERIFICATION.md) and
[cross-season audit](docs/M2_CROSS_SEASON_AUDIT.json).

After ingesting the supported seasons, repeat the default offline audit:

```bash
PYTHONPATH=. python scripts/verify_historical_seasons.py --report /tmp/historical-audit.json
```

It verifies published canonical schemas, all deadline cutoffs, complete home/away
fixture coverage, important missingness, settled points reconciliation, fresh
rebuilds and checksum-verified reuse. It also reports final cumulative points
separately: 2024/25 Ferguson has 27 fixture points versus 28 final aggregate points,
a pinned upstream inconsistency documented in the verification record.

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

### Verified 2025/26 and five-season closure

The normal command publishes 38 Gameweeks, 841 players, 20 teams, 380 fixtures,
29,747 unique fixture facts and 29,645 deadline rows. All **43/43** quality checks
pass, with **38/38** pre-deadline captures and **29,338/29,338** settled points
comparisons (coverage 1.0, zero unexplained mismatches). Both existing provider pins
suffice; the observed schema is `vaastav-2025-26-v1`.

Ten exactly repeated merged rows arise in overlapping renamed player histories.
A season/commit/file-hash/key/count-bound policy retains one copy only when every
raw field agrees; all other duplicate/conflict cases fail. Raw files remain intact.
New defensive statistics and partial-season metadata are retained in pinned raw
sources and deliberately excluded from the unchanged common canonical schema.

2025/26 captures precede deadlines by 22 minutes–5h35. GW38 uses May 24 08:39,
not the 13:49 payload captured after its 13:30 deadline despite `is_next=true`.
Sillah's later final identity is not backfilled into the deadline snapshot. Final
settlement is May 25 10:23, after earlier captures still reported unsettled flags.

Build: `v3-9779cdbc0c07-33dac28d1895-build-0fa66b641643`.
All five seasons pass fresh offline rebuilds and checksum-verified reuse. All earlier
published files, identities and catalogue entries remain unchanged. The full-range
audit rechecks raw deadline observations, settlement timing, field availability,
identity and fixture structure; the authorized 2021/22 GW18 3h27 freshness limitation
and all other documented anomalies remain intact.

See [2025/26 verification](docs/M2_2025_26_VERIFICATION.md),
[source evidence](docs/M2_2025_26_SOURCE_AUDIT.json),
[field availability and identity guide](docs/M2_FIVE_SEASON_AVAILABILITY.md), and
[the machine-readable full-range audit](docs/M2_CROSS_SEASON_AUDIT.json).

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

- `gameweeks`: every scheduled gameweek, including the fixture-empty 2022/23 GW7; deadline, selected capture, hours before deadline, source path, and coverage flag.
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

For each gameweek, the selector accepts only the latest snapshot where the target event is `is_next`, its deadline exactly matches the recorded deadline, and capture is strictly before that deadline. The sole superseded-deadline exception is the exact 2021/22 GW18 case documented above; its capture precedes both deadlines. A post-deadline capture is never accepted. Missing snapshots are not interpolated or backfilled, and missing values are never converted to zero. Because the pinned inputs do not preserve fixture-list snapshots at every deadline, no fixture ID, opponent, home/away flag, kickoff, difficulty, score, played minutes, started/finished flag, or rescheduling state is attached to `player_deadline_snapshots`.

All fixtures in a double gameweek share one gameweek-deadline information cutoff. The first fixture's outcomes therefore cannot become information for the second fixture. This milestone creates no modelling features.

## Validation and reproducibility

Current ingestion retains its required-field, unique-ID, and foreign-key validation. Historical processing additionally checks:

- the explicitly selected season-specific Vaastav schema and required types;
- unique season-qualified player, team, fixture, fact, and snapshot keys;
- player/fixture/team foreign keys and fixture-derived player team/opponent;
- UTC timestamps, exact deadlines, and capture strictly before deadline;
- expected, fixture-bearing, missing, and snapshot-covered gameweeks;
- null counts, duplicate counts, and source/processed row counts;
- configured expectations: 380 fixtures per season; 2022/23 has 37 fixture-bearing gameweeks, 26,505 facts and 778 fact elements; 2023/24 has 29,725 facts and 865 fact elements, while 2024/25 has 27,605 and 804, and 2025/26 has 29,747 unique facts and 841 players.
- Vaastav fixture-level `total_points`, summed by player/Gameweek, against `fplcache` `event_points` from a later snapshot where that event is both `finished` and `data_checked`.

Vaastav `merged_gw.csv` remains canonical for fixture-grain `total_points`; `fplcache` is the independent Gameweek-total check. Reconciliation coverage is `compared_row_count / eligible_row_count`: eligible rows are the unique `(season, gameweek, element)` totals obtained by summing canonical fixture rows, while compared rows additionally have an integer `event_points` in a later snapshot whose event is `finished` and `data_checked`. For all five verified seasons reconciliation is required and the tracked minimum coverage is `1.0`. No eligible rows, no usable comparisons, coverage below the threshold, or any points mismatch fails the build. Only a season explicitly configured with optional reconciliation may record `skipped_optional`.

The standalone reconciliation artifact records coverage counts, unmatched reasons, policy, threshold, both identities, creation time, provider/repository/revision/path provenance, and its processed-file hash in the manifest. Gameweek 38 uses `cache/2023/5/29/0623.json.xz` for 2022/23, `cache/2024/5/20/0625.json.xz` for 2023/24, `cache/2025/5/26/0206.json.xz` for 2024/25, and `cache/2026/5/25/1023.json.xz` for 2025/26.

Vaastav schemas are registered by schema ID and restricted to declared seasons. The 2024/25 definition records disjoint required, optional, ignored, quarantined, and forbidden categories; executable trusted and quarantine mappings; expected types and metrics; and known exceptions. A small declarative normalisation adapter validates each source value and maps it to canonical names before generic transformations run. Integer, finite decimal, explicit `True`/`False`, string/enumeration, nullability, and UTC ISO-8601 rules are enforced with row-level diagnostics. Validation rejects duplicate or overlapping declarations, undeclared mapping sources, ambiguous canonical or quarantine targets, malformed schemas/adapters, and every mapping from a forbidden field. `xP` is structurally forbidden from mapping to any output. Reports separately list required-present/missing, optional-present/absent, unexpected, ignored, quarantined, and encountered-forbidden columns; an absent optional target remains null. The verified `vaastav-2023-24-v1` definition reuses the inspected common mappings, removes the absent manager and `modified` fields, and restricts fixture positions to GK/DEF/MID/FWD. No generic transformation or reconciliation change was needed.

For 2021/22, `earliest_settled_current_event_v1` independently searches
strictly after final fixture kickoff plus two hours (and the event deadline), and
before the next deadline or seven days after final kickoff, whichever comes first.
It chooses the earliest archived current-event payload with exact event deadline
and both settlement flags true. The API does not timestamp settlement itself;
flags prove it had occurred by capture. The selector never receives canonical
player points. Every inspected candidate is consumed evidence; selection paths,
times, hashes, flags, bounds and reasons are recorded in reconciliation metadata.
Later settled-value mutations are diagnostic only. Accepted older seasons retain
their previous pinned comparison contracts and identities.

Every new processed build owns `source_inventory.json`, an atomic frozen copy of its canonicalised, materially consumed records. Exact duplicate registrations merge their sorted roles; conflicting registrations or any mismatch between resolved dependencies and actual consumption fail. Its portable relative path, SHA-256, full source identity, and source-identity hash are recorded in the processed manifest and catalogue. Raw files remain shared without duplication, but later additions to the raw cache cannot change a successful build's provenance, identity, or CSVs. Catalogue schema v2 retains a version-indexed build history as well as the latest-successful lookup.

Builds created before this contract are readable as `legacy_shared_raw_inventory` only while their original shared raw inventory still matches the checksum recorded in their manifest. They are never rewritten or retroactively described as frozen. `load_historical_build(season, version, output_dir)` performs the explicit checksum-verified compatibility lookup.

A table-quality failure does not update `catalogue.json`. It is retained under `data/historical/failed/<season>/` with a unique attempt timestamp, failure status, dataset version, both identity hashes, and `catalogue_updated: false`. Manifest and catalogue writes are atomic. A successful rerun verifies both identities and all raw and processed checksums, then reuses the same build without network access or rewriting data. A same-path content collision fails instead of overwriting immutable raw data.

## Assumptions and limitations

- Historical support covers the complete verified 2021/22–2025/26 range. New defensive/raw metadata fields are not part of the common canonical tables; see the five-season availability guide.
- `fplcache` capture filenames are interpreted as UTC because the pinned archive is generated by GitHub Actions' UTC runner.
- Assistant Manager elements have club-slot rather than stable person identity semantics.
- CSV is retained for portability and zero dependencies; downstream readers must apply `schemas.json`.
- There is no retry/backoff, database, scheduler, orchestration framework, feature pipeline, model, prediction, or optimiser.
- Current endpoint responses are sequential rather than an atomic upstream snapshot.
- Data use and redistribution require a separate review; see [DATA_NOTICE.md](DATA_NOTICE.md).

For wider context, see [PROJECT_VISION.md](PROJECT_VISION.md), [ROADMAP.md](ROADMAP.md), [PROJECT_STATE.md](PROJECT_STATE.md), and [DECISIONS.md](DECISIONS.md).

## Milestone 3: features and baseline evaluation

```bash
.venv/bin/python -m fpl_ai features
PYTHONPATH=. .venv/bin/python scripts/verify_modelling.py --report docs/M3_VERIFICATION.json
```

The command consumes the five published M2 builds without modifying them. It
predicts unmultiplied total points in one upcoming Gameweek for football players
present in its accepted snapshot, keyed by `(season, target_gameweek, element)`.
Doubles sum all fixture points. A player without fixture facts in a fixture-bearing
GW has an explicit empty-sum zero label; globally empty 2022/23 GW7 has null labels
and stays outside fitting/scoring. AM elements are excluded.

The 27 predictors comprise eight snapshot state fields, seven settlement-gated
points-history fields and 12 missingness flags. History is season-local, strictly
before the target GW, and independently observed settled by the accepted capture.
No final fixture context, final identity, quarantined metadata or Vaastav xP is used.
The 2021/22 GW18 12:33 state/207-minute freshness limitation remains in row metadata.

Train: 2021/22–2023/24; validation: 2024/25; final holdout: 2025/26. Overall/position
means fit only settled training labels. Recent-three-GW and player-season means use
available earlier observations, with declared cold-start fallbacks. Archived FPL
ep_next is an external benchmark, never an engineered predictor. MAE, RMSE and
within-GW Spearman include coverage and split/season/position breakdowns.

Artifacts are ignored under `data/modelling/<identity>/`: separate `features.csv`,
`labels.csv`, `predictions.csv`, `row_audit.csv`, `schema.json`, `evaluation.json`
and `manifest.json`. The manifest records exact M2 versions/source/build identities,
contracts and hashes of actual serialized products. Reuse regenerates candidate
outputs and requires the exact artifact set and every checksum;
fresh builds are deterministic across output roots. Use `--artifact-dir` for another
output root or `--builds-from <prior-manifest.json>` to pin exact historical versions.

Verified: **137,662 rows**, 137,038 labels, 132 passing tests, all five historical
offline rebuilds and independent row traces. The original M3 exit criterion is
satisfied; Milestone 4 predictive experiments are next. See
[full verification and reproducible commands](docs/M3_VERIFICATION.md) and
[Decisions 031–035](DECISIONS.md). Fixture strength, other outcome-statistic features,
cross-season player linking and trained models remain unimplemented.

M3 hardening requires matching integer settlement evidence for every non-null
label, including all 4,553 empty-player zeros. Missing or disagreeing evidence fails.
Identity `serialized-products-v2` covers the actual derived population, predictions,
metrics and serialization rather than selected source-code hashes. Reuse costs a
fresh computation but never rewrites published files. Verification remains active
under `PYTHONOPTIMIZE=1`; see the M3 verification record for both executed runs.
