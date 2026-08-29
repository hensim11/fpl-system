"""Minimum schema and relationship checks for public FPL data."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from fpl_ai.errors import FPLValidationError

PLAYER_FIELDS = {"id", "first_name", "second_name", "web_name", "team", "element_type"}
TEAM_FIELDS = {"id", "name", "short_name"}
POSITION_FIELDS = {"id", "singular_name", "singular_name_short"}
FIXTURE_FIELDS = {"id", "team_h", "team_a", "finished", "kickoff_time"}


def validate_payloads(
    bootstrap: Mapping[str, Any], fixtures: list[Mapping[str, Any]]
) -> None:
    """Validate enough of the upstream contract to produce trustworthy tables."""

    if not isinstance(bootstrap, Mapping):
        raise FPLValidationError("bootstrap payload must be an object")
    if not isinstance(fixtures, list):
        raise FPLValidationError("fixtures payload must be an array")

    players = _required_list(bootstrap, "elements")
    teams = _required_list(bootstrap, "teams")
    positions = _required_list(bootstrap, "element_types")

    if not players:
        raise FPLValidationError("bootstrap payload contains no players")
    if not teams:
        raise FPLValidationError("bootstrap payload contains no teams")
    if not positions:
        raise FPLValidationError("bootstrap payload contains no player positions")

    _validate_rows(players, PLAYER_FIELDS, "player")
    _validate_rows(teams, TEAM_FIELDS, "team")
    _validate_rows(positions, POSITION_FIELDS, "position")
    _validate_rows(fixtures, FIXTURE_FIELDS, "fixture")

    team_ids = _unique_integer_ids(teams, "team")
    position_ids = _unique_integer_ids(positions, "position")
    _unique_integer_ids(players, "player")
    _unique_integer_ids(fixtures, "fixture")

    for player in players:
        if player["team"] not in team_ids:
            raise FPLValidationError(
                f"player {player['id']} references unknown team {player['team']}"
            )
        if player["element_type"] not in position_ids:
            raise FPLValidationError(
                f"player {player['id']} references unknown position {player['element_type']}"
            )

    for fixture in fixtures:
        if fixture["team_h"] not in team_ids or fixture["team_a"] not in team_ids:
            raise FPLValidationError(
                f"fixture {fixture['id']} references an unknown team"
            )
        if fixture["team_h"] == fixture["team_a"]:
            raise FPLValidationError(
                f"fixture {fixture['id']} has the same home and away team"
            )


def _required_list(payload: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise FPLValidationError(f"bootstrap field '{key}' must be an array")
    return value


def _validate_rows(
    rows: Iterable[Mapping[str, Any]], required_fields: set[str], label: str
) -> None:
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise FPLValidationError(f"{label} row {index} must be an object")
        missing = required_fields.difference(row)
        if missing:
            names = ", ".join(sorted(missing))
            raise FPLValidationError(f"{label} row {index} is missing fields: {names}")


def _unique_integer_ids(rows: Iterable[Mapping[str, Any]], label: str) -> set[int]:
    ids: set[int] = set()
    for row in rows:
        row_id = row["id"]
        if not isinstance(row_id, int) or isinstance(row_id, bool):
            raise FPLValidationError(f"{label} id must be an integer: {row_id!r}")
        if row_id in ids:
            raise FPLValidationError(f"duplicate {label} id: {row_id}")
        ids.add(row_id)
    return ids
