# M5F focused hardening verification

M5F's initial implementation was **not accepted**. Review found three correctness/
reporting defects after its 16-focused/350-full-test run. This document records the
focused correction; original evidence is archived without alteration under
`local/m5f-hardening/pre-hardening-evidence/`. Decision 069 preserves that history.
Final machine results are in [acceptance](M5F_ACCEPTANCE.json),
[regression/preservation](M5F_REGRESSION.json) and [CLI lifecycle](M5F_LIFECYCLE.json).

The branch remains `m5f-prospective-decision-review`, based on merged M5E commit
`06cf0069eb5ee50d1a69f1115ae5e5525199b0e1`. No commit, push or merge is performed.
The architecture, score definitions, original candidate order, M5B optimiser,
M5C settlements/calibration, M5D simulation and M5E arithmetic are unchanged.

## Findings and exact corrections

1. **Impossible later-GW hits.** Validation previously did exact count/hit
   reconciliation only for the first target. Later targets checked a literal
   four-point unit but not the feasible count/hit combinations. Now every explicit
   hit is a non-negative integer multiple of `Rules.hit_cost`. If both count n and
   hit are explicit, require membership in `{Rules.hit(n, f): f in 0..cap}`. With
   current registered rules this means paid transfers between max(0,n−5) and n,
   inclusive, each costing four points. Zero transfers therefore force zero hits;
   a six-transfer assertion cannot have zero hits. The range is derived from the
   registered valid FT domain used by the squad reader and transfer-path arcs.
   First-GW exact reconciliation remains. **No later FT balance is inferred**;
   feasibility under some valid state is not proof of the exact account deduction.
   Unknown transfer count or hit preserves existing partial semantics.
2. **Cross-position pairs.** Known IDs, final squad legality and matching aggregate
   transfer sets did not ensure each asserted pair was position-compatible. Each
   pair now checks equality of the two exact frozen positions before scoring or
   full-match classification. No user pair is reordered or rematched. Synthetic
   fixture authors explicitly construct legal pairs. The real-data demonstration
   has MID 42→124 and DEF 60→391; crossing those incoming players is rejected.
3. **Incomplete headline.** `assemble` previously copied only retention exclusions
   to the top level. It now produces a sorted, unique union of retention and all
   attached confirmation exclusions, including predecessors. Separate
   `retention_exclusions` and `confirmation_exclusions` expose the components;
   the latter can include inherited retention reasons. CLI, Markdown and HTML all
   use the same overall `prospective_exclusions` field. A timely eligible retention
   cannot hide a late or synthetic confirmation.

No production verification uses Python `assert`. Additional actual frozen-population
synthetic validation probes are in [M5F_HARDENING_PROBES.json](M5F_HARDENING_PROBES.json).

## Compatibility boundary

M5F binds the **entire contract content**, not a separate source implementation hash.
The smallest substantive change adds `action_validation` (including the existing
rules definition) and `review_exclusions` to that contract. Family/version names
remain v1; this is a focused pre-acceptance correction, not a new milestone.

Hardened canonical contract SHA-256:
`3273e103fba316c79081fd59a63db1d3ddd307aeeb6d6f02cff06cb326b8eed1`.

Old M5F retention `c6b2a3dc…`, confirmation `b30c91d6…` and review `9c1bd5a7…`
were explicitly reverified and each rejects with `M5F contract mismatch`. They
remain on disk unchanged. No old timestamp is reused for a new retention. The
fresh actual-time retention is:
`dc8d02aabf1991b6e2370ea689a2faaf4aa11f6fae27a0d0a01c0835c8eb5ac7`, under
`data/decision_reviews/hardened/retentions/`, bound to unchanged M5E identity
`1ee8a90b35c7a823c9050d0d6d5bbd7462ba2ef4b1e22ddacb82b0ded108c6f5`.

An existing output root containing the old same-request retention fails reuse
rather than silently migrating it. Deliberately use the separate hardened root.

## Tests and independent reconstruction

```bash
.venv/bin/python -m unittest tests.test_decision_review
.venv/bin/python -O -m unittest tests.test_decision_review
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -O -m unittest discover -s tests
```

All rerun suites pass:

| Scope | Normal | Optimized (`-O`) |
| --- | --- | --- |
| Focused M5F | 20 tests, 69.620s | 20 tests, 82.934s |
| Full repository | 354 tests, 135.543s | 354 tests, 135.567s |

Four focused regressions were added:

- Rule-derived later-GW count/hit feasibility, valid neighbours, cap-induced lower
  bound, null partial cases, zero-transfer scored case, and rehashed impossible-hit
  rejection before any confirmed-score arithmetic.
- Correct two-position pairs pass; swapping their incoming players preserves both
  aggregate sets but fails for first and later targets.
- Timely eligible retention with synthetic or late manual-labelled fixture actions:
  JSON component/overall fields, Markdown, HTML, CLI, semantic reconstruction and
  replay agree. Duplicate input does not duplicate messages; rehashed hidden
  exclusions fail reconstruction. All such manual labels are test fixtures only.
- Pre-hardening contract rejection without reinterpretation.

Existing pending, blank, double, partial/full-horizon, explicit partial execution,
monotone extensions, conflict, corruption, immutable reuse and replay tests remain.
The complete two-GW synthetic confirmation test reconstructs and independently
checks a fully declared horizon; this is not a live manager result.

