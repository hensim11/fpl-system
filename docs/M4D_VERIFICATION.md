# M4D — OOS expected minutes → xPts v2

**Implemented and verified; recommend accepting M4D as complete.**
Historical integration experiment, 2026-09-18. The predefined stacked candidate
improves RMSE, MAE and mean within-GW Spearman against its matched control, but
**worsens forecast top-10 realised points**. It slightly loses on RMSE to the frozen
M4 model, whose larger fitting population makes that comparison descriptive.
Neither result establishes transfer, captaincy, squad-selection or prospective utility.
2025/26 was already consumed by M4; there is **no new untouched holdout**.

## Exact identities and interface

| Product | SHA-256 identity |
| --- | --- |
| Frozen M3 | `57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a` |
| Accepted chronological M4C minutes | `3550ded6a2aff16fa9f799b9c993b8799726d0243a3b1e643e6249af475867be` |
| Frozen M4 reference holdout | `21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd` |
| M4D prediction/model bundle | `1440b30cce2a51d233ca71bfffb1f3c960ed0c7dc18d00694971839483e925a0` |
| M4D outcome/score bundle | `73e1ebd13d0bafd1305339e2a4a1ae397c98027cc793713622f8b7f27015e05b` |

Exact source/build identities, source manifests, model states and checksums are bound
in `upstream.json`, the experiment manifest and [machine evidence](M4D_VERIFICATION.json).
The accepted M4C family is loaded through `minutes_oos.load_downstream`; arbitrary
CSV, M4B development, prospective or score products are not accepted.

The one-to-one key is `(season, target_gameweek, element)`. Each matched row must
also agree on capture, deadline, snapshot path/hash, age, observed player code,
freshness exception and payload deadline. Historical source/build identities and
shared consumed table hashes must agree. M4C independently verifies the minutes
model's selection/fitting evidence strictly precedes the forecast's capture, which
strictly precedes its deadline. Historical timestamps denote reconstructed
information cutoffs, not fabricated historical execution timestamps.

| Season | OOS forecasts / joined rows | Independent points labels | Fit / scored rows |
| --- | ---: | ---: | ---: |
| 2024/25 | 27,159 | 27,159 | 27,159 fitted |
| 2025/26 | 29,645 | 29,645 | 29,645 evaluated |
| Total | 56,804 | 56,804 | 56,804 |

Both seasons cover GW1–38. No forecast or point label is missing on this exact
population. The 80,858 earlier rows remain unavailable under M4C's prior-selection
history, with explicit reason `insufficient_prior_selection_history`; their keyed
audit remains in the bound M4C artifact. No earlier forecast is fabricated.
The join implementation retains missing OOS forecasts as null features and audited
exclusions; no actual, baseline, in-sample or zero fallback is allowed. Missing point
labels are independently audited and excluded from fitting/scoring, never zeroed.

Ferguson 2024/25 GW27 (element 123) has a valid pre-deadline forecast and an independently
verified **1-point** label, so it is included. Its OOS expectation is
**22.36760267048595 minutes**, as of **2025-02-25 12:45 UTC**. The later unresolved minutes target is
never required by this adapter. Decisions 042–043 and all M4C masking remain unchanged.

## Predeclared model and temporal protocol

Fit only 2024/25 points labels, identically for control and v2. Latest fitted label:
**2025-05-26 02:06 UTC**. First evaluation capture: **2025-08-15 12:52 UTC**.
The fit entry point rejects any other season and requires every fitted capture and
settlement before the evaluation boundary. The production workflow loads evaluation
points labels only after fitting both pipelines.

Reuse M4 `hist_15`: squared error; learning rate .05; 150 iterations; 15 leaves;
minimum leaf size 50; L2 10; random seed 1729; one thread; no early stopping.
No search, refit on evaluation labels, clipping or post-result tuning. xPts v2 is
the predefined candidate; the control is never promoted through a winner selection.

Exact control input order (25 fields):

```text
price, selected_by_percent, transfers_in_event, transfers_out_event,
chance_of_playing_next_round, previous_points, points_mean_3, points_mean_5,
points_count_3, points_count_5, season_points_mean, season_points_count,
deadline_position_id_missing, price_missing, selected_by_percent_missing,
transfers_in_event_missing, transfers_out_event_missing, status_missing,
chance_of_playing_next_round_missing, previous_points_missing,
points_mean_3_missing, points_mean_5_missing, season_points_mean_missing,
deadline_position_id, status
```

V2 appends only `oos_expected_minutes` (expected **total GW** minutes, no 90-minute
cap). Original numeric median imputation and StandardScaler, missingness passthrough,
and one-hot position/status semantics are reused. The extra numeric column has its
own train-only median/scaler branch; missing forecasts are rejected before it.
The control projection and serialized pipeline are tested against the original M4
implementation. Season-local team ID and its flag remain excluded. No fixture
context, Vaastav xP, ep_next, realised minutes or target points enter predictors.

Feature rows contain keys plus only the 26 allowed predictors. Outcomes reside in
a separate immutable score family. Forecasts, row audits, fitting evidence hashes,
serialized pipelines, protocol and upstream identities form the prediction bundle.
The closed artifact sets use existing atomic publication and checksum-verified reuse.
A verification-discovered serialization defect was fixed: NumPy dtype/Python alias
sharing after prior unpickling changed ordinary pickle bytes without changing model
values. The new family uses protocol-5 pickle with memoization disabled for these
acyclic local estimator states, rejecting cycles. This preserves every prediction
and makes artifact identity independent of that incidental reference sharing. The
extra model file size is small; old families retain their original serialization.

## Common-row historical results

All metrics below use the same 29,645 independently labelled evaluation rows.
Lower RMSE/MAE is better; higher Spearman/top-10 is better.

