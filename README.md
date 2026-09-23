# FPL AI Platform

## Frozen uncertainty and prospective scoring (M5C)

M5C adds fixed empirical 50%, 80% and 90% prediction intervals to the unchanged
M5B GW+0..4 forecasts. Separate complete-window residual pools supply cumulative
three/five-GW intervals. Calibration uses consumed 2025/26 historical evidence;
its quality must be assessed prospectively, and scoring never refits it.

```bash
.venv/bin/python -m fpl_ai uncertainty calibrate
.venv/bin/python -m fpl_ai uncertainty freeze --projections-dir "$PROJECTIONS" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL"
.venv/bin/python -m fpl_ai uncertainty verify --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL"
# Only after this target GW is authoritatively complete and checked:
.venv/bin/python -m fpl_ai uncertainty settle --uncertainty-dir "$UNCERTAINTY" \
  --calibration-dir "$CALIBRATION" --m4e-model-dir "$M4E_MODEL" --gameweek 6
.venv/bin/python -m fpl_ai uncertainty score --calibration-dir "$CALIBRATION" \
  --m4e-model-dir "$M4E_MODEL" --settlement-pair "$UNCERTAINTY" "$SETTLEMENT"
```

Add repeated `--settlement-pair` arguments as targets complete, including across
projections. Reports expose each target, horizon, position and aggregate errors,
interval coverage/widths, missingness and small-sample flags. Complete-window
cumulative scoring waits for all relevant outcomes; single targets do not.
Use `score --uncertainty-dir ...` without settlement pairs for a pending report.
Repeated evidence is deduplicated; conflicting versions fail for explicit review.

New families live under `data/multi_uncertainty/`, separately from original point
forecasts and outcomes. New freezes use actual clocks; `verify` reuses existing
attestations without redating. Calibration is fixed for 2026/27; point models and
the expected-points optimiser remain unchanged. Broad horizon-only intervals do
not provide player-conditional guarantees or a joint Monte Carlo distribution.

**279 tests pass normally and under optimized Python.** The real GW6–10 projection
has verified uncertainty, but its targets remain unfinished/unchecked as of the
September 23 API observation. No real coverage score is claimed. The full-population
planner profile reproduces the accepted top-three decision in 110.84s; no heuristic
or ranking change was made. See [exact commands, identities and evidence](docs/M5C_VERIFICATION.md)
and Decisions 053–056.

## Multi-Gameweek projections and transfer paths (M5B)

`project fit`, `project freeze` and `project verify` provide five direct,
horizon-specific points models from one frozen deadline state. `plan` evolves
your squad, exact selling prices, bank, free transfers and hits across those GWs,
selecting the best legal XI/captain each week. It returns deterministic complete
paths, a no-transfer baseline and a sequential greedy comparison.

```bash
.venv/bin/python -m fpl_ai plan --projections-dir "$PROJECTIONS" \
  --model-dir "$MULTI_MODEL" --m4e-model-dir "$M4E_MODEL" \
  --squad my-squad.json --horizon 5 --max-transfers 2 --top-n 3
```

`--max-transfers` is a per-GW search limit. Planning is offline; `project freeze`
requires the actual clock to precede the target deadline. Prices and strict
snapshot selectability stay static across the horizon. Initial selling prices
remain exact; purchased players later sell at their static purchase price.
There are no chips, fixture predictors, speculative prices or risk penalties.

GW+0 is explicitly distinct from M4E because the direct family uses a larger
historical fitting population. Later forecasts are separate trained targets,
never copies/scalings of the M4E forecast. Both M4E models remain frozen.
2025/26 evaluation is consumed historical evidence, not a new untouched holdout.
Projected plan gains do not establish realised FPL improvement.

See [M5B verification, results and exact commands](docs/M5B_VERIFICATION.md),
[independent oracle evidence](docs/M5B_ORACLE.json), and Decisions 050–052.
New immutable products live under `data/multi_projection/` and
`data/transfer_paths/`; existing M4E and M5A products retain their contracts.

## One-Gameweek transfer optimiser v1 (M5A)

`python -m fpl_ai optimise` consumes an immutable M4E forecast, an explicit
`--model control|v2`, and your `current-squad-v1` JSON. Supply all 15 element IDs,
exact selling prices, bank (integer £0.1m units) and available free transfers.
It returns ranked legal transfer plans, optimal XI/captain, transfer hits, bank
and gain against an explicit no-transfer baseline. SciPy/HiGHS solves the joint
squad/XI/captain problem; no dependency or model change is needed. Incoming players
must have boolean `can_select=true` in the exact frozen forecast snapshot.
Already-owned unselectable players may remain; missing/malformed flags fail closed.
Reports distinguish the full forecast population from transfer-in eligibility.
Verified GW6 counts are 659 forecast rows and 554 selectable players. The exact
objective tie band remains inclusive <=1e-6 points. Solver scaling is numerical
conditioning. Structural constraints remain independently checked after rounding;
objective-row candidates reach the exact Fraction check without an intervening
numerical residual cutoff. Admission to that check is not acceptance into the tie
band: out-of-band squads are excluded and retried. Both reviewer cases and 1,600
exhaustive small-population comparisons pass in normal and optimized Python;
see Decision 049 and the verification record.

