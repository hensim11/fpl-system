# M5F — prospective decision retention and fixed-lineup review v1

Contract fixed before implementation, 2026-09-28. No new ranking, model, calibration,
simulation law, account access or outcome-dependent candidate selection.

## Evidence boundaries

Three separate immutable families use the existing closed-set atomic publisher:
retention, manager confirmation, outcome review. Retention semantically verifies an
exact M5E bundle and copies its entire summary, candidate order, baselines, forecasts,
simulation statistics, assumptions and original times. It also binds all target
deadlines from the original M5C archive and the evaluation protocol below. New
retention has actual import/publication-check times. Snapshot M5E or retention at/
after the first deadline is retrospective and excluded from prospective claims.
No clock override is exposed. Local timestamps are not an external witness.

A confirmation binds one retention, its exact M5E identity, season and target GW.
Provenance is explicitly manual or synthetic. Selection/rejection of a named frozen
candidate is an intention only. Separate nullable fields explicitly assert executed
transfers (ordered pairs), current squad, XI, captain, total target-GW hit points and
chip status. Null means unknown, [] means confirmed no transfers, and chip='none'
means explicitly no chip. User-declared action time, actual import and publication
check stay distinct. No inference from intention to execution. Unknown players,
invalid formation, duplicate IDs, unsupported chips and contradictory assertions
fail closed. Prices, bank and account history are not independently verified.

One confirmation may extend an explicitly referenced predecessor for the same GW;
it can fill unknown fields but cannot revise a confirmed fact or intention. Existing
facts retain their original record/time through the predecessor. Transfer lists are
the complete declared sequence for that target GW; do not append invented events.
Corrections require explicit investigation outside v1. Reviews reject competing
heads rather than choosing the latest or most favourable assertion. Parent chains
are verified and retained; repeating any evidence never increases its weight.

Confirmations imported or publication-checked at/after their target deadline are
late even if the user declares an earlier action time. A later extension cannot
upgrade a late record. Synthetic evidence is always excluded from real decision-
value claims. Eligibility is only a timing/provenance prerequisite, never proof
of causal benefit or independently verified account activity.

## Predeclared evaluation

Use only `multi_outcomes.load_settlement`, hence the existing M5C authoritative
finished/data_checked/fixture reconciliation, identity and complete-player gates.
Each GW is independent. Exact duplicate settlement identity is deduplicated;
different settlements for one target fail, including later captures with equal
totals. Absent evidence is pending. Authoritative season-wide blanks remain null
and unscorable, never zero. Doubles use the verified total once.

For each original candidate, in original order, each GW's diagnostic is sum of
settled XI points + one extra captain score - frozen hits. Compare with the same
fixed-lineup forecast (settled minus forecast error), no-transfer and greedy.
Retain simulation distributions unchanged; do not tune them or select another
candidate. Horizon totals and deltas require every GW and every required label.
No partial-horizon totals masquerade as full results.

Confirmed actions have a supported fixed-lineup score only with explicit squad,
legal XI, captain, hits and no chip. Transfers may remain unknown; in that case a
score does not establish plan adherence. Compare each known component with the
selected candidate at that GW, reporting partial/divergent/full declared match;
even a full match is a manual assertion. Future planned transfers remain
hypothetical unless separately confirmed. Frozen-path scores are arithmetic
diagnostics, not executable counterfactual utility: later prices, eligibility,
availability and circumstances are unsupported. Official FPL scores are never
claimed: vice captain, automatic substitutions and chips are outside v1.

## Verification and privacy

Readers reconstruct retained summaries, timing labels, confirmation validation,
component matches and review arithmetic, then compare canonical JSON digests and
rendered reports. Dependency references bind identity and exact manifest/artifact
bytes. Rehashed semantic changes fail; a consistently forged standalone manual
assertion/time cannot be disproved without an external witness. Reuse verifies
same-input evidence without redating; replay preserves original artifact bytes.
Review accepts an explicit evidence set and can extend a verified prior review;
it never replaces or rewrites it. All personal inputs/reports stay under ignored
`local/` or `data/decision_reviews/`; tracked fixtures are synthetic.

Acceptance: focused/full normal and optimized tests, independent arithmetic and
identity audit, CLI lifecycle with deterministic synthetic settlements, current
real-data M5E bundle pending without fabricated actions/results, and prior byte/
nanosecond-mtime preservation. Future real settlement is operational follow-up,
not a prerequisite for implementation acceptance.

## Focused hardening before acceptance

Review found three gaps in the initial implementation: later-GW hit/count
combinations were not bounded, pair positions were unchecked, and the headline
reported retention exclusions alone. Acceptance was withheld pending these fixes.
The architecture and scoring definitions remain unchanged.

Use the existing `Rules` contract. All non-null hits are non-negative integer
multiples of `hit_cost`. When transfers and hits are both explicit, require the
later-GW hit to belong to `{Rules.hit(n, f): f in Rules.next_free(0, 0)..free_transfer_cap}`.
The existing transition guarantees weekly accrual capped by the FT cap; the
minimum is currently one. This is a necessary feasibility check, not an estimate
of the exact later usable FT balance. Paid transfers range from max(0,n-cap)
through max(0,n-minimum), inclusive. Thus one transfer permits only zero hit; two
permit zero or one hit-cost, never two. First-target exact reconciliation with
original usable FTs remains (including a known zero FT state).
Null transfer lists or null hits retain their prior partial/unknown semantics.

Every asserted out/in pair must have equal positions in the exact frozen
population. Validate the pair as written; never rematch it using aggregate sets.
The separate comparison with a candidate's overall in/out sets remains unchanged.

Review `prospective_exclusions` is the sorted unique union of retention and all
attached confirmation exclusions, including predecessor records. Separate
`retention_exclusions` and `confirmation_exclusions` expose the components (the
latter may itself include inherited retention reasons). JSON, CLI, Markdown and
HTML all consume the same aggregate headline.

Compatibility uses M5F's existing full-contract content comparison; it has no
separate implementation hash. Add only the substantive `action_validation` and
`review_exclusions` contract fields, keeping the v1 family names. Old M5F bundles
lack those semantics and fail `M5F contract mismatch`; they are preserved, not
reinterpreted or rewritten. New retention binds the unchanged M5E bundle and
records its actual new time. Use a separate output root for this deliberate new
retention; same-request reuse of an old contract correctly fails. M2–M5E identities
and computations remain untouched.

Final correction (Decision 070), specified before implementation: the previous
0..cap range confused initial squad states with subsequent-GW entry states. Reuse
`Rules.next_free(0, 0)` without changing planner transitions; amend the content-bound
hit invariant and preserve all earlier bundles. Independently derive the lower
bound from archived weekly accrual/cap in audits. Require complete-confirmation
and real subprocess rejection evidence plus fresh normal/optimized regressions.
