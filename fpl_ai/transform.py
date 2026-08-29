"""Transform FPL API payloads into stable, analysis-friendly table rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PLAYER_COLUMNS = [
    "id", "first_name", "second_name", "web_name", "team_id", "team_name",
    "team_short_name", "position_id", "position_name", "position_short_name",
    "status", "now_cost", "selected_by_percent", "total_points", "event_points",
    "minutes", "starts", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps", "influence",
    "creativity", "threat", "ict_index", "expected_goals", "expected_assists",
    "expected_goal_involvements", "expected_goals_conceded",
    "chance_of_playing_next_round", "news", "news_added",
]

TEAM_COLUMNS = [
    "id", "name", "short_name", "code", "strength", "strength_overall_home",
    "strength_overall_away", "strength_attack_home", "strength_attack_away",
    "strength_defence_home", "strength_defence_away", "played", "win", "draw",
    "loss", "points", "position",
]

FIXTURE_COLUMNS = [
    "id", "code", "gameweek", "kickoff_time", "started", "finished",
    "provisional_start_time", "home_team_id", "home_team_name",
    "home_team_short_name", "away_team_id", "away_team_name",
    "away_team_short_name", "home_score", "away_score", "home_difficulty",
    "away_difficulty", "minutes",
]


def transform_players(bootstrap: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select player facts and replace opaque foreign keys with useful labels."""

    teams = {team["id"]: team for team in bootstrap["teams"]}
    positions = {position["id"]: position for position in bootstrap["element_types"]}
    rows: list[dict[str, Any]] = []
    for player in bootstrap["elements"]:
        team = teams[player["team"]]
        position = positions[player["element_type"]]
        row = {
            "id": player["id"],
            "first_name": player["first_name"],
            "second_name": player["second_name"],
            "web_name": player["web_name"],
            "team_id": team["id"],
            "team_name": team["name"],
            "team_short_name": team["short_name"],
            "position_id": position["id"],
            "position_name": position["singular_name"],
            "position_short_name": position["singular_name_short"],
        }
        row.update({column: player.get(column) for column in PLAYER_COLUMNS[10:]})
        rows.append(row)
    return rows


def transform_teams(bootstrap: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select the team identity, strength, and current table fields."""

    return [
        {column: team.get(column) for column in TEAM_COLUMNS}
        for team in bootstrap["teams"]
    ]


def transform_fixtures(
    fixtures: list[Mapping[str, Any]], bootstrap: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Flatten fixtures and attach readable team names."""

    teams = {team["id"]: team for team in bootstrap["teams"]}
    rows: list[dict[str, Any]] = []
    for fixture in fixtures:
        home_team = teams[fixture["team_h"]]
        away_team = teams[fixture["team_a"]]
        rows.append(
            {
                "id": fixture["id"],
                "code": fixture.get("code"),
                "gameweek": fixture.get("event"),
                "kickoff_time": fixture.get("kickoff_time"),
                "started": fixture.get("started"),
                "finished": fixture.get("finished"),
                "provisional_start_time": fixture.get("provisional_start_time"),
                "home_team_id": home_team["id"],
                "home_team_name": home_team["name"],
                "home_team_short_name": home_team["short_name"],
                "away_team_id": away_team["id"],
                "away_team_name": away_team["name"],
                "away_team_short_name": away_team["short_name"],
                "home_score": fixture.get("team_h_score"),
                "away_score": fixture.get("team_a_score"),
                "home_difficulty": fixture.get("team_h_difficulty"),
                "away_difficulty": fixture.get("team_a_difficulty"),
                "minutes": fixture.get("minutes"),
            }
        )
    return rows