```bash
.venv/bin/python -m fpl_ai optimise --forecast-dir "$FORECAST" --model-dir "$MODEL" \
  --model control --squad my-squad.json --max-transfers 2 --top-n 3
```

See [complete commands, input contract and verification](docs/M5A_VERIFICATION.md)
and the [synthetic demo input](tests/fixtures/optimiser/demo_gw6_squad.json).
Outputs are immutable under `data/decisions/<identity>/`, with an inspectable
`report.md`, complete plans/population, rules and provenance. Identical reruns
verify/reuse content without rewriting. This single-GW objective is XI points plus
captain bonus minus hits; it cannot value rolling transfers, future fixtures,
uncertainty, chips or multi-GW flexibility. M4E prospective evaluation continues
independently. No demo result is a recommendation for your actual team.

## Current-season prospective xPts (M4E)

The CLI now supports `prospective xpts fit`, `freeze`, `verify` and `score`.
It reuses existing snapshot/minutes capture and settlement commands. Fixed control
and v2 models use identical prior-season training and live populations; v2 adds
verified expected minutes. Earlier settled points history is provenance-backed;
missing history stays missing. Actual computation and final publication verification
must precede the authoritative deadline, with no timestamp override.

A real 659-player 2026/27 GW6 forecast was published on September 18 at 21:07 UTC,
before its October 10 10:00 UTC deadline. It is an early forecast with missing
retained history, not a quality result. GW5's minutes evidence is unchanged and
has no retrospective xPts forecast. No live xPts score exists yet.

See [M4E verification](docs/M4E_VERIFICATION.md) for exact model identities,
commands, fitting cutoffs, evidence and limitations. M4D's historical evidence is
mixed; both models remain available and require new prospective evaluation before
any claim of better FPL decisions. M5A now adds the one-Gameweek decision layer described below.


Data foundation for an AI-powered Fantasy Premier League analytics platform. Milestone 1 downloads current public FPL data; Milestone 2 builds reproducible, leakage-classified historical tables for the complete 2021/22–2025/26 range. Milestones 2 and 3 are complete: deadline-safe features and chronological non-ML baseline evaluation now build offline from those historical inputs. Milestone 4 now adds reproducible trained regressors and a frozen-model holdout workflow. The selected model improves the frozen next-GW prediction benchmark. M4B now adds independently evidenced playing-time features, a bounded expected-minutes model, and a CLI for immutable prospective forecasts and separate settled scoring. M4C adds annual chronological OOS minutes artifacts with guarded downstream eligibility and a verified real 2026/27 GW5 forecast. M4D adds a fixed historical xPts-v2 ablation using verified OOS expected minutes: modest RMSE/MAE gains over its matched control, but weaker top-10 realised points. M5A adds rules-aware one-Gameweek transfer plans; M5B adds separately trained multi-horizon forecasts and legal multi-Gameweek transfer paths.

## Quick start

Python 3.11 or newer is required. Install the pinned small scikit-learn numerical stack for modelling and the full test suite. Ingestion modules still use the standard library.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

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
- There is no retry/backoff, database, scheduler, orchestration framework. Offline features and trained experiments are implemented; live model serving is not.
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
satisfied; the first Milestone 4 trained experiment is now verified below. See
[full verification and reproducible commands](docs/M3_VERIFICATION.md) and
[Decisions 031–035](DECISIONS.md). Fixture strength, other outcome-statistic features,
and cross-season player linking remain unimplemented.

M3 hardening requires matching integer settlement evidence for every non-null
label, including all 4,553 empty-player zeros. Missing or disagreeing evidence fails.
Identity `serialized-products-v2` covers the actual derived population, predictions,
metrics and serialization rather than selected source-code hashes. Reuse costs a
fresh computation but never rewrites published files. Verification remains active
under `PYTHONOPTIMIZE=1`; see the M3 verification record for both executed runs.

## Milestone 4: reproducible trained experiments

The first batch compares Ridge (alpha 10/100) and histogram gradient boosting
(15/31 leaves) using the frozen M3 artifacts. Median imputation, numeric scaling
and categorical encoding fit only labelled 2021/22–2023/24 training rows. Original
missingness flags remain intact; season-local team ID and its flag are explicitly
excluded, leaving 25 inputs. No new features, target changes or fixture context.

