# Project state

Last updated: 2026-09-23

## Current milestone

**M5D — Joint Monte Carlo Simulation and Risk-Aware Plan Evaluation v1** is
implemented and verified; **recommend acceptance**. `joint-simulation-v1`
uses a size-weighted shared as-of block and complete donor player trajectories.
M5C residuals and M5B forecasts/expected-points optimisation remain unchanged.
The matched independent null is diagnostic only. No team/match or current-player
conditional dependence, calibration-quality or realised decision-value claim.

The real 659-player GW6–10 simulation uses **16,384 scenarios, seed 1729** and
26,305 complete prior-season trajectories across 34 blocks. All 3,340 excluded
windows are explicit season-end truncations. Three-seed doubling to 32,768 changes
means by at most 0.166 points, tail quantiles by 0.684 points and paired win
probabilities by 0.006. This numerical precision does not resolve tiny top-N gaps
or account for model uncertainty.

Simulation: `0a4dceb30cd0fba3c4ef50c8f09b4c89e74eeb3a4b3704dc70baa69ac5029a62`.
Deterministic simulation key: `355559e361d9721b598900f2507ccf73a71c7bb40fdf9dc551235de235e9b1dd`.
Evaluation: `36a266e775e124a6d36bfb813e0aedf364c200a394a82d9b25e0b48a75902c3f`.
The retained September 18 state was computed by M5B on September 21. M5D started
at September 23 10:15:48 UTC and computed its product at 10:18:25 UTC; publication
passed actual-clock final verification before the bound **October 10 10:00 UTC**
deadline. No newer information was fetched.

The demonstration squad is synthetic, not the user's team. Joint simulated means
are 165.75 no-transfer, 189.77 greedy, and 195.99/195.85/195.74 for exact paths 1–3.
Path 1's P10/P90 is 171.58/222.74, with 96.53% beating no-transfer and 67.40%
beating greedy. The independent null gives lower SD (16.90 versus 20.36 for path
1), illustrating sensitivity to dependence assumptions, not model superiority.
Raw residual bias explains simulation means differing from unchanged M5B objectives.

**299 full tests and 20 focused tests pass normally and under optimized Python.**
Independent M5D reports are byte-identical across modes. M5B's 22-case/82-path
oracle and M5B/M5C audits reproduce accepted bytes in both modes; M2/M3/M4E
audits also pass. All **1,015 pre-batch evidence files (965 data files)** preserve
bytes and nanosecond mtimes. Fresh/reuse/replay and real rehashed-corruption
probes pass. Default both-law plan computation took 4.88s; a fully verified fresh
publication took 44.82s; contended replay operations took 50–182s.

See [the exact design](docs/M5D_DESIGN.md), [verification and commands](docs/M5D_VERIFICATION.md),
[convergence evidence](docs/M5D_CONVERGENCE.json),
[acceptance summary](docs/M5D_ACCEPTANCE.json), and Decisions 057–060.
Next: personalised squad/state capture and an explainable comparison workflow;
continue prospective retention/settlement and evaluate the fixed simulator before
considering a new risk-aware optimisation objective. No commit, merge or push.

## Prior M5C result

**M5C — Prospective multi-Gameweek outcome scoring and uncertainty calibration**
is implemented and verified; recommend acceptance within its empirical-interval
scope. Fixed prior-season signed residual pools attach 50/80/90% intervals to
unchanged M5B GW+0..4 points. Separate three/five-GW pools calibrate complete
cumulative residuals directly, without assuming independent Gameweeks.

Calibration uses exactly 139,857 consumed 2025/26 historical OOS prediction rows
from the accepted M5B/M3 identities. Latest label is May 25, 2026; the information
cutoff is July 1. Historical coverage on that same evidence is not validation.
Horizon-only pools are fixed for 2026/27; scoring cannot tune them, change point
models or alter expected-points optimiser semantics. Player-specific/conditional
coverage and a joint Monte Carlo distribution are not claimed.

