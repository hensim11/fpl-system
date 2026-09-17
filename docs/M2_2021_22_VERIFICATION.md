# Milestone 2 — 2021/22 acceptance evidence

Verified 2026-09-17. **2021/22 is accepted and published.** The normal pipeline
passes all **43/43 quality checks**, preserves the **38/38 snapshot expectation**,
and reconciles **23,230/23,230** eligible player/Gameweek totals exactly.

## Inspection and scope

Preserved the existing uncommitted compatibility, independent settlement and audit
work. Inspected the working diff/status, architecture, tests, raw source manifest,
failed reports and required repository documentation before this exception batch.
The starting **94 tests passed**. No commit, merge, model or optimizer was created.

The only new production eligibility policy is version-1
`superseded_deadline_exception`, implemented in `historical_snapshot_policy.py`
and selected explicitly through the existing source catalogue/pipeline. The full
configuration participates in deterministic build identity. The shared canonical
schemas and generic exact-deadline rule remain unchanged.

## Exact source and temporal proof

| Field | Verified value |
| --- | --- |
| Season / Gameweek | 2021-22 / 18 |
| Provider | Randdalf/fplcache |
| Immutable revision | `33dac28d18953bee5bc4bd56ddd8a5e32e169d68` |
| Path | `cache/2021/12/18/1233.json.xz` |
| SHA-256 | `9c8fbad59eecb978494d98425e0dadcfa16fbb3a3954f99b4263c65277e2eed1` |
| Raw byte size | 79,444 |
| Capture / state-as-of UTC | 2021-12-18 12:33 |
| Observed payload deadline UTC | 2021-12-18 13:30 |
| Authoritative final deadline UTC | 2021-12-18 16:00 |
| Event flags | Exactly one GW18 event; `is_next=true`; no competing upcoming event |
| Player records | 656 |
| Age before payload deadline | 57 minutes |
| Age before final deadline | **3 hours 27 minutes** |

The raw manifest, decompressed payload, final reference and independently computed
raw-file hash confirm these fields. The final reference remains
`cache/2022/5/22/1239.json.xz`. The payload is not rewritten to say 16:00.

The user explicitly authorized this one superseded-deadline case. **12:33 precedes
both 13:30 and 16:00**, so it contains no post-cutoff information. The final deadline
in canonical Gameweek and snapshot rows remains 16:00, while capture time remains
12:33. This is observed player state as of 12:33, **not state immediately before
16:00**. News, prices or availability changes during that 3h27 interval are not
reconstructed. The **18:25 capture remains forbidden** as post-deadline.

The validator requires exact season, Gameweek, path, raw hash, source revision,
capture time and both deadlines. It requires exactly one target event and one
unambiguous `is_next=true` event. V1 timestamps/path/scope are restricted to this
case; arbitrary earlier deadlines are not accepted. Missing or stale policy use
fails. Immutable-source checks and normal player/team/position transformations
still run. There is no generic allow-mismatch flag.

The retained quality report and cross-season audit expose the complete policy,
exception type/reason, both deadlines, source hash, capture ages and state-as-of
UTC. Raw source bytes remain unchanged. No outcome data fills player state.

## Existing compatibility and settlement contracts

