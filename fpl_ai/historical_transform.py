"""Transform pinned historical sources into leakage-classified canonical rows."""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_schema import validate_vaastav_source_schema

# FPL introduced Assistant Manager chip elements in 2024/25. They remain
# identifiable source observations (position AM), while the manager-only stat
# columns are deliberately excluded from canonical facts.
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD", 5: "AM"}


def read_source_csv(
    value: bytes,
    filename: str,
    source_schema: dict[str, object],
    *,
    include_schema_audit: bool = False,
) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate and normalize one Vaastav CSV through its selected adapter."""

    schema = validate_vaastav_source_schema(source_schema)
    files = schema["files"]
    if not isinstance(files, dict) or filename not in files:
        raise FPLValidationError(
            f"Vaastav source schema {schema['schema_id']!r} has no contract for {filename}"
        )
    file_schema = files[filename]
    if not isinstance(file_schema, dict):
        raise FPLValidationError(f"invalid Vaastav source contract for {filename}")
    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FPLValidationError(f"{filename} is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    actual = reader.fieldnames or []
    known = file_schema["known_column_order"]
    required = file_schema["required_columns"]
    optional = file_schema["optional_columns"]
    ignored = file_schema["ignored_columns"]
    quarantined = file_schema["quarantined_columns"]
    forbidden = file_schema["forbidden_columns"]
    if not all(
        isinstance(value, list)
        for value in (known, required, optional, ignored, quarantined, forbidden)
    ):
        raise FPLValidationError(f"invalid Vaastav source contract for {filename}")
    duplicate_columns = sorted(
        {column for column in actual if actual.count(column) > 1}
    )
    additions = sorted(set(actual) - set(known))
    missing_required = sorted(set(required) - set(actual))
    required_present = sorted(set(required) & set(actual))
    optional_present = sorted(set(optional) & set(actual))
    missing_optional = sorted(set(optional) - set(actual))
    expected_present_order = [column for column in known if column in actual]
    actual_known_order = [column for column in actual if column in known]
    audit = {
        "schema_id": schema["schema_id"],
        "schema_version": schema["schema_version"],
        "filename": filename,
        "unexpected_columns_policy": schema["unexpected_columns_policy"],
        "unexpected_additions": additions,
        "unexpected_columns": additions,
        "required_columns_present": required_present,
        "missing_required_columns": missing_required,
        "required_columns_missing": missing_required,
        "optional_columns_present": optional_present,
        "missing_optional_columns": missing_optional,
        "optional_columns_absent": missing_optional,
        "ignored_columns_present": sorted(set(ignored) & set(actual)),
        "quarantined_columns_present": sorted(set(quarantined) & set(actual)),
        "forbidden_columns_encountered": sorted(set(forbidden) & set(actual)),
        "type_validated_columns": sorted(
            set(file_schema["type_expectations"]) & set(actual)
        ),
        "duplicate_columns": duplicate_columns,
        "known_column_order_matches": actual_known_order == expected_present_order,
        "source_row_count": 0,
    }
    if missing_required or duplicate_columns:
        raise FPLValidationError(
            f"Vaastav schema {schema['schema_id']} rejected {filename}; "
            f"missing required columns={missing_required}, duplicate columns={duplicate_columns}"
        )
    raw_rows = list(reader)
    audit["source_row_count"] = len(raw_rows)
    rows = [
        _normalize_source_row(
            raw,
            row_number,
            filename,
            schema,
            file_schema,
        )
        for row_number, raw in enumerate(raw_rows, 2)
    ]
    if include_schema_audit:
        return rows, audit
    if additions and schema["unexpected_columns_policy"] == "quality_failure":
        raise FPLValidationError(
            f"Vaastav schema {schema['schema_id']} detected unexpected columns in "
            f"{filename}: {additions} (policy: quality_failure)"
        )
    return rows


def _normalize_source_row(
    raw: dict[str, str],
    row_number: int,
    filename: str,
    source_schema: dict[str, object],
    file_schema: dict[str, object],
) -> dict[str, Any]:
    adapter_id = source_schema.get("adapter_id")
    if adapter_id not in {"declarative-normalization-v1", "declarative-normalization-v2"}:
        raise FPLValidationError(
            f"Vaastav source schema {source_schema.get('schema_id')!r} has unsupported "
            f"adapter_id {adapter_id!r}"
        )
    expectations = file_schema["type_expectations"]
    if not isinstance(expectations, dict):
        raise FPLValidationError(f"invalid type expectations for {filename}")
    parsed: dict[str, Any] = {}
    for field, expectation in expectations.items():
        if field not in raw:
            continue
        parsed[field] = _parse_source_value(
            raw[field],
            expectation,
            source_schema,
            filename,
            row_number,
            field,
        )

    trusted: dict[str, Any] = {}
    trusted_mappings = file_schema["source_to_canonical_mappings"]
    quarantine_mappings = file_schema["quarantined_source_to_canonical_mappings"]
    if not isinstance(trusted_mappings, dict) or not isinstance(
        quarantine_mappings, dict
    ):
        raise FPLValidationError(f"invalid source mappings for {filename}")
    for source_field, target in trusted_mappings.items():
        trusted[target.split(".", 1)[1]] = parsed.get(source_field)
    separated_quarantine: dict[str, Any] = {}
    for source_field, target in quarantine_mappings.items():
        separated_quarantine[target.split(".", 1)[1]] = parsed.get(source_field)
    return {
        "trusted": trusted,
        "quarantined": separated_quarantine,
        "source_row_number": row_number,
    }


def _parse_source_value(
    value: str | None,
    expectation: object,
    source_schema: dict[str, object],
    filename: str,
    row_number: int,
    column: str,
) -> Any:
    if not isinstance(expectation, dict):
        raise FPLValidationError(f"invalid type expectation for {filename}.{column}")
    data_type = expectation.get("type")
    nullable = expectation.get("nullable") is True
    missing = value is None or value.strip() in ("", "None", "null")
    if missing:
        if nullable:
            return None
        _source_type_failure(
            source_schema, filename, row_number, column, value, expectation
        )
    try:
        if data_type == "integer":
            if value is None or not re.fullmatch(r"[+-]?\d+", value.strip()):
                raise ValueError
            parsed: Any = int(value)
        elif data_type == "decimal":
            if value is None:
                raise InvalidOperation
            parsed_decimal = Decimal(value)
            if not parsed_decimal.is_finite():
                raise InvalidOperation
            parsed = value
        elif data_type == "boolean":
            if value == "True":
                parsed = True
            elif value == "False":
                parsed = False
            else:
                raise ValueError
        elif data_type == "string":
            if value is None:
                raise ValueError
            parsed = value
        elif data_type == "utc_timestamp":
            if value is None:
                raise ValueError
            raw_timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if (
                raw_timestamp.tzinfo is None
                or raw_timestamp.utcoffset() is None
                or raw_timestamp.utcoffset().total_seconds() != 0
            ):
                raise ValueError
            parsed = utc_string(raw_timestamp)
        else:
            raise ValueError
    except (InvalidOperation, ValueError):
        _source_type_failure(
            source_schema, filename, row_number, column, value, expectation
        )
    # Versioned, schema-scoped aliases standardize source labels only.
    if data_type == "string" and source_schema["adapter_id"] == "declarative-normalization-v2":
        parsed = expectation.get("value_aliases", {}).get(parsed, parsed)
    allowed_values = expectation.get("allowed_values")
    if allowed_values is not None and parsed not in allowed_values:
        _source_type_failure(
            source_schema, filename, row_number, column, value, expectation
        )
    return parsed


def _source_type_failure(
    source_schema: dict[str, object],
    filename: str,
    row_number: int,
    column: str,
    value: str | None,
    expectation: object,
) -> None:
    seasons = source_schema.get("applicable_seasons")
    season = seasons[0] if isinstance(seasons, list) and len(seasons) == 1 else seasons
    raise FPLValidationError(
        "historical source type validation failed: "
        f"season={season!r}, schema_id={source_schema.get('schema_id')!r}, "
        f"source_artifact={filename!r}, row={row_number}, column={column!r}, "
        f"rejected_value={value!r}, expected={expectation!r}"
    )


def _trusted_values(source: dict[str, Any], filename: str) -> dict[str, Any]:
    trusted = source.get("trusted")
    if not isinstance(trusted, dict):
        raise FPLValidationError(
            f"{filename} transformation requires a normalized source row"
        )
    return trusted


def transform_players(
    season: str, source_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for normalized in source_rows:
        source = _trusted_values(normalized, "players_raw.csv")
        element = source["element"]
        if element in seen:
            raise FPLValidationError(f"duplicate player element: {element}")
        seen.add(element)
        position_id = source["end_of_season_position_id"]
        if position_id not in POSITIONS:
            raise FPLValidationError(f"unknown position id {position_id} for element {element}")
        rows.append(
            {
                "season": season,
                "element": element,
                "player_code": source["player_code"],
                "first_name": source["first_name"],
                "second_name": source["second_name"],
                "web_name": source["web_name"],
                "end_of_season_position_id": position_id,
                "end_of_season_position": POSITIONS[position_id],
                "end_of_season_team_id": source["end_of_season_team_id"],
            }
        )
    return rows


def transform_teams(
    season: str, source_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for normalized in source_rows:
        source = _trusted_values(normalized, "teams.csv")
        team_id = source["team_id"]
        if team_id in seen:
            raise FPLValidationError(f"duplicate team id: {team_id}")
        seen.add(team_id)
        rows.append(
            {
                "season": season,
                "team_id": team_id,
                "team_code": source["team_code"],
                "name": source["name"],
                "short_name": source["short_name"],
            }
        )
    return rows


def transform_fixtures(
    season: str, source_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for normalized in source_rows:
        source = _trusted_values(normalized, "fixtures.csv")
        fixture = source["fixture"]
        if fixture in seen:
            raise FPLValidationError(f"duplicate fixture id: {fixture}")
        seen.add(fixture)
        kickoff = source["kickoff_time_utc"]
        rows.append(
            {
                "season": season,
                "fixture": fixture,
                "fixture_code": source["fixture_code"],
                "gameweek": source["gameweek"],
                "home_team_id": source["home_team_id"],
                "away_team_id": source["away_team_id"],
                "kickoff_time_utc": kickoff,
                "home_difficulty": source["home_difficulty"],
                "away_difficulty": source["away_difficulty"],
                "home_score": source["home_score"],
                "away_score": source["away_score"],
                "finished": source["finished"],
            }
        )
    return rows


def validate_fixture_kickoff_reconciliation(policy: Any) -> None:
    """Require exact, counted post-event discrepancies rather than a blanket fallback."""

    if not isinstance(policy, list) or not policy:
        raise FPLValidationError("fixture kickoff reconciliation must be a non-empty list")
    seen = set()
    for entry in policy:
        required = {"fixture", "gameweek", "source_kickoff", "fixture_kickoff", "expected_rows", "reason"}
        if not isinstance(entry, dict) or set(entry) != required:
            raise FPLValidationError("malformed fixture kickoff reconciliation entry")
        for key in ("fixture", "gameweek", "expected_rows"):
            if type(entry[key]) is not int or entry[key] < 1:
                raise FPLValidationError(f"fixture kickoff reconciliation {key} must be positive integer")
        if entry["fixture"] in seen:
            raise FPLValidationError("duplicate fixture kickoff reconciliation")
        seen.add(entry["fixture"])
        for key in ("source_kickoff", "fixture_kickoff"):
            value = entry[key]
            if not isinstance(value, str) or utc_string(parse_utc(value, key)) != value:
                raise FPLValidationError("fixture kickoff reconciliation requires canonical UTC timestamps")
        if entry["source_kickoff"] == entry["fixture_kickoff"]:
            raise FPLValidationError("fixture kickoff reconciliation must describe a difference")
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise FPLValidationError("fixture kickoff reconciliation requires a reason")


def reconcile_fixture_kickoffs(
    source_rows: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
    policy: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize only declared post-event kickoff discrepancies; keep raw bytes intact."""

    validate_fixture_kickoff_reconciliation(policy)
    by_fixture = {r["fixture"]: r for r in fixtures}
    rules = {r["fixture"]: r for r in policy}
    counts = {key: 0 for key in rules}
    normalized = []
    for row in source_rows:
        source = row["trusted"]
        rule = rules.get(source["fixture"])
        if rule is None:
            normalized.append(row)
            continue
        fixture = by_fixture.get(source["fixture"])
        if (fixture is None or source["gameweek"] != rule["gameweek"]
                or fixture["gameweek"] != rule["gameweek"]
                or source["kickoff_time_utc"] != rule["source_kickoff"]
                or fixture["kickoff_time_utc"] != rule["fixture_kickoff"]):
            raise FPLValidationError(f"fixture kickoff reconciliation no longer matches: {rule['fixture']}")
        counts[rule["fixture"]] += 1
        normalized.append({**row, "trusted": {**source, "kickoff_time_utc": rule["fixture_kickoff"]}})
    for rule in policy:
        if counts[rule["fixture"]] != rule["expected_rows"]:
            raise FPLValidationError(f"fixture kickoff reconciliation row count mismatch: {rule['fixture']}")
    return normalized, [{**r, "normalized_rows": counts[r["fixture"]]} for r in policy]


