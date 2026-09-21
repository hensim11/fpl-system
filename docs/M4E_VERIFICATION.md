# M4E — Prospective xPts and current-season adaptation

M4E implements the fixed operational control/v2 pipeline and has produced a real
2026/27 GW6 forecast for **659 players**. Both predictions remain available; neither
model is selected as a winner. Verification evidence is in
[M4E_VERIFICATION.json](M4E_VERIFICATION.json), [M4E_LIVE.json](M4E_LIVE.json) and
[M4E_REGRESSION.json](M4E_REGRESSION.json).

## Frozen fitting protocol

`m4e-prospective-xpts-v1` reuses M4D's `hist_15` configuration, original ordered
25 inputs, preprocessing and deterministic serialization. V2 appends only
`oos_expected_minutes`. No model, feature, clipping or hyperparameter search ran.
The models use the **same 56,804 keys**: 27,159 rows from 2024/25 and 29,645 from
2025/26, each independently labelled with points and joined through the verified
M4C downstream boundary. No realised-minutes label is required. Earlier 80,858
rows remain unavailable. Ferguson GW27 remains eligible for points, and the
existing minutes quarantine and 2021/22 GW18 exception are unchanged.

The latest fitting label is **2026-05-25 10:23 UTC**. All fitting captures and
labels must precede the first supported current-season state,
**2026-07-01 00:00 UTC**. Only the two exact prior-season populations are accepted;
2026/27 targets cannot enter fitting or preprocessing. This is an operational
refit using previously consumed evidence, not another holdout evaluation.

| Product | Identity |
| --- | --- |
| Operational model bundle | `11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230` |
| Control fitted identity | `1c69628141cc77f55c991f259ac565bf29af674bf2fda63578ca89c82835dcf4` |
| V2 fitted identity | `07c1bca1e7e525278720d8bcb3ca5013106bcc57f50623032a350312e68bb1ea` |
| Control serialized SHA-256 | `86640a2df73d2ef34e59db26d0e432695c6e130b1d92fb152e7975b97d6414a5` |
| V2 serialized SHA-256 | `320eaf19f4ec155b3f1ea7cb93117663b3f086c642a9eca68715296494d01412` |

`fit.json`, `training.csv`, `sources.json`, the protocol, serialized pipelines and
manifest retain exact fitting keys, feature/label hashes, source and minutes-OOS
identities, label cutoff, preprocessing hashes/state and dependency identity.
Environment: Python 3.14.0, scikit-learn 1.7.2, NumPy 2.3.3, SciPy 1.16.2,
joblib 1.5.2, threadpoolctl 3.6.0; Darwin arm64. No dependencies changed.

## Live features and evidence boundaries

The adapter copies `now_cost` in tenths, ownership, event transfers, status,
chance and position from the accepted bootstrap, using M3's original parsers and
types. Team ID is excluded. No fixtures, final identities, Vaastav xP, ep_next,
current aggregate points, realised minutes or target outcomes enter the matrix.
The original ordered 25 inputs and missingness flags remain exact; V2 adds the
26th input. Unknown categories and imputation use the saved M4 preprocessing.

History reuses existing verified minutes-forecast/settlement pairs. Each pair
must be same-season and strictly earlier, with settlement received no later than
the target bootstrap request. The existing reader requires `finished` and
`data_checked`, fixture-v2 schedule/completion validation, and integer live points
reconciled with fixture explanations. Its forecast population must be covered.
An element absent from retained earlier evidence remains missing. Explicit zero
is an observation. The previous-GW, three/five calendar-GW means/counts and
available-season mean/count match M3. A positive-schedule blank stays null.
Unsettled, future, duplicate and cross-season histories fail closed.

Each history observation retains its season/GW/element, integer points, capture
time, source identities, source hashes and manifest hash. Forecast bundles retain
exact-byte copies of snapshot, minutes and prior evidence in `evidence.json`;
`history.json` holds the derived provenance. Readers reconstruct these copies into
temporary bundles and invoke the established readers. Target outcomes are absent
from forecast feature/prediction files. Prior settled outcomes are intentionally
retained as feature evidence, separately from later target outcomes.

