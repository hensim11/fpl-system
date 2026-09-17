"""Independent, versioned selection of archived settled event-point evidence."""

from datetime import timedelta

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_transform import parse_utc, utc_string

STRATEGY = "earliest_settled_current_event_v1"
POLICY = {
    "strategy": STRATEGY,
    "minimum_hours_after_last_kickoff": 2,
    "maximum_days_after_last_kickoff": 7,
    "require_current_event": True,
    "require_exact_event_deadline": True,
    "tie_policy": "reject",
    "later_mutation_policy": "report_next_deadline_only",
}


def validate_policy(policy):
    if (not isinstance(policy, dict) or policy != POLICY
            or any(type(policy[k]) is not type(v) for k, v in POLICY.items())):
        raise FPLValidationError("unsupported or malformed settled-event selection policy")


def event_and_points(payload, gameweek, deadline):
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise FPLValidationError("malformed settlement events")
    matches = [e for e in payload["events"] if isinstance(e, dict) and e.get("id") == gameweek]
    if len(matches) != 1:
        raise FPLValidationError("missing or ambiguous settlement event")
    event = matches[0]
    for flag in ("finished", "data_checked", "is_current"):
        if type(event.get(flag)) is not bool:
            raise FPLValidationError(f"malformed settlement flag {flag}")
    if not isinstance(event.get("deadline_time"), str) or parse_utc(event["deadline_time"], "settlement deadline") != deadline:
        raise FPLValidationError("settlement event deadline mismatch")
    elements = payload.get("elements")
    if not isinstance(elements, list) or not elements:
        raise FPLValidationError("missing settlement elements")
    points = {}
    for element in elements:
        if (not isinstance(element, dict) or type(element.get("id")) is not int
                or type(element.get("event_points")) is not int):
            raise FPLValidationError("malformed settlement element or event_points")
        if element["id"] in points:
            raise FPLValidationError("ambiguous duplicate settlement element")
        points[element["id"]] = element["event_points"]
    return event, points


def select_settled_events(fixtures, deadlines, entries, policy, obtain, decode, on_consume=None):
    """Choose earliest observed settlement, without access to canonical player points.

    Settlement time itself is not timestamped by the API. True settlement flags
    are the evidence that settlement preceded capture; the final kickoff plus
    two hours is an additional conservative lower bound, never a settlement claim.
    """
    validate_policy(policy)
    last_kickoff = {}
    for fixture in fixtures:
        if fixture["finished"] is not True:
            raise FPLValidationError("settlement selection requires finished fixtures")
        gw = fixture["gameweek"]
        kickoff = parse_utc(fixture["kickoff_time_utc"], "fixture kickoff")
        last_kickoff[gw] = max(last_kickoff.get(gw, kickoff), kickoff)
    selected, evidence, consumed = {}, {}, []
    for gw, kickoff in sorted(last_kickoff.items()):
        lower = max(deadlines[gw], kickoff + timedelta(hours=policy["minimum_hours_after_last_kickoff"]))
        upper = kickoff + timedelta(days=policy["maximum_days_after_last_kickoff"])
        next_deadline = deadlines.get(gw + 1)
        if next_deadline is not None:
            upper = min(upper, next_deadline)
        candidates = sorted((capture, path) for capture, path in entries if lower < capture < upper)
        if len({capture for capture, _ in candidates}) != len(candidates):
            raise FPLValidationError(f"ambiguous settlement capture timestamps for GW{gw}")
        rejected = []
        for capture, path in candidates:
            value, record = obtain(path)
            # Every inspected candidate proves why the first acceptable one wins.
            consumed.append((record, "settlement_selection_evidence"))
            if on_consume is not None:
                on_consume(record, "settlement_selection_evidence")
            payload = decode(value, path)
            event, points = event_and_points(payload, gw, deadlines[gw])
            current_events = [e for e in payload["events"] if isinstance(e, dict) and e.get("is_current") is True]
            if len(current_events) > 1:
                raise FPLValidationError(f"ambiguous current settlement event for GW{gw}")
            if not event["is_current"]:
                raise FPLValidationError(f"stale settlement evidence for GW{gw}: {path}")
            if not (event["finished"] and event["data_checked"]):
                rejected.append({"path": path, "sha256": record["sha256"],
                                 "capture_time_utc": utc_string(capture),
                                 "finished": event["finished"], "data_checked": event["data_checked"],
                                 "reason": "event_not_settled"})
                continue
            selected[gw] = (payload, path, record["sha256"])
            consumed.append((record, "total_points_reconciliation"))
            if on_consume is not None:
                on_consume(record, "total_points_reconciliation")
            evidence[str(gw)] = {
                "source_path": path, "source_sha256": record["sha256"],
                "capture_time_utc": utc_string(capture),
                "finished": True, "data_checked": True, "is_current": True,
                "deadline_time_utc": utc_string(deadlines[gw]),
                "strict_lower_bound_utc": utc_string(lower), "strict_upper_bound_utc": utc_string(upper),
                "selection_reason": "earliest archived current-event capture with both settlement flags true after the final fixture cutoff",
                "rejected_candidates": rejected,
            }
            break
        if gw not in selected:
            raise FPLValidationError(f"no valid settled-event evidence for GW{gw}")
    return selected, evidence, consumed


def later_mutations(selected, deadline_snapshots, deadlines):
    """Audit already-consumed later captures; never select by point agreement."""
    mutations = []
    for gw, (payload, path, _) in sorted(selected.items()):
        later = deadline_snapshots.get(gw + 1)
        if later is None:
            continue
        _, later_path, later_payload, record = later
        _, points = event_and_points(payload, gw, deadlines[gw])
        later_event, later_points = event_and_points(later_payload, gw, deadlines[gw])
        if not (later_event["finished"] and later_event["data_checked"]):
            continue
        for element in sorted(points.keys() & later_points.keys()):
            if points[element] != later_points[element]:
                mutations.append({"gameweek": gw, "element": element,
                                  "selected_event_points": points[element],
                                  "later_event_points": later_points[element],
                                  "selected_source_path": path, "later_source_path": later_path,
                                  "later_source_sha256": record["sha256"]})
    return mutations
