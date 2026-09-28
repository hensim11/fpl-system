# M5E — Personal decision workflow verification

The current attestation-hardening acceptance is described in
[M5E attestation verification](M5E_ATTESTATION_VERIFICATION.md).
The results below are the historical initial M5E acceptance, retained for context;
its [compact acceptance record](M5E_ACCEPTANCE.json) has not been rewritten. It implements the real-input
workflow over unchanged accepted M5B/C/D contracts.
The demonstration is explicitly synthetic, not the user's squad or personalised
advice. There are no new realised outcomes or model/decision-quality claims.

## Scope and operator entry points

Production modules: `fpl_ai/personal_decision.py`, `fpl_ai/decision_report.py`.
CLI and the shared closed artifact registry are extended. `current-squad-v1`,
M5B ranking/solver, M5C calibration and M5D simulation/evaluation implementations
are unchanged. See [design](M5E_DESIGN.md), Decisions 061–064, and the practical
quick start at the beginning of [README](../README.md).

```bash
PY=.venv/bin/python
SIMULATION=data/simulations/0a4dceb30cd0fba3c4ef50c8f09b4c89e74eeb3a4b3704dc70baa69ac5029a62
$PY -m fpl_ai decision init --config local/my-decision.json --simulation-dir "$SIMULATION"
# Supply actual values and provenance in local/my-decision-state.json.
# The untouched template must fail validation; the player catalog is a lookup, not a squad.
$PY -m fpl_ai decision validate --config local/my-decision.json
$PY -m fpl_ai decision run --config local/my-decision.json
BUNDLE=data/personal_decisions/PASTE_RETURNED_ID
$PY -m fpl_ai decision verify --bundle "$BUNDLE"
$PY -m fpl_ai decision replay --bundle "$BUNDLE" --artifact-dir local/decision-replay
```

All 15 IDs, sale prices, bank and FTs are explicit. Available FTs includes target-GW
accrual before any target-GW transfer. Chips, prior transfers and incurred hits are
rejected. Personal observation is a user assertion; import/creation use the actual
local clock. Prebuilt-path comparison canonicalizes player ordering, while rejecting
different account economics/configurations. New path IDs always retain exact replay.

Missing evidence produces setup instructions and cannot trigger fitting/capture.
The explicit simulation anchor resolves exact IDs with no latest selection. Ordinary
runs, validation, verification and replay are offline. Snapshot mode is always
labelled what-if. New pre-deadline records require the actual bound deadline gate
and the documented 24-hour market/personal freshness policy. No CLI time override.

## End-to-end retained-evidence demonstration

The user-facing `decision init`, `decision validate` and `decision run` commands
were executed. The initialized local wrapper was filled only with the existing
explicitly synthetic `tests/fixtures/optimiser/demo_gw6_squad.json`, labelled synthetic
and confirmed at the actual runtime. No public manager account was fetched.

| Product | Exact identity |
| --- | --- |
| Personal bundle | `a4ef6e6949af0b45962ed6a5a99c46c0adea571587484f455cb106f9301f9468` |
| Canonical M5B path | `6051dbbe4da465a8f7f0ae1574ed7548ed85ca2d0d3013679d0e9aff4a29bf56` |
| M5D evaluation of that path | `a8a5e125b5caff8f15ad1fe47d5d7aab10f911a0692ecc619fd9cacf42ebc339` |
| Reused simulation | `0a4dceb30cd0fba3c4ef50c8f09b4c89e74eeb3a4b3704dc70baa69ac5029a62` |

The new path identity results from canonical sorted squad serialization; it is
**not** in M5D's accepted-demo whitelist. Its exact optimiser and greedy replay
were required during evaluation and verification. The resulting `decision.json`
is byte-identical to the equivalent original M5B top-three decision. Its
`evaluation.json` is byte-identical to the equivalent original M5D evaluation.
Only the dependency/publication identities differ.

The historical initial report is under
`data/personal_decisions/a4ef6e6949af0b45962ed6a5a99c46c0adea571587484f455cb106f9301f9468/`:

- `summary.json`: canonical state, all five candidate entries, exact per-GW economics,
  both baseline decompositions, original full simulation metrics and M5C intervals.
- `report.md` and `report.html`: deterministic renderings of the same reconstructed
  summary, including names/clubs/positions from the embedded bound snapshot.
