"""Transform pinned historical sources into leakage-classified canonical rows."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_schema import VAASTAV_SOURCE_COLUMNS

# FPL introduced Assistant Manager chip elements in 2024/25. They remain
# identifiable source observations (position AM), while the manager-only stat
# columns are deliberately excluded from canonical facts.
POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD", 5: "AM"}


def read_source_csv(value: bytes, filename: str) -> list[dict[str, str]]:
    try:
        text = value.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FPLValidationError(f"{filename} is not valid UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    actual = reader.fieldnames or []
    expected = VAASTAV_SOURCE_COLUMNS[filename]
    additions = sorted(set(actual) - set(expected))
    removals = sorted(set(expected) - set(actual))
    if additions or removals or actual != expected:
        raise FPLValidationError(
            f"unexpected schema for {filename}; additions={additions}, removals={removals}"
        )
    return list(reader)


def transform_players(
    season: str, source_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, source in enumerate(source_rows, 2):
        element = required_int(source["id"], f"players_raw.csv row {index} id")
        if element in seen:
            raise FPLValidationError(f"duplicate player element: {element}")
        seen.add(element)
        position_id = required_int(
            source["element_type"], f"players_raw.csv row {index} element_type"
        )
        if position_id not in POSITIONS:
            raise FPLValidationError(f"unknown position id {position_id} for element {element}")
        rows.append(
            {
                "season": season,
                "element": element,
                "player_code": required_int(source["code"], f"element {element} code"),
                "first_name": source["first_name"],
                "second_name": source["second_name"],
                "web_name": source["web_name"],
                "end_of_season_position_id": position_id,
                "end_of_season_position": POSITIONS[position_id],
                "end_of_season_team_id": optional_int(source["team"], f"element {element} team"),
            }
        )
    return rows


def transform_teams(
    season: str, source_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, source in enumerate(source_rows, 2):
        team_id = required_int(source["id"], f"teams.csv row {index} id")
        if team_id in seen:
            raise FPLValidationError(f"duplicate team id: {team_id}")
        seen.add(team_id)
        rows.append(
            {
                "season": season,
                "team_id": team_id,
                "team_code": required_int(source["code"], f"team {team_id} code"),
                "name": source["name"],
                "short_name": source["short_name"],
            }
        )
    return rows


def transform_fixtures(
    season: str, source_rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for index, source in enumerate(source_rows, 2):
        fixture = required_int(source["id"], f"fixtures.csv row {index} id")
        if fixture in seen:
            raise FPLValidationError(f"duplicate fixture id: {fixture}")
        seen.add(fixture)
        kickoff = optional_utc(source["kickoff_time"], f"fixture {fixture} kickoff_time")
        rows.append(
            {
                "season": season,
                "fixture": fixture,
                "fixture_code": optional_int(source["code"], f"fixture {fixture} code"),
                "gameweek": optional_int(source["event"], f"fixture {fixture} event"),
                "home_team_id": required_int(source["team_h"], f"fixture {fixture} team_h"),
                "away_team_id": required_int(source["team_a"], f"fixture {fixture} team_a"),
                "kickoff_time_utc": kickoff,
                "home_difficulty": optional_int(
                    source["team_h_difficulty"], f"fixture {fixture} team_h_difficulty"
                ),
                "away_difficulty": optional_int(
                    source["team_a_difficulty"], f"fixture {fixture} team_a_difficulty"
                ),
                "home_score": optional_int(source["team_h_score"], f"fixture {fixture} home score"),
                "away_score": optional_int(source["team_a_score"], f"fixture {fixture} away score"),
                "finished": required_bool(source["finished"], f"fixture {fixture} finished"),
            }
        )
    return rows


def transform_facts(
    season: str,
    source_rows: list[dict[str, str]],
    players: list[dict[str, Any]],
    fixtures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    player_by_element = {row["element"]: row for row in players}
    fixture_by_id = {row["fixture"]: row for row in fixtures}
    rows: list[dict[str, Any]] = []
    quarantined: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for index, source in enumerate(source_rows, 2):
        element = required_int(source["element"], f"merged_gw.csv row {index} element")
        fixture_id = required_int(source["fixture"], f"merged_gw.csv row {index} fixture")
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
        was_home = required_bool(source["was_home"], f"fact {key} was_home")
        team_id = fixture["home_team_id"] if was_home else fixture["away_team_id"]
        opponent_id = fixture["away_team_id"] if was_home else fixture["home_team_id"]
        source_opponent = required_int(source["opponent_team"], f"fact {key} opponent_team")
        if source_opponent != opponent_id:
            raise FPLValidationError(
                f"fact {key} opponent {source_opponent} conflicts with fixture-derived {opponent_id}"
            )
        gameweek = required_int(source["GW"], f"fact {key} GW")
        if fixture["gameweek"] != gameweek:
            raise FPLValidationError(
                f"fact {key} gameweek {gameweek} conflicts with fixture {fixture['gameweek']}"
            )
        kickoff = required_utc(source["kickoff_time"], f"fact {key} kickoff_time")
        if fixture["kickoff_time_utc"] != kickoff:
            raise FPLValidationError(f"fact {key} kickoff conflicts with fixture")
        position = source["position"]
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
            row[field] = required_int(source[field], f"fact {key} {field}")
        row["starts"] = optional_int(source["starts"], f"fact {key} starts")
        for field in (
            "influence", "creativity", "threat", "ict_index", "expected_goals",
            "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
        ):
            row[field] = optional_decimal(source[field], f"fact {key} {field}")
        rows.append(row)
        quarantined.append(
            {
                "season": season,
                "element": element,
                "gameweek": gameweek,
                "fixture": fixture_id,
                "selected": optional_int(source["selected"], f"fact {key} selected"),
                "value": optional_int(source["value"], f"fact {key} value"),
                "transfers_balance": optional_int(
                    source["transfers_balance"], f"fact {key} transfers_balance"
                ),
                "transfers_in": optional_int(source["transfers_in"], f"fact {key} transfers_in"),
                "transfers_out": optional_int(
                    source["transfers_out"], f"fact {key} transfers_out"
                ),
                "modified": optional_bool(source["modified"], f"fact {key} modified"),
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
