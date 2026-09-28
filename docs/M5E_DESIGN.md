# M5E — Personal decision workflow v1

Implement a local, offline vertical slice over the accepted M5B–M5D readers.
`decision init|players|validate|run|verify|replay` shares one versioned configuration.
No network, fitting, calibration, new objective or account access occurs.

## Inputs and binding

`personal-state-v1` wraps the unchanged `current-squad-v1` with explicit evidence
kind (manual or synthetic), source description, user-declared observation time,
confirmation, zero already-made transfers, zero incurred hits and no active chip.
Available FTs means usable transfers before any transfer for the target GW, with
that GW's accrual already included. Other transfer/chip states are rejected rather
than partially costed. All 15 season-qualified IDs, exact sale prices, bank and
FTs are mandatory; money is integer tenths. Templates contain nulls and are invalid.
Import time is recorded by the runtime, separately from the user's assertion.
Manual evidence is not independently verified account data.

An explicit simulation directory anchors resolution. Exact dependency IDs come
from its verified binding, projection state and the fixed calibration contract.
Search only configured evidence roots for those IDs; zero or multiple physical
matches fails with setup/location instructions. Explicit dependency locations may
disambiguate but cannot override identities. Never select latest. Verify through
M5D, M5C and M5B semantic readers, including embedded M4E forecast/snapshot replay.
Configuration may name an existing path; squad, rules and effective settings must
match exactly. Otherwise build M5B paths, then use the existing M5D evaluator.
New path IDs retain mandatory exact optimiser/greedy replay. Default horizon five
(truncated at GW38), max transfers two, top N three; scenario settings are inherited
from the explicitly selected simulation (normally 16,384 / 1729), with optional
strict expected settings. A shorter planning horizon uses the first H weeks of
the bound simulation with its original donor population, as already supported by
M5D; it does not substitute a newly sampled shorter-horizon law. Every comparison
uses the same planning horizon. No fitting prerequisites are created implicitly.

## Time and publication

Snapshot mode is explicitly an offline what-if, even if created before deadline.
Pre-deadline mode additionally requires import and both publication checks before
the bound deadline, all upstream computation before import, observation at/after
snapshot capture and at/before import, and market/personal observations at most
24 hours old at each check. This conservative freshness gate is a workflow
policy, not an assertion of synchronous capture or model accuracy. No clock option.
Capture/request/receipt, forecast/projection computation, simulation attestation,
personal observation/import and report creation remain separate. Mixed ages and
missing retained history are displayed. All upstream publication gates remain.

A deterministic request key binds canonical state/provenance, effective settings,
exact upstream references, implementation and environment, excluding local paths
and runtime attestation. A fresh bundle records local import, creation-start and publication-check times.
A same-key run verifies and reuses one existing bundle without redating. An explicit
path identity conflicting with that cached bundle fails even when its squad is
equivalent; choose a separate output root to record that provenance. Ambiguous
matches fail. Explicit replay verifies and copies original bytes/attestation to a
new root. Verify reconstructs every summary field and both renderings from original
inputs, rechecks exact paths and evaluations, and rejects rehashed false content.
Canonical JSON digests preserve numeric/boolean type distinctions during summary,
canonical-squad and effective-config reconstruction; Python equality is insufficient.
The existing atomic publisher enforces a closed artifact family. All expensive
verification completes before publication; final clock failure removes staging.
Successful upstream path/evaluation artifacts may survive a failed personal run;
no personal report is published. Existing upstream bytes are never rewritten.

`created_at` records report creation start. After initial rendering, the runtime
samples `publication_checked_at` and checks deadline/freshness at that instant.
It embeds that value in the manifest, summary and both reports, then seals the
artifacts. The publisher runs another local-clock guard after manifest creation
and before atomic rename, requiring its clock not precede the retained check.
This last guard is not retained. Verification validates the retained check and
chronology, never substitutes creation time or claims an exact publication time.
There is an unavoidable scheduling/clock gap between the last guard and rename.
The local clock is not an independent or external witness. A consistently forged
local timestamp cannot be disproved without an external trusted witness.

## Reports and scope

Bundle: manifest, contract, canonical squad, personal metadata, effective config,
exact dependency references, summary.json, report.md and self-contained report.html.
Use names/clubs/positions/prices/selectability solely from the bound snapshot.
Report every returned path and both baselines, all GW economics and fixed XI/bench/
captain, plus independent XI/captain/hit arithmetic against both baselines. Preserve
forecast objective, analytical simulation expectation, Monte Carlo statistics and
M5C player intervals separately. Do not sum marginal intervals into plan intervals.
Keep M5D duplicate entries and exact simulation tie credit; probabilities concern
only supplied candidates. Ranking remains M5B ranking, never simulated risk order.
HTML escapes supplied text, has no scripts or external assets. Reports are read-only
conditional plans, never automated actions or evidence of realised improvement.

Real personal inputs/configs/source descriptions belong under ignored `local/`;
reports belong under ignored `data/personal_decisions/`. `data/` generally is not
ignored and must not be treated as a private-input location. Only
explicitly synthetic fixtures/examples and compact acceptance evidence are tracked.
