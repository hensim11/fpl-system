# Milestone 4 — First reproducible trained-model experiment

Verified 2026-09-17. **The first modelling batch is complete, and the narrow M4
exit criterion is satisfied:** a saved, reproducible trained model improves next-GW
point prediction over all five frozen baselines on validation and the separate
holdout. This is evidence for the registered-player prediction problem, not evidence
of profitable transfers, captain selection, squad optimisation or a live product.

## Frozen inputs and architecture

M3 identity: `57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a`.
M2/M3 files and contracts were read-only. All five exact historical versions,
source/build identities, settlement hashes and the GW18 exception are inherited in
`upstream.json`, an exact semantic copy of the M3 manifest. No M2/M3 generation code
changed. M3 retains 137,662 feature rows, 137,038 labels and the 624 globally empty
GW rows. The target, population, double summation, AM exclusion and all point-in-time
protections remain unchanged.

`experiment_io.py` verifies M3 identity, contract, exact artifact set and hashes,
then applies a keyed stage-specific adapter. `experiments.py` owns the closed model
matrix, pipelines, train-only fits, validation selection and frozen holdout scoring.
`experiment_diagnostics.py` reuses M3 metrics for diagnostics and comparisons.
The CLI exposes `experiment validate` and `experiment holdout`. No notebook is needed.

## Predeclared experiment

Train: **2021/22–2023/24**, 80,234 labelled rows (80,858 total; 624 null labels excluded).
All fitted imputation, scaling, encoding and model parameters use only these rows.
The latest training settlement is 2024-05-20 06:25 UTC, before the first validation
capture at 2024-08-16 12:38 UTC. Validation: **2024/25**, 27,159 rows.
Final test: **2025/26**, 29,645 rows. Neither season refits preprocessing or models.
Earlier settled points may update the existing M3 histories prospectively within
each season; this is the original contract, not model retraining.

Primary selection metric, declared before evaluation: **overall validation RMSE**,
minimised with configuration-name tie-breaking. Squared error targets the conditional
mean appropriate for expected points. MAE and within-GW Spearman remain reported.
No random split, CV sweep, test-label selection, output clipping or early stopping.

Exactly four candidates:

- Ridge with alpha 10 and 100; SVD solver and intercept. A transparent regularised
  additive model exposes what the narrow feature set can do without interactions.
- Histogram gradient boosting with 15 or 31 maximum leaves; squared-error loss,
  150 iterations, learning rate 0.05, minimum 50 samples per leaf, L2 regularisation
  10, seed 1729, early stopping disabled. These capture bounded nonlinear interactions.

Common preprocessing was fixed before seeing results. The model uses **25 of the
27 M3 predictors**. Team ID and its missingness flag are explicitly excluded because
season-local numeric team IDs do not identify the same club across seasons. No
replacement identity or new historical feature was introduced.

The remaining 12 numeric fields use training-median imputation followed by training
standardisation. An entirely missing training column is retained with computational
fill 0. Eleven original missingness indicators pass through unchanged. Position and
status use training-fitted one-hot encoding, retaining all categories; an unknown
category maps to all zeros. A categorical null becomes `__missing__`. Numerical fills
do not assert that unknown chance means fit, or that absent history means zero.
The independent indicators retain that information. All transformations and the
estimator are serialized as one fitted sklearn Pipeline. Both families use the same
projection. Coefficients are conditional associations, not causal effects.

## Validation results

| Approach | MAE | RMSE | Mean within-GW Spearman | Scored / labelled |
| --- | ---: | ---: | ---: | ---: |
| historical_mean | 1.4768 | 2.3451 | undefined | 27,159 / 27,159 |
| position_mean | 1.4719 | 2.3405 | 0.1011 | 27,159 / 27,159 |
| recent_points | 1.0888 | 2.2029 | 0.6750 | 27,159 / 27,159 |
| player_scoring_rate | 1.1035 | 2.0747 | 0.6046 | 27,159 / 27,159 |
| fpl_ep_next | 1.1071 | 2.1213 | 0.6470 | 27,159 / 27,159 |
| ridge_10 | 1.0906 | 1.9783 | 0.7123 | 27,159 / 27,159 |
| ridge_100 | 1.0903 | 1.9783 | 0.7123 | 27,159 / 27,159 |
| hist_15 | 0.9853 | 1.9164 | 0.7269 | 27,159 / 27,159 |
| hist_31 | 0.9840 | 1.9218 | 0.7280 | 27,159 / 27,159 |

