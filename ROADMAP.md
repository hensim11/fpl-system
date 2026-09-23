# Roadmap

The platform will grow in small, testable milestones. Dates are intentionally omitted until priorities and operating constraints are agreed.

## Milestone 1 — Project foundation and current FPL ingestion

Status: implemented; verification details are recorded in `PROJECT_STATE.md`.

- Establish a small Python package and command-line entry point.
- Retrieve current public player, team, and fixture data.
- Validate minimum schemas and entity relationships.
- Store immutable raw JSON separately from processed CSV tables.
- Add deterministic tests and working-state documentation.

## Milestone 2 — Reproducible historical data foundation

Status: **complete**. All five seasons, 2021/22–2025/26, are published and verified, including the full-range identity, availability, temporal-integrity and offline reproducibility audit. Evidence: `docs/M2_2025_26_VERIFICATION.md`.

- [x] Set the eventual target range to 2021/22–2025/26 and pin the permitted historical sources.
- [x] Add a machine-readable 2024/25 source catalogue and season audit expectations.
- [x] Define explicit nullable schemas, information classes, and a data-quality report.
- [x] Add immutable raw provenance, idempotent version handling, atomic manifests/catalogue, and a stable latest-successful lookup.
- [x] Ingest 2024/25 player-fixture outcomes and strict pre-deadline snapshots without modelling.
- [x] Harden 2024/25 with deadline-time team/position identity, an explicit fixture availability allowlist, cross-source points reconciliation, complete source-pin identity, and unambiguous CLI arguments.
- [x] Close the 2024/25 architecture slice with enforced reconciliation coverage, validated season-specific Vaastav schemas, separate source/build identities, frozen per-build source inventories, and build-safe processed versioning.
- [x] Make 2024/25 schema mappings/types executable and scope frozen provenance to materially consumed records, with byte-identical canonical outputs.
- [x] Verify 2023/24 through its own observed schema/catalogue entry, 38/38 deadline coverage, complete points reconciliation, deterministic rebuilds, and byte-identical 2024/25 regression checks.
- [x] Verify 2022/23 end-to-end, preserving fixture-empty GW7 and observed person-code changes; require complete points reconciliation and cross-season schema/rebuild checks.
- [x] Investigate 2021/22 schema differences, implement strict label/kickoff compatibility, and reproduce source blockers without publishing invalid data.
- [x] Implement independently selected, pinned settled-event comparisons for 2021/22: 23,230/23,230 exact matches, including GW3/GW17; preserve accepted-season identities.
- [x] Make the default audit verify published seasons and route unpublished attempts through explicit investigation mode.
- [x] Complete 2021/22 publication with 43/43 passing checks, 38/38 snapshots and complete settlement reconciliation, using one authorized, pinned GW18 superseded-deadline exception (state as of 12:33; 3h27 freshness limitation).
- [x] Add and verify 2025/26 through the proven pipeline, with exact duplicate-source evidence and complete settled points coverage.
- [x] Re-run cross-season identity and availability audits over all five seasons; preserve all earlier outputs and identities.

Exit criterion: **satisfied** — a documented, reproducible dataset suitable for exploratory analysis across all five agreed seasons.

## Milestone 3 — Feature and evaluation design

Status: **complete** against the current exit criterion. Five-season deterministic features and non-ML evaluation verified; see `docs/M3_VERIFICATION.md`. No trained model or recommendation claim.

- [x] Define prediction targets and guard against future-data leakage.
- [x] Create time-aware train/validation/test splits.
- [x] Build deterministic feature tables from versioned inputs.
- [x] Establish simple non-ML baselines and evaluation metrics.

Exit criterion: **satisfied** — an evaluation harness that can compare approaches honestly. 132 tests pass; five-season fresh rebuild/reuse, temporal protections and source traces are verified. No product recommendation claims yet.

## Milestone 4 — First predictive experiments

Status: **first substantial batch complete; current exit criterion satisfied**.
See `docs/M4_VERIFICATION.md` for the separate validation and frozen holdout evidence.

- [x] Train transparent Ridge and bounded nonlinear models for the frozen M3 target.
- [x] Track exact upstream identity, preprocessing, models, predictions and evaluation.
- [x] Select with validation RMSE, publish the fitted winner, then evaluate holdout.
- [x] Compare all five non-ML baselines, positions, history segments and uncertainty.
- [x] Verify fit boundaries, source anomalies, exact replay and upstream preservation.

Exit criterion: **satisfied for the agreed prediction problem** — held-out RMSE
1.9164 versus 2.0880 scoring rate and 2.1234 external ep_next, with MAE/ranking gains,
full coverage and lower squared error in all 38 test GWs. This does not establish
squad/transfer/captain utility or universal superiority. 145 tests pass.

### M4B — Playing-time foundation and prospective evaluation

Status: **implemented and verified**; see `docs/M4B_VERIFICATION.md`.