| Predictor | RMSE | MAE | Mean GW Spearman | Top-10 realised points |
| --- | ---: | ---: | ---: | ---: |
| Matched control | 1.925490 | 0.952499 | 0.738961 | 5.050000 |
| **xPts v2** | **1.916745** | **0.932555** | **0.744086** | **4.815789** |
| Frozen M4 hist_15 | 1.916449 | 0.953678 | 0.741470 | 4.721053 |
| M3 recent points | 2.207674 | 1.072937 | 0.707077 | 3.765789 |
| M3 player scoring rate | 2.088004 | 1.104412 | 0.632589 | 4.118421 |
| Archived FPL ep_next | 2.123411 | 1.069175 | 0.689183 | 4.507895 |
| M3 historical mean | 2.374896 | 1.536840 | undefined | 2.097368 |
| M3 position mean | 2.372535 | 1.532172 | 0.080473 | 1.815789 |

V2 minus control: **RMSE −0.008745**, **MAE −0.019944**, **Spearman +0.005125**,
**top-10 −0.234211 points**. RMSE improvement is about 0.45%.
V2 minus frozen M4: RMSE **+0.000296**. M4 trained on 2021/22–2023/24 and was
selected on 2024/25; its comparison is product context, not a clean feature ablation.

Top-10 was fixed before reading results: descending forecast, ascending element ID
tie break; take min(10,n) per GW; average their realised points, then equally average
across GWs. Every selected element and each GW's value is retained. It is descriptive
player ordering without budget, squad, position, transfer or captain constraints.

Machine evidence includes per-GW counts/metrics, positions 1–4, established history
(season points count ≥3), low history, any original missingness and missing chance.
Segments overlap. Original M3 baseline definitions and missingness are unchanged;
ep_next is only a separate reference. Paired comparison products record common-row
counts and key hashes, including any missing-reference exclusion.

## Reproduce and verify

```bash
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m fpl_ai.xpts_v2
```

The defaults bind the three exact upstream identities above. `--data-dir` and
`--output-dir` relocate storage without changing deterministic identity. See the
machine evidence for output identities. Reproduction and adversarial verification:

```bash
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=. .venv/bin/python scripts/verify_xpts_v2.py \
  --prediction-dir data/xpts_v2/1440b30cce2a51d233ca71bfffb1f3c960ed0c7dc18d00694971839483e925a0 \
  --score-dir data/xpts_v2/scores/73e1ebd13d0bafd1305339e2a4a1ae397c98027cc793713622f8b7f27015e05b \
  --report /tmp/m4d-verification.json
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m unittest discover -s tests -q
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -O -m unittest discover -s tests -q
```

Verification reconstructs the join independently by key, rebuilds M3 points from
pinned settled historical evidence, independently computes metrics/ranking, replays
saved models and checks fitting provenance. Adversarial checks cover duplicate or
mismatched captures, boundaries, forbidden feature fields, missing forecasts/points,
wrong artifact families, incompatible rehashed contracts and corrupt/missing/extra
files. All verification uses explicit exceptions, never removable `assert` statements.

## Verification result and preservation

**198 tests pass normally and with `python -O`**, including 12 new focused tests.
The complete independent M4D verification script also passes normally and under
optimized Python; both produce identical machine evidence. It verifies all 56,804
point-evidence rows and exact join states, all 29,645 common evaluation predictions,
independent RMSE/MAE/Spearman/top-10 calculations, saved-model replay, and a fresh
build after loading existing model states. Fresh build manifests match exactly.
Same-root rebuilds reuse both identities without byte or mtime changes.

Changing every available 2025/26 target by +1,000 leaves the entire prediction bundle
(features, fitted preprocessing/models, training provenance and predictions)
byte-identical; only the separate outcome/score bundle changes. Family rejection
probes include M4B minutes, ordinary playing-time features, prospective captures and
forecasts, minutes scores and xPts scores. A correctly rehashed incompatible M4C
contract is rejected. Corrupt/missing/extra files are rejected in both M4D and OOS
inputs. No weakening of the M4C reader was needed.

Full five-season M2 offline rebuild/reuse passes. M3, frozen M4, M4B and M4C replay
reports are **identical to their prior checked-in verification reports**. All
**783 pre-batch data files retain their SHA-256 and nanosecond mtime**, including
historical raw/processed data, catalogue, all earlier experiment families and the
prospective GW5 artifacts. Inventory and exact commands are recorded in
[M4D regression evidence](M4D_REGRESSION.json). Compilation, CLI help, dependency
consistency and `git diff --check` pass. No new dependencies or network data.

Created `fpl_ai/xpts_v2.py`, `scripts/verify_xpts_v2.py`, `tests/test_xpts_v2.py`,
this record and its verification/regression JSON companions. Updated only the
shared artifact-family registry, ignored output root, README, PROJECT_STATE,
ROADMAP and Decision 044. No existing modelling or minutes implementation was
rewritten. The serialization fix affects only this new artifact family and leaves
the predeclared model inputs/configuration and measured results unchanged.

## Limitations and handoff

This establishes a defensible first minutes-to-points interface and a small historical
incremental accuracy benefit, with a worse top-10 diagnostic. It does not establish
statistical significance, prospective confirmation or useful FPL decisions. Only one
fit season and one already-consumed evaluation season are available; expanding
minutes models also change their training history between those seasons.

No external datasets, dependencies, fixture-context reconstruction, multi-GW forecasts,
optimiser, simulation, service, scheduler or UI were added. Current-season xPts
adaptation remains future work. The separate 2026/27 GW5 forecast was not settled or
used here; its legal settlement remains an independent operational task. No arithmetic
resolution of Ferguson, guessed correction, commit, merge or push was performed.
