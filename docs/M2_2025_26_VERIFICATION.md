# Milestone 2 — 2025/26 acceptance and five-season closure

Verified 2026-09-17. **Accepted and published. Milestone 2 exit criterion satisfied.**
No feature, evaluation, model, optimiser or recommendation implementation was added.

## Immutable sources and observed contracts

Both existing pins already contain the complete required season inputs:

- Vaastav: `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`.
- fplcache: `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`.

The newer archive revision `60211fa056c5bc195c4f9e2b2cc014767c4a2ab5` was inspected
only as discovery evidence. Its blobs for the 1,210 existing August 2025–May 2026
archive paths are unchanged. No configured provider revision or catalogue schema
version changed, and no moving ref participates in a build.

[Machine-readable source inspection](M2_2025_26_SOURCE_AUDIT.json) retains exact
URLs, SHA-256, byte sizes, tree evidence, all four CSV headers, field additions and
removals, empty counts, duplicate rows and final archive event evidence. Reproduce:

```bash
# Initial acquisition, if the separate inspection cache is absent:
PYTHONPATH=. .venv/bin/python scripts/inspect_historical_2025_26.py --acquire --report /tmp/source-audit.json
# Deterministic inspection of local pinned evidence:
PYTHONPATH=. .venv/bin/python scripts/inspect_historical_2025_26.py --report /tmp/source-audit.json
```

Observed inputs: 29,757 merged rows, 841 final players, 20 teams, 380 completed
fixtures, and 38 fixture-bearing Gameweeks. Exact schema `vaastav-2025-26-v1` uses
the existing typed declarative adapter. All real rows pass retained type contracts.

Compared with 2024/25:

- Merged outcomes add `clearances_blocks_interceptions`, `defensive_contribution`,
  `recoveries`, and `tackles`. All 29,757 source rows have integer values. The
  schema validates these fields but deliberately leaves them in immutable raw
  evidence rather than extending the seven shared canonical tables.
- Final players add those statistics plus `defensive_contribution_per_90`,
  `known_name`, `price_change_percent`, `scout_news_link`, and `scout_risks`.
- Teams add `link_url`; fixture headers are unchanged.
- All seven `mng_*` fields disappear from merged/final-player inputs. There are no
  Assistant Manager elements. Positions are GK/DEF/MID/FWD, without an alias.
- Starts, all four expected metrics, minutes, ownership/value/transfers and
  `modified` are present. Quarantine remains unchanged; Vaastav `xP` is forbidden.

## Exact duplicate evidence and policy

The initial build failed honestly on duplicate `(element, fixture)` keys and
published nothing. There are ten repeated keys, each occurring exactly twice:

- Element 391, Ben Doak / Ben Gannon-Doak: fixture 1, GW1.
- Element 100, Eli Junior Kroupi / Junior Kroupi: fixtures 1, 12, 29, 32, 42, 56,
  63, 73 and 83, GW1–9.

Every field of each repeated merged row is equal, including name, ignored fields,
quarantined fields and forbidden `xP`. The old player directories contain one and
nine rows; the renamed directories contain 38 rows each. Every overlapping
per-player row is identical. The evidence is consistent with duplicate aggregation
of overlapping renamed directories; no conflicting points are resolved by choice.

Version-1 `exact_duplicate_rows` configuration binds the entire merged SHA-256
`0d09f1f1cb1b5520ec8e2f25238aa652efe2a263d8ca7cb2b6538b27bf86727d`, season, revision,
source path, original 29,757 count, every key/Gameweek and exact occurrence count.
It retains the first raw row once per fixture. Hash/count changes, stale rules,
undeclared duplicates and any field conflict fail. Without the policy, the original
duplicate-key failure remains. Original CSV bytes are never rewritten.

The full policy enters build identity only when configured; all earlier seasons
retain v6 and their exact identities. The quality report's merged source-schema
audit records the original source count, ten removals and original retained/omitted
CSV record numbers. Its generic `source_row_counts` describes the 29,747 normalized
rows supplied to the transforms. See Decision 029.

## Published dataset

