# M4C — 2024/25 cumulative-minutes investigation

The discrepancy remains **unresolved**. Pinned evidence identifies a later change
in the upstream cumulative aggregate, rather than a second canonical fixture.
No value, settlement choice or earlier artifact has been corrected.

## Evidence and reproducibility

[Machine-readable evidence](M4C_DISCREPANCY.json) contains source/build identities,
accepted captures, all canonical fixture observations for element 123 (Evan
Ferguson), and 56 neighbouring bootstrap captures. The neighbours are **every**
blob dated February 24 through March 9, 2025 inclusive in the existing immutable
fplcache commit `33dac28d18953bee5bc4bd56ddd8a5e32e169d68`. This time interval was
chosen around GW27 and its accepted settlement, before inspecting their values.
The complete pinned tree is not truncated. Each additional compressed raw file is
checked against its tree Git blob SHA-1 and size, with SHA-256 retained in the report.
Raw additions live separately in ignored `data/m4c_investigation/`; historical raw
inventories and processed builds are not changed.

```bash
PYTHONPATH=. .venv/bin/python scripts/investigate_minutes.py --download
# Exact offline reproduction after retaining those immutable inputs:
PYTHONPATH=. .venv/bin/python scripts/investigate_minutes.py --report /tmp/m4c-discrepancy.json
```

| Observation (UTC) | Cumulative minutes | Total points | GW event points | GW27 finished / checked |
| --- | ---: | ---: | ---: | --- |
| Accepted pre-GW27: Feb 25 12:45 | 270 | 21 | 1 (prior event) | false / false |
| Feb 28 01:48, after the fixture | 287 | 22 | 1 | false / false |
| Feb 28 06:31 | 287 | 22 | 1 | true / false |
| Feb 28 12:44 through Mar 2 18:29 | 287 | 22 | 1 | true / true |
| Mar 3 01:52 | 304 | 23 | 1 | true / true |
| Selected settlement: Mar 8 06:25 | 304 | 23 | 1 | true / true |

Canonical fixture 266, February 27 at 20:00 UTC, reports **17 minutes and 1 point**.
The accepted delta is therefore 304 − 270 = **34**, while the earlier independently
observed aggregate increase was 287 − 270 = **17**. The later aggregate change is
bounded by the March 2 18:29 and March 3 01:52 captures; it is not an exact change
or correction timestamp. It adds 17 cumulative minutes and one total point without
changing the GW event point. No reset to zero is observed in this interval.

The selected settlement was fixed by the historical next-deadline capture policy.
The earlier settled captures are diagnostic evidence only: selecting one because
it agrees with the fixture value would change that policy after seeing outcomes.
The pinned archive tree has **no live-event paths**; it preserves bootstrap captures,
not archived `/event/27/live/` responses. Present-day live data cannot reconstruct
that historical response. No historical live minutes are invented.

## Scope and conclusion

Only **element 123 / GW27** fails the cumulative-delta minutes check in 2024/25.
The settled cumulative aggregate stays 17 above the canonical season sum in each
GW27–38 capture (12 disagreements). Independently reconciled subsequent GW deltas,
including 21 minutes in GW28 and 1 minute in GW29, still agree. The previously
reported final total-points difference of one is consistent with the observed
aggregate change, but does not establish its cause. The sources do not tell us
whether the fixture record or cumulative aggregate was intentionally corrected,
nor why. Transfer-related double counting is not asserted as fact.

The five-season M4C audit finds no other minutes-delta or cumulative mismatch outside
this exact case. This supports a player-specific quarantine; it does not prove the
API's aggregate semantics universally reliable.

## Narrow policy: `ferguson-unresolved-minutes-v1`

- Bind the exact season, element, GW, complete source identity, before/after hashes,
  selected settlement time, sole delta disagreement and 12 cumulative offsets.
  Any other disagreement fails, including missing or noninteger evidence.
- Keep his GW27 minutes label **null**, with an explicit unresolved reason. It is
  excluded from every fit, recent-history calculation and minutes metric.
- From the first accepted capture where the discrepancy is evidenced
  (**2025-03-08 06:25 UTC**, also GW28's capture), mask only this player's cumulative
  minutes feature through season end. This affects **11 rows**, GW28–38; the
  missingness flag remains explicit. No future observation changes the GW27 inputs.
- Retain later GW deltas only after their own explicit endpoint/fixture reconciliation
  and settlement. The constant offset cancels in those independently verified deltas;
  no division, clipping, subtraction of 17, or imputed history is performed.
- Retain all other players and fields. Cumulative starts have no evidenced mismatch
  and remain directly observed. Season-local identity prevents spillover into 2025/26.

The missing **target** does not make Ferguson's pre-GW27 **forecast input** temporally
invalid. That forecast is an eligible OOS feature; its minutes outcome remains
unavailable for evaluation/fitting. Downstream eligibility never promises a usable
label for a later modelling task. This distinction avoids using a future target
anomaly to alter an already-valid pre-deadline forecast.

The policy is in deterministic OOS identity. Original M4B still rejects the season;
its strict defaults, contracts and artifact bytes are unchanged.