- `squad.json`, `personal.json`, `config.json`, `dependencies.json`, `contract.json`
  and `manifest.json`: canonical inputs, exact dependency hashes and runtime attestation.

Local config: `local/synthetic-demo.json`; local wrapper and player catalog share
that stem. Real inputs are intentionally absent. Earlier development reports, if
retained locally, have earlier implementation identities and are not this final
initial acceptance bundle. The original `a4ef6e…` bundle is preserved, but does
not pass the current semantic reader because the implementation/contract changed.
Its generic artifact hashes remain valid. No mutable latest alias is used.

```bash
BUNDLE=data/personal_decisions/a4ef6e6949af0b45962ed6a5a99c46c0adea571587484f455cb106f9301f9468
.venv/bin/python -m fpl_ai decision run --config local/synthetic-demo.json
.venv/bin/python -m fpl_ai decision verify --bundle "$BUNDLE"
PYTHONPATH=. .venv/bin/python scripts/verify_personal_decision.py --bundle "$BUNDLE" \
  --report local/m5e-independent-recheck.json
```

## Timing and numerical results

Original market capture: **2026-09-18 21:07:27.274412 UTC**. Projection computation:
**September 21 22:51:47.767427 UTC**. Simulation computation: **September 23
10:18:25.273024 UTC**. Synthetic assertion: **11:29:07.595954 UTC**; final-run import:
**15:24:29.990344 UTC**; report creation: **15:29:29.813974 UTC**, September 23.
Bound first deadline: **2026-10-10 10:00 UTC**, from retained evidence, not a fresh
status lookup. The report is **synthetic / snapshot**. It exposes the 114.37-hour
market age and mixed observations; it does not claim fresh pre-deadline advice.
M5D's final publication gate is preserved, but its exact final publication time was
not separately retained upstream and is not invented from file mtimes.

Five GWs, full 659-player forecast population, two transfers/GW maximum, **three
returned exact paths**, 16,384 scenarios and seed 1729. No-transfer and sequential
greedy are separate candidate entries. First GW of path 1 sells Guessand [42] and
Hill [60], buys Groß [124] and Gvardiol [391], captains Rogers [40], incurs four
hit points, leaves bank 3 (£0.3m) and FT state 1 → 1. This is an arithmetic example,
not an instruction for any actual manager.

| Candidate | Forecast objective | Analytical simulation expectation | MC mean | P10 | P90 | Lower 10% mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| No transfer | 164.065 | 166.015 | 165.745 | 140.847 | 192.737 | 132.392 |
| Greedy | 188.020 | 189.970 | 189.770 | 165.110 | 216.464 | 156.798 |
| Exact 1 | 194.178 | 196.128 | 195.990 | 171.580 | 222.738 | 163.111 |
| Exact 2 | 194.046 | 195.995 | 195.847 | 171.510 | 222.349 | 163.076 |
| Exact 3 | 193.924 | 195.873 | 195.745 | 171.395 | 222.361 | 162.846 |

Path 1's paired win probabilities are 96.53% versus no-transfer and 67.40% versus
greedy, conditional on this empirical law. Tiny top-N gaps do not imply decisive
advice or statistical significance. Residual bias explains the difference between
forecast and simulation expectation. Highest-return probabilities retain supplied
candidate/duplicate/tie semantics, not probabilities of beating every legal plan.

Path 1 versus no-transfer decomposes into **+38.11327122244173 XI points,
+0 captain bonus, −8 hits = +30.113271222441732**. Versus greedy it is
**+14.158354176133727 XI, +0 captain, −8 hits = +6.158354176133727**.
All 50 per-GW comparisons and horizon sums are independently checked. Transfer-only
player forecast subtraction is not used as the explanation.

## Observed verification

The actual pre-change baseline ran **299 tests normally and under optimized Python**.
The final implementation runs **31 focused M5E tests and 330 full tests in both
modes**. Final full runs after canonical-order and strict JSON-type verification corrections
took 46.819s normal and 48.011s optimized under concurrent local work. Focused tests cover:

- Invalid templates, duplicate/unknown IDs, season/GW, strict money/FT types,
  provenance, prior transfers/hits/chips and exact sale-price preservation.