The independent audit script still sums raw fixture explanation points and checks
identities, forecasts, baseline deltas and completeness without production scoring
helpers. It now independently checks paid-transfer bounds from frozen rules,
pair positions, and derives exclusions from provenance/publication checks. Pending,
partial and complete sample audits must be byte-identical normally and under `-O`.
See [pending](M5F_PENDING_AUDIT.json), [partial](M5F_PARTIAL_AUDIT.json) and
[complete](M5F_AUDIT.json) audit products. Exact test counts, timings and log hashes
are recorded in M5F_REGRESSION.json after the hardening rerun.

## Fresh CLI lifecycle and sample

```bash
.venv/bin/python -m fpl_ai review retain \
  --decision data/personal_decisions/1ee8a90b35c7a823c9050d0d6d5bbd7462ba2ef4b1e22ddacb82b0ded108c6f5 \
  --artifact-dir data/decision_reviews/hardened/retentions
.venv/bin/python -m scripts.verify_decision_review_lifecycle \
  --retention data/decision_reviews/hardened/retentions/dc8d02aabf1991b6e2370ea689a2faaf4aa11f6fae27a0d0a01c0835c8eb5ac7 \
  --root local/m5f-hardening/lifecycle --output docs/M5F_LIFECYCLE.json
```

The script invokes actual CLI subprocesses with networking forbidden, without
mocking production readers. It records/reuses a synthetic GW6 confirmation,
reviews one target, accumulates all five using `--previous`, reuses, verifies and
replays the review. Exact commands, identities, exit codes and timings are in the
lifecycle JSON. CLI syntax and assertion schema remain in [README](../README.md).

The real-data pending review has **no action or settlement**. GW6–10 remain pending
and all confirmed scores are null. Their original deadlines run from October 10
to November 7. No newer API evidence or manager behaviour is fetched or invented.
The demonstration remains a **synthetic squad / snapshot**, not prospective value
validation. Its independent deterministic settled fixtures live only under ignored
`local/m5f-hardening/lifecycle/synthetic-settlements/`, separate from that pending
review. Fixture request times are synthetic, not live captures.

The scoring definition is unchanged. The five-GW synthetic fixture totals remain
316 (no-transfer), 314 (greedy), 300/308/304 (exact paths 1–3), in original order.
Only GW6 has a synthetic action: XI 52 + captain 8 − hit 4 = **56**. GW7–10 actions
remain unconfirmed, hence the confirmed five-GW total remains null. A populated
review headline now also names `synthetic confirmation`, alongside snapshot and
synthetic-decision exclusions.

## Preservation and limits

The original inventory is still exactly **1,191 files**, loaded from
`local/m5f/prior-evidence.json`; it is not replaced with a convenient new baseline.
It contains 1,025 data files, 68 prior documentation/evidence files and 98 local
files. Check both SHA-256 bytes and nanosecond mtimes. A separate additional inventory of
60 pre-hardening M5F files verifies their immutability too. Updated M5F documentation
and machine evidence are intentionally regenerated; their previous copies are
archived locally. No accepted upstream artifact is rewritten.

These checks do not establish official FPL scoring, autosubs, vice-captain
substitution, chips, independently verified account history, later market
feasibility, causal decision value or realised model/optimiser superiority.
Manual assertions and local clocks are not external witnesses. Monotone extensions
only fill unknown fields; corrections/changed intentions still require investigation.
Later-GW hit feasibility proves internal possibility only, not actual FT balance.

Reproduce an audit from the identity printed by `review outcomes`:

```bash
.venv/bin/python -m scripts.verify_decision_review --review "$REVIEW" \
  --evidence-root data \
  --evidence-root local/m5f-hardening/lifecycle/synthetic-confirmations \
  --evidence-root local/m5f-hardening/lifecycle/synthetic-settlements \
  --output local/m5f-hardening/audit-normal.json
.venv/bin/python -O -m scripts.verify_decision_review --review "$REVIEW" \
  --evidence-root data \
  --evidence-root local/m5f-hardening/lifecycle/synthetic-confirmations \
  --evidence-root local/m5f-hardening/lifecycle/synthetic-settlements \
  --output local/m5f-hardening/audit-optimized.json
cmp local/m5f-hardening/audit-normal.json local/m5f-hardening/audit-optimized.json
git diff --check
```

Final hardening acceptance: all eight fresh CLI subprocesses passed with networking
forbidden, totaling **1,017.006 seconds**. Confirmation and review reuse preserved
identities; replay reproduced all **five** complete-review files byte-for-byte.
Independent pending, partial and complete audits pass in normal and optimized
Python with identical output. The final preservation check re-used the original
inventory: all **1,191** upstream files and all **60** separately inventoried old
M5F files retain exact bytes and nanosecond mtimes. `git diff --check` passes;
upstream M5B–M5E computation modules are unchanged. No commit, push or merge.

Fresh complete synthetic review identity:
`5fa048a4be78dad44d9a2f474fb3d4f93e1ddd8c9ee1b7e4e6cf3a597d859cc6`.
Its confirmed GW6 fixed-lineup score is **56**; its confirmed horizon is **null**
because GW7–10 actions are unconfirmed. Candidate horizon totals in original order
are **316, 314, 300, 308, 304**. Headline exclusions include snapshot/what-if,
synthetic decision and synthetic confirmation. These are deterministic synthetic
fixtures only. The separate real pending review has no manager confirmation and
no settled targets. See `M5F_LIFECYCLE.json` for every exact CLI argument/log hash,
`M5F_REGRESSION.json` for test/audit hashes and `M5F_ACCEPTANCE.json` for final status.

**Recommendation: accept M5F within its documented limited v1 scope after this
hardening.** This is an implementation acceptance recommendation, not evidence of
prospective eligibility or realised decision value for the demonstration.