`python -m fpl_ai uncertainty calibrate|freeze|verify|settle|score` exposes four
separate immutable artifact families under `data/multi_uncertainty/`. Every target
GW can settle independently through the existing authoritative FPL validator.
Reports accumulate deduplicated point-error/interval evidence by target, horizon
and position; cumulative scores require all corresponding outcomes. Missing
players reject settlement, explicit zeros remain zeros and genuine blanks stay null.

The real retained 659-player GW6–10 projection now has an uncertainty artifact,
published September 23 at 08:57:50 UTC. An actual official API check at 09:01 UTC
confirms GW6–10 unfinished/unchecked; GW6's deadline is October 10 at 10:00 UTC.
Premature settlement fails closed. The real report has zero settled targets and
all five pending; full settlement/scoring is proven with deterministic synthetic
fixtures, not fabricated current outcomes. GW5 is now observed settled, but its
separate original M4C lifecycle artifacts remain unchanged.

**279 tests pass normally and under optimized Python**, including 18 focused
M5C tests. Independent M5C reports match across both modes; M5B's existing
historical/model/plan audit and 22-case/82-path oracle reproduce accepted bytes.
All **951 pre-batch data files retain bytes and nanosecond mtimes**. No accepted
historical/model artifact, dependency or planner implementation changed.

The representative unchanged full-population top-three planner run took 110.84s:
29 MILP calls including greedy, with top-three count proofs consuming 63.30s.
Its rebuilt decision is byte-identical to M5B. Profiling did not justify a safe
production optimisation, and exact ranking remains intact.

See [M5C verification and operator commands](docs/M5C_VERIFICATION.md),
[machine evidence](docs/M5C_VERIFICATION.json), [live status](docs/M5C_LIVE.json),
[regression/preservation](docs/M5C_REGRESSION.json), and
[runtime profile](docs/M5C_PROFILE.json). Decisions 053–056 record the fixed contract.
No commit, merge or push was performed in M5C.

Next: retain useful nearer-deadline states when the actual clock permits; settle
and accumulate genuine GW6–10 evidence after authoritative completion. A later
Monte Carlo/risk-aware planning batch must define joint dependencies and test
utility; M5C does not authorise automatic recalibration or a risk penalty.

## Prior M5B result

**M5B — Multi-Gameweek Projections and Transfer-Path Optimiser v1** is verified
and complete; recommend acceptance. Five direct hist_15 models forecast
individual GW offsets 0–4 from one frozen state. Historical fits use
2021/22–2024/25, evaluated on consumed 2025/26; production refits use all valid
prior-season evidence. GW+0 has a distinct fitting population from frozen M4E;
both control/v2 remain unchanged and explicit comparisons are retained.

The separate sparse MILP evolves legal squads, integer bank, original selling
rights, free transfers and hits, selecting XI/captain every GW. It ranks complete
paths with exact tie semantics, no-transfer and sequential greedy comparisons.
Prices/selectability are static assumptions; no chips, fixture features, price
forecasts, risk penalties or realised utility improvement is claimed.

Use `python -m fpl_ai project fit|freeze|verify` and `python -m fpl_ai plan`.
See [M5B verification and exact commands](docs/M5B_VERIFICATION.md),
[machine evidence](docs/M5B_VERIFICATION.json),
[independent exhaustive oracle](docs/M5B_ORACLE.json), and
[regression/preservation](docs/M5B_REGRESSION.json). The real GW6–10 projection
uses the retained September 18 state with actual September 21 UTC computation;
it is early evidence, not near-deadline confirmation. Demonstration squads are
synthetic, not the user's team.

**261 tests pass normally and under optimized Python.** The independent sweep
checks 22 cases / 82 feasible ranked paths: 15 cases return five and seven
return only the no-transfer path because no transfer is affordable. Top-N is a
maximum, not a guaranteed count; all returned paths pass the oracle checks.
Normal/optimized verification and oracle reports are byte-identical. Two focused
regressions guard the top-N and emitted-count reporting contracts; see the
[evidence correction](docs/M5B_EVIDENCE_CORRECTION.json). Fresh models, separate scores and full top-three
plans reproduce their identities; reuse preserves bytes/mtimes. All **920**
pre-batch data files retain bytes and nanosecond mtimes. The full-population
five-GW demo scores **194.178** after eight hit points versus **164.065** with no
transfers and **188.020** sequential greedy. It rolls in GW9 and uses two FTs in
GW10. These are projected objectives on a synthetic squad, not realised gains.
The final top-three run took approximately 110 seconds locally. No commit,
merge or push was performed.

