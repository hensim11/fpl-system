# Architecture decisions

This file records decisions that shape the foundation. New decisions should be appended with their context and consequences.

## 001 — Use a small Python package and standard library

Status: accepted for Milestone 1.

The repository needs one reliable ingestion path, not an application framework. The package separates HTTP access, validation, transformation, persistence, and CLI concerns. Python's `urllib`, `json`, `csv`, `pathlib`, and `unittest` cover the current need, so runtime dependencies remain empty.

Consequence: setup and execution are simple. A third-party HTTP/dataframe library can be added later if retries, richer typing, larger data, or analyst workflows justify it.

## 002 — Treat raw snapshots as immutable inputs

Status: accepted.

Each run writes full responses beneath `data/raw/<UTC snapshot id>/` and derived tables beneath the matching `data/processed/<UTC snapshot id>/`. Existing snapshot paths are never overwritten.

Consequence: transformations remain reproducible and upstream fields are not lost. Generated data is ignored by Git and needs a separate retention/backup policy if it becomes operationally important.

## 003 — Use CSV for processed Milestone 1 tables

Status: accepted.

CSV is inspectable, portable, and requires no optional engine. Current data volume is small enough that its weaker typing and larger size are acceptable.

Consequence: downstream readers must apply data types. Reassess Parquet when historical or gameweek-level data makes stronger schemas and columnar storage valuable.

## 004 — Validate a minimum upstream contract

Status: accepted.

The FPL endpoints are not a versioned developer contract. Validation therefore targets fields and relationships required by our transformations rather than mirroring every upstream field.

Consequence: irrelevant upstream additions do not break ingestion, while missing keys, duplicate IDs, and invalid references fail before a misleading snapshot is saved.

## 005 — Keep FPL rules out of the data layer

Status: accepted.

Milestone 1 copies current facts and does not implement scoring, squad, pricing, transfer, chip, or deadline logic. When product logic needs those rules, season-specific values and effective dates will be supplied through versioned configuration.

Consequence: models will not silently embed rules that change between seasons. A configuration format will be selected only when the first real rule-backed use case is defined.

## 006 — Use the public endpoints consumed by the FPL website

Status: accepted with risk.

`bootstrap-static/` and `fixtures/` provide the smallest useful current player/team/fixture foundation without credentials or aggregation by a third party.

Consequence: the project depends on an unofficially supported and unversioned schema. Raw preservation, validation, clear errors, and tests reduce—but do not remove—that risk.

## 007 — Pin historical providers and start with one season

Status: accepted for Milestone 2.

The eventual supported range is 2021/22–2025/26. The first vertical slice uses only Vaastav's historical FPL repository at `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` and Randdalf's `fplcache` at `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`, for 2024/25 only. Moving branches and extra providers are not allowed.

Consequence: the current slice is reproducible and small enough to audit. The remaining four seasons must be introduced through reviewed catalogue entries rather than broadening the downloader implicitly.

## 008 — Separate four information classes

Status: accepted.

Historical schemas classify realised outcomes, pre-deadline observable state, fixture context, and source fields with unverified timing. No modelling features are created in Milestone 2. Vaastav `xP` is excluded entirely; ownership/value/transfer fields are quarantined; manager-only `mng_*` statistics are excluded.

Consequence: post-match outcomes cannot be mistaken for same-gameweek predictors. Future rolling features must be lagged at the shared gameweek deadline, including every fixture in a double gameweek.

## 009 — Accept only exact pre-deadline archive snapshots

Status: accepted.

For each gameweek, use the latest archive capture where that event is exactly `is_next`, the event deadline exactly equals the season deadline, and the minute-stamped capture is strictly earlier than the deadline. Archive path timestamps are interpreted as UTC from the GitHub Actions environment that created them. Never use a post-deadline capture, interpolate, or backfill.

Consequence: snapshot gaps remain visible as missing gameweeks and nulls. Selection is conservative even when a nearby capture exists.

