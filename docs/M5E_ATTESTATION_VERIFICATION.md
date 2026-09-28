# M5E attestation hardening acceptance

This pass changes time attestation and privacy guidance only. M5B exact ranking,
M5C calibration, M5D simulation, squad economics and dependency identities remain
unchanged. The current acceptance bundle and command results are recorded below. The example is synthetic, not personal advice.

## What is attested

The runtime records import, then `created_at` at report-creation start. After
initial rendering, it samples `publication_checked_at` and validates chronology,
deadline and source freshness. That retained event is embedded in the manifest,
summary and reports before sealing. After artifact hashing and manifest writing,
a final unretained local-clock guard repeats the checks before atomic rename.
A failed check removes staging and leaves no successful personal bundle; separate
valid upstream plan/evaluation artifacts may remain.

Verification validates the retained `publication_checked_at`, not `created_at`
as a substitute for a final check. Reuse and replay retain all original attestation
fields and artifact bytes. Tests cover exactly 24 hours (allowed), one microsecond
over (rejected), one microsecond before deadline (allowed), at/after deadline
(rejected), crossings after report creation and during sealing, clock regression,
and rehashed missing, malformed, reversed, stale, deadline-reaching and inconsistent
attestations. A pre-deadline bundle accepted at exactly 24 hours is reused and
replayed after deadline with its original attestation.

An immutable bundle cannot include its exact atomic rename time. The recorded
check is before sealing; the final guard is not retained. Scheduling or clock
changes between the last guard and rename remain possible. The local clock is
not an independent or external witness. Semantic verification cannot disprove a
coherently forged local-clock history; it validates consistency and policy at the
recorded event, not external truth or fresh account state.

## Privacy and historical compatibility

Real personal inputs, configs and source descriptions belong in ignored `local/`.
Reports belong in ignored `data/personal_decisions/`. `data/` generally is **not**
ignored. README and the M5E design guidance now say this explicitly.

The initial bundle `a4ef6e6949af0b45962ed6a5a99c46c0adea571587484f455cb106f9301f9468`
and all prior machine-readable evidence are preserved. It passes generic artifact
hash verification but **does not pass the current semantic reader**: its original
implementation/contract binding differs. The real CLI rejects it with
`personal decision implementation/environment/contract mismatch`. No historical
version dispatcher or silent migration has been added. Initial evidence remains
in `M5E_ACCEPTANCE.json`, `M5E_VERIFICATION.json`, `M5E_LIFECYCLE.json`,
`M5E_REGRESSION.json` and `M5E_PROFILE.json`.

## Acceptance results

Current synthetic snapshot bundle:
`data/personal_decisions/1ee8a90b35c7a823c9050d0d6d5bbd7462ba2ef4b1e22ddacb82b0ded108c6f5`.
Local import: `2026-09-23T16:23:46.713336Z`; creation start:
`2026-09-23T16:29:00.750982Z`; retained publication check:
`2026-09-23T16:29:00.837030Z`. Real CLI creation took 314.151664 seconds.
The frozen September 18 market snapshot is stale, so this demonstration deliberately
uses snapshot mode. It is not evidence of fresh pre-deadline account use.

All non-timing summary fields are identical to the initial bundle. The dependency,
squad, personal and effective-config JSON files are byte-identical. In particular,
the path remains `6051dbbe4da465a8f7f0ae1574ed7548ed85ca2d0d3013679d0e9aff4a29bf56`
and evaluation remains `a8a5e125b5caff8f15ad1fe47d5d7aab10f911a0692ecc619fd9cacf42ebc339`.

The commands below record the acceptance run; the published records alone are
**not a clean-checkout replay recipe**. Repeating the preservation check requires
the original pre-edit inventory (`local/m5e-attestation/before.json`), the original
files it inventories, and the raw test/run/stale-input logs under ignored
`local/m5e-attestation/`. The local finalizer, configs, bundle pointer, prior-bundle
result and optimized audit output are also required; they are not supplied by the
published JSON records. An inventory recreated after editing cannot establish the
original preservation claim. Retain these local inputs and logs before finalizing.

Exact commands from the repository root (log redirections omitted here):