- Source version: `v3-9779cdbc0c07-33dac28d1895`.
- Build: `v3-9779cdbc0c07-33dac28d1895-build-0fa66b641643`.
- Source identity: `1bcdf1b685588c462bfd6b04a7c546a15d7ed295d85d33efedb9370b5a8a26ea`.
- Build identity: `0fa66b6416438b1149992ed4b8cae7d0cf8914bb47e48a08302f91d891c581e0`.
- Frozen inventory: 44 consumed artifacts; SHA-256
  `1b1cf8b00991fab11caf0a2ba2ff2ae415787c607f9e6cae364700bcd15e6fd1`.
- Output: 38 Gameweeks, 841 players, 20 teams, 380 fixtures, **29,747 fixture facts**,
  **29,645 deadline rows**, 29,747 quarantine rows; seven CSVs and five metadata files.
- **43/43 hard quality checks pass**; no duplicate canonical fact or snapshot keys.
- 18,255 zero-minute facts are preserved. Starts/expected metrics have no null facts.

Full CSV SHA-256 values are recorded under `seasons.2025-26` in the
[cross-season audit](M2_CROSS_SEASON_AUDIT.json).

## Deadlines and settlement

All 38 Gameweeks have an eligible snapshot with exact payload/reference deadline,
`is_next=true`, and capture strictly before the deadline. No exception is needed.
Capture ages span **22 minutes** (GW30) to **5h35** (GW18). Every canonical deadline
row was additionally compared with its exact raw observation, including team,
position, price, ownership, transfer, availability and news fields.

GW38 deadline is `2026-05-24T13:30:00Z`. Reference/accepted capture:
`cache/2026/5/24/0839.json.xz` (4h51 earlier). The 13:49 payload still says
`is_next=true` but is after the deadline and is rejected. Final player 841, Lamin
Sillah, is absent from the 840-player accepted GW38 capture. No later identity or
state is backfilled. All 29,645 deadline rows have team/position identity and prices;
27 elements change their observed team, and none changes position within the season.

Final settlement is `cache/2026/5/25/1023.json.xz`: both `finished` and `data_checked`
are true. May 24 19:25 and May 25 04:38 are still unsettled. Selection used timestamps
and flags before any comparison with canonical points. The established next-deadline
plus explicit final-settlement strategy suffices; no strategy or threshold changed.

**29,338 eligible player/Gameweek totals; 29,338 compared and matching; coverage
1.0; zero unmatched and zero mismatching rows.** All 841 cumulative player totals
also match fixture sums, reported separately from the primary settlement gate.
Raw settlement hashes, flags and capture-after-last-kickoff evidence are in the
expanded audit. Flags prove settlement by capture, not its exact transition time.

## Season structure and full-range audit

All five seasons pass fresh offline builds, manifest/source checksum validation,
canonical schema compatibility and reuse without byte or modification-time changes.
There are 190 accepted deadline captures across the five seasons. The authorized
2021/22 GW18 state remains as of 12:33, **3h27 before its final deadline**;
its exact path/hash/policy is revalidated. No generalized deadline exception exists.

Each season has 380 fixtures, 20 clubs, 38 fixtures per club, and exactly one of
each directed home/away pairing. 2022/23 retains fixture-empty GW7. In 2025/26, GW26
and GW36 have 11 fixtures, GW33 has 13, GW31 has eight and GW34 has seven; all other
Gameweeks have ten. The audit enumerates team-level blanks and doubles separately.

[Availability and identity guide](M2_FIVE_SEASON_AVAILABILITY.md) explains the field
classes and limitations. The expanded machine audit retains prior season entries
unchanged and adds per-season raw temporal checks, field availability/types,
team/position changes, final-vs-snapshot code differences and settlement timing.
Across the five seasons, 1,777 distinct non-AM final player codes occur; 1,016 occur
in multiple seasons, and 51 have different positions across seasons. There are no
duplicate final football-player codes within a season. 841 numeric element IDs are
reused for different people, so element alone is never a cross-season join key.

The earlier Luke Harris/Hugo Bueno code differences, AM slot semantics, `GKP` alias,
delayed fixture 263, independent 2021/22 settlement and Ferguson cumulative-total
inconsistency all remain represented and unmodified.