## 010 — Use immutable raw revisions and an atomic JSON latest lookup

Status: accepted.

Historical raw data is stored under a deterministic season/schema/revision version. Every source file has repository provenance, retrieval time, SHA-256, and size. Same-path content changes fail. Processed versions and the season catalogue use atomic replacement; `catalogue.json` records the latest successful manifest instead of using a symlink.

Consequence: reruns can verify and reuse a version without network access, partial writes cannot appear successful, and tools have a portable stable lookup.

## 011 — Preserve fixture rows and nullable historical availability

Status: accepted.

CSV remains sufficient at the current volume. Canonical schemas are explicit and machine-readable. Zero-minute player-fixture rows are valid observations. A scheduled gameweek may have no fixtures. Statistics absent in an older source remain null rather than becoming numeric zero.

Consequence: later season expansion can represent legitimate empty gameweeks such as 2022/23 GW7 and schema evolution without fabricating observations.

## 012 — Audit the 2024/25 Assistant Manager identity exception

Status: accepted.

FPL's 2024/25 Assistant Manager pseudo-elements are retained because they are part of the pinned 27,605-row and 804-element source contract. They represent club-manager slots, so a real-manager replacement can change `code` within one `element`. This is an explicit quality-report exception; stable code consistency remains mandatory for football-player positions.

Consequence: row-count reproducibility is preserved without pretending that Assistant Manager slots have normal cross-season player identity. Downstream player analyses must exclude or separately handle position `AM`.

## 013 — Take Gameweek team and position only from the accepted deadline snapshot

Status: accepted.

`player_deadline_snapshots` stores `deadline_team_*` and `deadline_position_*` directly from the accepted `fplcache` payload, including labels from that payload's team and element-type dictionaries. The season identity table retains only explicitly named end-of-season team/position fields. Missing snapshot identity remains null; it is never filled from end-of-season metadata.

Consequence: transfers and any position changes retain their point-in-time meaning. The live 2024/25 data contains 31 elements with more than one deadline-time team, demonstrating why the distinction matters.

## 014 — Treat the pinned fixture file as post-event context

Status: accepted.

The pinned sources do not provide a fixture-list snapshot for every deadline. The only fixture-related fields asserted safe in a decision-time row are season, target gameweek, and exact deadline. Final fixture ID, assignment, teams/opponent, home/away, kickoff, difficulty, status, minutes, score, and rescheduling implications remain in `fixtures` or `player_fixture_facts`, classified as post-event context or realised outcomes.

Consequence: no final fixture value is silently presented as if it were known at the deadline. Later work may widen the allowlist only after adding a source that proves fixture state at that decision time.

## 015 — Reconcile canonical Vaastav points with settled fplcache event points

Status: accepted.

Vaastav `merged_gw.csv` is canonical for fixture-grain `total_points`. Reconciliation sums those rows by `(season, gameweek, element)` and compares the result with `fplcache` `event_points` from the next accepted deadline snapshot, provided the prior event is `finished` and `data_checked`. A separately pinned settled snapshot supplies the Gameweek 38 comparison. Cumulative-total differencing is not used because the pre-Gameweek-1 archive still contains stale prior-season totals.

Consequence: every disagreement records both source values and identifiers and is a hard quality failure, so no processed version or latest-catalogue update is published. The hardened live run compared 27,231 player/Gameweeks with zero disagreements.

## 016 — Preserve configured and resolved Git source identity

Status: accepted.

Each historical source records the requested season, repository, configured ref, resolved 40-character commit SHA, and configured artifact paths. Raw file records add URL, retrieval time, SHA-256, and size. The processed manifest and latest-successful catalogue retain the complete source identity plus its deterministic hash. Moving refs such as `main` and `master`, missing resolved commits, or URLs that do not contain the resolved commit are rejected.

Consequence: a future developer can identify both what was requested and the immutable upstream content used. The dataset version continues to include the schema version and both resolved commit prefixes.