```bash
M3=data/modelling/57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a
python -m fpl_ai experiment validate --m3-dir "$M3"
# Use the published validation directory printed by the previous command:
FREEZE=data/experiments/09eb67bd0fc9198073c28f921e3ba0ffd67876f341d32a97dc0f76743e0d411c
python -m fpl_ai experiment holdout --m3-dir "$M3" --frozen-dir "$FREEZE"
```

Validation-only RMSE selects `hist_15`; its fitted pipeline and configuration are
published before test evaluation. There is no validation refit, early stopping or
prediction clipping. Only the saved winner is evaluated on 2025/26. Validation
MAE/RMSE/Spearman: **0.9853 / 1.9164 / 0.7269**. Separate holdout:
**0.9537 / 1.9164 / 0.7415**, with full coverage. Holdout RMSE is 8.2% lower than
player scoring rate and 9.7% lower than archived FPL ep_next. All five baselines,
position/history segments, negative predictions and uncertainty remain reported.

Immutable outputs live under ignored `data/experiments/<identity>/` and
`data/experiment_holdouts/<identity>/`. Manifests identify upstream M3/source/build
provenance, contracts, preprocessing, dependency versions, seeds, model state,
keyed predictions, metrics, diagnostics and checksums. Fresh runs reproduce all
saved bytes in the recorded environment; same-root reuse verifies without rewriting.
Use only trusted locally generated pickle bundles. Data remains separate from models.

**145 tests pass**; M2/M3 rebuilds, complete artifact replay and 17 raw anomaly traces
pass. The narrow M4 exit criterion is satisfied by held-out prediction gains; this
is not yet squad/captain/transfer utility evidence. Small negative forecasts and
2025/26 defender underprediction remain known limitations. Next: targeted,
independently proven point-in-time feature expansion and prospective evaluation.

See [the complete experiment record and reproduction commands](docs/M4_VERIFICATION.md),
[machine-readable results](docs/M4_VERIFICATION.json),
[source sanity traces](docs/M4_SANITY_TRACES.json),
[upstream preservation evidence](docs/M4_REGRESSION.json), and Decisions 036–037.


## M4B: expected minutes and prospective evaluation

The new `playing-time-v2` contract is separate from frozen M3/M4. It admits
independently reconciled earlier-GW minutes, observed cumulative minutes/starts,
and availability changes with explicit missingness. Stale GW1 cumulative values
are excluded. Historical fixture context remains unavailable; the GW18 207-minute
freshness exception is preserved.

Train **2021/22–2022/23**, develop **2023/24**. A single fixed histogram model has
development minutes MAE **12.6596**, RMSE **23.2921**; the availability-aware recent
baseline has MAE **12.3024**, RMSE **25.3470**. Thus RMSE improves while MAE does not.
Neither 2024/25 nor consumed 2025/26 selects or evaluates the new model. A separate
2024/25 source audit finds a minutes discrepancy; no correction is fabricated.

```bash
.venv/bin/python -m fpl_ai minutes features
.venv/bin/python -m fpl_ai minutes train --features-dir data/playing_time/4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c
.venv/bin/python -m fpl_ai prospective --help
```

`prospective capture` freezes official bootstrap/fixtures before a future deadline;
`freeze` generates expected minutes with exact source/model provenance; `settle`
captures settled live per-GW evidence; `score` publishes separate metrics and leaves
the forecast unchanged. `verify` checks an existing forecast without re-dating it.
M4C subsequently verified a real GW5 minutes forecast. The original minutes-only
product retains null expected points; M4E publishes control/v2 points separately.
No in-sample minutes predictions are exported for downstream xPts training.

Modules: `playing_time.py` (evidence/features), `minutes.py` (bounded experiment),
`prospective.py` (capture/freeze/settle/score), with shared immutable experiment IO.
Generated bundles use separate ignored `data/playing_time/`, `data/minutes/` and
`data/prospective_*/` roots. No new dependency or scheduler.

See [M4B verification](docs/M4B_VERIFICATION.md) for exact contracts, metrics,
operational commands, limitations and all 176 tests; [machine source evidence](docs/M4B_SOURCE_AUDIT.json)
and [regression preservation](docs/M4B_REGRESSION.json) accompany it.

Blank-GW evidence is now explicit: prospective capture/settlement/scoring rejects
empty, missing or structurally unusable season schedules. A nonempty schedule with
valid team/event assignments can establish a target-specific blank. Historical
minutes labels use processed `fixtures.csv` to determine fixture-bearing GWs and
require player facts for every scheduled fixture. This is label validation only;
no final fixture field becomes a historical predictor. See Decision 041 and the
M4B verification record for new identities and unchanged model results.


## M4C: chronological OOS minutes and real prospective evidence

