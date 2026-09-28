# M5F final free-transfer lower-bound correction

Decision 070 corrects Decision 069's later-GW `0..cap` range. The prior 20-focused /
354-full-test evidence did not validate this edge; it is archived unchanged under
`local/m5f-final/pre-final-evidence/`. All fresh checks passed; acceptance is recommended within the documented limited v1 scope.
Starting checkout: clean branch `m5f-prospective-decision-review`, commit `ba652d5`
(previous M5F work), descended from merged M5E `06cf006`. No commit/push/merge.

## Corrected invariant

Actions.transfers is the complete target-GW transfer list. General initial squad
states may include zero FTs, but a later GW begins after weekly accrual. Production
uses the existing unchanged `Rules.next_free(0, 0)` transition for the minimum.
This is min(cap, weekly_free_transfers), currently one. Explicit later hits must
belong to `{Rules.hit(n, f): f in minimum..cap}`. Hit units use `Rules.hit_cost`.
First-GW exact reconciliation against original usable FTs remains, including zero.
No exact later balance, prior account actions, bank or prices are reconstructed.

| Complete later transfer count | Hit points | Feasible |
|---|---:|---|
| 0 | 0 | yes |
| 0 | 4 | no |
| 1 | 0 | yes |
| 1 | 4 | no |
| 2 | 0 | yes |
| 2 | 4 | yes |
| 2 | 8 | no |

Per-pair frozen positions, partial/null semantics, monotone confirmation extensions,
complete exclusion headlines and fixed-lineup scoring are preserved. No upstream
rules/planner transition, ranking, M5C settlement/calibration, M5D simulation or M5E
arithmetic changes. The audit independently derives the bound from archived cap
and weekly accrual and emits all seven boundary probes; it does not call production
`Rules.next_free`, `Rules.hit` or the action validator.

## Compatibility

The existing full-contract content binding remains; v1 family names are unchanged.
New canonical contract SHA-256:
`6f157a8424a7dbb4974cc4ee3a990e3c798a55b86e6fd44783b3ea9aa6f658cf`.
Previous contract `3273e103…` retention `dc8d02aa…`, confirmation `b58e4a9b…` and
review `5fa048a4…` each reject with `M5F contract mismatch`. All are preserved.
Tests also reject the earlier pre-hardening contract. New actual-time records use
`data/decision_reviews/final/retentions` and ignored `local/m5f-final/lifecycle`.
The unchanged M5E source is
`1ee8a90b35c7a823c9050d0d6d5bbd7462ba2ef4b1e22ddacb82b0ded108c6f5`.

## Reproduction

```bash
.venv/bin/python -m unittest tests.test_decision_review
.venv/bin/python -O -m unittest tests.test_decision_review
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -O -m unittest discover -s tests
.venv/bin/python -m fpl_ai review retain --decision "$DECISION" \
  --artifact-dir data/decision_reviews/final/retentions
.venv/bin/python -m scripts.verify_decision_review_lifecycle \
  --retention "$RETENTION" --root local/m5f-final/lifecycle \
  --output docs/M5F_LIFECYCLE.json
.venv/bin/python -m scripts.verify_decision_review --review "$REVIEW" \
  --evidence-root data --evidence-root local/m5f-final/lifecycle/synthetic-confirmations \
  --evidence-root local/m5f-final/lifecycle/synthetic-settlements --output "$AUDIT"
# Repeat each audit with python -O and compare bytes.
git diff --check
```

The full fresh lifecycle is regenerated because the contract creates new retention,
confirmation and review identities. It adds two public subprocess boundary commands:
reject complete later one-transfer + hit-cost, accept its zero-hit neighbour. Network
connects are forbidden in every lifecycle subprocess; no authority reader is mocked.
This separate later-GW confirmation is not attached to the GW6-only outcome demo.
A full two-GW confirmed horizon is independently reconstructed in both test modes.

## Preservation and limitations

The original inventory `local/m5f/prior-evidence.json` remains the baseline:
1,191 files (1,025 data, 68 docs, 98 local), digest
`477acf3e16a715fcdc9eb05df656760d38b10774460c0105d3051da647871c80`.
The separate `local/m5f-hardening/old-m5f-inventory.json` protects 60 older M5F
files. An additional 77 files from the preceding hardening run are protected by
`local/m5f-final/previous-hardening-inventory.json`; this supplements rather than
replaces either prior baseline. All checks compare SHA-256 and nanosecond mtimes.