Both providers retain their existing immutable revisions:
Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88` and fplcache as above.
The four Vaastav files under `data/2021-22/` are `gws/merged_gw.csv`,
`players_raw.csv`, `teams.csv` and `fixtures.csv`.

Schema `vaastav-2021-22-v1` retains absent starts/expected metrics as null and
forbids `xP` from all mappings. No manager or `modified` fields occur. The scoped
adapter-v2 `GKP -> GK` alias handles 101 GW37 rows; the exact fixture-263 policy
reconciles 78 scheduled-15:00 player rows to fixture-source 15:30 in post-event
context only. These earlier compatibility policies remain unchanged.

Independent `earliest_settled_current_event_v1` selection remains separate from
snapshot eligibility. It selects the earliest pinned current-event capture with
exact event deadline, `finished=true`, `data_checked=true`, unique players and
integer points, strictly after the later of event deadline and final kickoff plus
two hours, and before the earlier of next deadline or final kickoff plus seven days.
The flags establish settlement by capture time; the API supplies no settlement
transition timestamp. Selection never receives Vaastav player point totals.
Inspected candidates and selected captures remain materially consumed evidence.
Final GW38 selection still agrees with `cache/2022/5/23/0632.json.xz`.

All **23,230 eligible, compared and matching totals** pass at coverage **1.0**,
with **zero unmatched and zero mismatching rows**. GW17 still independently selects
`cache/2021/12/17/0626.json.xz` and compares all **460** totals. GW3 still selects
`cache/2021/8/30/0104.json.xz`; Daniel James has **1**. His later settled value of 0
is retained only as a mutation diagnostic. The new deadline eligibility changes
none of these selected outcome sources or canonical fixture facts.

## Dataset and football sanity

| Table / measure | Published count |
| --- | ---: |
| Gameweeks / accepted deadlines | 38 / 38 |
| Players | 737 |
| Teams | 20 |
| Fixtures | 380 |
| Player-fixture facts | 25,447 |
| Player-deadline observations | **25,150** |
| Audit-only quarantined metadata rows | 25,447 |
| Hard quality checks passing | **43/43** |

The exception adds exactly 656 deadline rows to the previously rejected 24,494-row
attempt. No fixture facts or synthetic zero-point rows are added. Every club has
38 fixtures and each directed home/away pairing occurs once. All 737 season point
sums match final Vaastav aggregates. There are 21,013 single-fixture and 2,217
double-fixture player/Gameweek groups, including 14,962 preserved zero-minute rows.
GW18/GW30 have four fixtures each; GW36 has 16. No Gameweek is entirely fixture-empty.

Sixteen elements change observed deadline team. All important deadline identity,
price and ownership fields are populated; unavailable statistics/availability
remain null. Full null counts and hashes are in the machine-readable audit.

## Executed verification

```bash
.venv/bin/python -m fpl_ai historical --season 2021-22 --output-dir data
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report docs/M2_CROSS_SEASON_AUDIT.json
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --season 2021-22 --report /tmp/fpl-2122-selected.json
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q fpl_ai tests scripts
.venv/bin/python -m fpl_ai --help
.venv/bin/python -m fpl_ai historical --help
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --help
.venv/bin/python -m pip --no-cache-dir check
git diff --check
```

All commands exit **0**. The normal command publishes seven CSVs and five metadata
artifacts, including manifest, quality/reconciliation reports and a frozen source
inventory. The successful catalogue entry automatically makes status `published`.
Default audits now include all four seasons; explicitly selected 2021/22 passes.

**102 tests pass**: 94 baseline plus eight focused exception tests. They cover exact
pinned acceptance/evidence, each identifying field, altered event identity/deadline/
upcoming flags, duplicate/competing events, forbidden post-deadline use, unrelated
mismatches, unchanged ordinary eligibility, policy identity, stale/missing exceptions,
and malformed/failed attempts producing no partial publication. Existing settlement,
provenance, deterministic successful build/reuse and regression tests remain passing.

The default audit creates fresh **offline** builds of all four seasons from cached
immutable bytes, re-executes normalization/selection/reconciliation/quality, and
compares identities and all seven CSV hashes. It revalidates the exception against
raw bytes and frozen inventory. Reuse verifies hashes and preserves bytes/mtimes.
All three prior seasons' complete evidence entries equal their pre-batch baseline.
Compilation, all help commands and whitespace checks pass; dependency check reports
**No broken requirements found**. No dedicated lint/type checker is configured.

## Final identities and checksums

- Version: `v3-9779cdbc0c07-33dac28d1895-build-5644015b364e`.
- Source identity: `c4045c8739a4dfd0d3d47115f23d8a0c6ee211b510e8572ab6315f699542f863`.
- Build identity: `5644015b364e43177485c5d5c3f520efe64b7a17d4113b84b56c400bab2c57d8`.
- Frozen inventory: **134** artifacts; SHA-256 `4c094e22593ebfd61b77602720ec3b00309bdc75b5468acf16503b4ac4c57137`.

| Canonical CSV | SHA-256 |
| --- | --- |
| fixtures.csv | `019a435c07f25f15acdc57ce404397f10b44e0e3467454a92acb9bfc98e5bde6` |
| gameweeks.csv | `daa2e9a9b39a03a63cbd8d9f56002a23c73ab3fe60846fd2c96e368c3612e3d1` |
| player_deadline_snapshots.csv | `c3c01dcd8aeccdfb6276875cd63144904683e6fb8eb200a71e80c027d132c17b` |
| player_fixture_facts.csv | `8310163bc8c3abfc5033af1ee1a77812e0268a3f9d2802911dfa7c52a72b9876` |
| players.csv | `1b358661dfb235b35a27258964d4a4c3bafcdc4f343ec31c7215ea0f051ca122` |
| quarantined_source_metadata.csv | `a4f7be8b33e2b736cf375e9617060ce4bd22067faac35070690a083a05b652ed` |
| teams.csv | `f46e390afddb375624503cac6ef295b508183e297346b918c22f2c396e60ba4e` |

## History, limitations and next handoff

Earlier failed attempts remain retained and did not publish partial datasets. The
[source-search record](M2_2021_22_SOURCE_SEARCH.json) is unchanged historical
evidence: no exact-final-deadline pre-16:00 capture was found; Wayback checks were
unavailable. Acceptance rests on the subsequent explicit exception authorization,
not a claim that a new source was discovered.

No unresolved acceptance failures remain. Material limitations are the GW18 12:33
as-of / 3h27 freshness gap, periodic archive captures and UTC filename convention,
unavailable deadline fixture lists, nullable historical fields and the separately
reported later settled-value mutation. These limitations must survive downstream
analysis. Full generated data remains Git-ignored; pins, fixtures and audit scripts
make it reproducible.

Next substantial batch: add 2025/26, then perform full-range identity/availability
audits before feature and evaluation design. No commit or merge was performed.