All scored approaches have 100% coverage. Constant-mean ranking is undefined in all
38 GWs, not zero. Hist_31 has slightly better MAE/ranking, but hist_15 wins the
predeclared RMSE criterion (1.916383 versus 1.921773). The tiny between-tree-model
difference is not claimed significant. No additional search was performed.

**Frozen winner: hist_15.** Validation artifact identity:
`09eb67bd0fc9198073c28f921e3ba0ffd67876f341d32a97dc0f76743e0d411c`.
Its immutable `frozen.json`, validation predictions/metrics and all four fitted
pipelines were published before the holdout command was invoked. It explicitly
records `holdout_evaluated: false`; that original freeze is never rewritten.
Only the selected saved pipeline is used on test. Other candidates have no test
ML scores and cannot become alternatives selected from holdout performance.

## Separate final holdout

| Approach | MAE | RMSE | Mean within-GW Spearman | Scored / labelled |
| --- | ---: | ---: | ---: | ---: |
| historical_mean | 1.5368 | 2.3749 | undefined | 29,645 / 29,645 |
| position_mean | 1.5322 | 2.3725 | 0.0805 | 29,645 / 29,645 |
| recent_points | 1.0729 | 2.2077 | 0.7071 | 29,645 / 29,645 |
| player_scoring_rate | 1.1044 | 2.0880 | 0.6326 | 29,645 / 29,645 |
| fpl_ep_next | 1.0692 | 2.1234 | 0.6892 | 29,645 / 29,645 |
| hist_15 | 0.9537 | 1.9164 | 0.7415 | 29,645 / 29,645 |

Holdout identity:
`21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd`.
It references the exact freeze identity and manifest checksum. No refitting and no
model/configuration changes occurred after holdout scoring. Subsequent runs were
exact reproducibility replays, not new model selection.

## Deltas and uncertainty

Deltas are model minus baseline; negative error deltas are improvements. All
comparisons use exactly the common labelled/predicted rows. The FPL benchmark is
not imputed. Here all five baselines cover every validation and test row.

| Baseline | Validation ΔMAE | Validation ΔRMSE | Holdout ΔMAE | Holdout ΔRMSE | Holdout ΔSpearman | Holdout GW bootstrap 95% interval, ΔRMSE |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| historical_mean | -0.4915 | -0.4287 | -0.5832 | -0.4584 | undefined | [-0.4864, -0.4332] |
| position_mean | -0.4866 | -0.4241 | -0.5785 | -0.4561 | 0.6610 | [-0.4844, -0.4308] |
| recent_points | -0.1035 | -0.2865 | -0.1193 | -0.2912 | 0.0344 | [-0.3277, -0.2568] |
| player_scoring_rate | -0.1182 | -0.1583 | -0.1507 | -0.1716 | 0.1089 | [-0.1970, -0.1462] |
| fpl_ep_next | -0.1218 | -0.2049 | -0.1155 | -0.2070 | 0.0523 | [-0.2342, -0.1794] |

On test the winner reduces RMSE by **8.2%** versus player scoring rate (the strongest
non-ML baseline by validation RMSE) and **9.7%** versus archived ep_next. It has lower
squared error than every baseline in **38/38 test GWs**. On validation it beats
scoring rate in 38/38 and ep_next in 36/38 GWs. The effect is not just a tiny pooled
score difference. These are descriptive paired GW-cluster bootstrap intervals
(2,000 samples, seed 1729); they preserve player dependence within a GW but do not
model serial dependence between GWs, season shift, or selection uncertainty. They
are not a guarantee of future performance or downstream decision utility.

## Position and history segments

All position groups have full coverage; exact season/position metrics for every
candidate and baseline, ranking-defined counts, common-coverage deltas and uncertainty
are in [M4_VERIFICATION.json](M4_VERIFICATION.json).

