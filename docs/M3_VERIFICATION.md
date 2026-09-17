# Milestone 3 — Feature and evaluation foundation

Verified 2026-09-17. This batch satisfies the current Milestone 3 exit criterion:
an honest, reproducible evaluation harness. It implements deterministic features
and five non-ML baselines, not a trained predictive model or recommendations.
No commit or merge was made.

Inspected README, PROJECT_STATE, ROADMAP, PROJECT_VISION, DECISIONS, historical
source configuration/schemas/pipeline/tests, all seasonal acceptance records and
the full-range availability/identity audit before implementation. M1/M2 production
code, configurations, builds and evidence remain unchanged.

## Contracts and artifacts

See Decisions 031–035 and `fpl_ai/modelling_contract.py` for executable definitions.
Target: unmultiplied realised player points in the upcoming GW, summed across its
fixtures. Population: accepted snapshot football positions 1–4, keyed by season,
target GW and element. Missing player fixture groups in otherwise fixture-bearing
GWs have zero labels only with matching integer settlement evidence; globally fixture-empty 2022/23 GW7 has
null labels and is excluded from fitting/scoring. No AM observations enter M3.

Features comprise eight snapshot fields (team/position IDs, price, ownership,
transfers in/out, status, chance next round), seven points-history fields (previous
GW points, 3/5-GW means and counts, season mean/count), and 12 missingness flags.
They use accepted snapshot capture time, not a claim of immediate deadline state.
All history is season-local, strictly earlier-GW and independently settled by
capture. Missing means remain null; windows count calendar GWs, not appearances.
Other final-source outcome statistics and all fixture strength/context are deferred.

Data lives under `data/modelling/<identity>/`:

- `features.csv`: keys plus the 27 allowlisted predictors; no labels/benchmark.
- `labels.csv`: keys, split, nullable target and label availability timestamp.
- `predictions.csv`: keys and five baseline predictions; ep_next stays separate.
- `row_audit.csv`: capture/deadline, freshness, source path/hash, observed code,
  exception/payload deadline and label status; audit fields are not predictors.
- `schema.json`: full versioned target/feature/split/evaluation contract.
- `evaluation.json`: coverage, sanity/missingness counts and split/season/position metrics.
- `manifest.json`: exact consumed historical versions, source/build identities and
  contracts, table hashes, settlement sources/hashes and serialized-product hashes.

Default resolves the five published builds; `--builds-from` pins an earlier
manifest's exact versions. Atomic publication and checksum-verified reuse exclude
absolute paths and generation times from identity. Fresh outputs match byte-for-byte.

## Actual verification

The full machine record is [M3_VERIFICATION.json](M3_VERIFICATION.json), including
artifact hashes, exact historical identities, every feature's missing count,
segmented metrics and 17 independent raw-source row traces. Full M2 offline rebuild
and audit also passes for all five seasons (`/tmp/m3-hardening-historical.json`).

132 tests pass: all 112 M1/M2 tests plus 20 M3 tests. New regressions cover same-GW
and future-outcome mutations, future snapshot state, calendar lag/missingness,
double aggregation and first-fixture isolation, delayed settlement, season reset,
code anomalies, null versus zero, empty GWs, AM exclusion, forbidden fields,
benchmark separation, exact splits, no validation/holdout fitting, tied ranking,
coverage metrics, historical adapter/raw checksum failure, deterministic publication,
reuse and output corruption. Compilation, CLI help, dependency and whitespace checks pass.

The real audit compares a fresh build in a temporary root to the published M3
artifacts, including manifests, then confirms reuse preserves bytes and mtimes.
All **124 pre-existing historical processed files** and catalogue bytes remain
unchanged during the M3 verification. Historical loader verifies the accepted
raw inventories; the M3 code performs no historical writes.

## Population and sanity

| Season | Split | Rows |
| --- | --- | ---: |
| 2021/22 | train | 25,150 |
| 2022/23 | train | 26,198 |
| 2023/24 | train | 29,510 |
| 2024/25 | validation | 27,159 |
| 2025/26 | final test | 29,645 |

Total: **137,662** rows, **137,038** labelled; 624 unlabeled GW7 rows.
Train has 80,858 rows (80,234 labelled). Positions: GK 15,277; DEF 45,987;
MID 59,884; FWD 16,514. Exactly 320 AM snapshot rows excluded.
132,485 labels have fixture rows; 4,553 are explicit empty player sums.
Target range −5 to 30, mean 1.167662, 85,478 zeros and 575 negatives.

All eight state fields are complete except chance next round (50,791 nulls).
Previous points has 3,675 nulls; rolling/season means each have 3,051 nulls.
Counts and missingness flags are complete. No forbidden/quarantined, post-event
fixture or external benchmark column entered features.csv.

All 656 GW18 2021/22 rows preserve state as of 12:33 and the 207-minute freshness
gap to 16:00, with the superseded 13:30 payload deadline. Harris/Bueno original
codes remain; 2025/26 GW38 Sillah is absent, without final-state backfill.

Source tracing checks raw snapshot price/team/code and independently recomputes
prior three calendar-GW points against the pinned settled event points. Examples:
Salah 2021/22 GW18 has target 2 and prior-three mean 7⅓; Roerslev GW21 has
fixture targets 14+0=14 and prior-three mean ⅔. Salah 2022/23 GW7 retains features
(prior-three mean 5⅓) but no target. Each season also has a true double and an
observed team-transfer trace. Exact prior values and source hashes are in JSON.

## Frozen baseline results

Train 2021/22–2023/24, validation 2024/25, final holdout 2025/26. Means fit only
settled training labels; training reports expand chronologically, while validation
and test use fixed training fits. Player history updates prospectively from earlier
settled GWs within its own season. All baseline/window/fallback choices were fixed
before first evaluation; none were selected using holdout scores.