The real-data GW6–10 M5E demonstration is a synthetic squad/snapshot and remains
pending as genuine manager evidence. The 56-point GW6 arithmetic comes solely from
isolated deterministic synthetic fixtures: it is not a user score, a live result,
optimiser performance or evidence of benefit. Confirmed horizon stays null when
later actions are unconfirmed. Fixed-lineup calculations do not represent official
FPL scores, autosubs, vice-captain substitution or chips. Manual assertions/local
clocks are not independently witnessed account history. Later market feasibility,
causal decision value and realised model/optimiser superiority remain unestablished.

Fresh test results (these logs were generated after the correction):

| Command suffix | Tests | Seconds | Result |
|---|---:|---:|---|
| `-m unittest tests.test_decision_review` | 21 | 75.155 | pass |
| `-O -m unittest tests.test_decision_review` | 21 | 92.986 | pass |
| `-m unittest discover -s tests` | 355 | 140.296 | pass |
| `-O -m unittest discover -s tests` | 355 | 139.749 | pass |

Exact log hashes are in `M5F_REGRESSION.json`. The corrected neighbour grid covers
zero, one, two and cap-plus-one transfers. A new complete one-transfer regression
proves zero hit can score and a hit-cost deduction fails both confirmation and
rehashed semantic review; it also rejects the previous `0..cap` contract. Existing
first-GW, null, pair, headline, extension and full-horizon tests still pass.

The real CLI boundary commands returned expected exit codes **1** (rejected) and
**0** (accepted). Their inputs differ only in hit points. The failed command left
no published confirmation. The command input path was then populated with the
valid neighbour; rejected bytes are preserved separately in
`local/m5f-final/lifecycle/rejected-later-one-transfer-snapshot.json`. Its SHA-256 is
`9ee9b73a7cc5f493dce49c0c141a37f300a41c5e34221b82bf95bd506a4fb6d1`.
For direct reproduction, run `review confirm` with that rejected snapshot as
`--assertion` and the new retention identity; expected error is
`transfers contradict hit points under every valid FT state`.

Independent pending, partial and complete audits all passed in normal and optimized
Python with byte-identical JSON, checking 25 candidate/GW entries per review.
The complete review retains original candidate totals 316, 314, 300, 308, 304; its
only confirmed synthetic target is GW6 (56), and its confirmed horizon remains null.

New actual-time identities:

- Retention: `b08bf724a3dc20ad9b3716f95dba95092b475b8ba54cf56f1e8b292869cccfc2`
- Pending review: `85452cf9f91258bb51dfa24288096624420a97440844a76ced0df0b323d2c50c`
- Partial review: `d3ce6abff519317e3e18129f00a3a92e92ca0f6a1609c1642553a1a803880671`
- Complete synthetic review: `f754f05a4e48306ffb0c7d74a62f739bb535f9a1c4a37e4a4fd7ad92330d2142`

Confirmation reuse and complete-review reuse retained identities. Semantic CLI
verification passed. All runtime products stay in ignored locations.

Final verification: all **10 CLI steps** returned their expected exit codes with
networking forbidden (1245.432 seconds total): nine successes and the deliberate
invalid-hit rejection. Replay reproduced all **five** bundle files byte-for-byte.
The final inventory check preserved **1,191 upstream + 60 older M5F + 77 additional
preceding-hardening files**, with exact bytes and nanosecond mtimes. No baseline
was rebased. Every lifecycle log hash was rechecked. `git diff --check` passes;
no commit, push or merge was made.

**Recommendation: accept M5F within its documented limited fixed-lineup v1 scope
after this final correction.** This is implementation acceptance, not a claim of
prospective eligibility or realised benefit for the synthetic/snapshot demonstration.
Machine evidence: `M5F_ACCEPTANCE.json`, `M5F_REGRESSION.json`, the three audit JSONs
and `M5F_LIFECYCLE.json` (exact CLI arguments, identities, timings and log hashes).