`minutes oos` keeps M4B selection fixed from 2023/24, then refits the unchanged
candidate once per season on the expanding prior-season population. It provides
**56,804 downstream-safe forecasts**, GW1–38 of 2024/25 (27,159) and 2025/26 (29,645).
The 80,858 earlier rows have null predictions and explicit unavailability. All
fitting/preprocessing/fallback and selection evidence precedes each prediction's
capture. This is historical walk-forward evidence, not a new untouched holdout.

```bash
FEATURES=data/playing_time/4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c
MINUTES=data/minutes/e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m fpl_ai minutes oos --features-dir "$FEATURES" --model-dir "$MINUTES"
```

The new `fpl_ai.minutes_oos` module reuses the existing feature projection, fitted
candidate, baselines and atomic publication. `data/minutes_oos/<identity>/` contains
predictions, features/audits, complete fitting populations, per-season model states,
source evidence and protocol. `data/minutes_oos/scores/<identity>/` separately
contains realised outcomes and diagnostics. No current or frozen M4B artifact is
rewritten. `load_downstream(Path(OOS_DIR))` verifies this specific artifact family
and eligibility before returning forecast rows; passing a development freeze fails.
That batch added no xPts stacking; the separate M4D integration below now consumes this boundary.

Ferguson's 2024/25 GW27 target remains unresolved (34 observed versus 17 canonical).
Pinned neighbours show a later +17 cumulative change after settlement. One target
is excluded; its value never enters later history. His cumulative minutes feature
is masked in GW28–38, while independently reconciled deltas and unrelated players
remain available. Details: [discrepancy report](docs/M4C_DISCREPANCY.md).

On September 18, 2026, the real CLI captured and froze **659 GW5 forecasts** at
08:27:13.598395 UTC, before the authoritative 17:30 deadline. Verification passed;
the live settlement command correctly rejected the upcoming event. No settlement,
score or model-quality claim is made yet. The forecast has no prior prospective
history and expected points remains null. Exact identities and next-stage commands:
[live record](docs/M4C_LIVE.json), [M4C verification](docs/M4C_VERIFICATION.md).

The verification record includes the exact chronological protocol, per-season/GW
and segment diagnostics, checksums, deterministic rebuild/reuse, 186 normal/optimized
tests, and preservation of all 664 pre-batch data files in both bytes and mtimes.
The earlier M4/M4B sections above describe their frozen evidence; this new family
does not retrospectively change the meaning of those development predictions.


## M4D: bounded xPts v2 using OOS expected minutes

```bash
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m fpl_ai.xpts_v2
```

This command accepts the exact verified M3/M4C products, joins **56,804** forecasts
by player/GW plus capture, deadline, snapshot and build provenance, and fits two
fixed M4 `hist_15` pipelines on the same **27,159 2024/25 rows**. The control uses
the original 25 inputs; v2 adds only predicted total GW minutes. Both are evaluated
on the same **29,645 2025/26 rows**. No search or early stopping is performed.
2025/26 is already-consumed historical evidence, **not a fresh holdout**.

| Model | RMSE | MAE | Mean GW Spearman | Top-10 realised points |
| --- | ---: | ---: | ---: | ---: |
| Matched control | 1.925490 | 0.952499 | 0.738961 | 5.050000 |
| xPts v2 | 1.916745 | 0.932555 | 0.744086 | 4.815789 |
| Frozen M4 (different fitting population) | 1.916449 | 0.953678 | 0.741470 | 4.721053 |

V2 improves the primary matched-ablation RMSE by 0.008745 (about 0.45%) but worsens
top-10 realised points by 0.234211. This is mixed historical evidence, not proof of
transfer or captaincy utility. No earlier OOS minutes are fabricated. Ferguson's
pre-GW27 forecast is retained because its points target is independently valid;
no realised minutes or future correction enters the feature table.

`fpl_ai/xpts_v2.py` provides the adapter, fixed models, metrics and verification;
`scripts/verify_xpts_v2.py` independently reconstructs point evidence and joins,
replays models, probes invalid artifacts, and checks deterministic rebuild/reuse.
Predictions/features/models use immutable `data/xpts_v2/<identity>/`; outcomes and
metrics use separate `data/xpts_v2/scores/<identity>/`. No prior artifact is rewritten.
Missing forecasts or points stay audited and excluded, never filled with zero.

See [M4D verification](docs/M4D_VERIFICATION.md), [machine evidence](docs/M4D_VERIFICATION.json)
and [regression/preservation](docs/M4D_REGRESSION.json) for exact identities, feature
order, all diagnostics, tests and limitations. The prospective GW5 lifecycle remains
separate. M4E now provides the current-season adapter described above; M5A consumes it for one-Gameweek transfer decisions.
