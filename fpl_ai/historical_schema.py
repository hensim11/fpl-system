"""Explicit schemas and source contracts for historical FPL tables."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    nullable: bool
    information_class: str


GAMEWEEK_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("gameweek", "integer", False, "identity"),
    Column("deadline_time_utc", "utc_timestamp", False, "fixture_context"),
    Column("selected_snapshot_capture_time_utc", "utc_timestamp", True, "pre_deadline_state"),
    Column("hours_before_deadline", "decimal_string", True, "provenance"),
    Column("snapshot_source_path", "string", True, "provenance"),
    Column("valid_predeadline_snapshot", "boolean", False, "provenance"),
]

PLAYER_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("element", "integer", False, "identity"),
    Column("player_code", "integer", False, "cross_season_identity"),
    Column("first_name", "string", False, "identity"),
    Column("second_name", "string", False, "identity"),
    Column("web_name", "string", False, "identity"),
    Column("position_id", "integer", False, "identity"),
    Column("position", "string", False, "identity"),
    Column("end_of_season_team_id", "integer", True, "identity_audit_only"),
]

TEAM_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("team_id", "integer", False, "identity"),
    Column("team_code", "integer", False, "identity"),
    Column("name", "string", False, "identity"),
    Column("short_name", "string", False, "identity"),
]

FIXTURE_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("fixture", "integer", False, "identity"),
    Column("fixture_code", "integer", True, "fixture_context"),
    Column("gameweek", "integer", True, "fixture_context"),
    Column("home_team_id", "integer", False, "fixture_context"),
    Column("away_team_id", "integer", False, "fixture_context"),
    Column("kickoff_time_utc", "utc_timestamp", True, "fixture_context"),
    Column("home_difficulty", "integer", True, "fixture_context"),
    Column("away_difficulty", "integer", True, "fixture_context"),
    Column("home_score", "integer", True, "realised_outcome"),
    Column("away_score", "integer", True, "realised_outcome"),
    Column("finished", "boolean", False, "realised_outcome"),
]

FACT_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("element", "integer", False, "identity"),
    Column("player_code", "integer", False, "cross_season_identity"),
    Column("gameweek", "integer", False, "fixture_context"),
    Column("fixture", "integer", False, "identity"),
    Column("team_id", "integer", False, "fixture_context"),
    Column("opponent_team_id", "integer", False, "fixture_context"),
    Column("was_home", "boolean", False, "fixture_context"),
    Column("kickoff_time_utc", "utc_timestamp", False, "fixture_context"),
    Column("position", "string", False, "fixture_context"),
    Column("minutes", "integer", False, "realised_outcome"),
    Column("total_points", "integer", False, "realised_outcome"),
    Column("starts", "integer", True, "realised_outcome"),
    Column("goals_scored", "integer", False, "realised_outcome"),
    Column("assists", "integer", False, "realised_outcome"),
    Column("clean_sheets", "integer", False, "realised_outcome"),
    Column("goals_conceded", "integer", False, "realised_outcome"),
    Column("own_goals", "integer", False, "realised_outcome"),
    Column("penalties_saved", "integer", False, "realised_outcome"),
    Column("penalties_missed", "integer", False, "realised_outcome"),
    Column("saves", "integer", False, "realised_outcome"),
    Column("yellow_cards", "integer", False, "realised_outcome"),
    Column("red_cards", "integer", False, "realised_outcome"),
    Column("bonus", "integer", False, "realised_outcome"),
    Column("bps", "integer", False, "realised_outcome"),
    Column("influence", "decimal_string", True, "realised_outcome"),
    Column("creativity", "decimal_string", True, "realised_outcome"),
    Column("threat", "decimal_string", True, "realised_outcome"),
    Column("ict_index", "decimal_string", True, "realised_outcome"),
    Column("expected_goals", "decimal_string", True, "realised_outcome"),
    Column("expected_assists", "decimal_string", True, "realised_outcome"),
    Column("expected_goal_involvements", "decimal_string", True, "realised_outcome"),
    Column("expected_goals_conceded", "decimal_string", True, "realised_outcome"),
]

SNAPSHOT_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("gameweek", "integer", False, "identity"),
    Column("element", "integer", False, "identity"),
    Column("player_code", "integer", False, "cross_season_identity"),
    Column("price", "integer", True, "pre_deadline_state"),
    Column("selected_by_percent", "decimal_string", True, "pre_deadline_state"),
    Column("transfers_in_event", "integer", True, "pre_deadline_state"),
    Column("transfers_out_event", "integer", True, "pre_deadline_state"),
    Column("status", "string", True, "pre_deadline_state"),
    Column("chance_of_playing_this_round", "integer", True, "pre_deadline_state"),
    Column("chance_of_playing_next_round", "integer", True, "pre_deadline_state"),
    Column("news", "string", True, "pre_deadline_state"),
    Column("news_added_utc", "utc_timestamp", True, "pre_deadline_state"),
    Column("expected_points_next_gameweek", "decimal_string", True, "pre_deadline_state"),
    Column("corners_and_indirect_freekicks_order", "integer", True, "pre_deadline_state"),
    Column("direct_freekicks_order", "integer", True, "pre_deadline_state"),
    Column("penalties_order", "integer", True, "pre_deadline_state"),
    Column("capture_time_utc", "utc_timestamp", False, "provenance"),
    Column("deadline_time_utc", "utc_timestamp", False, "provenance"),
    Column("source_path", "string", False, "provenance"),
    Column("source_sha256", "string", False, "provenance"),
]

QUARANTINE_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("element", "integer", False, "identity"),
    Column("gameweek", "integer", False, "identity"),
    Column("fixture", "integer", False, "identity"),
    Column("selected", "integer", True, "unverified_timing"),
    Column("value", "integer", True, "unverified_timing"),
    Column("transfers_balance", "integer", True, "unverified_timing"),
    Column("transfers_in", "integer", True, "unverified_timing"),
    Column("transfers_out", "integer", True, "unverified_timing"),
    Column("modified", "boolean", True, "unverified_timing"),
]

TABLE_SCHEMAS = {
    "gameweeks": GAMEWEEK_COLUMNS,
    "players": PLAYER_COLUMNS,
    "teams": TEAM_COLUMNS,
    "fixtures": FIXTURE_COLUMNS,
    "player_fixture_facts": FACT_COLUMNS,
    "player_deadline_snapshots": SNAPSHOT_COLUMNS,
    "quarantined_source_metadata": QUARANTINE_COLUMNS,
}


def column_names(table: str) -> list[str]:
    return [column.name for column in TABLE_SCHEMAS[table]]


def schemas_as_dict() -> dict[str, list[dict[str, object]]]:
    return {
        table: [
            {
                "name": column.name,
                "type": column.data_type,
                "nullable": column.nullable,
                "information_class": column.information_class,
            }
            for column in columns
        ]
        for table, columns in TABLE_SCHEMAS.items()
    }


# Exact contracts observed at the pinned Vaastav revision. Additions are treated
# as a source-schema change so they are reviewed rather than silently trusted.
VAASTAV_SOURCE_COLUMNS = {
    "merged_gw.csv": [
        "name", "position", "team", "xP", "assists", "bonus", "bps",
        "clean_sheets", "creativity", "element", "expected_assists",
        "expected_goal_involvements", "expected_goals", "expected_goals_conceded",
        "fixture", "goals_conceded", "goals_scored", "ict_index", "influence",
        "kickoff_time", "minutes", "mng_clean_sheets", "mng_draw",
        "mng_goals_scored", "mng_loss", "mng_underdog_draw", "mng_underdog_win",
        "mng_win", "modified", "opponent_team", "own_goals", "penalties_missed",
        "penalties_saved", "red_cards", "round", "saves", "selected", "starts",
        "team_a_score", "team_h_score", "threat", "total_points",
        "transfers_balance", "transfers_in", "transfers_out", "value", "was_home",
        "yellow_cards", "GW",
    ],
    "players_raw.csv": [
        "assists", "birth_date", "bonus", "bps", "can_select", "can_transact",
        "chance_of_playing_next_round", "chance_of_playing_this_round",
        "clean_sheets", "clean_sheets_per_90", "code",
        "corners_and_indirect_freekicks_order", "corners_and_indirect_freekicks_text",
        "cost_change_event", "cost_change_event_fall", "cost_change_start",
        "cost_change_start_fall", "creativity", "creativity_rank",
        "creativity_rank_type", "direct_freekicks_order", "direct_freekicks_text",
        "dreamteam_count", "element_type", "ep_next", "ep_this", "event_points",
        "expected_assists", "expected_assists_per_90", "expected_goal_involvements",
        "expected_goal_involvements_per_90", "expected_goals",
        "expected_goals_conceded", "expected_goals_conceded_per_90",
        "expected_goals_per_90", "first_name", "form", "form_rank", "form_rank_type",
        "goals_conceded", "goals_conceded_per_90", "goals_scored",
        "has_temporary_code", "ict_index", "ict_index_rank", "ict_index_rank_type",
        "id", "in_dreamteam", "influence", "influence_rank", "influence_rank_type",
        "minutes", "mng_clean_sheets", "mng_draw", "mng_goals_scored", "mng_loss",
        "mng_underdog_draw", "mng_underdog_win", "mng_win", "news", "news_added",
        "now_cost", "now_cost_rank", "now_cost_rank_type", "opta_code", "own_goals",
        "penalties_missed", "penalties_order", "penalties_saved", "penalties_text",
        "photo", "points_per_game", "points_per_game_rank", "points_per_game_rank_type",
        "red_cards", "region", "removed", "saves", "saves_per_90", "second_name",
        "selected_by_percent", "selected_rank", "selected_rank_type", "special",
        "squad_number", "starts", "starts_per_90", "status", "team", "team_code",
        "team_join_date", "threat", "threat_rank", "threat_rank_type", "total_points",
        "transfers_in", "transfers_in_event", "transfers_out", "transfers_out_event",
        "value_form", "value_season", "web_name", "yellow_cards",
    ],
    "teams.csv": [
        "code", "draw", "form", "id", "loss", "name", "played", "points",
        "position", "short_name", "strength", "team_division", "unavailable", "win",
        "strength_overall_home", "strength_overall_away", "strength_attack_home",
        "strength_attack_away", "strength_defence_home", "strength_defence_away", "pulse_id",
    ],
    "fixtures.csv": [
        "code", "event", "finished", "finished_provisional", "id", "kickoff_time",
        "minutes", "provisional_start_time", "started", "team_a", "team_a_score",
        "team_h", "team_h_score", "stats", "team_h_difficulty",
        "team_a_difficulty", "pulse_id",
    ],
}
