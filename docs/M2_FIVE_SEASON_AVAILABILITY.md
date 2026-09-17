# Five-season historical availability and identity guide

Verified range: **2021/22–2025/26**, 190 deadline captures. This is a data-contract
inventory for Milestone 3 design, not an implemented feature set or evaluation plan.
Exact counts, source categories, observed JSON types and per-field Gameweeks are in
`evidence_audit` in [the machine-readable audit](M2_CROSS_SEASON_AUDIT.json).

## Accepted coverage

| Season | Players | Fixture facts | Deadline rows | Settled totals compared | Team-changing elements |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2021/22 | 737 | 25,447 | 25,150 | 23,230 | 16 |
| 2022/23 | 778 | 26,505 | 26,198 | 24,957 | 29 |
| 2023/24 | 865 | 29,725 | 29,510 | 28,742 | 23 |
| 2024/25 | 804 | 27,605 | 27,479 | 27,231 | 31 |
| 2025/26 | 841 | 29,747 | 29,645 | 29,338 | 27 |

Each season has 20 teams, 380 fixtures, 38 deadlines, complete eligible points
comparison coverage (`1.0`) and zero unexplained mismatches. Every team has 38
fixtures and every directed home/away pairing occurs exactly once. Canonical
schemas remain compatible. Season counts differ because the player population,
zero-minute observations and scheduling differ; no equal population is fabricated.

## Can a field support consistent, leakage-safe construction?

| Field family | 2021/22 | 2022/23 | 2023/24 | 2024/25 | 2025/26 | Information boundary |
| --- | --- | --- | --- | --- | --- | --- |
| Minutes, total points and core outcomes | Present | Present | Present | Present | Present | Realised fixture outcomes; unavailable for predicting that same fixture/GW |
| Starts | Absent/null | Present | Present | Present | Present | Realised outcome; do not infer unavailable 2021/22 starts from minutes |
| xG, xA, xGI, xGC | Absent/null | Present | Present | Present | Present | Realised outcomes; presence does not establish comparability of upstream metric methodology |
| Deadline team/position, price, ownership | Complete | Complete | Complete | Complete | Complete | Snapshot-observed state only; price is integer tenths of £1m |
| Transfers in/out for event | Complete | Complete | Complete | Complete | Complete | Observed counters at capture, not final GW transfer counts |
| Availability status | Complete | Complete | Complete | Complete | Complete | Observed status at capture |
| Chances, news, news timestamp | Partial/empty values | Partial/empty values | Partial/empty values | Partial/empty values | Partial/empty values | Preserve missingness and empty news; absence is not certainty of fitness |
| Set-piece orders | Sparse | Sparse | Sparse | Sparse | Sparse | Only declared orders at capture; null is not zero |
| Archived FPL `ep_next` | Complete | Complete | Three null rows | Complete | Complete | Existing timestamped external prediction field; distinct from forbidden Vaastav `xP` |
| Vaastav selected/value/transfers | Quarantined | Quarantined | Quarantined | Quarantined | Quarantined | Independent capture timing unproved; never trusted deadline state |
| Vaastav `modified` | Absent/null | Absent/null | Absent/null | Quarantined | Quarantined | Audit-only flag; not temporal evidence |
| Vaastav `xP` | Forbidden | Forbidden | Forbidden | Forbidden | Forbidden | Structurally unmappable to every processed table |
| Defensive contribution, CBI, recoveries, tackles | Absent from merged inputs | Absent | Absent | Absent | Present, raw-only | Typed fixture outcomes retained in raw files; intentionally excluded from shared canonical tables |
| Assistant Manager elements/metrics | Absent | Absent | Absent | AM slots present; metrics excluded | Absent | Manager slots are not football-player person identities |
| Final fixture schedule/opponents/difficulty/results | Post-event | Post-event | Post-event | Post-event | Post-event | Never a deadline-known fixture schedule |

“Complete” describes populated canonical observations at accepted captures, not
continuous coverage between captures or a guaranteed external semantic contract.
Nullable metrics and nonempty counts are distinct: an empty news string is preserved
but is not useful news content. Raw arrays count as nonempty only when populated.

The audit separates five cases explicitly:

1. **Genuinely unavailable:** e.g. 2021/22 starts/expected metrics and historical
   per-deadline fixture lists. No filling, interpolation or proxy fabrication.
2. **Intentionally excluded/forbidden:** final-player aggregates and metadata,
   manager metrics and new defensive raw-only fields are excluded from common
   outputs; unsafe Vaastav `xP` is forbidden, not merely an unused predictor.