| Split | Position | Rows | Winner MAE | Winner RMSE | Winner Spearman | Scoring-rate RMSE | FPL ep_next RMSE |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| validation | GK | 2,855 | 0.7602 | 1.5997 | 0.6948 | 1.7509 | 1.8467 |
| validation | DEF | 9,099 | 0.9950 | 1.8281 | 0.6556 | 1.9685 | 2.0343 |
| validation | MID | 12,203 | 0.9907 | 1.9722 | 0.7550 | 2.1257 | 2.1655 |
| validation | FWD | 3,002 | 1.1483 | 2.2025 | 0.7735 | 2.4319 | 2.4212 |
| test | GK | 3,416 | 0.6048 | 1.4114 | 0.6738 | 1.5754 | 1.6079 |
| test | DEF | 9,707 | 1.0761 | 2.1028 | 0.6965 | 2.2864 | 2.3417 |
| test | MID | 13,255 | 0.9257 | 1.8509 | 0.7620 | 2.0212 | 2.0436 |
| test | FWD | 3,267 | 1.0682 | 2.0509 | 0.7908 | 2.2043 | 2.2298 |

| Split | Segment | Rows | Winner RMSE | Scoring-rate RMSE | FPL ep_next RMSE |
| --- | --- | ---: | ---: | ---: | ---: |
| validation | cold_start | 610 | 1.9385 | 2.2755 | 2.0180 |
| validation | low_history | 2,172 | 1.8686 | 2.2652 | 2.0544 |
| validation | established_history | 24,987 | 1.9205 | 2.0573 | 2.1270 |
| validation | missing_chance | 10,108 | 1.9730 | 2.1117 | 2.2009 |
| test | cold_start | 685 | 2.2261 | 2.5540 | 2.3400 |
| test | low_history | 2,363 | 2.0620 | 2.4235 | 2.2703 |
| test | established_history | 27,282 | 1.9033 | 2.0564 | 2.1102 |
| test | missing_chance | 11,544 | 2.0329 | 2.1672 | 2.2452 |

Cold start means zero prior settled observations; low history means fewer than
three. These segments overlap by design and are not summed. The cold-start segment
includes first-GW players and new entrants, not a cross-season debut definition.
Missing-chance performance remains reported, without replacing its semantics.

## Interpretation and investigated anomalies

- Ridge's largest positive numeric coefficients include chance of playing (about
  +0.51 points per training standard deviation), season scoring mean (+0.50), and
  price (+0.27). Correlated history means/flags distribute weight; status dummy
  coefficients must be interpreted with the chance/status combination and intercept.
  In particular the positive `status_u` coefficient is not evidence that unavailable
  players are good selections. This additive model has substantial negative tails.
- Within-GW grouped permutation importance on a deterministic uniform sample of
  4,096 validation rows identifies incoming transfers, chance of playing and price
  as the largest nonlinear signals. Hist_15 mean MSE increases are approximately
  0.867, 0.335 and 0.184 respectively. Outgoing transfers, ownership and points-history
  fields also contribute. Each value is permuted with its missingness indicator,
  three repetitions; correlations can mask importance and the perturbations are not
  causal interventions. No test-label feature selection or test permutation was run.
- Hist_15 validation forecasts range **−0.307 to 10.193**, median 0.591, with
  **1,269 negative values (4.67%)**. Test forecasts range **−0.379 to 10.232**,
  median 0.369, with **1,654 negatives (5.58%)**. The test 1st/99th percentiles are
  −0.023/5.168. Small negative fitted expectations are retained and documented;
  some actual FPL returns are negative. No clipping was introduced.
- Ridge_10 validation forecasts range −2.859 to 12.590, with 4,984 negative values;
  Ridge_100 is similar. Hist_31 has 2,081 negatives and range −0.479 to 10.991.
  These are genuine model behaviours, not missing-value conversion errors.
- The largest hist_15 validation forecast is Saka GW33: **10.193 versus 2 actual**,
  with 601,445 incoming transfers and 100% chance in the accepted snapshot.
  The low forecast for Alexander-Arnold GW29 is −0.307 versus 0 actual, alongside
  25% chance and 659,883 outgoing transfers. Saka GW18 explains Ridge's extreme
  negative tail: injury status, 0% chance and 2,366,646 outgoing transfers.
