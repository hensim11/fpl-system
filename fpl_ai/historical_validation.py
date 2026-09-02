"""Cross-table data-quality contract for canonical historical data."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_schema import TABLE_SCHEMAS, schemas_as_dict
from fpl_ai.historical_transform import parse_utc


def build_quality_report(
    season: str,
    tables: dict[str, list[dict[str, Any]]],
    expected_gameweeks: list[int],
    expected_counts: dict[str, int],
    source_row_counts: dict[str, int],
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
            row["team_id"] != derived_team
            or row["opponent_team_id"] != derived_opponent
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
    position_by_element = {row["element"]: row["position"] for row in players}
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
        "schema_version": 1,
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
        "source_schema_changes": {
            "unexpected_additions": {},
            "unexpected_removals": {},
        },
        "leakage_contract": {
            "realised_outcomes": "player_fixture_facts statistics and fixture scores; unavailable as same-gameweek model inputs",
            "pre_deadline_state": "player_deadline_snapshots selected strictly before the shared gameweek deadline",
            "fixture_context": "fixture identity, teams, gameweek, kickoff and difficulty",
            "unverified_timing": "quarantined_source_metadata; never a trusted feature source",
            "vaastav_xP": "excluded from every output table",
        },
        "known_identity_exceptions": {
            "assistant_manager_elements": "2024/25 AM elements represent club-manager slots; person codes can change within an element",
            "assistant_manager_code_change_rows": len(assistant_manager_code_changes),
        },
    }


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
