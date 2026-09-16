# Milestone 2 — 2022/23 acceptance evidence

Verified 2026-09-16. This expansion batch passes all acceptance criteria; Milestone 2
as a whole remains open for 2021/22 and 2025/26. The starting working tree was clean
and the baseline 60 tests passed. No commit, publication, or model was created.

## Implementation and source observations

The same ingestion, typed normalization, canonical transforms, strict snapshot
selector, reconciliation, immutable raw storage and frozen build inventory process
2022/23. New season configuration selects `vaastav-2022-23-v1`. The four observed
headers exactly match 2023/24 and reuse its mappings/types through a deep copy;
no separate importer or canonical schema was introduced.

Pinned inputs:

- Vaastav `9779cdbc0c07f6c900c2d0c181ddf6bb9c800f88`, with
  `data/2022-23/gws/merged_gw.csv`, `players_raw.csv`, `teams.csv`, and `fixtures.csv`
  (the latter three are under `data/2022-23/`).
- fplcache `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`, with its complete,
  non-truncated archive tree and UTC filename-based capture timestamps.
- Deadline reference: `cache/2023/5/28/1231.json.xz`.
- Final settlement: `cache/2023/5/29/0623.json.xz`. The inspected earlier
  `cache/2023/5/29/0139.json.xz` has both settlement flags false; the configured
  later capture has `finished=true` and `data_checked=true`.

All rows of all four CSVs execute the selected types and mappings. Starts and
all four expected metrics are present. Manager fields and `modified` are absent;
canonical quarantine `modified` stays null for all 26,505 rows. `xP` remains
structurally unmappable. Expected metrics are post-event outcomes, not deadline
features; Vaastav prices/ownership/transfers remain quarantined.

## Temporal and identity integrity

All 38 scheduled deadlines have accepted `is_next` snapshots with exact deadline
matches and strictly earlier capture times, ranging from 5 minutes to 6 hours
9 minutes before deadline. No backfill, interpolation or final-team/position
substitution was used. All deadline identity and price fields are populated;
29 elements have multiple observed deadline teams.

GW7 has a `2022-09-10T10:00:00Z` deadline and an accepted
`cache/2022/9/10/0633.json.xz` capture. Its 624 player observations are retained.
It has no fixtures or fixture facts and contributes no eligible reconciliation
rows. The season still has 380 fixtures across 37 fixture-bearing gameweeks.

The initial full run failed the existing person-code consistency check on exactly
two GW1 rows. Accepted GW1 and GW2 raw observations show:

| Element | Person | GW1 code | GW2/final code | Observed identity otherwise |
| --- | --- | ---: | ---: | --- |
| 546 | Luke Harris | 536122 | 515024 | Same name, team 9, position 3 |
| 558 | Hugo Bueno | 530332 | 490721 | Same name, team 20, position 2 |

The relevant captures are `cache/2022/8/5/1249.json.xz` and
`cache/2022/8/13/0627.json.xz`. Small exact identity excerpts are checked in.
Decision 024 introduces a narrowly scoped, versioned season-configured validation
policy. Each exception requires gameweek, element, both codes, source path and a
reason; every declared transition must actually be observed. Malformed, duplicate,
stale and unrelated exceptions fail. Original GW1 codes remain in deadline rows.
No corrected future identity is injected into those rows. The source pin and full
exception policy participate in the source/build identity contracts respectively.

The existing v6 default semantics and both newer build identities remain unchanged;
the additional exception policy has its own build-identity version `1`. This policy
must be considered when later designing cross-season person joins. No blanket
identity check was disabled.

## Cross-season results

All three published canonical table schemas match, including names, order, types,
nullability and information classes. Counts are explicitly separated by grain:

| Season | Players | Fixtures | Scheduled / fixture GWs | Fixture facts | Player/GW totals | Deadline rows | Hard checks |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| 2022/23 | 778 | 380 | 38 / 37 | 26,505 | 24,957 | 26,198 | 44/44 |
| 2023/24 | 865 | 380 | 38 / 38 | 29,725 | 28,742 | 29,510 | 40/40 |
| 2024/25 | 804 | 380 | 38 / 38 | 27,605 | 27,231 | 27,479 | 40/40 |

All three seasons have 20 teams, 38/38 accepted deadlines, zero duplicate fact
or snapshot keys, and 100% required settled-event points reconciliation with
zero unmatched or mismatching rows. All have zero missing snapshot codes,
team/position identities, prices and ownership. Full per-field null counts,
identities and checksums are in [the machine-readable audit](M2_CROSS_SEASON_AUDIT.json).

Additional football sanity checks verify every directed home/away club pairing
occurs exactly once, each club has 38 fixtures, all 380 fixtures are finished and
represented in the facts, and all fact minutes are within 0–90. For 2022/23,
15,160 zero-minute facts remain preserved. There are 23,409 single-fixture and
1,548 double-fixture player/Gameweek groups, explaining the difference between
26,505 fixture facts and 24,957 aggregated player/Gameweek rows. No synthetic
zero-point observation was added for a blank gameweek.

Every 2022/23 player season sum also matches the final Vaastav player aggregate;
2023/24 passes that extra check too. This cumulative comparison is distinct from
the required independent settled-event reconciliation.

### Additional 2024/25 source limitation found

