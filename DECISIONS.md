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

Consequence: a future developer can identify both what was requested and the immutable upstream content used. The raw source version includes the catalogue schema version and both resolved commit prefixes; Decision 019 adds a separate build identity to processed versions.

## 017 — Enforce season-configured points-reconciliation coverage

Status: accepted for Milestone 2.

Reconciliation coverage is `compared_row_count / eligible_row_count`. An eligible row is one unique `(season, gameweek, element)` total produced by summing canonical player-fixture facts; it becomes compared only when the independent snapshot supplies integer `event_points` and marks the event `finished` and `data_checked`. The season catalogue declares reconciliation `required` or `optional` and a minimum ratio in `[0, 1]`. For 2024/25 it is required at `1.0`.

Consequence: a required check with no eligible/usable comparisons, coverage below its threshold, or any points mismatch fails quality and cannot update the latest catalogue. Only an explicitly optional season may record `skipped_optional`; missing comparisons are never counted as matches.

## 018 — Select an explicit Vaastav source schema per season

Status: accepted for Milestone 2.

The source catalogue selects a registered Vaastav schema ID and version. Each definition declares applicable seasons, required and optional columns, mappings, type expectations, quarantined and ignored fields, expected-metric availability, known exceptions, leakage-forbidden fields, and its schema-drift policy. The first real definition is `vaastav-2024-25-v1`.

Consequence: the canonical output contract stays stable while archive-specific changes remain explicit. Required-column loss and unknown/inapplicable schemas fail immediately; optional loss remains null and is reported; unexpected additions or column-order drift fail the quality report. Supporting 2023/24 requires adding configuration and a schema definition rather than editing the generic importer.

## 019 — Separate exact source identity from transformation/build identity

Status: accepted for Milestone 2.

`source_identity_sha256` covers configured providers and revisions plus exact raw artifact paths, sizes, and hashes. `build_identity_sha256` separately covers the explicit transformation-contract version, canonical schema contract, season expectations, selected source schema, snapshot-selection settings, and reconciliation policy. Canonical JSON ordering makes it deterministic; retrieval/build times and absolute output paths are excluded.

Processed directories append the build-hash prefix to the existing source version. Manifests, quality and reconciliation artifacts, and the latest catalogue record both complete identities and hashes.

Consequence: equivalent configuration is stable, a semantic option change creates a distinct build, and two builds over identical raw sources cannot silently overwrite one another. The raw directory remains shared by immutable source version.

## 020 — Freeze the source inventory inside every processed build

Status: accepted for Milestone 2.

Each new processed build owns an atomically written `source_inventory.json` containing the exact provider, repository, season, revision, path, URL, hash, and byte-size records used for that build, plus the complete source identity. The build manifest records the inventory's portable relative path, SHA-256, source identity, and source-identity hash. Immutable raw files remain shared and are not copied.

Catalogue schema v2 keeps version-indexed build entries alongside the latest-successful entry. Builds predating this decision are labelled `legacy_shared_raw_inventory` and are readable only while the shared raw inventory still matches the checksum they originally recorded; they are never silently migrated or rewritten.

Consequence: changing a shared raw-cache inventory cannot alter the provenance of a new frozen build. The on-disk provenance contract changed, so the explicit transformation contract advanced from `historical-transform-v4` to `historical-transform-v5`, producing a distinct build identity while preserving earlier builds.

## 021 — Make forbidden source fields structurally unmappable

Status: accepted for Milestone 2.

Season-specific source schemas use disjoint required, optional, ignored, quarantined, and forbidden field categories. Validation runs before ingestion and rejects duplicates, category overlap, unsupported mapping sources, malformed targets, multiple sources targeting one canonical field, and any forbidden-to-trusted mapping. Trusted and quarantine mappings are separate contracts.

Consequence: Vaastav `xP` is not merely ignored by the current transformer; the schema invariant prevents it from mapping to `expected_points_next_gameweek` or any other trusted canonical field. Unexpected upstream columns continue to follow the explicit quality-failure and reporting policy.

## 022 — Make consumed provenance and season mappings executable

Status: accepted for the 2024/25 Milestone 2 slice.

A successful build now registers raw records at their material use sites and compares that actual set with its resolved dependency set. Only canonicalised consumed records enter `source_inventory.json` and source identity. Exact duplicate registrations merge sorted consumption roles; conflicts and missing registrations fail. Rejected selection candidates and unrelated cache entries remain separate discovery/cache audit records. Source identity contract v2 intentionally omits configured-but-unused artifacts.