## Regression protection and actual verification

[Regression evidence](M2_2025_26_REGRESSION.json): all **112 pre-existing processed
files** retain their bytes and modification times, including legacy builds. All
four earlier source configurations, successful catalogue entries and original audit
season entries are equal to the saved pre-batch baseline. Fresh builds retain all
four source/build identities and all 28 canonical CSV hashes.

Commands actually run successfully:

```bash
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q fpl_ai scripts tests main.py
.venv/bin/python -m fpl_ai --help
.venv/bin/python -m fpl_ai historical --help
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --help
PYTHONPATH=. .venv/bin/python scripts/inspect_historical_2025_26.py --help
.venv/bin/python -m pip check
.venv/bin/python -m fpl_ai historical --season 2025-26 --output-dir data
PYTHONPATH=. .venv/bin/python scripts/inspect_historical_2025_26.py --report /tmp/source-audit.json
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report docs/M2_CROSS_SEASON_AUDIT.json
git diff --check
```

112 network-free tests pass (102 existing plus ten new). New tests include invalid
source types, removed fields/positions, forbidden mappings, duplicate hash/key/count
and conflict failures, unchanged old build identities, full synthetic publication,
reconciliation/inventory/reuse, raw deadline-state tampering, settlement timing,
source checksums and cross-season identity semantics. Initial test-fixture issues
were corrected; the final full suite passes. Conflicting CLI season options and
published/investigation audit mode conflicts return argparse status 2 as expected.
No dedicated lint/type checker is configured; no runtime dependency was added.

The live acquisition occurred only against immutable public URLs; every accepted
season was then freshly rebuilt using a local URL-to-bytes fetcher and reused with
a fetcher that raises on any network request. The source-inspection report also
reproduces offline. No commits or merges were made.

## Changed and created files

- `fpl_ai/historical_sources.json`: new season, observed counts, reference/settlement
  paths and exact duplicate policy; all older entries retained.
- `fpl_ai/historical_schema.py`: explicit observed 2025/26 source contract.
- `fpl_ai/historical_duplicates.py`: new exact duplicate validation/filtering.
- `fpl_ai/historical_transform.py` and `historical_pipeline.py`: opt-in policy
  execution, evidence and deterministic build identity.
- `fpl_ai/historical_audit.py`: new read-only temporal, availability and identity audit.
- `scripts/verify_historical_seasons.py`: expanded full-range audit integration.
- `scripts/inspect_historical_2025_26.py`: reproducible source inspection/acquisition.
- `tests/test_historical_2025_26.py`: ten deterministic tests with failure subcases.
- `tests/fixtures/historical_2025_26/`: four observed CSV samples, `events.json`
  excerpts and provenance `README.md`.
- `PROJECT_STATE.md`, `ROADMAP.md`, `README.md`: accepted range, milestone closure,
  limitations, usage and Milestone 3 design handoff.
- `DECISIONS.md`: material Decisions 029 and 030 only.
- `docs/M2_2025_26_VERIFICATION.md`, `M2_2025_26_SOURCE_AUDIT.json`,
  `M2_2025_26_REGRESSION.json`, `M2_FIVE_SEASON_AVAILABILITY.md`: new evidence/guide.
- `docs/M2_CROSS_SEASON_AUDIT.json`: five-season machine-readable audit.

Suggested commit message: `Complete Milestone 2 with verified 2025/26 data and five-season audit`.
No commit or merge was performed.

## Remaining limitations and handoff

Snapshots are periodic observations, not instantaneous deadline state. Unavailable
values remain null/empty. New defensive outcomes and partial-season metadata are
available in raw evidence but intentionally excluded from the common canonical
schema. Per-deadline fixture lists remain unavailable, so final fixture assignment,
opponents, difficulty and results remain post-event context. All 2021/22 limitations
and documented identity anomalies remain applicable.

Milestone 2 now has the documented, reproducible five-season foundation required by
its exit criterion. No unresolved blocker prevents this acceptance. The next batch
is Milestone 3 feature and evaluation **design**, including explicit field availability,
identity linking, prediction targets and time-aware evaluation policies before models.