The minutes join calls `prospective.verify_prediction`, then requires the exact
season, GW, deadline, capture identity, bootstrap/fixture hashes, manifest hash,
timing, feature contract and player key set. It pins the accepted M4B model
identity, manifest hash and artifact hashes. Another snapshot, GW, element set or
model fails. The v1 minutes boundary requires complete finite nonnegative
predictions: missing minutes invalidate the input bundle; there is no xPts
fallback or silent population reduction. Control and v2 therefore share every row.

The operational minutes model remains the existing frozen M4B model. Historical
OOS minutes came from annual expanding fits. This distribution difference is
explicit; M4E does not silently replace the live minutes family or retune it.

## Publication and separate scoring

`prospective xpts fit|freeze|verify|score` extends the existing CLI and shared
atomic/content-addressed artifact publisher. Capture and settlement remain the
existing commands. Freeze checks the real clock at start, computation completion,
publication and after final verification of the actual published destination.
Semantics are also replayed in private staging before publication. A deadline or
clock failure removes a newly published output. Existing reused artifacts are
never deleted or redated. No CLI clock override exists.

The forecast records start/computation/publication-start timestamps and snapshot
freshness. The final post-publication clock gate executes after checksum and
semantic replay; the live verification report independently records completion.
Locally recorded clocks and hashes are not external timestamp attestation.
Different actual publication times deliberately produce different forecast
identities. Use `verify` to reuse an existing forecast without rewriting it.

Scoring reads a later settlement for the exact bound minutes forecast and writes
a separate `prospective-xpts-score` bundle. Missing player outcomes fail; legitimate
blanks remain unlabelled. Both models use identical independently labelled rows.
Reports include RMSE, MAE, valid within-GW Spearman, coverage, prediction quantiles,
positions, history/missingness segments, common-key hashes and paired deltas.
Top-10 uses M4D's descending forecast/ascending element tie rule and mean realised
points for the selected players. No evaluation result changes either model.
Each score is one GW observation; pooling across retained GWs is a later analysis.

## Actual live result

GW5's September 18 17:30 UTC deadline had passed before implementation. Its
existing minutes snapshot/forecast was neither rewritten nor represented as xPts.
The official API inspected at **21:04:06 UTC** showed GW5 current, unfinished and
unchecked; no settlement or score was attempted or claimed for it in M4E.

The same response showed GW6 as the unique next event, deadline
**2026-10-10 10:00 UTC**. Real CLI capture, minutes freeze, xPts freeze and verification
succeeded using actual runtime timestamps:

- Snapshot: `debbe980cdb6b8f5cc136949007f0dd0536a057c77c3acedb6cff622194cfa6c`.
- Minutes: `ac3268702d82cb723dd62220efb4ff7792c20f89e1556eacfb54f698c905e395`.
- xPts: `1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527`.
- Computation complete: **2026-09-18 21:07:49.825026 UTC**.
- Independent final verification complete: **2026-09-18 21:08:23.634880 UTC**.
- **659 common predictions**, no outcomes or score. Control mean 1.083531 points;
  v2 mean 0.900338. These are forecast distributions, not accuracy results.

This is an early GW6 state, approximately 21.5 days before its deadline, with no
near-deadline freshness claim. No qualifying prior points settlement pairs were
retained. All points history and recent minutes are missing. The existing GW5
snapshot supplies only permitted availability changes for minutes. Earlier GWs
are not reconstructed from current cumulative points. Retain a new capture nearer
the deadline and include GW5 history only after authoritative settlement.

## Operator commands