Ferguson (element 123) has 27 summed fixture points and 28 final cumulative points.
The final fplcache snapshot also reports cumulative 28, while all of his settled
Gameweek `event_points` match canonical fixture sums. The archive itself exposes
the divergence:

| fplcache path | Current GW | `event_points` | `total_points` |
| --- | ---: | ---: | ---: |
| `cache/2025/2/25/1245.json.xz` | 26 | 1 | 21 |
| `cache/2025/3/8/0625.json.xz` | 27 | 1 | 23 |
| `cache/2025/5/26/0206.json.xz` | 38 | 0 | 28 |

The cumulative increase exceeds the intervening event points by one. This proves
a source cumulative/event inconsistency; its cause and the fixture to which the
extra point belongs cannot be established from these inputs. The extra aggregate
diagnostic reports it, while the existing required reconciliation still passes.
Retain the established fixture-level canonical policy; do not invent a point
allocation, rewrite the prior season, or claim final aggregates always equal sums.

## Reproducibility and commands actually run

The ingestion command downloaded and immutably preserved the real pinned inputs.
After the initial identity-quality failure, a cache-backed run with the documented
exact policy generated the successful build. Failed attempts never updated the
latest-successful catalogue. The failed report is retained as audit evidence.

Commands run successfully after implementation:

```bash
.venv/bin/python -m fpl_ai historical --season 2022-23 --output-dir data
.venv/bin/python -m fpl_ai historical --season 2023-24 --output-dir data
.venv/bin/python -m fpl_ai historical --season 2024-25 --output-dir data
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report docs/M2_CROSS_SEASON_AUDIT.json
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q fpl_ai tests scripts
.venv/bin/python -m fpl_ai --help
.venv/bin/python -m fpl_ai historical --help
git diff --check
```

- The 2022/23 command generated all seven CSVs and five metadata artifacts;
  subsequent commands reused checksum-verified builds for all three seasons.
- The checked-in audit script runs with a rejecting network fetcher and cached
  immutable bytes. It creates a fresh temporary full build of **each** season,
  reruns normalization, transforms, quality and reconciliation, and compares both
  identity hashes and all seven CSV hashes to the existing build. All match.
- Fresh-build reuse preserves every file hash and modification time. Original
  processed artifacts remain unchanged. Explicit `load_historical_build` lookups
  verify catalogue/manifest, processed-file and frozen-source checksums.
- Eight new regression tests bring the full suite to **68 passing tests**. They
  cover real headers/types, absent optional metrics, forbidden/newer columns,
  required-field loss, blank-GW grain, settled capture rejection, exact code
  exception behavior and preservation, malformed configuration, exception identity
  hashing, source evidence, and unchanged newer-season build hashes.
- Compilation, both help commands and whitespace checks pass. No dedicated lint
  or static type-check tool is configured in `pyproject.toml`.

## Build identity and artifact evidence

- `version`: `v3-9779cdbc0c07-33dac28d1895-build-9227d246d371`
- `source_identity_sha256`: `12c000cd16399629ccfb762581e479906651834ca1f377234b98e5f26fb0c3c3`
- `build_identity_sha256`: `9227d246d3718724d8118898b6548077c8963837bdf49e9bc6bf64b30a7762a0`
- `source_inventory_sha256`: `63696cce33db071417e9c7992918b7afb2cf2a33a9b8b7a71494c237ebac5a72`
- `consumed_source_records`: `44`

The frozen inventory contains four CSV inputs, the archive tree, 38 accepted
captures (including the reference), and the final settlement capture.

| Canonical CSV | SHA-256 |
| --- | --- |
| fixtures.csv | `c81bb9f945653a6386b95543f48e2c065ee6efbb9d203fd6c7f1ac496a0fb271` |
| gameweeks.csv | `00a4ae6a8f6dd0b605b49c64ffbcb3162bac0506456f4c9957aac93b9ec93f43` |
| player_deadline_snapshots.csv | `67a7f5d00e7b5ac8f64e7ad4a8aded1e8c0ad3e3ade715e316e51e6aa3c34d79` |
| player_fixture_facts.csv | `5713293c4b75c3681c2b74e949a941127ad7a1dcf1c43d4da517d95f5e2b72b6` |
| players.csv | `babd0338884a07788fb99236cf02f3e162f4aae191e6828bd7fc1a23a1b9c52e` |
| quarantined_source_metadata.csv | `5673455b5768f5adc4ddb6ac75d2138d8c00d60f02d5bb507fae8dbc50f66f90` |
| teams.csv | `e6d9b1d47004ea82c008ed13ccfd8755cda306100c743d15be6746241bca50d1` |

## Limitations and next handoff

No unresolved acceptance failures remain. Known data limitations are explicit:
periodic captures rather than exact-deadline observations; UTC filename assumption;
nullable availability and set-piece fields; unavailable historical deadline fixture
lists; quarantined unproven timing; two observed 2022/23 code changes; manager slot
identity in 2024/25; and the separate Ferguson cumulative discrepancy above.
Full generated raw/processed data remains Git-ignored. The tracked verification
report, exact pins, fixtures, tests and audit script make the batch reproducible.

Next substantial batch: add 2021/22, explicitly inspect older metric availability
and archive/settlement coverage, then complete 2025/26 and the full-range identity
and availability audit before feature/evaluation design or modelling.