The subsequent M5C result is recorded above. Continue manual nearer-deadline
retention and settled M4E evidence without control/v2 reselection or retrospective
performance claims.

## Prior M5A result

**M5A — Rules-aware current-squad transfer optimiser v1** is **verified hardened and complete**. It takes
an immutable M4E forecast, explicit control/v2 choice and a validated 15-player
squad with exact selling prices, bank and free transfers. It returns deterministic
ranked legal transfer plans, optimal XI/captain, hits, bank and gain against the
best legal no-transfer baseline. Rules and decisions are separately versioned;
M4E models and all earlier analytical guarantees remain frozen.

Run `.venv/bin/python -m fpl_ai optimise --forecast-dir "$FORECAST" --model-dir
"$MODEL" --model control --squad my-squad.json --max-transfers 2 --top-n 3`.
Use `--model v2` for an explicitly chosen separate run. See
[M5A verification](docs/M5A_VERIFICATION.md) for exact real forecast/model paths,
input format, algorithm, checks and limitations;
[machine evidence](docs/M5A_VERIFICATION.json) records the synthetic GW6 demo,
independent arithmetic/XI checks and deterministic fresh/reuse results.
[Regression evidence](docs/M5A_REGRESSION.json) records full normal/optimized tests
and prior-artifact byte/mtime preservation. **238 tests pass normally and under
optimized Python** (236 before this pass plus two new; 28 focused tests in both modes). The demo
checks both explicit models over 659 forecast rows, **554 transfer-in-eligible**
players, 540 eligible not owned, and 15 owned (one unselectable but retainable).
The solver population is 555. Selectability comes only from the bound snapshot's
strict boolean `can_select`; no later data or status proxy. Tie loss is <=1e-6
inclusive from each rank's best remaining objective, with exact input-float-sum
boundary checks before fewer-transfers and lexicographic squad priorities.
All original demo plan fields remain unchanged, including winners 124 and 449,
independently confirmed selectable in that snapshot;
control net is 34.090866 versus baseline 30.700207, and v2
net is 30.701324 versus baseline 28.014028. These are projected demo objectives,
not outcome or model-quality evidence. All **904 pre-hardening data files retain
bytes and nanosecond mtimes**; normal/optimized real-verifier reports match exactly.
M5A acceptance is restored after separating structural validation from semantic
tie admission (Decision 049 corrects Decision 048's incomplete conclusion).
All structural rows remain checked after rounding. The conditioned objective row
admits candidates directly to the exact Fraction gate; numerical admission never
implies acceptance within the unchanged inclusive <=1e-6 band. Presolve-disabled
retry and fail-closed optimality are retained. The reviewer's seeds 1596/top-1 and
26/top-10 fail against the old guard and pass the new exhaustive regressions.
A 400-seed positive-xPts sweep at depths 1/3/10/20 verifies 1,600 cases against an
independent exhaustive oracle, with 121 actual out-of-band rejections; normal and
optimized sweep reports are byte-identical. No commit, merge or push performed.

This is a **one-Gameweek optimiser v1**, not full multi-Gameweek planning. It cannot
value rolling transfers, future fixtures, uncertainty, chips or squad flexibility.
The demo squad is synthetic and is not the user's team. No model quality or
realised decision-utility improvement is inferred from optimised forecasts.

M4E prospective evaluation continues independently: retain nearer-deadline GW6
states when the actual clock permits, settle/score only authoritative outcomes,
and accumulate evidence without premature control/v2 selection. Recommended next
substantial objective: **multi-Gameweek projections and transfer-path optimisation**.

The following sections preserve earlier milestone evidence and its original scope.

## Current M4E result

M4E implements fixed prospective control/v2 xPts for 2026/27. Both models refit on
exactly **56,804** prior-season downstream-safe rows (27,159 in 2024/25 and 29,645
in 2025/26); latest label **2026-05-25 10:23 UTC**, supported states from
**2026-07-01 00:00 UTC**. No new search or current-season fitting target.

The live adapter preserves all 25 original inputs and adds independently frozen
expected minutes only for v2. Current-season points history uses earlier verified
settlements received by capture, retaining explicit zeros, missingness and source
provenance. Exact snapshot/model/key joins and actual-clock publication gates fail
closed. Outcomes and scoring remain separate immutable products.

A real **659-player GW6** control/v2 forecast completed at **2026-09-18 21:07:49 UTC**
and independently verified at **21:08:23 UTC**, before the **October 10 10:00 UTC**
deadline. This is an early state with missing retained points/recent-minutes history,
not near-deadline confirmation. GW5's original minutes artifacts are unchanged;
GW5 was still unfinished/unchecked. No live xPts outcome or score is claimed.

M4D's mixed historical result remains unchanged. Both models coexist; new settled
prospective evidence is necessary before claiming v2 improves real FPL decisions.
No untouched historical holdout, optimiser, recommendation or product-utility claim.
210 tests pass normally and under optimized Python; independent evidence matches
in both modes. All 822 pre-batch data files retain bytes and mtimes.
See [M4E verification and exact operator commands](docs/M4E_VERIFICATION.md),
[machine evidence](docs/M4E_VERIFICATION.json), [real live evidence](docs/M4E_LIVE.json)
and [regression/preservation](docs/M4E_REGRESSION.json).

The sections below preserve the earlier batch records.

## Current M4D result

M4D is implemented and verified: the first historical OOS minutes-to-xPts interface. Exactly **56,804**
verified forecasts join to frozen M3 decision states: **27,159** 2024/25 fitting rows
and **29,645** 2025/26 evaluation rows. All have independent points labels. Earlier
80,858 rows remain unavailable; no backwards stacking or minutes-outcome requirement.
Ferguson GW27 remains eligible for points without resolving its minutes anomaly.

The fixed `hist_15` control/v2 comparison uses the same rows and original 25 inputs,
with v2 adding only OOS expected total GW minutes. RMSE **1.925490 → 1.916745**,
MAE **0.952499 → 0.932555**, Spearman **0.738961 → 0.744086**; top-10 realised points
**5.050000 → 4.815789**. The ranking tradeoff is real. Frozen M4 RMSE is 1.916449,
slightly better than v2, with a different training population. No model reselection.

Fit labels end **2025-05-26 02:06 UTC**, before first evaluation capture
**2025-08-15 12:52 UTC**. 2025/26 is consumed historical evidence, not a fresh holdout.
No prospective or FPL decision-utility claim. Separate immutable prediction/score
families preserve feature/outcome separation; strict source/state joins and the
M4C downstream loader reject incompatible or corrupt inputs.

198 tests pass normally and under `python -O`; independent M4D evidence is identical
in both modes. Fresh builds, saved-state replay, target-mutation isolation, reuse and
all prior milestone replays pass. All **783 pre-batch files** retain bytes and mtimes.
M4D is recommended complete; no commit, merge or push has been performed.

See [M4D verification](docs/M4D_VERIFICATION.md), [machine evidence](docs/M4D_VERIFICATION.json)
and [preservation/regression](docs/M4D_REGRESSION.json). The following M4C section
is its frozen historical batch record, including the separate pending GW5 lifecycle.

## Prior M4C result

M4C is implemented and verified. **56,804 chronological OOS minutes forecasts** are
available: **2024/25 GW1–38: 27,159**, **2025/26 GW1–38: 29,645**. Earlier 2021/22–
2023/24 rows (**80,858**) remain explicitly unavailable for downstream training.

Selection remains the M4B bounded `hist_15` choice, with information cutoff
**2024-05-20 06:25 UTC**. Refit once before each forecast season: 80,234 evidenced
2021/22–2023/24 labels for 2024/25; 107,392 labels through 2024/25 for 2025/26.
Fitting cutoffs are respectively 2024-05-20 06:25 and 2025-05-26 02:06 UTC, strictly
before first captures 2024-08-16 12:38 and 2025-08-15 12:52. Preprocessing and
baseline fallbacks share the same fitting populations. No within-season refit or
later/prospective selection. OOS outputs, outcomes, and M4B development predictions
remain distinct immutable families; `load_downstream` enforces the OOS boundary.

The Ferguson GW27 discrepancy was investigated across 56 pinned neighbours:
287 cumulative minutes was already marked settled, then changed to 304 between
March 2 18:29 and March 3 01:52, with one additional total point. Cause remains
unresolved. One minutes target is unavailable, never fitted or used in history;
his cumulative predictor is missing in GW28–38 (11 rows). Later independently
reconciled GW deltas and all unrelated players remain usable. No correction.

A real **2026/27 GW5 snapshot and 659-row forecast** were created with the existing
CLI, forecast completed **2026-09-18 08:27:13.598395 UTC**, before the **17:30 UTC**
deadline. Immutable verification passed. Premature live settlement was rejected;
**no settlement or score yet**. Initial recent history and availability changes
are missing; expected points is null. Full successful settlement schema compatibility
still needs that next legal stage. Current fixture v2 remains enforced.

Walk-forward model MAE/RMSE: **13.304010 / 22.944441** (2024/25; 27,158 scored),
**12.114528 / 21.776158** (2025/26; 29,645 scored). Availability-aware baseline
MAE/RMSE: 12.603902 / 24.818716 and 11.410267 / 23.873513. Better RMSE, worse MAE;
no new untouched holdout, prospective quality or decision-utility claim.

186 tests pass normally and under `python -O`; M2/M3/frozen M4/M4B replays and
new independent raw-evidence/fresh/reuse checks pass. All **664 pre-batch data files**
retain bytes and mtimes. No dependency change, xPts v2, scheduler, commit or merge.
See [M4C verification](docs/M4C_VERIFICATION.md), [machine evidence](docs/M4C_VERIFICATION.json),
[discrepancy](docs/M4C_DISCREPANCY.md), [live evidence](docs/M4C_LIVE.json), and
[preservation](docs/M4C_REGRESSION.json). Historical milestone sections below remain
frozen records of the earlier batches.

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
- Milestone 3 provides offline features and baseline evaluation through `python -m fpl_ai features`. Milestone 4 consumes its frozen products through `python -m fpl_ai experiment validate` and `experiment holdout`; M5A now implements the one-GW rules/decision boundary described above.

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

## Verified Milestone 3 batch (2026-09-17)

- 137,662 football-player rows; 137,038 labels, with 624 fixture-empty GW7 rows
  retained but unlabelled. AM excluded. Target sums all target-GW fixture points.
- 27 allowlisted predictors: eight accepted snapshot fields, seven points-history
  fields and 12 missingness flags. Earlier GW points require independently settled
  evidence at or before capture; no fixture context, quarantine, xP or final identity.
- Season-local identity and observed code audit preserve all historical anomalies;
  656 GW18 exception rows retain the 12:33 state and 207-minute freshness gap.
- Train 2021/22–2023/24; validation 2024/25; final holdout 2025/26. Training means
  cannot consume validation/test labels. Player histories update prospectively.
- Five deterministic baselines: overall/position training means, recent points,
  player season scoring rate, and separate FPL ep_next. MAE/RMSE and per-GW
  Spearman report coverage by split, season and position.
- Versioned, checksum-verified artifacts under ignored `data/modelling/<identity>`
  separate predictors, labels, predictions and audit metadata. Fresh outputs are
  byte-identical across roots; reuse preserves bytes/mtimes. Exact historical build
  pins, source identities, contracts, schemas and hashes are in the manifest.
- 132 tests pass, including all 112 existing tests. Full five-season M2 offline
  rebuild/audit passes. All 124 pre-existing historical processed files and catalogue
  bytes remain unchanged in M3 verification; no M2 source/configuration code changed.
- Validation recent-points MAE/RMSE: 1.0888/2.2029; FPL: 1.1071/2.1213.
  Final holdout separately: recent 1.0729/2.2077; FPL 1.0692/2.1234. No tuning
  or significance/superiority claim follows from these descriptive differences.
- [Verification, exact commands and limits](docs/M3_VERIFICATION.md),
  [machine evidence and source traces](docs/M3_VERIFICATION.json), Decisions 031–035.

## Milestone 3 hardening

All four review findings are addressed: every target requires matching integer
settlement evidence; identity covers serialized products; reuse enforces the exact
artifact set and checksums; verification uses explicit checks active under python -O.
The 137,662-row population, 137,038 labels, features, splits and baseline definitions
remain unchanged. All 4,553 empty-player zeros have explicit matching settlement
evidence. The new identity intentionally replaces the incomplete four-file code-hash
boundary; old published artifacts remain intact. See Decision 035 and the verification
record for normal/optimized runs, preservation and unchanged metric comparisons.

## Verified Milestone 4 batch (2026-09-17)

- M3 input `57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a`;
  feature, target, split and freshness contracts unchanged. 25 model inputs from
  the 27-feature artifact, excluding season-local team ID and its indicator.
- Ridge alpha 10/100 and histogram boosting 15/31 leaves; fixed common train-only
  imputation/scaling/encoding, original missingness flags retained. No new features.
- 80,234 labelled training rows from 2021/22–2023/24; 27,159 validation rows in
  2024/25. Validation RMSE selected hist_15. No early stopping, validation refit,
  test-based selection or clipping. Pipelines saved before test evaluation.
- Freeze `09eb67bd0fc9198073c28f921e3ba0ffd67876f341d32a97dc0f76743e0d411c`;
  validation MAE **0.9853**, RMSE **1.9164**, within-GW Spearman **0.7269**.
- Separate test `21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd`;
  29,645 rows, MAE **0.9537**, RMSE **1.9164**, Spearman **0.7415**, full coverage.
  RMSE improves 8.2% over scoring rate and 9.7% over archived ep_next, with lower
  squared error in every one of 38 test GWs against every baseline.
- Coefficients, validation permutation diagnostics, paired GW bootstrap deltas,
  all position/history segments, distributions/extremes and disagreements retained.
  17 extreme/disagreement rows match all eight raw snapshot state fields.
- Known model limits: 1,654 small negative test forecasts; test defender average
  1.086 predicted versus 1.240 actual; strong reliance on transfer activity and
  availability; no causal interpretation or squad-selection utility established.
- **145 tests pass**. Fresh training and holdout replay produce identical model,
  prediction, metric and diagnostic bytes. Reuse preserves mtimes. All 146 tracked
  pre-batch historical/M3 files (124 historical processed, 21 M3, one catalogue)
  remain byte/mtime-identical; M3 verification JSON is exactly unchanged.
- Added pinned scikit-learn 1.7.2 / NumPy 2.3.3 / SciPy 1.16.2 / joblib 1.5.2 /
  threadpoolctl 3.6.0. No large framework or architectural rewrite.
- Full record: [M4 verification](docs/M4_VERIFICATION.md),
  [machine-readable evidence](docs/M4_VERIFICATION.json),
  [anomaly traces](docs/M4_SANITY_TRACES.json),
  [preservation](docs/M4_REGRESSION.json), Decisions 036–037.

## Verified M4B batch (2026-09-17)

- Separate `playing-time-v2`: 80,858 rows, 80,234 independently checked minutes
  targets, 3,784 explicit empty-player zeros, 4,705 multi-fixture rows; all 624
  fixture-empty GW7 rows and all 656 GW18 freshness exceptions preserved.
- 11 values + 9 missingness flags: observed position/status/chance, previous and
  recent evidenced minutes, appearance fraction, cumulative minutes/starts,
  consecutive availability changes. GW1 stale cumulative totals excluded.
- Train 2021/22–2022/23 (50,724 labels), development 2023/24 (29,510).
  Latest fit label 2023-05-29 06:23; first development capture 2023-08-11 12:31 UTC.
- One fixed histogram model plus three baselines. Selected model minutes MAE
  12.659552 / RMSE 23.292082; availability-aware baseline 12.302370 / 25.346981.
  Better RMSE does not imply better MAE or clean prospective confirmation.
- Feature identity `4f2ef778e5df032ffa22457811c6ba5845d0f8dbc51ff83cb6292cbfa8f6003c`;
  minutes freeze `e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc`.
- 2024/25 source-only audit finds element 123 GW27 cumulative delta 34 versus
  canonical 17; excluded from minutes build, no guessed correction. No new
  2025/26 model/feature selection or minutes evaluation.
- Historical fixture context still unavailable. Prospective official fixture
  snapshots retain timing/identity, but v1 minutes does not consume fixture inputs.
- CLI capture/freeze/verify/settle/score implements pre-deadline immutable minutes
  forecasts and separate verified settled scoring. Optional prior snapshot and
  settled forecast pairs provide availability/minutes history. Expected points
  remains null. Tested offline, not yet smoke-tested on live 2026/27 endpoints.
- No stacked xPts inputs: development-only predictions are explicitly forbidden
  as downstream training features. Chronological OOS integration remains next work.
- 176 tests pass normally and under `python -O`. Fresh minutes builds and normal /
  optimized reports match exactly. All five historical builds, M3 and frozen M4
  replay pass; 179 pre-batch fingerprinted files retain bytes/mtimes.
- No new dependency, scheduler, service, optimiser, commit or push.
- [Full verification](docs/M4B_VERIFICATION.md), [source evidence](docs/M4B_SOURCE_AUDIT.json),
  [machine checks](docs/M4B_VERIFICATION.json), [regression](docs/M4B_REGRESSION.json).

## M4B fixture-evidence hardening

- Prospective schedule/settlement contracts are v2: empty/missing payloads,
  malformed rows, unknown event assignments and schedules with no assigned events
  fail. A valid nonempty schedule may establish a blank target GW.
- `playing-time-v2` derives fixture-bearing GWs from independent processed
  `fixtures.csv`; every scheduled fixture requires football-player facts with a
  matching GW. The verifier independently performs the same schedule-vs-fact audit.
- Schedule use is exclusively post-event label/evidence validation, never a predictor.
  Whole-GW or partial-double fact loss now fails instead of becoming a blank.
- Six additional regressions; 176 tests normally and under `python -O`. All
  feature/label/audit CSVs, saved minutes model bytes, forecasts and metrics remain
  identical to the original M4B products. New identities bind the stronger contract
  and the exact consumed schedule hash; old artifact directories remain untouched.
- M2/M3/original M4 and prior M4B artifacts retain all 638 fingerprinted data files'
  bytes/mtimes. Fresh/reuse verification remains exact, including optimized Python.
- Genuine 2022/23 GW7 stays unlabelled; doubles, explicit player zeros, GW18 freshness,
  the 2024/25 discrepancy and downstream-training prohibition remain unchanged.

## Recommended next step

Review M4E's fixed operational protocol and verified real GW6 forecast. Continue
manual retention, preferably nearer the deadline, and include only history already
settled before each capture. After GW5 is authoritatively finished/checked with
finished fixtures, settle and score its unchanged minutes forecast; then it can
supply history for a later GW6 state. Settle and score GW6 separately when legal.
Exact commands are in `docs/M4E_VERIFICATION.md`.

Both control and v2 remain available. Accumulate new prospective evidence; do not
retune on consumed 2025/26 or infer decision value from one early forecast. The
Ferguson cause, unavailable historical fixture predictors, initial history warm-up,
local timestamp attestation and optimisation utility remain unresolved. No commit,
merge or push has been performed for M4E.