def transform_facts(
    season: str,
    source_rows: list[dict[str, Any]],
    players: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    player_by_element = {row["element"]: row for row in players}
    fixture_by_id = {row["fixture"]: row for row in fixtures}
    rows: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for normalized in source_rows:
        source = _trusted_values(normalized, "merged_gw.csv")
        quarantine_source = normalized.get("quarantined")
        if not isinstance(quarantine_source, dict):
            raise FPLValidationError(
                "merged_gw.csv transformation requires separated quarantine values"
            )
        element = source["element"]
        fixture_id = source["fixture"]
        key = (element, fixture_id)
        if key in seen:
            raise FPLValidationError(
                f"duplicate player-fixture key: season={season}, element={element}, fixture={fixture_id}"
            )
        seen.add(key)
        if element not in player_by_element:
            raise FPLValidationError(f"fact references unknown element {element}")
        if fixture_id not in fixture_by_id:
            raise FPLValidationError(f"fact references unknown fixture {fixture_id}")
        player = player_by_element[element]
        fixture = fixture_by_id[fixture_id]
        was_home = source["was_home"]
        team_id = fixture["home_team_id"] if was_home else fixture["away_team_id"]
        opponent_id = fixture["away_team_id"] if was_home else fixture["home_team_id"]
        source_opponent = source["opponent_team_id_at_fixture"]
        if source_opponent != opponent_id:
            raise FPLValidationError(
                f"fact {key} opponent {source_opponent} conflicts with fixture-derived {opponent_id}"
            )
        gameweek = source["gameweek"]
        if fixture["gameweek"] != gameweek:
            raise FPLValidationError(
                f"fact {key} gameweek {gameweek} conflicts with fixture {fixture['gameweek']}"
            )
        kickoff = source["kickoff_time_utc"]
        if fixture["kickoff_time_utc"] != kickoff:
            raise FPLValidationError(f"fact {key} kickoff conflicts with fixture")
        position = source["position_at_fixture"]
        if position not in POSITIONS.values():
            raise FPLValidationError(f"fact {key} has unknown position {position!r}")
        row: dict[str, Any] = {
            "season": season,
            "element": element,
            "player_code": player["player_code"],
            "gameweek": gameweek,
            "fixture": fixture_id,
            "team_id_at_fixture": team_id,
            "opponent_team_id_at_fixture": opponent_id,
            "was_home": was_home,
            "kickoff_time_utc": kickoff,
            "position_at_fixture": position,
        }
        for field in (
            "minutes", "total_points", "goals_scored", "assists", "clean_sheets",
            "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
            "saves", "yellow_cards", "red_cards", "bonus", "bps",
        ):
            row[field] = source[field]
        row["starts"] = source.get("starts")
        for field in (
            "influence", "creativity", "threat", "ict_index", "expected_goals",
            "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
        ):
            row[field] = source.get(field)
        rows.append(row)
        quarantined.append(
            {
                "season": season,
                "element": element,
                "gameweek": gameweek,
                "fixture": fixture_id,
                "selected": quarantine_source.get("selected"),
                "value": quarantine_source.get("value"),
                "transfers_balance": quarantine_source.get("transfers_balance"),
                "transfers_in": quarantine_source.get("transfers_in"),
                "transfers_out": quarantine_source.get("transfers_out"),
                "modified": quarantine_source.get("modified"),
            }
        )
    return rows, quarantined


def transform_snapshot_elements(
    season: str,
    gameweek: int,
    payload: dict[str, Any],
    capture_time: datetime,
    deadline: datetime,
    source_path: str,
    source_sha256: str,
) -> list[dict[str, Any]]:
    elements = payload.get("elements")
    if not isinstance(elements, list):
        raise FPLValidationError(f"snapshot {source_path} elements must be an array")
    teams = payload.get("teams")
    positions = payload.get("element_types")
    if teams is not None and not isinstance(teams, list):
        raise FPLValidationError(f"snapshot {source_path} teams must be an array")
    if positions is not None and not isinstance(positions, list):
        raise FPLValidationError(f"snapshot {source_path} element_types must be an array")
    team_by_id = {
        team.get("id"): team
        for team in teams or []
        if isinstance(team, dict) and isinstance(team.get("id"), int)
    }
    position_by_id = {
        position.get("id"): position
        for position in positions or []
        if isinstance(position, dict) and isinstance(position.get("id"), int)
    }
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            raise FPLValidationError(f"snapshot {source_path} element {index} is not an object")
        for field in ("id", "code"):
            if field not in element:
                raise FPLValidationError(f"snapshot {source_path} element {index} missing {field}")
        element_id = json_int(element["id"], f"snapshot {source_path} element id")
        if element_id in seen:
            raise FPLValidationError(f"snapshot {source_path} has duplicate element {element_id}")
        seen.add(element_id)
        team_id = json_optional_int(
            element.get("team"), f"snapshot element {element_id} team"
        )
        position_id = json_optional_int(
            element.get("element_type"), f"snapshot element {element_id} element_type"
        )
        team = team_by_id.get(team_id)
        position = position_by_id.get(position_id)
        rows.append(
            {
                "season": season,
                "gameweek": gameweek,
                "element": element_id,
                "player_code": json_int(element["code"], f"snapshot element {element_id} code"),
                "deadline_team_id": team_id,
                "deadline_team_code": (
                    json_optional_int(team.get("code"), f"snapshot team {team_id} code")
                    if team is not None
                    else None
                ),
                "deadline_team_name": team.get("name") if team is not None else None,
                "deadline_team_short_name": (
                    team.get("short_name") if team is not None else None
                ),
                "deadline_position_id": position_id,
                "deadline_position": (
                    position.get("singular_name_short") if position is not None else None
                ),
                "deadline_position_name": (
                    position.get("singular_name") if position is not None else None
                ),
                "price": json_optional_int(element.get("now_cost"), f"snapshot element {element_id} now_cost"),
                "selected_by_percent": json_optional_decimal(
                    element.get("selected_by_percent"), f"snapshot element {element_id} ownership"
                ),
                "transfers_in_event": json_optional_int(
                    element.get("transfers_in_event"), f"snapshot element {element_id} transfers in"
                ),
                "transfers_out_event": json_optional_int(
                    element.get("transfers_out_event"), f"snapshot element {element_id} transfers out"
                ),
                "status": element.get("status"),
                "chance_of_playing_this_round": json_optional_int(
                    element.get("chance_of_playing_this_round"), f"snapshot element {element_id} chance this"
                ),
                "chance_of_playing_next_round": json_optional_int(
                    element.get("chance_of_playing_next_round"), f"snapshot element {element_id} chance next"
                ),
                "news": element.get("news"),
                "news_added_utc": json_optional_utc(
                    element.get("news_added"), f"snapshot element {element_id} news_added"
                ),
                "expected_points_next_gameweek": json_optional_decimal(
                    element.get("ep_next"), f"snapshot element {element_id} ep_next"
                ),
                "corners_and_indirect_freekicks_order": json_optional_int(
                    element.get("corners_and_indirect_freekicks_order"),
                    f"snapshot element {element_id} corners order",
                ),
                "direct_freekicks_order": json_optional_int(
                    element.get("direct_freekicks_order"),
                    f"snapshot element {element_id} free kicks order",
                ),
                "penalties_order": json_optional_int(
                    element.get("penalties_order"), f"snapshot element {element_id} penalties order"
                ),
                "capture_time_utc": utc_string(capture_time),
                "deadline_time_utc": utc_string(deadline),
                "source_path": source_path,
                "source_sha256": source_sha256,
            }
        )
    return rows


def required_int(value: str, label: str) -> int:
    parsed = optional_int(value, label)
    if parsed is None:
        raise FPLValidationError(f"{label} is required")
    return parsed


def optional_int(value: str | None, label: str) -> int | None:
    if value is None or value.strip() in ("", "None", "null"):
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise FPLValidationError(f"{label} must be an integer: {value!r}") from exc


def required_bool(value: str, label: str) -> bool:
    parsed = optional_bool(value, label)
    if parsed is None:
        raise FPLValidationError(f"{label} is required")
    return parsed


def optional_bool(value: str | None, label: str) -> bool | None:
    if value is None or value.strip() in ("", "None", "null"):
        return None
    if value == "True":
        return True
    if value == "False":
        return False
    raise FPLValidationError(f"{label} must be True or False: {value!r}")


def optional_decimal(value: str | None, label: str) -> str | None:
    if value is None or value.strip() in ("", "None", "null"):
        return None
    try:
        Decimal(value)
    except InvalidOperation as exc:
        raise FPLValidationError(f"{label} must be decimal-like: {value!r}") from exc
    return value


def required_utc(value: str, label: str) -> str:
    parsed = optional_utc(value, label)
    if parsed is None:
        raise FPLValidationError(f"{label} is required")
    return parsed


def optional_utc(value: str | None, label: str) -> str | None:
    if value is None or value.strip() in ("", "None", "null"):
        return None
    return utc_string(parse_utc(value, label))


def parse_utc(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FPLValidationError(f"{label} is not an ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise FPLValidationError(f"{label} has no timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def utc_string(value: datetime) -> str:
    if value.tzinfo is None:
        raise FPLValidationError("timestamp has no timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def json_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise FPLValidationError(f"{label} must be an integer: {value!r}")
    return value


def json_optional_int(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return json_int(value, label)


def json_optional_decimal(value: Any, label: str) -> str | None:
    if value is None or value == "":
        return None
    return optional_decimal(str(value), label)


def json_optional_utc(value: Any, label: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise FPLValidationError(f"{label} must be a timestamp string")
    return optional_utc(value, label)