| Baseline | Validation MAE | Validation RMSE | Test MAE | Test RMSE |
| --- | ---: | ---: | ---: | ---: |
| Historical mean | 1.4768 | 2.3451 | 1.5368 | 2.3749 |
| Position mean | 1.4719 | 2.3405 | 1.5322 | 2.3725 |
| Recent points (3 GWs) | 1.0888 | 2.2029 | 1.0729 | 2.2077 |
| Player season scoring rate | 1.1035 | 2.0747 | 1.1044 | 2.0880 |
| External FPL ep_next | 1.1071 | 2.1213 | 1.0692 | 2.1234 |

All baselines have 100% validation/test coverage. Archived ep_next has three null
training rows in 2023/24; these are excluded only from its metrics, not imputed.
Mean within-GW Spearman for recent points is 0.6750 validation / 0.7071 test;
FPL benchmark is 0.6470 / 0.6892. Constant overall-mean ranks are undefined, not
reported as zero. Complete position/season breakdowns and ranking counts are in JSON.
These are descriptive scores, not significance tests or product utility evidence.
The holdout has now been reported: future feature choices must use validation,
not repeatedly tune against these test scores.

## Reproduce

Commands executed successfully from the repository root:

```bash
.venv/bin/python -m fpl_ai features
.venv/bin/python -m fpl_ai features --help
.venv/bin/python -m unittest discover -v
.venv/bin/python -m compileall -q fpl_ai scripts tests main.py
.venv/bin/python -m pip check
PYTHONPATH=. .venv/bin/python scripts/verify_modelling.py --report docs/M3_VERIFICATION.json
PYTHONPATH=. PYTHONOPTIMIZE=1 .venv/bin/python scripts/verify_modelling.py --report /tmp/m3-hardening-optimized.json
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/m3-hardening-historical.json
git diff --check
```

For exact pinned reproduction, use the `--builds-from` command recorded below.
The verification script runs offline using the actual published data and explicitly checks
fresh rebuild equivalence, reuse and preservation, rather than merely suggesting
those checks. No lint/type checker is configured. No dependency was added.

## Remaining limits

No deadline fixture lists, opponent strength or double/blank schedule predictors;
no minutes/goals/expected-statistic features until their historical availability is
verified; no cross-season person links; no sophisticated ML. Snapshot freshness
and the GW18 exception remain visible. Ep_next methodology is opaque and may change.
The broad registered-player population is dominated by non-players and zero returns;
strong ranking/low error here does not prove value for squad selection or captaincy.
No season scoring reconstruction, uncertainty intervals or expanding-season tuning
framework is claimed. Next work is Milestone 4's transparent predictive experiments
under these frozen temporal and evaluation boundaries.

Original-batch exact-build reuse command (its existing manifest can also pin inputs for the hardened implementation):

```bash
.venv/bin/python -m fpl_ai features --builds-from data/modelling/43019484073d51d4e9fd0b28c0e34c4d2d5a8168ca4f2a8f3308599a65f6ae3f/manifest.json
```

Original modelling identity:
`43019484073d51d4e9fd0b28c0e34c4d2d5a8168ca4f2a8f3308599a65f6ae3f`.

## Focused hardening verification (2026-09-17)

All four review findings are resolved without changing predictors, target definition,
splits or baselines:

1. Every non-null target must match an integer event_points for that element in
   its target GW's accepted settlement. Empty sums need explicit zero evidence;
   missing players, missing settlement, non-integers and disagreements fail.
2. `serialized-products-v2` identifies the actual six serialized data products,
   contracts and source/build provenance. This includes all derived rows, predictions,
   metrics and schema regardless of helper implementation. evaluation.json enters
   identity before its identity reference is inserted, avoiding a hash cycle; final
   evaluation bytes also have their own checksum. The incomplete implementation-file
   hash list is removed. Identical behaviour/inputs retain portable identity.
3. Publication and reuse share the exact six-data-artifact-plus-manifest set. Missing
   or unexpected files, directories/symlinks, missing/extra checksum entries,
   regenerated-manifest differences and checksum mismatches are rejected.
4. All verification assertions became explicit VerificationError checks, including
   calls that would previously be skipped under optimization. An intentionally
   failing fresh-build condition fails in both normal and optimized subprocesses.

The normal and optimized real-data verification runs check the same 137,662 rows,
137,038 labels and **4,553/4,553 explicit settled empty-player zeros**. Both perform
fresh temporary rebuilds and checksum/mtime-preserving reuse. All 124 historical
processed files and catalogue bytes remain unchanged. The full five-season M2
historical verification, 132-test suite, compilation, dependency and whitespace
checks pass. No dependency, commit, push or merge was introduced.

Hardened identity:
`57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a`.
The identity changes intentionally because its boundary changed. The four CSVs
and schema.json retain their exact original bytes; all summary counts and all
train/validation/test metrics are exactly equal to the saved pre-hardening evidence.
Only identity/provenance-bearing manifest/evaluation bytes change. Existing M3
artifacts are preserved, not migrated or overwritten.

[M3_HARDENING_VERIFICATION.json](M3_HARDENING_VERIFICATION.json) records the
before/after identities, content/preservation comparison and optimized-report equality.
The complete current counts, metrics and source traces remain in M3_VERIFICATION.json.

Trade-off: reuse now recomputes features, evaluation and temporary serialization
before checking the existing build. It avoids published writes, not computation.
Code-only edits with no output/contract change intentionally preserve identity.
The existing fixture-availability, snapshot-freshness and modelling limitations
above are unchanged; this hardening adds no model or recommendation functionality.