- Owned/unowned selectability, scenario/horizon settings, missing/ambiguous/conflicting
  references, another squad's paths and input-order-independent compatibility.
- Mixed/stale observations, after-deadline offline labels, no future assertion or
  backdating, final deadline/freshness gates and unchanged replay attestation.
- Independent small-fixture XI/captain/hit/economics arithmetic, both baseline
  decompositions, unchanged simulation fields and duplicate/tie credit.
- Escaped names, bound club names, deterministic renderings, semantic reconstruction,
  rehashed false summary/personal/dependency/report/evaluation/path rejection,
  including boolean-for-integer substitutions in otherwise rehashed summaries/squads
  and explicit path identity conflicts with cached decisions,
  incomplete artifacts, final-gate/partial-failure cleanup and upstream mtimes.

The [independent audit](M5E_VERIFICATION.json) is byte-identical in normal and
optimized Python (SHA-256 `03a00a93edf39274426b89d7e2550c09c3ceebdce5aee2702773fdef1fb2e2d2`).
It verifies **3 exact paths, 5 candidate
entries, 25 candidate-GW plans and 50 per-GW baseline decompositions**. It reuses
the independent exhaustive M5B XI/economics oracle and independent scalar M5D
RNG/return/metric audit on the **actual new path/evaluation**. It does not use the
production report builder or decomposition function as its oracle.

The existing M5B audit, **22-case / 82-path exhaustive oracle**, M5C audit and M5D
audit reproduce the accepted reports byte-for-byte in both modes. M2 five-season,
M3 and M4E audits pass. Dependency checks, compilation, standard-library CLI help,
whitespace and unchanged analytical-module/dependency-file checks pass. Full logs
are under ignored `local/m5e-checks/`; [regression evidence](M5E_REGRESSION.json)
records exact command results and hashes.

All **1,030 pre-batch evidence files**, including **973 data files**, retain SHA-256
bytes and nanosecond mtimes. The inventory was captured before implementation.
No commit, merge or push was performed. No upstream artifact was rewritten.

The [real CLI lifecycle evidence](M5E_LIFECYCLE.json) records successful verification,
same-config reuse and explicit replay of the final bundle, plus rejection of a
rehashed summary whose horizon gain was increased by ten points. Every CLI process
ran with Python audit hooks forbidding socket connection and name-resolution calls.
Original bundle bytes and nanosecond mtimes were unchanged; replay copied identical
bytes, identity and original import/creation attestation. Separate focused tests also
reject boolean-for-integer substitutions and an explicit path identity conflicting
with a cached decision. No new path was added to M5D's accepted-demo whitelist.

The HTML is 58,601 bytes, with 21 tables, 17 headings, no scripts and no external
resource references. Escaping and reconstruction are tested. Browser screenshot
QA was not completed: browser automation was unavailable, and native browser
selection stalled. This does not affect the offline generated report or semantic
checks; visual appearance is not claimed to have been screenshot-verified.

## Runtime and limits

The full-build user-facing run took **432.59 seconds** under concurrent
verification: upstream semantic checks 24.45s, planning 136.84s, evaluation with
exact path replay 135.39s, and final verification/publication 135.92s. An earlier
complete run took 414.83s. The final publication, including strict-type and explicit-identity checks, reused the explicit
compatible path and took **299.94 seconds**: source checks 16.75s, path compatibility
check 0.001s, evaluation/exact replay 157.51s and final verification/publication
125.69s. Its path still underwent mandatory exact optimiser/greedy replay.
These are measurements, not latency bounds. Repeated
exact solves dominate; no unsafe cache, accepted-demo whitelist, population pruning
or optimiser redesign was introduced to avoid them.

Model limitations remain: static prices/selectability; missing retained history;
no historical fixture predictors; forecast-selected fixed XIs/captains; no autosubs,
vice-captain substitutions or chips; limited player/team/match dependence; no
established realised decision-value improvement. Manual state is not independently
verified account data. Prospective retention/settlement remains separate and
requires genuine authoritative results; M5E does not invent future outcomes.

Next: prospective decision retention and outcome review, with confirmed manager
actions kept separate from hypothetical paths, predeclared comparisons and immutable
original decisions. New risk-aware optimisation still requires an explicit utility
contract and stronger prospective evidence.