```bash
export LOKY_MAX_CPU_COUNT=1
MODEL=data/prospective_xpts/models/11aa9eb62174997637edf2e2a7090aa6a197f068526ed981434e869556db9230
MINUTES_MODEL=data/minutes/e8b168652ce16cf238f84186977b329c55a3d754605066b7e50422b7a0bb3ddc
GW5_SNAPSHOT=data/prospective_snapshots/ffcdc756331c67fa780f2bec92237f28486032416b80a6f843ed6d9161fef0ce
GW5_MINUTES=data/prospective_predictions/19622ab3d853222513b977fac4ae6c11d6f8e160ad9dd48f66a064892b078e24
# Fixed refit or checksum-verified deterministic reuse:
.venv/bin/python -m fpl_ai prospective xpts fit

# Run only while GW6 is the unique next event and before its real deadline.
# Each command prints its immutable directory; assign the actual returned paths.
.venv/bin/python -m fpl_ai prospective capture --season 2026-27 --gameweek 6
SNAPSHOT=RETURNED_SNAPSHOT_DIR
.venv/bin/python -m fpl_ai prospective freeze --snapshot-dir "$SNAPSHOT" \
  --model-dir "$MINUTES_MODEL" --previous-dir "$GW5_SNAPSHOT"
MINUTES=RETURNED_MINUTES_DIR
.venv/bin/python -m fpl_ai prospective xpts freeze --snapshot-dir "$SNAPSHOT" \
  --minutes-dir "$MINUTES" --model-dir "$MODEL"
FORECAST=RETURNED_XPTS_DIR
.venv/bin/python -m fpl_ai prospective xpts verify --forecast-dir "$FORECAST" --model-dir "$MODEL"

# Only after authoritative settlement; use the exact bound minutes directory:
.venv/bin/python -m fpl_ai prospective settle --prediction-dir "$MINUTES"
SETTLEMENT=RETURNED_SETTLEMENT_DIR
.venv/bin/python -m fpl_ai prospective xpts score --forecast-dir "$FORECAST" \
  --model-dir "$MODEL" --settlement-dir "$SETTLEMENT"
```

For GW5's separate existing lifecycle, run `prospective settle --prediction-dir
"$GW5_MINUTES"` after it is finished/checked; then `prospective score` with its
returned settlement. To include that history in a later GW6 state, append
`--history-pair "$GW5_MINUTES" "$GW5_SETTLEMENT"` to **both** freeze commands,
provided the settlement predates the new snapshot. Repeated pairs support more
retained GWs. Omit unavailable pairs; do not create substitutes.

Verify the already-published real xPts forecast with:

```bash
.venv/bin/python -m fpl_ai prospective xpts verify --model-dir "$MODEL" \
  --forecast-dir data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527
```

## Verification and limits

The verifier is an **independent verification entry point with raw-evidence
reconstruction**, not a fully independent reimplementation of feature equations.
It calls production feature, fitting and forecast-verification functions. It
opens pinned raw bootstrap and settlement captures,
checks their hashes and flags, reconstructs all 56,804 feature rows using the live
projection, and compares every ordered value/type/missingness and fitting-row hash
with M3/M4C. It independently checks integer points labels, keyed populations,
aggregate fitting hashes and categorical/numeric preprocessing parity. Fresh fits,
post-unpickle fits and checksum-verified reuse reproduce both model states exactly.

**210 tests pass normally and under `python -O`**. The independent M4E reports
are byte-identical in both modes. Raw parity covers 78 source captures and 618,223
explicit zero history observations; 1,295 previous-GW values remain missing.

Focused tests exercise pre-deadline operation, late capture/computation/final
publication, mismatched snapshots/GWs/elements/models, duplicates/corruption,
future/unsettled/absent history, explicit zeros, warm-up, doubles, blanks, malformed
schedules, missing outcomes, target mutation, common rows, fresh/reuse behavior,
closed feature inputs and absence of CLI backdating. Normal and optimized full
suites and M2/M3/M4/M4B/M4C/M4D verification are recorded in regression evidence.
M3 through M4D replay reports equal their previously accepted JSON exactly; all
**822 pre-batch data files retain bytes and nanosecond mtimes**, including GW5.

```bash
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -m unittest discover -s tests -q
LOKY_MAX_CPU_COUNT=1 .venv/bin/python -O -m unittest discover -s tests -q
LOKY_MAX_CPU_COUNT=1 PYTHONPATH=. .venv/bin/python scripts/verify_prospective_xpts.py \
  --model-dir "$MODEL" \
  --forecast-dir data/prospective_xpts/forecasts/1aebfd57e85b4a1d44904f0669d0ff03a4caf2dfaa6bb40473d828f5c8128527 \
  --report /tmp/m4e-verification.json
# Repeat the verifier with python -O; reports must be identical.
```

M4D improved matched RMSE/MAE/Spearman but worsened top-10; no untouched historical
holdout remains. **New settled 2026/27 prospective evidence is required before
claiming v2 is better for real FPL decisions.** Historical fixture predictors,
external timestamp attestation, the Ferguson anomaly's cause and downstream
optimiser/product utility remain unresolved. No optimiser, transfers, captaincy,
chips, scheduler, UI, commit, merge or push was added. Successful real xPts
settlement/scoring remains pending its legal stage; offline lifecycle checks do not
claim a live outcome.
