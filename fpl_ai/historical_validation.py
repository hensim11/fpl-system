"""Cross-table data-quality contract for canonical historical data."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import canonical_json_bytes, sha256_bytes
from fpl_ai.historical_schema import (
    FIXTURE_CONTEXT_AVAILABILITY_POLICY,
    POST_EVENT_FIXTURE_CONTEXT_FIELDS,
    TABLE_SCHEMAS,
    schemas_as_dict,
)
from fpl_ai.historical_transform import parse_utc


def build_quality_report(
    season: str,
    tables: dict[str, list[dict[str, Any]]],
    expected_gameweeks: list[int],
    expected_counts: dict[str, int],
    source_row_counts: dict[str, int],
    total_points_reconciliation: dict[str, Any],
    source_schema_audits: dict[str, dict[str, Any]],
    vaastav_source_schema: dict[str, object],
) -> dict[str, Any]:
    failures: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, detail: Any) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            failures.append(f"{name}: {detail}")

    for table, schema in TABLE_SCHEMAS.items():
        rows = tables[table]
        expected_columns = [column.name for column in schema]
        actual_columns = list(rows[0]) if rows else expected_columns
        check(
            f"{table}.canonical_schema",
            actual_columns == expected_columns,
            {
                "unexpected_additions": sorted(set(actual_columns) - set(expected_columns)),
                "unexpected_removals": sorted(set(expected_columns) - set(actual_columns)),
                "column_order_matches": actual_columns == expected_columns,
            },
        )
        type_errors = _type_errors(rows, schema)
        check(f"{table}.required_fields_and_types", not type_errors, type_errors[:20])

    players = tables["players"]
    teams = tables["teams"]
    fixtures = tables["fixtures"]
    facts = tables["player_fixture_facts"]
    snapshots = tables["player_deadline_snapshots"]
    gameweeks = tables["gameweeks"]

    player_ids = {row["element"] for row in players}
    team_ids = {row["team_id"] for row in teams}
    fixture_ids = {row["fixture"] for row in fixtures}
    expected_gw_set = set(expected_gameweeks)

    check(
        "players.unique_season_element",
        len(player_ids) == len(players),
        {"rows": len(players), "distinct": len(player_ids)},
    )
    player_codes = [row["player_code"] for row in players]
    check(
        "players.unique_season_player_code",
        len(set(player_codes)) == len(player_codes),
        {"rows": len(player_codes), "distinct": len(set(player_codes))},
    )
    check(
        "teams.unique_season_team_id",
        len(team_ids) == len(teams),
        {"rows": len(teams), "distinct": len(team_ids)},
    )
    check(
        "fixtures.unique_season_fixture",
        len(fixture_ids) == len(fixtures),
        {"rows": len(fixtures), "distinct": len(fixture_ids)},
    )

    fixture_team_errors = [
        row["fixture"]
        for row in fixtures
        if row["home_team_id"] not in team_ids
        or row["away_team_id"] not in team_ids
        or row["home_team_id"] == row["away_team_id"]
    ]
    check("fixtures.team_foreign_keys", not fixture_team_errors, fixture_team_errors[:20])

    fact_keys = [(row["element"], row["fixture"]) for row in facts]
    duplicate_fact_keys = _duplicates(fact_keys)
    check(
        "facts.unique_season_element_fixture",
        not duplicate_fact_keys,
        duplicate_fact_keys[:20],
    )
    unknown_fact_players = sorted({row["element"] for row in facts} - player_ids)
    unknown_fact_fixtures = sorted({row["fixture"] for row in facts} - fixture_ids)
    check("facts.player_foreign_keys", not unknown_fact_players, unknown_fact_players[:20])
    check("facts.fixture_foreign_keys", not unknown_fact_fixtures, unknown_fact_fixtures[:20])

    fixture_by_id = {row["fixture"]: row for row in fixtures}
    fact_context_errors: list[dict[str, Any]] = []
    for row in facts:
        fixture = fixture_by_id.get(row["fixture"])
        if fixture is None:
            continue
        derived_team = fixture["home_team_id"] if row["was_home"] else fixture["away_team_id"]
        derived_opponent = fixture["away_team_id"] if row["was_home"] else fixture["home_team_id"]
        if (
            row["team_id_at_fixture"] != derived_team
            or row["opponent_team_id_at_fixture"] != derived_opponent
            or row["gameweek"] != fixture["gameweek"]
            or row["kickoff_time_utc"] != fixture["kickoff_time_utc"]
        ):
            fact_context_errors.append(
                {"element": row["element"], "fixture": row["fixture"]}
            )
    check("facts.fixture_derived_context", not fact_context_errors, fact_context_errors[:20])

    snapshot_keys = [(row["gameweek"], row["element"]) for row in snapshots]
    duplicate_snapshot_keys = _duplicates(snapshot_keys)
    check(
        "snapshots.unique_season_gameweek_element",
        not duplicate_snapshot_keys,
        duplicate_snapshot_keys[:20],
    )
    unknown_snapshot_players = sorted({row["element"] for row in snapshots} - player_ids)
    check(
        "snapshots.player_foreign_keys",
        not unknown_snapshot_players,
        unknown_snapshot_players[:20],
    )
    player_code_by_element = {row["element"]: row["player_code"] for row in players}
    position_by_element = {
        row["element"]: row["end_of_season_position"] for row in players
    }
    snapshot_code_errors = [
        {"gameweek": row["gameweek"], "element": row["element"]}
        for row in snapshots
        if row["element"] in player_code_by_element
        and position_by_element[row["element"]] != "AM"
        and row["player_code"] != player_code_by_element[row["element"]]
    ]
    check(
        "snapshots.player_code_consistency",
        not snapshot_code_errors,
        snapshot_code_errors[:20],
    )
    snapshot_identity_reference_errors = [
        {"gameweek": row["gameweek"], "element": row["element"]}
        for row in snapshots
        if (
            row["deadline_team_id"] is not None
            and (
                row["deadline_team_code"] is None
                or row["deadline_team_name"] is None
                or row["deadline_team_short_name"] is None
            )
        )
        or (
            row["deadline_position_id"] is not None
            and (
                row["deadline_position"] is None
                or row["deadline_position_name"] is None
            )
        )
    ]
    check(
        "snapshots.deadline_identity_reference_integrity",
        not snapshot_identity_reference_errors,
        snapshot_identity_reference_errors[:20],
    )
    unknown_snapshot_teams = sorted(
        {
            row["deadline_team_id"]
            for row in snapshots
            if row["deadline_team_id"] is not None
        }
        - team_ids
    )
    check(
        "snapshots.deadline_team_foreign_keys",
        not unknown_snapshot_teams,
        unknown_snapshot_teams[:20],
    )
    assistant_manager_code_changes = [
        {
            "gameweek": row["gameweek"],
            "element": row["element"],
            "snapshot_player_code": row["player_code"],
            "season_end_player_code": player_code_by_element[row["element"]],
        }
        for row in snapshots
        if row["element"] in player_code_by_element
        and position_by_element[row["element"]] == "AM"
        and row["player_code"] != player_code_by_element[row["element"]]
    ]
    checks.append(
        {
            "name": "snapshots.assistant_manager_code_changes_audit",
            "passed": True,
            "detail": {
                "count": len(assistant_manager_code_changes),
                "examples": assistant_manager_code_changes[:20],
                "note": "AM elements are club-manager slots and may change person code; football-player code consistency remains strict",
            },
        }
    )
    timing_errors: list[dict[str, Any]] = []
    cutoffs_by_gameweek: dict[int, set[tuple[str, str]]] = defaultdict(set)
    for row in snapshots:
        capture = parse_utc(row["capture_time_utc"], "snapshot capture")
        deadline = parse_utc(row["deadline_time_utc"], "snapshot deadline")
        if capture >= deadline:
            timing_errors.append({"gameweek": row["gameweek"], "element": row["element"]})
        cutoffs_by_gameweek[row["gameweek"]].add(
            (row["capture_time_utc"], row["deadline_time_utc"])
        )
    check("snapshots.capture_strictly_before_deadline", not timing_errors, timing_errors[:20])
    multiple_cutoffs = {
        gameweek: sorted(cutoffs)
        for gameweek, cutoffs in cutoffs_by_gameweek.items()
        if len(cutoffs) != 1
    }
    check(
        "snapshots.one_shared_gameweek_cutoff",
        not multiple_cutoffs,
        multiple_cutoffs,
    )
    snapshot_columns = {
        column.name for column in TABLE_SCHEMAS["player_deadline_snapshots"]
    }
    leaked_fixture_fields = sorted(snapshot_columns.intersection(POST_EVENT_FIXTURE_CONTEXT_FIELDS))
    leaked_information_classes = sorted(
        column.name
        for column in TABLE_SCHEMAS["player_deadline_snapshots"]
        if column.information_class in {"post_event_fixture_context", "realised_outcome"}
    )
    check(
        "fixture_context.deadline_allowlist",
        not leaked_fixture_fields and not leaked_information_classes,
        {
            "unexpected_post_event_fields": leaked_fixture_fields,
            "unexpected_post_event_information_classes": leaked_information_classes,
            "policy": FIXTURE_CONTEXT_AVAILABILITY_POLICY,
        },
    )
    source_schema_failures = {
        filename: {
            "unexpected_additions": audit["unexpected_additions"],
            "missing_required_columns": audit["missing_required_columns"],
            "duplicate_columns": audit["duplicate_columns"],
            "known_column_order_matches": audit["known_column_order_matches"],
        }
        for filename, audit in source_schema_audits.items()
        if audit["unexpected_additions"]
        or audit["missing_required_columns"]
        or audit["duplicate_columns"]
        or not audit["known_column_order_matches"]
    }
    check(
        "vaastav.season_source_schema",
        not source_schema_failures,
        {
            "policy": "unexpected additions/order drift fail quality; missing optional columns are reported and remain null",
            "failures": source_schema_failures,
            "files": source_schema_audits,
        },
    )
    forbidden_source_fields = set(
        vaastav_source_schema["forbidden_trusted_output_fields"]
    )
    generated_columns = {
        column.name for columns in TABLE_SCHEMAS.values() for column in columns
    }
    forbidden_output_fields = sorted(forbidden_source_fields & generated_columns)
    check(
        "vaastav.forbidden_fields_excluded",
        not forbidden_output_fields,
        {
            "schema_id": vaastav_source_schema["schema_id"],
            "forbidden_fields_present": forbidden_output_fields,
        },
    )
    check(
        "total_points.cross_source_reconciliation",
        total_points_reconciliation["passed"],
        {
            "status": total_points_reconciliation["status"],
            "eligible_row_count": total_points_reconciliation["eligible_row_count"],
            "compared_row_count": total_points_reconciliation["compared_row_count"],
            "unmatched_row_count": total_points_reconciliation["unmatched_row_count"],
            "coverage_ratio": total_points_reconciliation["coverage_ratio"],
            "minimum_coverage_ratio": total_points_reconciliation[
                "minimum_coverage_ratio"
            ],
            "coverage_passed": total_points_reconciliation["coverage_passed"],
            "mismatching_row_count": total_points_reconciliation[
                "mismatching_row_count"
            ],
            "mismatches": total_points_reconciliation["mismatches"][:20],
            "reasons_for_exclusion_or_unavailability": total_points_reconciliation[
                "reasons_for_exclusion_or_unavailability"
            ],
        },
    )

    actual_gameweeks = {row["gameweek"] for row in gameweeks}
    check(
        "gameweeks.expected_rows",
        actual_gameweeks == expected_gw_set and len(gameweeks) == len(expected_gameweeks),
        {
            "expected": expected_gameweeks,
            "missing": sorted(expected_gw_set - actual_gameweeks),
            "unexpected": sorted(actual_gameweeks - expected_gw_set),
        },
    )
    fixture_gameweeks = {row["gameweek"] for row in fixtures if row["gameweek"] is not None}
    missing_snapshots = [
        row["gameweek"] for row in gameweeks if not row["valid_predeadline_snapshot"]
    ]

    actual_counts = {
        "players": len(players),
        "teams": len(teams),
        "fixtures": len(fixtures),
        "player_fixture_facts": len(facts),
        "distinct_fact_elements": len({row["element"] for row in facts}),
        "fixture_gameweeks": len(fixture_gameweeks),
        "gameweeks": len(gameweeks),
        "player_deadline_snapshots": len(snapshots),
        "gameweeks_with_valid_snapshot": len(gameweeks) - len(missing_snapshots),
    }
    expectation_results: dict[str, dict[str, Any]] = {}
    for name, expected in expected_counts.items():
        actual = actual_counts.get(name)
        matches = actual == expected
        expectation_results[name] = {"expected": expected, "actual": actual, "matches": matches}
        check(f"expectation.{name}", matches, expectation_results[name])

    null_counts = {
        table: {
            column.name: sum(row.get(column.name) is None for row in tables[table])
            for column in columns
        }
        for table, columns in TABLE_SCHEMAS.items()
    }
    duplicate_counts = {
        "player_fixture_facts": len(fact_keys) - len(set(fact_keys)),
        "player_deadline_snapshots": len(snapshot_keys) - len(set(snapshot_keys)),
    }

    return {
        "schema_version": 3,
        "season": season,
        "passed": not failures,
        "failures": failures,
        "checks": checks,
        "expected_gameweeks": expected_gameweeks,
        "fixture_gameweeks": sorted(fixture_gameweeks),
        "missing_gameweeks": sorted(expected_gw_set - actual_gameweeks),
        "missing_snapshot_gameweeks": missing_snapshots,
        "source_row_counts": source_row_counts,
        "processed_row_counts": {table: len(rows) for table, rows in tables.items()},
        "audit_counts": actual_counts,
        "expectations": expectation_results,
        "null_counts": null_counts,
        "duplicate_counts": duplicate_counts,
        "canonical_schemas": schemas_as_dict(),
        "fixture_context_availability_policy": FIXTURE_CONTEXT_AVAILABILITY_POLICY,
        "total_points_reconciliation": total_points_reconciliation,
        "source_schema_changes": source_schema_audits,
        "leakage_contract": {
            "realised_outcomes": "player_fixture_facts statistics and fixture scores; unavailable as same-gameweek model inputs",
            "pre_deadline_state": "player_deadline_snapshots selected strictly before the shared gameweek deadline",
            "deadline_fixture_context": "only season, gameweek and deadline are asserted deadline-safe",
            "post_event_fixture_context": "final fixture identity, assignment, teams, kickoff and difficulty remain outcome-side context",
            "unverified_timing": "quarantined_source_metadata; never a trusted feature source",
            "vaastav_xP": "excluded from every output table",
        },
        "known_identity_exceptions": {
            "assistant_manager_elements": "2024/25 AM elements represent club-manager slots; person codes can change within an element",
            "assistant_manager_code_change_rows": len(assistant_manager_code_changes),
        },
    }


def reconcile_total_points(
    facts: list[dict[str, Any]],
    comparison_snapshots: dict[int, tuple[dict[str, Any], str, str]],
    policy: dict[str, Any],
    provenance: dict[str, Any],
    *,
    artifact_created_at_utc: str,
    source_identity: dict[str, Any],
    source_identity_sha256: str,
    build_identity: dict[str, Any],
    build_identity_sha256: str,
) -> dict[str, Any]:
    """Compare canonical fixture-point sums with configured settled event points.

    Coverage is ``compared_row_count / eligible_row_count``. An eligible row is
    one unique ``(season, gameweek, element)`` total derived from canonical
    player-fixture facts. A row is compared only when the configured independent
    snapshot contains an integer ``event_points`` value and marks the event both
    finished and data-checked.
    """

    canonical: dict[tuple[int, int], int] = defaultdict(int)
    for row in facts:
        canonical[(row["gameweek"], row["element"])] += row["total_points"]

    mode = policy["mode"]
    minimum_coverage_ratio = policy["minimum_coverage_ratio"]
    compared = 0
    matching = 0
    mismatches: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    by_gameweek: dict[str, dict[str, int]] = {}
    for (gameweek, element), canonical_points in sorted(canonical.items()):
        counters = by_gameweek.setdefault(
            str(gameweek), {"eligible": 0, "compared": 0, "matching": 0, "mismatching": 0, "unmatched": 0}
        )
        counters["eligible"] += 1
        comparison = comparison_snapshots.get(gameweek)
        if comparison is None:
            counters["unmatched"] += 1
            unavailable.append(
                {"gameweek": gameweek, "element": element, "reason": "no settled comparison snapshot"}
            )
            continue
        payload, source_path, source_sha256 = comparison
        events = payload.get("events")
        event = next(
            (
                value
                for value in events or []
                if isinstance(value, dict) and value.get("id") == gameweek
            ),
            None,
        )
        if (
            event is None
            or event.get("finished") is not True
            or event.get("data_checked") is not True
        ):
            counters["unmatched"] += 1
            unavailable.append(
                {
                    "gameweek": gameweek,
                    "element": element,
                    "reason": "comparison snapshot does not mark the event finished and data_checked",
                    "source_path": source_path,
                }
            )
            continue
        elements = payload.get("elements")
        source_element = next(
            (
                value
                for value in elements or []
                if isinstance(value, dict) and value.get("id") == element
            ),
            None,
        )
        comparison_points = (
            source_element.get("event_points") if source_element is not None else None
        )
        if not isinstance(comparison_points, int) or isinstance(comparison_points, bool):
            counters["unmatched"] += 1
            unavailable.append(
                {
                    "gameweek": gameweek,
                    "element": element,
                    "reason": "comparison event_points unavailable",
                    "source_path": source_path,
                }
            )
            continue
        compared += 1
        counters["compared"] += 1
        if comparison_points == canonical_points:
            matching += 1
            counters["matching"] += 1
        else:
            counters["mismatching"] += 1
            mismatches.append(
                {
                    "season": facts[0]["season"] if facts else None,
                    "gameweek": gameweek,
                    "element": element,
                    "canonical_vaastav_total_points": canonical_points,
                    "comparison_fplcache_event_points": comparison_points,
                    "comparison_source_path": source_path,
                    "comparison_source_sha256": source_sha256,
                }
            )

    eligible = len(canonical)
    unmatched = eligible - compared
    coverage_ratio = compared / eligible if eligible else None
    coverage_passed = (
        coverage_ratio is not None and coverage_ratio >= minimum_coverage_ratio
    )
    mismatch_passed = not mismatches
    unavailable_reasons = Counter(item["reason"] for item in unavailable)
    if mode == "optional" and (eligible == 0 or compared == 0):
        status = "skipped_optional"
        passed = True
        coverage_passed = None
    elif eligible == 0 or compared == 0:
        status = "failed_unavailable"
        passed = False
    elif not mismatch_passed:
        status = "failed_mismatch"
        passed = False
    elif not coverage_passed:
        status = "failed_coverage"
        passed = False
    elif unmatched:
        status = "passed_partial"
        passed = True
    else:
        status = "passed"
        passed = True

    result = {
        "artifact_schema_version": 1,
        "artifact_created_at_utc": artifact_created_at_utc,
        "season": provenance["season"],
        "status": status,
        "policy": policy,
        "policy_version": policy["policy_version"],
        "configured_mode": mode,
        "minimum_coverage_ratio": minimum_coverage_ratio,
        "coverage_definition": (
            "compared_row_count / eligible_row_count; eligible rows are unique "
            "canonical (season, gameweek, element) totals, and compared rows have "
            "settled integer comparison event_points"
        ),
        "eligible_row_count": eligible,
        "compared_row_count": compared,
        "unmatched_row_count": unmatched,
        "coverage_ratio": coverage_ratio,
        "coverage_passed": coverage_passed,
        "matching_row_count": matching,
        "mismatching_row_count": len(mismatches),
        "mismatch_check_passed": mismatch_passed,
        # Compatibility aliases retained for readers of the first hardened slice.
        "expected_records": eligible,
        "compared_records": compared,
        "matching_records": matching,
        "mismatching_records": len(mismatches),
        "unavailable_records": len(unavailable),
        "mismatches": mismatches,
        "unavailable": unavailable,
        "reasons_for_exclusion_or_unavailability": {
            reason: count for reason, count in sorted(unavailable_reasons.items())
        },
        "by_gameweek": by_gameweek,
        "provenance": provenance,
        "source_identity": source_identity,
        "source_identity_sha256": source_identity_sha256,
        "build_identity": build_identity,
        "build_identity_sha256": build_identity_sha256,
        "passed": passed,
    }
    result["artifact_sha256"] = sha256_bytes(canonical_json_bytes(result))
    return result


def raise_for_quality_failures(report: dict[str, Any]) -> None:
    if not report["passed"]:
        summary = "; ".join(report["failures"][:5])
        raise FPLValidationError(f"historical data-quality checks failed: {summary}")


def _duplicates(values: list[Any]) -> list[Any]:
    return [value for value, count in Counter(values).items() if count > 1]


def _type_errors(rows: list[dict[str, Any]], schema: list[Any]) -> list[str]:
    errors: list[str] = []
    for index, row in enumerate(rows):
        for column in schema:
            value = row.get(column.name)
            if value is None:
                if not column.nullable:
                    errors.append(f"row {index} {column.name} is null")
                continue
            if column.data_type == "integer" and (
                not isinstance(value, int) or isinstance(value, bool)
            ):
                errors.append(f"row {index} {column.name} is not integer")
            elif column.data_type == "boolean" and not isinstance(value, bool):
                errors.append(f"row {index} {column.name} is not boolean")
            elif column.data_type in (
                "string",
                "decimal_string",
                "utc_timestamp",
                "cross_season_identity",
            ) and not isinstance(value, str):
                errors.append(f"row {index} {column.name} is not string")
            if column.data_type == "utc_timestamp" and isinstance(value, str):
                try:
                    parsed = parse_utc(value, f"row {index} {column.name}")
                    if parsed.utcoffset() is None:
                        errors.append(f"row {index} {column.name} is not UTC")
                except FPLValidationError as exc:
                    errors.append(str(exc))
            if len(errors) >= 100:
                return errors
    return errors