3. **Quarantined:** Vaastav ownership, prices, transfers and `modified` have no
   established independent deadline timestamp, regardless of apparent plausibility.
4. **Trusted deadline observations:** team, position, price, ownership, transfer
   counters, status/chances/news, set-piece orders and archived `ep_next`, from the
   selected raw snapshot only. New raw bootstrap fields have capture provenance
   but are not automatically included in the canonical allowlist.
5. **Post-event outcomes/context:** realised fixture facts, final fixture schedule
   and results, and explicitly named final identity audit fields. Use in future
   work requires respecting when outcomes/context actually became available.

### 2025/26 additions and exclusions

The four defensive statistics are present as integer values in all 29,757 merged
source rows and all 29,645 accepted raw bootstrap element observations. The latter
are cumulative state at capture, not same-GW realised fixture values. They are
available in pinned raw evidence, not in the common canonical schema. Building a
future feature from them would require a separately versioned contract and a
shorter supported training window; this batch implements neither.

Other raw bootstrap additions are partial-season:

| Field | Gameweeks where key exists | Rows with key | Nonempty values | Observed JSON type |
| --- | --- | ---: | ---: | --- |
| `scout_risks` | 15–38 | 19,348 | 1,795 | list |
| `known_name` | 27–38 | 9,916 | 851 | string |
| `price_change_percent` | 30–38 | 7,462 | 7,462 | string |
| `scout_news_link` | 30–38 | 7,462 | 649 | string |

Final-player CSVs have these fields, but final-season metadata cannot fill their
earlier absence. Team `link_url` is raw-only. No new field changes the established
canonical output schema. New scoring-related raw statistics also mean equal field
names alone do not prove equal scoring rules across seasons; any later scoring
reconstruction needs explicit season rules, which remain unimplemented.

## Identity and timing constraints

Use `(season, element)` for canonical local identity. Across all five seasons,
841 numeric element IDs correspond to different codes in different seasons. The
person-code audit excludes AM slots and finds 1,777 distinct final football-player
codes, 1,016 represented in multiple seasons, and no duplicate final codes within
a season. It reports 51 codes whose positions differ across seasons, including
Bowen (MID→FWD) and Gakpo (FWD→MID) in 2025/26. These are observations, not a
normalization rule. No player changes observed position within any of the five
seasons. Team changes remain snapshot-specific and never use final-season teams.

Specific retained limitations:

- 2022/23 GW1 Luke Harris (546) and Hugo Bueno (558) have exact audited code
  changes. Preserve earlier observed codes; do not naively join every snapshot
  to final person code. The source exceptions remain unchanged.
- 2024/25 Assistant Manager element 748 changes person code on ten accepted
  snapshot rows. The element represents a club-manager slot; exclude AM from
  football-player identity linking. Manager outcomes are not newly reconstructed.
- 2021/22 GW37 has 101 source `GKP` rows normalized through its existing explicit
  goalkeeper alias. Fixture 263 retains its exact 78-row delayed-kickoff policy.
- 2025/26 renamed directories produce ten identical repeated source facts.
  Exact hash-bound filtering preserves one fact per fixture without rewriting IDs.
- Final 2025/26 element 841 (Sillah) is absent from the accepted GW38 deadline
  observation and is not backfilled. Snapshot coverage means the observed player
  population, not every player who appears later in the final source.

Normal snapshots require an exact authoritative deadline and capture strictly
before it. The sole authorized exception remains 2021/22 GW18, observed at 12:33
with payload deadline 13:30 versus authoritative 16:00: **3h27 freshness limitation**.
The later capture is forbidden. 2025/26 ages range from 22 minutes to 5h35; its
post-deadline GW38 13:49 capture is rejected despite `is_next=true`.

2022/23 GW7 has deadline observations but no fixtures. Partial team blanks and
doubles are listed in the machine audit; all fixtures in a double share the same
Gameweek cutoff. Fixture assignment is final/post-event, not a historical schedule
as known at each deadline.

Settled-event reconciliation is the primary points gate. Earliest independent
settlement remains specific to the configured 2021/22 strategy. Other seasons use
their next-deadline comparisons plus pinned final settlement. All captures are
checked against deadlines, settlement flags and final kickoff timing. The 2024/25
Ferguson cumulative total (28) versus fixture sum (27) remains a separate diagnostic;
no point is invented or allocated to force equality.