- [x] Audit raw playing-time/availability fields and reject unsupported fixture history.
- [x] Version compact features with settlement evidence, nulls and freshness retained.
- [x] Forecast total GW minutes using earlier-season train/development boundaries.
- [x] Freeze one bounded minutes model and report three baselines and useful segments.
- [x] Add clock-checked prospective capture/freeze and separate settled scoring CLI.
- [x] Reproduce new artifacts and preserve all accepted M2/M3/M4 products.
- [x] Require positive schedule evidence for blanks: reject empty/unusable current
  schedules and reconcile historical player facts against independent `fixtures.csv`.
  This validates labels only and adds no historical fixture predictor.
- [x] Smoke-test real 2026/27 capture/freeze/verify: GW5, 659 forecasts before its
  September 18 17:30 UTC deadline.
- [ ] Capture legitimate settled GW5 outcomes and score separately once available.
- [x] Produce expanding chronological OOS minutes artifacts before xPts v2 stacking.
- [x] Investigate the 2024/25 cumulative-minute discrepancy without guessed corrections.
  Later aggregate change evidenced; cause unresolved; exact player/GW quarantine.

176 tests pass. No new untouched historical holdout is claimed. Historical fixture
context remains unavailable; current fixture snapshots have their own prospective
contract. The minutes-only freeze retains null expected points; M4E adds a separate
control/v2 forecast. Preserve M4's frozen results and do not retune against reported 2025/26.

### M4C — Chronological OOS and real prospective validation

Status: **implemented and verified**; see `docs/M4C_VERIFICATION.md`.

- [x] Annual expanding refits with frozen prior selection and strict information cutoffs.
- [x] 56,804 downstream-safe minutes forecasts, GW1–38 in 2024/25 and 2025/26;
  80,858 earlier rows explicitly unavailable, separate outcomes and diagnostics.
- [x] Immutable artifacts, guarded downstream reader, exact rebuild/reuse and preservation.
- [x] Independent five-season minutes/history/schedule checks and anomaly investigation.
- [x] Real GW5 snapshot and pre-deadline forecast; premature settlement rejected.
- [x] Full regression suite: 186 tests normally and under optimized Python; M2/M3/M4/M4B replay.

Live outcomes remain pending, so the combined M4B forecast-and-outcomes objective
is only partly satisfied. The historical xPts v2 integration is now implemented in
M4D below, with an explicit fixed downstream fitting/evaluation protocol.
The consumed 2025/26 holdout cannot be presented as untouched. Continue manual
prospective retention and score GW5 only after authoritative settlement.

### M4D — Bounded OOS expected-minutes xPts integration

Status: **implemented and verified; recommend acceptance**. 198 tests pass normally
and under optimized Python. Independent fresh/reuse/mutation checks and all prior
milestone replays pass; all 783 pre-batch data files retain bytes and mtimes.

- [x] Exact M3/M4C artifact binding and one-to-one decision-state/provenance join.
- [x] 27,159 2024/25 rows fit both models; 29,645 common 2025/26 rows evaluated.
- [x] Fixed M4 hist_15; original 25 inputs versus those inputs plus OOS total GW minutes.
- [x] Separate feature/prediction/outcome products; no early-season fabrication or fallback.
- [x] Independent points eligibility preserves Ferguson GW27's valid forecast.
- [x] Fixed RMSE/MAE/Spearman and top-10 diagnostics, paired deltas and frozen M4 references.

Matched RMSE improves **1.925490 → 1.916745**, MAE and Spearman also improve,
but top-10 realised points worsens **5.050000 → 4.815789**. Frozen M4 remains
slightly better on RMSE (1.916449) with a different fitting population. This is a
valid historical integration answer, not prospective confirmation or decision utility.
No tuning followed the result. See [verification](docs/M4D_VERIFICATION.md).

### M4E — Current-season prospective xPts

Status: implemented with a real pre-deadline GW6 control/v2 forecast; verification
and operational commands are in [M4E verification](docs/M4E_VERIFICATION.md).

- [x] Fixed 56,804-row prior-season refit, exact fitting keys/cutoffs and saved states.
- [x] Live 25-input adapter with raw historical parity and settled points history.
- [x] Strict verified expected-minutes join; identical control/v2 population.
- [x] Actual-clock forecast publication and separate immutable scoring lifecycle.
- [x] Real 659-player GW6 forecast; preserve the original GW5 minutes lifecycle.
- [ ] Retain near-deadline states and authoritatively settled prospective outcomes.
- [ ] Accumulate prospective evidence before any model-superiority or decision claim.

No new historical holdout or winner selection. Initial history is missing; the
first GW6 capture is early. M5A now consumes these forecasts for one-GW decisions.

## M5A — Rules-aware current-squad transfer optimiser v1

Status: **accepted/complete after verified structural/semantic tie separation**; evidence in [M5A verification](docs/M5A_VERIFICATION.md).