- Haaland GW4 validation is a major model/rate disagreement: hist_15 forecasts
  4.181 versus scoring-rate 13.667 and 13 actual. The model's availability adjustment
  (75% chance) and nonlinear response can undershoot a prolific player. The broad
  average improvement does not mean every major disagreement is correct.
- Test highs include Haaland GW36, 10.232 versus 11 actual, and B. Fernandes GW34,
  9.822 versus 5. The lowest test forecast, Gabriel GW13, is −0.379 versus 0,
  with 0% chance and 988,674 outgoing transfers.
- **17 unique extreme/disagreement rows were independently traced to the pinned raw
  accepted snapshots.** All eight snapshot state fields match, hashes verify and
  captures precede deadlines. No source correction was needed. Names here come only
  from those snapshots and never enter training. See
  [M4_SANITY_TRACES.json](M4_SANITY_TRACES.json).
- Test defenders average 1.086 predicted versus 1.240 observed, despite better RMSE
  than baselines. Other positions average 0.776/0.751 (GK), 1.209/1.174 (MID), and
  1.338/1.286 (FWD), predicted/observed. This calibration gap and the changed scoring
  environment deserve future investigation; this experiment does not establish a
  causal explanation and was not recalibrated using test labels.

Transfer counters are accepted pre-capture state, not final-season totals. They
can indirectly contain crowd information about availability or fixtures, but no
hindsight fixture/blank/double variable is used. Dependence on crowd activity and
capture freshness limits portability to other as-of times and user populations.

## Artifacts and reproducibility

Validation contains `upstream.json`, `frozen.json`, `validation.json`,
`predictions.csv`, `diagnostics.json`, `interpretation.json`, `comparisons.json`,
four fitted `.pickle` pipelines and `manifest.json`. Holdout has its own predictions,
metrics, diagnostics, comparisons and manifest. Prediction tables contain only keys
and forecasts; original features, labels and audit tables remain separately in M3.

Identities cover deterministic metadata and actual serialized artifact hashes,
including model state and predictions. Python/library versions, machine/system,
seed, single-thread numerical execution, feature order, preprocessing and model
configuration are recorded. No timestamps or absolute paths enter identity. Saved
pipeline bytes plus pinned sklearn versions preserve all effective estimator defaults.
This guarantees checked reproduction in the recorded environment, not bitwise equality
across every architecture or future library release. Model IDs are their pickle
SHA-256 values; the freeze identity binds all four to their inputs and selection.

Publication stages a complete directory then renames it. Reuse recomputes candidate
products and rejects any mismatch; it never overwrites different content. Readers
check manifest identity, directory identity, the exact stage artifact/checksum set,
and file checksums. Load only locally generated/trusted pickle artifacts: checksums
are integrity checks, not a way to make hostile pickle data safe.

Fresh independent validation fits and frozen holdout replays reproduced **all
artifact hashes, predictions, metrics, diagnostics and saved model bytes**. Reuse
preserved bytes and modification times. The 124 existing historical processed files,
all existing M3 artifacts and historical catalogue were preserved. All **146**
pre-batch files also retain their initial bytes and mtimes; see
[M4_REGRESSION.json](M4_REGRESSION.json).

The one post-holdout code hardening concerned artifact integrity: require the
directory identity and closed stage artifact set even when a supplied manifest is
internally self-consistent, and check stage completeness before publication. It does not alter preprocessing, models,
selection, predictions or metrics. No performance-driven adjustment was made.

## Verification and commands

145 automated tests pass (132 prior plus 13 M4). Tests cover closed feature projection,
target/audit exclusion, train-only fitting and preprocessing statistics, null-label
exclusion, settlement boundaries, unknown categories, all-null numeric handling,
missingness flags, RMSE tie-breaking, test-stage isolation, prediction alignment,
corruption/missing/extra files, directory identity, fresh reproduction, frozen-only
holdout inference, CLI misuse and checks active under Python optimization.