The selected season schema executes through `declarative-normalization-v1`: source values are validated for declared integer, finite decimal, explicit boolean, string/enumeration, nullability, and UTC timestamp contracts, then trusted and quarantined mappings populate separate namespaces. Generic canonical transforms accept only normalized rows. Optional-column reporting follows the declared category rather than treating every non-required field as optional, and quarantine targets must be unique.

Consequence: source identity truthfully describes contribution rather than cache contents, mapping configuration changes behavior, and schema types are enforceable. These semantic changes advance the transformation contract from `historical-transform-v5` to `historical-transform-v6` and create new provenance/build identities. The seven canonical CSVs remain byte-identical to the verified v5 baseline, which stays readable and unmodified.

## 023 — Verify 2023/24 through configuration and an observed source-schema delta

Status: accepted; full season verified 2026-09-16.

The existing Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` and fplcache
`33dac28d18953bee5bc4bd56ddd8a5e32e169d68` revisions also contain complete
2023/24 inputs. Inspection of all four CSV headers and execution against every
source row established that retained fields have the same mappings and types.
The separate `vaastav-2023-24-v1` contract declares the observed absent columns
and permits only GK/DEF/MID/FWD fixture positions. It removes the unavailable
`modified` quarantine mapping, preserving null in the unchanged canonical column.
Deep copying the shared contract preserves the 2024/25 definition and identity;
checked-in real header samples and a baseline build-hash test guard that boundary.

The reference capture is `cache/2024/5/19/1233.json.xz`. The first inspected May 20
capture, `0121.json.xz`, still reports GW38 unfinished and unchecked. Pin
`cache/2024/5/20/0625.json.xz`, which reports both flags true, for final settlement.
The rejected capture remains raw audit evidence but contributes neither to frozen
provenance nor deterministic source identity. Reconciliation remains required at
`1.0`: all 28,742 player/Gameweek totals match with zero unexplained differences.

Consequence: 2023/24 proves cross-season operation without changing generic
pipeline logic, canonical contracts, or transformation version. Both seasons
rebuild deterministically, and 2024/25 CSVs remain byte-identical. Archive snapshots
remain periodic observations rather than exact-deadline captures; unavailable
values remain null. Full acceptance evidence is in
[the verification record](docs/M2_2023_24_VERIFICATION.md).

## 024 — Preserve observed 2022/23 code changes with exact audited exceptions

Status: accepted; full season verified 2026-09-16.

The existing immutable provider revisions contain complete 2022/23 inputs. All
four Vaastav headers exactly match the inspected 2023/24 shape, so a season-scoped
`vaastav-2022-23-v1` schema deep-copies the shared definition. Starts and expected
metrics exist; `modified` and manager columns do not. Canonical schemas are unchanged.

The season has 38 deadlines but only 37 fixture-bearing gameweeks: GW7 has no
fixtures. Preserve its accepted snapshot and deadline rows without fabricating
zero-point fixture facts. Reconciliation eligibility continues to be derived from
actual fixture facts, so GW7 adds no eligible rows. All 24,957 eligible totals match.
The final reference is `cache/2023/5/28/1231.json.xz`; May 29 `0139.json.xz` is
unfinished/unchecked, while `0623.json.xz` is settled and is the configured comparison.

The initial full quality run caught two non-manager person-code differences:

| Element | Person | GW1 observed code | GW2 and final code |
| --- | --- | ---: | ---: |
| 546 | Luke Harris | 536122 | 515024 |
| 558 | Hugo Bueno | 530332 | 490721 |

The accepted GW1 capture (`cache/2022/8/5/1249.json.xz`) and GW2 capture
(`cache/2022/8/13/0627.json.xz`) agree on names, team and position, but not code.
Their raw excerpts are retained in tests. Preserve the original deadline code;
using the final code in GW1 would silently substitute later information.

The optional season catalogue `snapshot_player_code_exceptions` policy is exact
by gameweek, element, observed code, final code and source path, with a required
explanation. Configuration rejects malformed or duplicate entries. Quality checks
require every declared transition to be observed; stale exceptions and every
undeclared mismatch fail. No broad player or season exemption was added. The policy
is audit-only and does not rewrite identity, team, position or any snapshot value.

Its version (`snapshot_player_code_exception_policy_version: 1`) and complete
configuration enter the season build identity only when configured. This extends
the validation contract without changing the default v6 transformation semantics
or either newer season's build identity. All seven newer CSVs remain byte-identical
on fresh rebuilds. Future changes to this exception policy must advance its version.

An additional cross-season diagnostic compared fixture sums with final cumulative
player totals. Every 2022/23 and 2023/24 total matches. For 2024/25 Ferguson, the
pinned final aggregate is 28 while fixture and settled event sums are 27. Between
February 25 and March 8 archive captures, cumulative points rise from 21 to 23
while GW27 event points are 1. This establishes an upstream cumulative/event
inconsistency; the inputs inspected do not explain its cause or assign the extra
point to a fixture. Retain the existing fixture-grain source policy and report the
aggregate discrepancy separately. Do not invent an allocation or alter the passing
settled-event reconciliation. Detailed evidence and limitations are in
[the verification record](docs/M2_2022_23_VERIFICATION.md).

## 025 — Scope older label and kickoff compatibility without waiving acceptance

Status: compatibility implemented. Historical blocking status subsequently resolved by Decisions 026 and 028.

The pinned 2021/22 source omits starts and expected metrics. Its schema removes
unavailable mappings, so canonical nullable outcomes remain null. Retained source
fields keep their existing types. In GW37, 101 goalkeeper rows use `GKP` instead
of `GK`; their accepted archive positions are all goalkeeper ID 1.
`declarative-normalization-v2` permits explicit string-enumeration `value_aliases`.
Aliases may introduce only new labels mapped directly to declared allowed values;
chains, shadowing canonical labels, malformed mappings and use under v1 fail.
Only the 2021/22 schema selects v2 and `GKP -> GK`. Its entire schema and adapter
identity are hashed; other seasons retain the exact v1 contracts and build hashes.

Fixture 263 (Brighton–Aston Villa, GW27) has 78 merged player rows at scheduled
15:00 and a fixture source at 15:30. Contemporary reporting confirms the delay.
A version-1 optional `fixture_kickoff_reconciliation` policy records the exact
fixture, Gameweek, both timestamps, expected row count and explanation in build
identity. It standardizes only post-event fact context to the pinned fixture time.
Stale/missing rules, changed timestamps/counts and undeclared discrepancies fail.
The successful normalization is listed in the quality report; raw bytes and
point-in-time snapshots remain unchanged. Transformation failures now retain an
identified failed-attempt report and never publish a catalogue entry.

Consequence: these compatibility changes do not authorize weaker acceptance.
At the end of the compatibility batch, 2021/22 failed because the archive had no
exact pre-deadline GW18 capture and next-deadline points selection had missing
comparisons and one mismatch. Decision 026 resolves the settlement failures; GW18
remains unresolved.
The expected 38 snapshot Gameweeks and required 1.0 reconciliation remain intact.
Earlier settled points evidence is diagnostic only; it is not silently substituted.
No successful 2021/22 output is claimed. See
[the investigation record](docs/M2_2021_22_VERIFICATION.md).

## 026 — Select first observed settled current-event captures independently

Status: implemented and verified for the investigatory 2021/22 season.

The next-deadline strategy cannot compare GW17 when GW18 has no accepted deadline
snapshot, and Daniel James's settled GW3 event points change across the transfer
interval. Strategy `earliest_settled_current_event_v1` selects separately for each
fixture-bearing Gameweek. It searches immutable archive entries in timestamp order,
strictly after the later of the event deadline and final fixture kickoff plus two
hours, and strictly before the earlier of the next deadline or final kickoff plus
seven days. It requires one unambiguous event with the exact deadline,
`is_current=true`, `finished=true`, `data_checked=true`, and unique player IDs with
integer event points. Unsettled candidates are audited and skipped; missing,
malformed, stale, ambiguous or policy-inconsistent evidence fails. Final GW selection
must also equal its explicit, validated final-settlement pin.

The API has no timestamp for the transition to settled. True flags evidence that
settlement had occurred by capture time; the two-hour boundary is only a conservative
additional guard, not a claimed settlement timestamp. Earliest observed settlement
limits exposure to later transfer resets. The selector never receives Vaastav player
points. Comparison against them happens only after selection. Later differences in
already-consumed next-deadline captures are reported without changing selection.

Policy version 3 records the full immutable selection policy in build identity.
Every inspected candidate is materially consumed evidence for the earliest-selection
claim; selected records additionally carry the reconciliation role. Per-GW selection
records include timestamps, hashes, flags, search bounds, rejection reasons and
selection reason. Failure evidence is retained without publishing a dataset.

Consequence: all 23,230 2021/22 totals now reconcile exactly, including all 460 GW17
totals and James's GW3 value of 1. GW18 remains a separate decision-time source gap.
No points, snapshot or publication gate is weakened. Existing accepted seasons
retain their legacy selection contracts and exact source/build identities; migrating
them would be a separate intentional version change, not a silent overwrite.

## 027 — Derive operational support status from successful publication

Status: implemented.

Source configuration is not evidence of acceptance. The audit enumerates published
seasons from `data/historical/catalogue.json`, then checksum-verifies their builds.
Configured seasons without publication are `blocked` when failed attempts exist,
and otherwise `investigatory`. Status is operational metadata, excluded from build
identity. Successful publication automatically brings a season into the default audit.

`--season` selects published seasons; `--investigate-season` explicitly audits
unpublished attempts. Invalid mode combinations produce argparse errors. The
2021/22 diagnostic acquisition option remains explicit and separate from the fully
offline default. This fixes the default-audit regression without a season exclusion
list or changing any accepted dataset.

## 028 — Admit one exact superseded-deadline snapshot for 2021/22 GW18

Status: explicitly authorized by the user; implemented, published and verified.

The user approved the pinned 12:33 capture despite its superseded 13:30 deadline.
The final 16:00 deadline remains authoritative. Capture precedes both deadlines,
so no future state is introduced; the limitation is freshness, not temporal leakage.
State is as of 12:33, **3 hours 27 minutes before final deadline**, not immediately
before 16:00. No exact-final-deadline archive capture was discovered.

Version-1 `superseded_deadline_exception` in season configuration identifies season,
GW18, source path, SHA-256, immutable revision, capture timestamp, payload and final
deadlines, exception type and reason. The entire policy enters build identity.
The validator admits only this scoped case with exact identifying fields and one
unambiguous upcoming GW18 event. Capture must precede both deadlines. Missing,
changed, malformed or stale exceptions fail. The 18:25 capture remains forbidden.
Normal exact-deadline selection remains unchanged everywhere else.

Quality and cross-season evidence expose the policy, both deadlines, source hash,
capture age and state-as-of time. Canonical deadlines remain 16:00. Raw bytes,
fixture facts, outcome selection and points reconciliation are unchanged. All 43
checks pass; 38/38 snapshots and all 23,230 exact comparisons are retained. The
successful manifest, frozen inventory and catalogue publish normally; operational
status derives from that publication. All three prior seasons' identities and CSVs
remain unchanged. Decisions 025/026's GW18 blocking status is superseded by this
specific authorization, not by finding a new source or relaxing coverage.

## 029 — Collapse only exact, hash-bound duplicate source observations

Status: accepted; 2025/26 published and verified.

At the existing Vaastav pin, 2025/26 `merged_gw.csv` contains 29,757 rows but only
29,747 distinct player-fixture keys. Ten keys occur twice: Ben Doak/Gannon-Doak
(391, GW1) and Eli Junior Kroupi/Junior Kroupi (100, GW1–9). Every merged field is
identical in each pair. Pinned old/new player directories contain identical
intersecting histories, consistent with duplicate aggregation after renaming.
The initial normal build rejected these duplicates before publication.

Optional version-1 `exact_duplicate_rows` season configuration identifies the
immutable revision, source path, entire file SHA-256, original row count and exact
key/Gameweek/occurrence inventory, with an evidence reason. The typed ingestion
boundary retains the first record only after verifying every raw CSV field is equal,
including fields that normalization would subsequently ignore or forbid. Source
row numbers and each removal are retained in the quality schema audit. Changes to
hash, count, key or field values, undeclared duplicates and stale policies fail;
without a policy, existing duplicate-key rejection is unchanged.

The complete policy enters the season build identity only when configured. Raw
bytes remain untouched, and the frozen inventory identifies the original file.
This is a source-row multiplicity correction, not a points adjustment or identity
rewrite; it neither changes snapshot selection nor chooses settlement by agreement.
All 29,338 independent settled player/Gameweek totals match after normalization.
All four prior season contracts, outputs and identities remain unchanged.

Evidence: [source inspection](docs/M2_2025_26_SOURCE_AUDIT.json) and
[acceptance record](docs/M2_2025_26_VERIFICATION.md).

## 030 — Preserve the common canonical schema and audit raw-only availability

Status: accepted for five-season Milestone 2 closure.

2025/26 adds four defensive outcome statistics, final-player metadata and a team
link, while removing Assistant Manager metrics. The observed season schema declares
all columns, types the four new defensive statistics and retains their raw bytes;
it deliberately excludes them from the seven common canonical tables. This avoids
changing all previously accepted schemas/build identities solely for fields that
are unavailable across the full training range. These outcomes are not forbidden
or of unknown fixture timing; their exclusion is an explicit scope choice.

The separate read-only audit describes canonical information classes/nonempty
counts, source field categories, and raw bootstrap field presence, JSON types and
Gameweeks. This exposes partial-season fields such as `scout_risks`, `known_name`,
`price_change_percent` and `scout_news_link` without importing final values into
earlier state. Archived cumulative defensive statistics remain distinct from
fixture-grain realised statistics. No new raw field automatically becomes trusted
canonical input or an engineered feature.

Consequence: the full-range foundation is reproducible and transparent about
availability, while any later feature/raw-field expansion requires its own explicit
versioned design. Existing temporal boundaries, Vaastav `xP` prohibition and
quarantine remain unchanged. See [the availability guide](docs/M2_FIVE_SEASON_AVAILABILITY.md).

## 031 — Predict snapshot-visible football players at one Gameweek horizon

Status: implemented and verified for Milestone 3.

Use `(season, target_gameweek, element)` and sum canonical fixture points across
all target-GW fixtures, including doubles. Population comes only from accepted
snapshot position IDs 1–4; AM is excluded. No final identity join or cross-season
player linking is needed. Observed person codes remain audit metadata, preserving
Harris/Bueno and the absent final Sillah observation without rewriting history.

In a fixture-bearing GW, a snapshot player with no fixture rows has an explicit
empty-sum label of zero: the accepted full-season fact coverage is the population
assumption. This includes team blanks and registered non-playing players; labels
carry an audit status. Entirely fixture-empty 2022/23 GW7 keeps 624 prediction rows
but has null labels, excluded from fitting, metrics and history. No synthetic
fixture facts or hindsight blank indicators enter features. Labels are unmultiplied
player points, not squad/captain/chip returns.

## 032 — Gate points history on observed settlement, not GW number alone

Status: implemented and verified for Milestone 3.

The as-of boundary is the accepted capture, stricter than its later deadline.
State features copy only snapshot team/position IDs, price (tenths of £1m), ownership
percent, event transfer counters, status and chance of playing next round.
Chance remains null when unavailable; do not reinterpret null as fit or zero.

Points history requires both an earlier GW and the accepted M2 settlement capture
at or before the target capture. The adapter checksum-verifies raw settlement
payloads, requires finished/data_checked, and checks observed event points against
canonical fixture sums. Missing player evidence remains missing. A no-fact prior
player sum is usable only with an explicit observed zero. Prior 3/5 windows are
calendar GWs, use means over available observations and expose counts. Season
means reset each season. Every nullable feature has a missingness indicator.

V1 deliberately excludes lagged minutes/goals/assists/bonus: M2 reconciles points
at a known historical capture but does not independently establish historical
versions of those other final-source statistics. Starts/xG also lack common
five-season coverage. This narrower contract avoids claiming all final-source
statistics were available just because a fixture had finished. It can be extended
with separately verified timestamped evidence. No final fixture context,
quarantined metadata, Vaastav xP, final identity or AM values become features.

GW18 2021/22 retains capture 12:33, payload deadline 13:30, final deadline 16:00,
207-minute freshness gap, exception flag and exact source path/hash per row; the
complete original exception policy remains in the modelling manifest.

## 033 — Freeze chronological evaluation and separate the FPL benchmark

Status: implemented and verified for Milestone 3.

Train 2021/22–2023/24; validate 2024/25; final holdout 2025/26. Overall and position
means consume only training labels settled by each prediction capture. Training
reports therefore use expanding history, not in-sample fitted means. Training
statistics are fixed for validation/test; no validation or holdout labels refit
them. Player histories may update with earlier settled GWs within each evaluation
season, as in prospective weekly forecasting. That is not fitting on future labels.

Recent-points baseline uses mean of available prior three calendar GWs. Player
scoring rate means points per observed settled GW, requiring at least three such
GWs (not points per appearance or per 90). Both fall back to the training position
mean, then training overall mean, then explicit zero at cold start. No tuning was
performed against the holdout; these definitions preceded the first results.

Archived ep_next is an external opaque FPL estimate for the upcoming is_next event
at the accepted capture. It is consistently present except three 2023/24 rows.
Keep its original values, including negatives; no imputation and no use as an
engineered input or fallback. Historical provider methodology is not established
or assumed stable. Benchmark coverage is reported separately.

Report MAE, RMSE, and mean per-GW Spearman correlation, using average ranks for
ties, omitting undefined constant/single-row groups with explicit counts. Ranking
is calculated within season/GW (and position for position segments), never across
unrelated GWs. Every segment reports population, labels, predictions and missing
coverage. Validation/test remain separate; small score differences are not evidence
of meaningful superiority. Registered non-playing players dominate many rows,
and season scoring differences limit cross-season comparability.

## 034 — Publish offline content-addressed modelling artifacts separately

Status: implemented and verified for the initial Milestone 3 batch; identity/reuse
boundaries superseded by Decision 035.

Extend fpl_ai with a standard-library-only `features` CLI. It reads checksum-verified
published M2 builds and writes only under a separate modelling artifact root.
features.csv is a closed projection; labels, split, predictions and row audit are
separate keyed tables. schema.json, evaluation.json and manifest.json record the
complete versioned contract, exact source/build identities, settled capture
sources/hashes, implementation hashes, feature schema, counts and artifact hashes.

Identity excludes build timestamps and local absolute paths. Historical build
metadata is retained semantically without ingesting its creation timestamp into
the new identity. Implementation bytes also participate to prevent stale reuse
when code changes without a manual version bump. Publication stages an entire
artifact directory before renaming it; reuse verifies identity and every artifact
checksum without rewriting. `--builds-from` pins the historical versions from an
existing modelling manifest even if the M2 latest lookup changes. Generated data
is ignored; compact contracts/tests and verification evidence are committed code.

## 035 — Enforce target evidence and identify serialized modelling products

Status: implemented in the focused Milestone 3 hardening batch.

Every non-null target now requires the target element's integer event_points in
that GW's accepted settlement payload to equal the canonical fixture sum. This
includes empty-player zero sums. Missing elements, missing settlement, non-integer
values (including booleans), or disagreements fail before publication. Globally
fixture-empty GWs remain unlabelled. The prediction target, features, splits and
baselines are unchanged; this enforces previously incomplete evidence requirements.

Identity `serialized-products-v2` supersedes Decision 034's four-file implementation
hash boundary. The pipeline regenerates and serializes all six data artifacts,
then identifies their exact hashes plus the existing contracts and source/build
provenance. The evaluation artifact is hashed before inserting its identity reference
to avoid a circular hash; its final bytes are separately checksummed in the manifest.
This covers feature/label/audit population, predictions, metrics, schema and their
serialization, regardless of which helper/dependency produced them. Source-code-only
changes that leave outputs and contracts unchanged intentionally retain identity.
No incomplete implementation-hash list remains. Absolute paths and times remain
excluded. Cost: reuse now performs feature generation, evaluation and temporary
serialization before validating the existing build; it avoids published rewrites,
not computation. Temporary products are removed even on failure.

Publication and reuse share one declared artifact set: six named data artifacts
plus manifest.json. Reuse rejects missing/extra directory entries, non-regular files,
missing/extra manifest checksum entries, a manifest differing from regenerated
identity/content, and any expected-file checksum mismatch. Existing published M3
builds remain intact; this identity-boundary change publishes a distinct version.

The verification script uses explicit VerificationError checks, not assertions,
including fresh rebuild/reuse calls that must execute under python -O. It independently
checks every label against raw settled event_points and counts all 4,553 supported
empty-player zeros. Success flags are returned only after all checks pass. A failing
fresh-build condition is tested in normal and optimized subprocesses. No historical
foundation files, predictors, model or milestone scope are changed.

## 036 — Use a bounded sklearn experiment with train-only preprocessing

Status: implemented and verified for the first Milestone 4 batch.

Introduce scikit-learn 1.7.2 with exact NumPy 2.3.3, SciPy 1.16.2, joblib 1.5.2 and
threadpoolctl 3.6.0 pins. Mature regression and fitted Pipeline implementations
justify these dependencies; the zero-dependency preference does not justify writing
inferior custom algorithms. Ingestion imports remain independent of ML modules.
The recorded Python/library/platform environment scopes exact numerical reproduction.

Consume the frozen M3 artifacts directly. Select 25 of its 27 predictors, excluding
team ID and its missingness flag because numeric club IDs are season-local. There
is no replacement team join or feature expansion. Train-median numeric fills plus
train-fitted standardisation, passthrough original missingness flags and training
one-hot position/status encoding form a common pipeline. Unknown categories map to
all zeros. Computational null fills do not reinterpret chance as fit or missing
history as observed zero. All-null numeric columns remain represented.

Compare only Ridge alpha 10/100 and squared-error histogram boosting with 15/31
leaves, 150 iterations, learning rate .05, minimum leaf 50, L2 10 and seed 1729.
Disable early stopping and use single-thread numerical work. Predeclare validation
RMSE as primary because expected points estimates the conditional mean; retain
MAE, within-GW Spearman and all existing baselines/coverage. No output clipping.
Training uses only labelled 2021/22–2023/24 rows with labels settled before validation.
2024/25 selects the configuration; it never fits preprocessing or refits the model.
Only the frozen saved winner is evaluated on 2025/26. No test-based candidate choice.

Consequences: deliberately limited search and fully inspectable fits; no claims
that the chosen two tree sizes differ significantly, or that global registered-player
prediction gains establish downstream FPL decision quality. Fixture timing,
settlement gates, quarantines, AM exclusion, xP prohibition and GW18 freshness remain
exactly as M3. [Experiment evidence](docs/M4_VERIFICATION.md).

## 037 — Separate immutable validation freeze from holdout products

Status: implemented and verified for Milestone 4.

Publish a validation artifact with all four fitted pipelines, validation predictions,
full metrics, diagnostics, coefficient/permutation information, common-row baseline
deltas and machine-readable selection. The original M3 manifest is inherited in
`upstream.json`. Hash actual serialized products together with the explicit protocol,
versions, feature order, configuration and seed. Timestamps/local paths are excluded.
Model pickle SHA-256 values identify the fitted states. The aggregate freeze identity
binds those states to the exact upstream data and selection evidence.

A separate holdout command requires that published freeze, verifies its identity,
closed artifact/checksum set, environment and selection, and loads only the selected
pipeline. It cannot fit a model or consider other test candidates. Holdout outputs
reference the exact freeze identity and manifest hash and never modify the freeze.
Predictions, labels, features and historical data remain separate. Pickle artifacts
must be trusted local products; checksums are not protection against malicious code.

Publication is staged and atomic. Same-identity differences, corruption, missing or
extra artifacts, wrong directory identity and incompatible contracts fail. Reuse
recomputes deterministic candidates and compares bytes without rewriting. Exact
replays are allowed for verification, not as a pretext for holdout tuning. Verification
checks stay active under Python optimization. M3 integer settlement-GW keys are
restored only for its original identity verification; no upstream bytes are changed.

The selected hist_15 improves the agreed prediction problem on validation and the
separate holdout. Every baseline, other metric, segment and negative forecast remains
visible. Paired GW bootstrap deltas are descriptive and do not account for inter-GW
serial dependence or product utility. The narrow M4 exit criterion is satisfied;
future work should establish point-in-time feature evidence and fresh prospective
evaluation. The reported 2025/26 test cannot become a new untouched holdout.

## 038 — Establish playing-time evidence separately from frozen M3

Status: implemented and verified in M4B.

Use accepted bootstrap captures directly for cumulative minutes/starts and
availability, retaining raw identities and missingness. GW1 cumulative fields are
stale prior-season values; exclude them from current-season features. Starts
remain null when absent, including all 2021/22 observations. Do not infer starts
from minutes or link to later/final player identity.

For GW1's target, compare the settled post-reset cumulative minutes with the
canonical GW1 fixture sum. For later GWs, compare settled cumulative minus that
GW's accepted pre-deadline cumulative minutes with the canonical full-GW sum.
Require independent existing settlement selection, finished/data_checked, capture
after the target deadline and before the next GW deadline, and explicit integer
player values. Every target, including no-fact zero, must agree. History additionally
requires a strictly earlier GW and settlement at or before the prediction capture.
No final-source minutes become predictors merely because points were settled.
This supplies the independent evidence required by Decision 032 without relaxing it.

Publish `playing-time-v1` separately: position, status, chance, previous minutes,
three-calendar-GW minutes mean/count and appearance fraction, observed cumulative
minutes/starts, and consecutive status/chance changes; 11 values plus 9 missingness
flags. No history means null, not zero. Globally fixture-empty GW7 remains unlabelled;
doubles sum all fixtures; the exact GW18 exception and 207-minute age remain visible.

All 80,234 targets in 2021/22–2023/24 reconcile. A source-only 2024/25 audit finds
GW27 element 123 observed minutes delta 34 versus canonical 17. No correction or
replacement evidence is invented; that season is excluded from this minutes build.
Historical fixture context is still unavailable under Decision 014. No Vaastav xP,
quarantine, FPL ep_next or final identity enters the new feature projection.

## 039 — Freeze a bounded minutes experiment before downstream integration

Status: implemented and verified in M4B.

Train 2021/22–2022/23, develop/select 2023/24. No 2024/25 or consumed 2025/26 model
selection, calibration or new minutes performance reporting. Latest training labels
must precede the first development capture. Target total GW minutes can exceed 90.

Compare fixed training-position, recent-minutes and availability-aware recent
baselines with one fixed 15-leaf histogram booster using the existing sklearn stack.
Use training-only preprocessing, explicit missingness, no early stopping or grid,
a zero lower bound and no upper cap. Select by development RMSE; report MAE,
actual-appearance, useful-history, missingness and position segments honestly.
The model wins RMSE but loses MAE to the availability-aware baseline.

Publish fitted state, baseline means, environment, exact feature identity, protocol,
development-only predictions and evaluation through the shared atomic immutable IO.
Do not export training predictions or feed development predictions into xPts.
`downstream_training_allowed: false` records this boundary. Future integration must
produce expanding chronological OOS predictions with both fitting and selection
information available before each downstream row's deadline. No new untouched
historical holdout exists; genuinely prospective evidence is required.

## 040 — Freeze forecasts with actual capture clocks; score in separate bundles

Status: implemented and verified with network-free prospective lifecycle tests.

Add explicit current-season capture/freeze/verify/settle/score commands. Bootstrap
and fixture responses carry separate request/receipt intervals, exact hashes,
season/GW and authoritative deadline. They are not assumed simultaneous. Target
capture, computation and the final publication check must precede the deadline;
there is no CLI timestamp override. Prediction timestamps are semantic provenance,
not incidental build timestamps. Immutable identities exclude machine-local paths.

Forecast artifacts contain features and predictions without outcomes, bound to
exact snapshot, fixture-context, contract and model/freeze identities. Current
fixture context is safely captured but is not an input to the v1 minutes model.
Optional previous snapshots and already settled prior forecast pairs supply history;
absent history remains missing. Expected points stays null pending an actual live
xPts feature adapter. Checksums protect integrity, not hostile pickle execution or
independently witnessed timestamps; model inputs must be trusted local artifacts.

Settlement captures official bootstrap, fixtures and per-GW live player statistics.
Require event finished/data_checked, finished target fixtures, explicit complete
player outcomes and live-stat/per-fixture-explanation agreement. Empty GWs retain
null outcomes. Scoring writes a separate immutable bundle referencing both source
identities; it cannot write within either input directory. Reuse verifies the exact
artifact set, contracts, hashes and identities without rewriting.

The lifecycle is tested offline, including missed deadlines, request crossings,
late publication cleanup, doubles/blanks, corrupted inputs, missing player evidence
and future history rejection. No live 2026/27 forecast or confirmation score is
claimed yet. Operational API compatibility and real capture retention are next;
a scheduler, service and external timestamp attestation are outside this batch.

## 041 — Require independent positive fixture-schedule evidence for blank GWs

Status: implemented and verified in the focused M4B hardening pass.

Missing evidence cannot establish absence of fixtures. Extend the existing current
fixture validation with a stricter forecast/settlement boundary: require a nonempty
fixture array, the existing required row fields plus an explicit nullable event,
valid unique fixture IDs, known distinct teams, boolean completion and known event
assignments. At least one fixture must be assigned to a known event. Reject missing,
empty, malformed and all-unassigned schedules; retain a genuine blank target when a
usable season schedule exists but none of its fixtures belongs to that target GW.
No arbitrary season fixture count is imposed. Ordinary between-season ingestion's
empty-response behaviour is not changed. Capture and read/scoring paths both enforce
this evidence requirement before publication.

For historical minutes labels, processed `fixtures.csv` independently defines the
fixture-bearing GWs. Reconcile every fact's season/fixture/GW against that schedule
and require football-player evidence for every scheduled fixture. Losing all facts
for a GW or one fixture in a double now fails. Player-level no-fact zero handling
still requires explicit independent settlement evidence. The verifier separately
reads and reconciles the schedule; it cannot repeat the old circular inference.
Final schedule use is strictly post-event label validation, not a predictor, so
Decision 014's historical feature boundary is unchanged.

Version the stronger contract as `playing-time-v2`, record the consumed schedule
checksum, and publish new feature/minutes identities without rewriting earlier
artifacts. Prospective snapshot/settlement contracts also become v2; forecasts bind
the updated feature contract. Readers reject older semantics rather than silently
migrating them. Feature/label/audit CSVs, fitted model bytes, development forecasts
and all metrics remain unchanged. No model tuning or selection-season change occurs.

Six focused regressions and the full 176-test normal/optimized suites pass. Real
verification reconciles all 1,140 schedule fixtures, preserves 624 blank GW7 rows,
explicit player zeros, doubles and GW18 freshness, and reproduces affected artifacts.
All 638 pre-existing data files remain byte/mtime-identical. Structurally plausible
server truncation cannot be ruled out without further authoritative evidence; live
operational verification remains pending. The next objective is unchanged: real
2026/27 retention and chronological OOS minutes before xPts stacking. No scheduler,
service, UI or optimiser is introduced.