- [x] Versioned rules and strict current-squad input with exact selling prices.
- [x] Explicit control/v2 consumption through the frozen M4E verification boundary.
- [x] Joint squad/XI/captain MILP with budget, club, position and transfer-hit rules.
- [x] Unique deterministic top-N plans and explicit legal no-transfer baseline.
- [x] Separate immutable decision artifacts and practical `optimise` CLI.
- [x] Hand-checkable optima, real GW6 demo, fresh/reuse and preservation checks.
- [x] Bound boolean selectability: 659 forecast rows, 554 transfer-in eligible;
  preserve owned unselectable players, reject malformed evidence.
- [x] Inclusive 1e-6 tie band with exact boundary checks and deterministic priorities.
- [x] 238 normal/optimized tests (28 focused in both modes); unchanged original demo
  plans and all 904 prior data files.
- [x] Reproduce reviewer seeds 1596/top-1 and 26/top-10; remove only the objective
  row's generic numerical gate while retaining strict structural checks.
- [x] Exact <=1e-6 tie authority and fail-closed optimality, including presolve retry.
- [x] 400 positive-xPts seeds × four depths: 1,600 independent exhaustive ranking
  comparisons; 121 out-of-band rejections, byte-identical normal/optimized evidence.

M5A retains its one-Gameweek objective. M5B below now supplies separate multi-GW
planning with rolling transfers and squad evolution. Future fixture predictors
remain unavailable; M5C adds separate uncertainty below. M4E retention/scoring continues
independently, without choosing a model prematurely or claiming realised utility.

## M5B — Multi-Gameweek projections and transfer-path optimiser v1

Status: **verified/complete; recommend acceptance**. Evidence in [M5B verification](docs/M5B_VERIFICATION.md): 261 normal/optimized tests, 82 feasible ranked paths across 22 oracle cases (15 return five; seven return only one because no transfer is affordable; top-N is a maximum), exact fresh/reuse identities and all 920 prior data files preserved.

- [x] Separate versioned direct GW+0..4 target/model family from one frozen state.
- [x] Chronological fixed-model historical evaluation, per-horizon/position metrics,
  distributions and cumulative three/five-GW diagnostics; consumed holdout disclosed.
- [x] Production prior-season refits and actual-clock current projection publication.
- [x] Multi-period squad, bank, initial selling rights, FT rolling/cap and hits.
- [x] Legal XI/captain every GW; explicit static-price/selectability contracts.
- [x] Deterministic complete-path ranking, no-transfer and sequential greedy baselines.
- [x] Independent exhaustive paths/XIs, numerical tie checks and fail-closed solving.
- [x] Offline CLI and immutable evidence; preserve M4E, M5A and earlier artifacts.

No realised decision-utility claim. See Decisions 050–052 for contracts and
verification for the real early-state demo, runtime limits and completed checks.

## M5C — Prospective multi-GW scoring and uncertainty calibration

Status: **implemented and verified; recommend acceptance**. See
[M5C verification](docs/M5C_VERIFICATION.md): 279 normal/optimized tests, independent
residual/order-statistic/settlement/metric reconstruction, unchanged M5B audit/oracle,
and all 951 prior data files preserved.

- [x] Fixed horizon-only empirical 50/80/90% residual intervals over consumed prior evidence.
- [x] Direct complete-window three/five-GW calibration with explicit exclusions.
- [x] Exact original projection binding, actual-clock uncertainty publication and replay.
- [x] Independent target-GW settlement reusing existing authoritative FPL contracts.
- [x] Immutable accumulated point-error/coverage/width evidence with duplicate guards.
- [x] Partial, blank, double, missing, corruption and complete-window lifecycle tests.
- [x] Real retained GW6–10 uncertainty artifact and premature-settlement rejection.
- [x] Profile unchanged full-population exact planner; reproduce accepted decision bytes.
- [ ] Observe real GW6–10 settlement and accumulate prospective coverage evidence.

No prospective calibration-quality claim yet. The operational calibration remains
frozen; no automatic model/quantile/segmentation selection follows new outcomes.
The final unchecked item awaits authoritative future results, not implementation.

## Next substantial objective

Continue prospective retention and settlement under the fixed contracts. A later
Monte Carlo/risk-aware planning batch can use the keyed residual evidence, but must
specify joint player/GW dependencies and evaluate uncertainty and decision utility.
Intervals alone do not define a joint distribution or justify a risk-adjusted
optimiser objective. M5B continues to optimise expected points exactly as accepted.

## Later milestones

Only after the data and evaluation foundations are reliable:

- prospective calibration assessment and risk-aware multi-Gameweek planning;
- user-specific decision support;
- scheduled ingestion and monitoring;
- service or UI layers;
- deployment and operational controls.

These are directions, not commitments. Frameworks, databases, hosted services, and prediction models should be introduced only when a concrete requirement justifies them.