```sh
.venv/bin/python -m unittest tests.test_personal_decision
.venv/bin/python -O -m unittest tests.test_personal_decision
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -O -m unittest discover -s tests
.venv/bin/python -m fpl_ai decision run --config local/synthetic-demo.json
BUNDLE=data/personal_decisions/1ee8a90b35c7a823c9050d0d6d5bbd7462ba2ef4b1e22ddacb82b0ded108c6f5
PYTHONPATH=. LOKY_MAX_CPU_COUNT=4 .venv/bin/python scripts/verify_personal_lifecycle.py --bundle "$BUNDLE" --config local/synthetic-demo.json --work-dir local/m5e-attestation/lifecycle --report docs/M5E_ATTESTATION_LIFECYCLE.json
PYTHONPATH=. LOKY_MAX_CPU_COUNT=4 .venv/bin/python scripts/verify_personal_decision.py --bundle "$BUNDLE" --report docs/M5E_ATTESTATION_AUDIT.json
PYTHONPATH=. LOKY_MAX_CPU_COUNT=4 .venv/bin/python -O scripts/verify_personal_decision.py --bundle "$BUNDLE" --report local/m5e-attestation/audit-optimized.json
.venv/bin/python -m fpl_ai decision verify --bundle data/personal_decisions/a4ef6e6949af0b45962ed6a5a99c46c0adea571587484f455cb106f9301f9468
# Run the stale-input check first; retain its expected rejection in stale-predeadline-run.log.
LOKY_MAX_CPU_COUNT=4 .venv/bin/python -m fpl_ai decision run --config local/m5e-attestation/stale-predeadline-config.json
git diff --check
# Finalization reads that log and the original pre-edit inventory and raw logs.
PYTHONPATH=. .venv/bin/python local/m5e-attestation/finalize.py
```

Tests: **35 focused / 334 full**, passing in normal and optimized Python.
Final logged durations: focused 29.394s / 32.980s; full 52.145s / 56.162s.
Logs and pre-edit byte/mtime inventory are under `local/m5e-attestation/`.
The old-bundle CLI verify exits 1 with the expected compatibility rejection.
The extra real pre-deadline CLI run uses a separate config with the same synthetic
inputs and an isolated output root; it exits 1 with the 24-hour freshness error
and leaves no personal manifest or staging directory.

The lifecycle driver invokes the actual CLI through `runpy`, with socket connection
and DNS calls forbidden by a Python audit hook. Its JSON records exact CLI arguments,
exit codes, runtimes and log hashes for validate, verify, same-config run (reuse),
replay, rehashed false summary and rehashed false attestation. The fresh creation
above was a separate actual CLI command.

The independent M5E audit passes in normal and optimized Python with byte-identical
JSON. It checks the retained attestation, 3 exact paths, 5 candidate entries, 25
candidate gameweeks and 50 per-GW baseline decompositions. Existing equivalent
M5B decision and M5D evaluation bytes match. See [audit](M5E_ATTESTATION_AUDIT.json).

All real CLI lifecycle checks pass. See [lifecycle evidence](M5E_ATTESTATION_LIFECYCLE.json)
and the [current acceptance record](M5E_ATTESTATION_ACCEPTANCE.json).

| Real CLI operation | Exit code | Seconds |
| --- | ---: | ---: |
| validate | 0 | 147.700 |
| verify | 0 | 129.295 |
| same-config run / verified reuse | 0 | 281.460 |
| replay | 0 | 139.421 |
| rehashed false summary / expected rejection | 1 | 143.858 |
| rehashed false attestation / expected rejection | 1 | 1.040 |

Replay preserves original identity, attestation and artifact bytes; reuse and
verification preserve bytes and nanosecond mtimes. The final inventory check finds
**zero changes across 1,123 prior files**, including 1,016 data files and 45 prior
JSON evidence files. Narrative documentation was deliberately corrected and now
points here; original machine-readable acceptance evidence was not overwritten.
`git diff --check` passes. No commit, merge or push was performed.

**Ready to accept for pre-deadline use within the documented local-clock check
policy.** This is not proof of exact atomic publication time, an external time
witness, or independent account truth. Actual inputs must satisfy the freshness
and deadline gates; the retained synthetic CLI example remains a stale snapshot.
No planning, calibration, simulation, economics, ranking or dependency identity
changes, prospective outcomes, manager-action tracking or general historical
verification dispatcher were introduced.