All five M2 seasons pass fresh offline rebuild/audit. M3 verification rechecks all
137,662 rows, all 137,038 settled targets and all 4,553 explicit empty-player zeros,
and reproduces its original artifact bytes and metrics. Compilation, dependency
consistency, CLI help and whitespace checks pass. No lint/type checker is configured.
No commit, push or merge was performed.

Pinned dependencies: scikit-learn 1.7.2, NumPy 2.3.3, SciPy 1.16.2, joblib 1.5.2,
threadpoolctl 3.6.0. Mature numerical implementations and fitted Pipelines justify
this small stack; no custom inferior regressor, dataframe stack or deep-learning
framework was added. Verified on Python 3.14.0 / Darwin arm64. Python >=3.11 remains
the package requirement. Standard-library ingestion paths retain lazy ML imports.
See [sklearn's histogram boosting API](https://scikit-learn.org/1.7/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html)
and [imputation contract](https://scikit-learn.org/1.7/modules/impute.html).

Run from the repository root with the existing historical/M3 artifacts available:

```bash
.venv/bin/python -m pip install -e .
M3=data/modelling/57c2e4a54faca1328dc77e19471564cedd41eb6b73238b476ff00ab21f194f7a
FREEZE=data/experiments/09eb67bd0fc9198073c28f921e3ba0ffd67876f341d32a97dc0f76743e0d411c
HOLDOUT=data/experiment_holdouts/21ea26b746acce28a243b749c6facab09e934a5e0fbffc7f163b6355055ca9bd

# Optional LOKY_MAX_CPU_COUNT suppresses restricted macOS CPU-discovery warnings.
# Numerical work already runs under threadpool_limits(limits=1).
export LOKY_MAX_CPU_COUNT=1
.venv/bin/python -m fpl_ai experiment validate --m3-dir "$M3"
.venv/bin/python -m fpl_ai experiment holdout --m3-dir "$M3" --frozen-dir "$FREEZE"
PYTHONPATH=. .venv/bin/python scripts/verify_experiments.py --m3-dir "$M3" --frozen-dir "$FREEZE" --holdout-dir "$HOLDOUT" --report docs/M4_VERIFICATION.json
PYTHONPATH=. .venv/bin/python scripts/inspect_experiment_sanity.py --m3-dir "$M3" --frozen-dir "$FREEZE" --holdout-dir "$HOLDOUT" --report docs/M4_SANITY_TRACES.json
.venv/bin/python -m unittest discover -v
PYTHONPATH=. .venv/bin/python scripts/verify_modelling.py --report /tmp/m4-m3-verification.json
PYTHONPATH=. .venv/bin/python scripts/verify_historical_seasons.py --report /tmp/m4-historical-verification.json
.venv/bin/python -m compileall -q fpl_ai scripts tests main.py
.venv/bin/python -m pip check
.venv/bin/python -m fpl_ai experiment --help
git diff --check
```

A fresh machine must first reproduce the M2/M3 artifacts with the commands in the
M3 verification record. Training does not download or regenerate upstream data.
`--artifact-dir` changes only the output root. The verification script deliberately
replays the unchanged experiment in fresh roots and then checks same-root reuse.
It is not permission to try different configurations against the reported holdout.

## Limits and recommended next batch

This is a useful first xPts model, with credible improvement for the frozen target.
It remains a broad, zero-heavy registered-player benchmark with just one validation
and one test season. No untouched test season remains in this five-season archive.
Feature importance and bootstrap intervals do not prove product value. Predictions
are still sensitive to injuries, crowd transfer activity and snapshot timing; the
2021/22 GW18 12:33 state/207-minute freshness limitation remains authoritative.

The next substantial batch should establish additional **point-in-time evidence**
for playing-time/availability history and, only if independently recoverable,
deadline fixture context. Specify the evidence and feature-version contract first,
then use chronological training/validation experiments, preserving this M4 result
as a frozen reference. Seek genuinely new prospective holdout observations for
future confirmation. Investigate position calibration and useful-player segments
without retuning on 2025/26. Arbitrary model complexity, inferred final fixture
schedules, optimiser scope and claims of beating live FPL forecasts are not justified.
