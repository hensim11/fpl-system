"""Explicit schemas and source contracts for historical FPL tables."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Callable

from fpl_ai.errors import FPLValidationError


TRANSFORMATION_CONTRACT_VERSION = "historical-transform-v6"
SUPPORTED_SOURCE_ADAPTERS = {"declarative-normalization-v1", "declarative-normalization-v2"}


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    nullable: bool
    information_class: str


GAMEWEEK_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("gameweek", "integer", False, "identity"),
    Column("deadline_time_utc", "utc_timestamp", False, "deadline_context"),
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
    Column("end_of_season_position_id", "integer", False, "identity_audit_only"),
    Column("end_of_season_position", "string", False, "identity_audit_only"),
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
    Column("fixture", "integer", False, "post_event_fixture_context"),
    Column("fixture_code", "integer", True, "post_event_fixture_context"),
    Column("gameweek", "integer", True, "post_event_fixture_context"),
    Column("home_team_id", "integer", False, "post_event_fixture_context"),
    Column("away_team_id", "integer", False, "post_event_fixture_context"),
    Column("kickoff_time_utc", "utc_timestamp", True, "post_event_fixture_context"),
    Column("home_difficulty", "integer", True, "post_event_fixture_context"),
    Column("away_difficulty", "integer", True, "post_event_fixture_context"),
    Column("home_score", "integer", True, "realised_outcome"),
    Column("away_score", "integer", True, "realised_outcome"),
    Column("finished", "boolean", False, "realised_outcome"),
]

FACT_COLUMNS = [
    Column("season", "string", False, "identity"),
    Column("element", "integer", False, "identity"),
    Column("player_code", "integer", False, "cross_season_identity"),
    Column("gameweek", "integer", False, "post_event_fixture_context"),
    Column("fixture", "integer", False, "post_event_fixture_context"),
    Column("team_id_at_fixture", "integer", False, "post_event_fixture_context"),
    Column("opponent_team_id_at_fixture", "integer", False, "post_event_fixture_context"),
    Column("was_home", "boolean", False, "post_event_fixture_context"),
    Column("kickoff_time_utc", "utc_timestamp", False, "post_event_fixture_context"),
    Column("position_at_fixture", "string", False, "post_event_fixture_context"),
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
    Column("deadline_team_id", "integer", True, "pre_deadline_state"),
    Column("deadline_team_code", "integer", True, "pre_deadline_state"),
    Column("deadline_team_name", "string", True, "pre_deadline_state"),
    Column("deadline_team_short_name", "string", True, "pre_deadline_state"),
    Column("deadline_position_id", "integer", True, "pre_deadline_state"),
    Column("deadline_position", "string", True, "pre_deadline_state"),
    Column("deadline_position_name", "string", True, "pre_deadline_state"),
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

# The pinned Vaastav fixture file is a season-end representation. It proves
# outcome context, but not what the schedule/difficulty looked like at an
# earlier deadline. Only these fields may appear in a decision-time record.
DEADLINE_FIXTURE_CONTEXT_ALLOWLIST = (
    "season",
    "gameweek",
    "deadline_time_utc",
)

POST_EVENT_FIXTURE_CONTEXT_FIELDS = (
    "fixture",
    "fixture_code",
    "home_team_id",
    "away_team_id",
    "team_id_at_fixture",
    "opponent_team_id_at_fixture",
    "was_home",
    "kickoff_time_utc",
    "home_difficulty",
    "away_difficulty",
    "home_score",
    "away_score",
    "finished",
    "minutes",
)

FIXTURE_CONTEXT_AVAILABILITY_POLICY = {
    "policy_version": 1,
    "decision_time_table": "player_deadline_snapshots",
    "deadline_safe_allowlist": list(DEADLINE_FIXTURE_CONTEXT_ALLOWLIST),
    "post_event_only_fields": list(POST_EVENT_FIXTURE_CONTEXT_FIELDS),
    "rule": (
        "The pinned source does not preserve fixture snapshots at every deadline. "
        "Final fixture identity, assignment, kickoff, difficulty, status and result "
        "remain only in fixtures/player_fixture_facts and are never attached to "
        "player_deadline_snapshots."
    ),
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


def schema_document(
    vaastav_source_schema: dict[str, object] | None = None,
) -> dict[str, object]:
    document: dict[str, object] = {
        "tables": schemas_as_dict(),
        "fixture_context_availability_policy": FIXTURE_CONTEXT_AVAILABILITY_POLICY,
        "transformation_contract_version": TRANSFORMATION_CONTRACT_VERSION,
    }
    if vaastav_source_schema is not None:
        document["vaastav_source_schema"] = vaastav_source_schema
    return document


# Exact contracts observed at the pinned Vaastav revision. Additions are treated
# as a source-schema change so they are reviewed rather than silently trusted.
VAASTAV_2024_25_SOURCE_COLUMNS = {
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


_VAASTAV_2024_25_REQUIRED_COLUMNS = {
    "merged_gw.csv": [
        "position", "assists", "bonus", "bps", "clean_sheets", "creativity",
        "element", "fixture", "goals_conceded", "goals_scored", "ict_index",
        "influence", "kickoff_time", "minutes", "opponent_team", "own_goals",
        "penalties_missed", "penalties_saved", "red_cards", "saves", "team_a_score",
        "team_h_score", "threat", "total_points", "was_home", "yellow_cards", "GW",
    ],
    "players_raw.csv": [
        "id", "code", "first_name", "second_name", "web_name", "element_type", "team",
    ],
    "teams.csv": ["id", "code", "name", "short_name"],
    "fixtures.csv": [
        "id", "code", "event", "finished", "kickoff_time", "team_a", "team_a_score",
        "team_h", "team_h_score", "team_h_difficulty", "team_a_difficulty",
    ],
}

_VAASTAV_2024_25_QUARANTINED_COLUMNS = {
    "merged_gw.csv": [
        "selected", "value", "transfers_balance", "transfers_in", "transfers_out", "modified",
    ],
    "players_raw.csv": [],
    "teams.csv": [],
    "fixtures.csv": [],
}

_VAASTAV_2024_25_FORBIDDEN_COLUMNS = {
    "merged_gw.csv": ["xP"],
    "players_raw.csv": [],
    "teams.csv": [],
    "fixtures.csv": [],
}

_VAASTAV_2024_25_OPTIONAL_COLUMNS = {
    "merged_gw.csv": [
        "starts", "expected_goals", "expected_assists",
        "expected_goal_involvements", "expected_goals_conceded",
    ],
    "players_raw.csv": [],
    "teams.csv": [],
    "fixtures.csv": [],
}

_VAASTAV_2024_25_IGNORED_COLUMNS = {
    "merged_gw.csv": [
        "name", "team", "round", "mng_clean_sheets", "mng_draw",
        "mng_goals_scored", "mng_loss", "mng_underdog_draw", "mng_underdog_win",
        "mng_win",
    ],
    "players_raw.csv": [
        "mng_clean_sheets", "mng_draw", "mng_goals_scored", "mng_loss",
        "mng_underdog_draw", "mng_underdog_win", "mng_win",
    ],
    "teams.csv": [],
    "fixtures.csv": [
        "finished_provisional", "minutes", "provisional_start_time", "started", "stats",
    ],
}

_VAASTAV_2024_25_MAPPINGS = {
    "merged_gw.csv": {
        "element": "player_fixture_facts.element",
        "fixture": "player_fixture_facts.fixture",
        "GW": "player_fixture_facts.gameweek",
        "position": "player_fixture_facts.position_at_fixture",
        "was_home": "player_fixture_facts.was_home",
        "kickoff_time": "player_fixture_facts.kickoff_time_utc",
        "opponent_team": "player_fixture_facts.opponent_team_id_at_fixture",
        "total_points": "player_fixture_facts.total_points",
        **{
            field: f"player_fixture_facts.{field}"
            for field in (
                "minutes", "starts", "goals_scored", "assists", "clean_sheets",
                "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
                "saves", "yellow_cards", "red_cards", "bonus", "bps", "influence",
                "creativity", "threat", "ict_index", "expected_goals",
                "expected_assists", "expected_goal_involvements",
                "expected_goals_conceded",
            )
        },
    },
    "players_raw.csv": {
        "id": "players.element",
        "code": "players.player_code",
        "first_name": "players.first_name",
        "second_name": "players.second_name",
        "web_name": "players.web_name",
        "element_type": "players.end_of_season_position_id",
        "team": "players.end_of_season_team_id",
    },
    "teams.csv": {
        "id": "teams.team_id",
        "code": "teams.team_code",
        "name": "teams.name",
        "short_name": "teams.short_name",
    },
    "fixtures.csv": {
        "id": "fixtures.fixture",
        "event": "fixtures.gameweek",
        "team_h": "fixtures.home_team_id",
        "team_a": "fixtures.away_team_id",
        "kickoff_time": "fixtures.kickoff_time_utc",
        "code": "fixtures.fixture_code",
        "finished": "fixtures.finished",
        "team_h_score": "fixtures.home_score",
        "team_a_score": "fixtures.away_score",
        "team_h_difficulty": "fixtures.home_difficulty",
        "team_a_difficulty": "fixtures.away_difficulty",
    },
}

_VAASTAV_2024_25_QUARANTINE_MAPPINGS = {
    "merged_gw.csv": {
        field: f"quarantined_source_metadata.{field}"
        for field in _VAASTAV_2024_25_QUARANTINED_COLUMNS["merged_gw.csv"]
    },
    "players_raw.csv": {},
    "teams.csv": {},
    "fixtures.csv": {},
}

def _type(
    data_type: str,
    *,
    nullable: bool = False,
    allowed_values: list[str] | None = None,
) -> dict[str, object]:
    expectation: dict[str, object] = {"type": data_type, "nullable": nullable}
    if allowed_values is not None:
        expectation["allowed_values"] = allowed_values
    return expectation


_VAASTAV_2024_25_TYPE_EXPECTATIONS = {
    "merged_gw.csv": {
        "position": _type("string", allowed_values=["GK", "DEF", "MID", "FWD", "AM"]),
        **{
            field: _type("integer")
            for field in (
                "assists", "bonus", "bps", "clean_sheets", "element", "fixture",
                "goals_conceded", "goals_scored", "minutes", "opponent_team",
                "own_goals", "penalties_missed", "penalties_saved", "red_cards",
                "saves", "team_a_score", "team_h_score", "total_points",
                "yellow_cards", "GW",
            )
        },
        **{
            field: _type("decimal")
            for field in ("creativity", "ict_index", "influence", "threat")
        },
        "kickoff_time": _type("utc_timestamp"),
        "was_home": _type("boolean"),
        "starts": _type("integer", nullable=True),
        **{
            field: _type("decimal", nullable=True)
            for field in (
                "expected_goals", "expected_assists", "expected_goal_involvements",
                "expected_goals_conceded",
            )
        },
        **{
            field: _type("integer", nullable=True)
            for field in (
                "selected", "value", "transfers_balance", "transfers_in", "transfers_out",
            )
        },
        "modified": _type("boolean", nullable=True),
    },
    "players_raw.csv": {
        "id": _type("integer"),
        "code": _type("integer"),
        "first_name": _type("string"),
        "second_name": _type("string"),
        "web_name": _type("string"),
        "element_type": _type("integer"),
        "team": _type("integer"),
    },
    "teams.csv": {
        "id": _type("integer"),
        "code": _type("integer"),
        "name": _type("string"),
        "short_name": _type("string"),
    },
    "fixtures.csv": {
        "id": _type("integer"),
        "code": _type("integer"),
        "event": _type("integer", nullable=True),
        "finished": _type("boolean"),
        "kickoff_time": _type("utc_timestamp", nullable=True),
        "team_h": _type("integer"),
        "team_a": _type("integer"),
        "team_h_score": _type("integer", nullable=True),
        "team_a_score": _type("integer", nullable=True),
        "team_h_difficulty": _type("integer"),
        "team_a_difficulty": _type("integer"),
    },
}


def _vaastav_2024_25_files() -> dict[str, dict[str, object]]:
    files: dict[str, dict[str, object]] = {}
    for filename, columns in VAASTAV_2024_25_SOURCE_COLUMNS.items():
        required = _VAASTAV_2024_25_REQUIRED_COLUMNS[filename]
        optional = _VAASTAV_2024_25_OPTIONAL_COLUMNS[filename]
        mappings = dict(_VAASTAV_2024_25_MAPPINGS[filename])
        quarantined = list(_VAASTAV_2024_25_QUARANTINED_COLUMNS[filename])
        forbidden = list(_VAASTAV_2024_25_FORBIDDEN_COLUMNS[filename])
        explicitly_ignored = set(_VAASTAV_2024_25_IGNORED_COLUMNS[filename])
        ignored = [
            column
            for column in columns
            if column not in required
            and column not in optional
            and column not in quarantined
            and column not in forbidden
        ]
        if not explicitly_ignored.issubset(ignored):
            raise AssertionError(f"invalid ignored-column contract for {filename}")
        files[filename] = {
            "known_column_order": list(columns),
            "required_columns": list(required),
            "optional_columns": list(optional),
            "ignored_columns": ignored,
            "quarantined_columns": quarantined,
            "forbidden_columns": forbidden,
            "source_to_canonical_mappings": mappings,
            "quarantined_source_to_canonical_mappings": dict(
                _VAASTAV_2024_25_QUARANTINE_MAPPINGS[filename]
            ),
            "type_expectations": dict(_VAASTAV_2024_25_TYPE_EXPECTATIONS[filename]),
        }
    return files


VAASTAV_SOURCE_SCHEMAS: dict[str, dict[str, object]] = {
    "vaastav-2024-25-v1": {
        "schema_id": "vaastav-2024-25-v1",
        "schema_version": 1,
        "adapter_id": "declarative-normalization-v1",
        "applicable_seasons": ["2024-25"],
        "unexpected_columns_policy": "quality_failure",
        "files": _vaastav_2024_25_files(),
        "expected_metric_fields_available": [
            "expected_goals", "expected_assists", "expected_goal_involvements",
            "expected_goals_conceded",
        ],
        "forbidden_trusted_output_fields": ["xP"],
        "known_source_exceptions": [
            "Assistant Manager pseudo-elements and mng_* columns exist in 2024/25.",
            "xP timing is not trusted and is forbidden from every processed table.",
        ],
    }
}


# Observed header differences at immutable Vaastav revision 9779cdbc0c07.
# All retained fields have the same source meaning and types as 2024/25.
_VAASTAV_2023_24_ABSENT_COLUMNS = {
    "merged_gw.csv": {
        "mng_clean_sheets", "mng_draw", "mng_goals_scored", "mng_loss",
        "mng_underdog_draw", "mng_underdog_win", "mng_win", "modified",
    },
    "players_raw.csv": {
        "birth_date", "can_select", "can_transact", "has_temporary_code",
        "mng_clean_sheets", "mng_draw", "mng_goals_scored", "mng_loss",
        "mng_underdog_draw", "mng_underdog_win", "mng_win", "opta_code",
        "region", "removed", "team_join_date",
    },
    "teams.csv": set(),
    "fixtures.csv": set(),
}


def _vaastav_2023_24_schema() -> dict[str, object]:
    """Declare the inspected older shape without mutating the regression baseline."""

    schema = deepcopy(VAASTAV_SOURCE_SCHEMAS["vaastav-2024-25-v1"])
    schema.update(
        schema_id="vaastav-2023-24-v1",
        applicable_seasons=["2023-24"],
        known_source_exceptions=[
            "No Assistant Manager elements or mng_* columns occur in 2023/24.",
            "The merged source has no modified column; quarantine modified remains null.",
            "xP timing is not trusted and is forbidden from every processed table.",
        ],
    )
    for filename, absent in _VAASTAV_2023_24_ABSENT_COLUMNS.items():
        file_schema = schema["files"][filename]
        for key in (
            "known_column_order", "required_columns", "optional_columns",
            "ignored_columns", "quarantined_columns", "forbidden_columns",
        ):
            file_schema[key] = [field for field in file_schema[key] if field not in absent]
        for key in (
            "source_to_canonical_mappings", "quarantined_source_to_canonical_mappings",
            "type_expectations",
        ):
            file_schema[key] = {
                field: value for field, value in file_schema[key].items()
                if field not in absent
            }
    schema["files"]["merged_gw.csv"]["type_expectations"]["position"]["allowed_values"] = [
        "GK", "DEF", "MID", "FWD",
    ]
    return schema


VAASTAV_SOURCE_SCHEMAS["vaastav-2023-24-v1"] = _vaastav_2023_24_schema()


def _vaastav_2022_23_schema() -> dict[str, object]:
    """The four inspected 2022/23 headers exactly match the 2023/24 shape."""

    schema = deepcopy(VAASTAV_SOURCE_SCHEMAS["vaastav-2023-24-v1"])
    schema.update(
        schema_id="vaastav-2022-23-v1",
        applicable_seasons=["2022-23"],
        known_source_exceptions=[
            "No Assistant Manager elements or mng_* columns occur in 2022/23.",
            "The merged source has no modified column; quarantine modified remains null.",
            "GW7 has a deadline and snapshots but no fixtures or player-fixture facts.",
            "xP timing is not trusted and is forbidden from every processed table.",
        ],
    )
    return schema


VAASTAV_SOURCE_SCHEMAS["vaastav-2022-23-v1"] = _vaastav_2022_23_schema()


# Observed omissions at the same immutable Vaastav revision as newer seasons.
_VAASTAV_2021_22_ABSENT_COLUMNS = {
    "merged_gw.csv": {
        "expected_assists", "expected_goal_involvements", "expected_goals",
        "expected_goals_conceded", "starts",
    },
    "players_raw.csv": {
        "clean_sheets_per_90", "expected_assists", "expected_assists_per_90",
        "expected_goal_involvements", "expected_goal_involvements_per_90",
        "expected_goals", "expected_goals_conceded", "expected_goals_conceded_per_90",
        "expected_goals_per_90", "form_rank", "form_rank_type", "goals_conceded_per_90",
        "now_cost_rank", "now_cost_rank_type", "points_per_game_rank",
        "points_per_game_rank_type", "saves_per_90", "selected_rank",
        "selected_rank_type", "starts", "starts_per_90",
    },
    "teams.csv": set(),
    "fixtures.csv": set(),
}


def _vaastav_2021_22_schema() -> dict[str, object]:
    """Keep unavailable older metrics null in the shared canonical contract."""

    schema = deepcopy(VAASTAV_SOURCE_SCHEMAS["vaastav-2023-24-v1"])
    schema.update(
        schema_id="vaastav-2021-22-v1",
        adapter_id="declarative-normalization-v2",
        applicable_seasons=["2021-22"],
        expected_metric_fields_available=[],
        known_source_exceptions=[
            "Starts and expected metrics are absent; canonical outcomes remain null.",
            "GW37 uses GKP for 101 goalkeeper rows; the position alias normalizes it to GK.",
            "No Assistant Manager or modified columns occur in 2021/22.",
            "xP timing is not trusted and is forbidden from every processed table.",
        ],
    )
    for filename, absent in _VAASTAV_2021_22_ABSENT_COLUMNS.items():
        file_schema = schema["files"][filename]
        for key in (
            "known_column_order", "required_columns", "optional_columns",
            "ignored_columns", "quarantined_columns", "forbidden_columns",
        ):
            file_schema[key] = [field for field in file_schema[key] if field not in absent]
        for key in (
            "source_to_canonical_mappings", "quarantined_source_to_canonical_mappings",
            "type_expectations",
        ):
            file_schema[key] = {
                field: value for field, value in file_schema[key].items()
                if field not in absent
            }
    schema["files"]["merged_gw.csv"]["type_expectations"]["position"]["value_aliases"] = {
        "GKP": "GK",
    }
    return schema


VAASTAV_SOURCE_SCHEMAS["vaastav-2021-22-v1"] = _vaastav_2021_22_schema()


def validate_vaastav_source_schema(
    schema: object, season: str | None = None
) -> dict[str, object]:
    """Reject contradictory or incomplete Vaastav source contracts."""

    if not isinstance(schema, dict):
        raise FPLValidationError(
            "malformed Vaastav source schema <unknown>; expected an object; "
            "corrective action: define a complete schema object"
        )
    schema_id = schema.get("schema_id", "<unknown>")

    def fail(message: str) -> None:
        context = f" for season {season!r}" if season is not None else ""
        raise FPLValidationError(
            f"Vaastav source schema {schema_id!r}{context}: {message}; "
            "corrective action: make field categories disjoint and mappings explicit"
        )

    if not isinstance(schema_id, str) or not schema_id.strip():
        fail("schema_id must be a non-empty string")
    if (
        not isinstance(schema.get("schema_version"), int)
        or isinstance(schema.get("schema_version"), bool)
        or schema["schema_version"] < 1
    ):
        fail("schema_version must be an integer")
    adapter_id = schema.get("adapter_id")
    if adapter_id not in SUPPORTED_SOURCE_ADAPTERS:
        fail(
            f"unsupported adapter_id {adapter_id!r}; supported adapters are "
            f"{sorted(SUPPORTED_SOURCE_ADAPTERS)}"
        )
    applicable = schema.get("applicable_seasons")
    if (
        not isinstance(applicable, list)
        or not applicable
        or any(not isinstance(value, str) or not value for value in applicable)
        or len(applicable) != len(set(applicable))
    ):
        fail("applicable_seasons must be a non-empty list without duplicates")
    files = schema.get("files")
    if not isinstance(files, dict) or not files:
        fail("files must be a non-empty object")
    if schema.get("unexpected_columns_policy") != "quality_failure":
        fail("unexpected_columns_policy must be 'quality_failure'")
    for metadata_field in (
        "expected_metric_fields_available",
        "known_source_exceptions",
        "forbidden_trusted_output_fields",
    ):
        values = schema.get(metadata_field)
        if not isinstance(values, list) or any(
            not isinstance(value, str) for value in values
        ):
            fail(f"{metadata_field} must be a string list")

    categories = (
        "required_columns",
        "optional_columns",
        "ignored_columns",
        "quarantined_columns",
        "forbidden_columns",
    )
    canonical_targets: dict[str, str] = {}
    quarantine_targets: dict[str, str] = {}
    forbidden_across_files: list[str] = []
    xp_declared = False
    for filename, file_schema in files.items():
        if not isinstance(filename, str) or not isinstance(file_schema, dict):
            fail("each files entry must map a filename to an object")
        known = file_schema.get("known_column_order")
        if not isinstance(known, list) or any(not isinstance(value, str) for value in known):
            fail(f"{filename} known_column_order must be a string list")
        if len(known) != len(set(known)):
            duplicate = next(value for value in known if known.count(value) > 1)
            fail(f"{filename} field {duplicate!r} is duplicated in known_column_order")

        declared_by_category: dict[str, list[str]] = {}
        field_categories: dict[str, list[str]] = {}
        for category in categories:
            values = file_schema.get(category)
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                fail(f"{filename} {category} must be a string list")
            if len(values) != len(set(values)):
                duplicate = next(value for value in values if values.count(value) > 1)
                fail(f"{filename} field {duplicate!r} is duplicated in {category}")
            declared_by_category[category] = values
            for field in values:
                field_categories.setdefault(field, []).append(category)
        conflicts = {
            field: declarations
            for field, declarations in field_categories.items()
            if len(declarations) > 1
        }
        if conflicts:
            field, declarations = next(iter(conflicts.items()))
            fail(
                f"{filename} field {field!r} has conflicting declarations "
                f"{declarations}"
            )
        declared = set(field_categories)
        if declared != set(known):
            fail(
                f"{filename} supported-field policy mismatch; undeclared="
                f"{sorted(set(known) - declared)}, unknown={sorted(declared - set(known))}"
            )

        forbidden = set(declared_by_category["forbidden_columns"])
        forbidden_across_files.extend(declared_by_category["forbidden_columns"])
        xp_declared = xp_declared or "xP" in known
        trusted_mappings = file_schema.get("source_to_canonical_mappings")
        quarantine_mappings = file_schema.get(
            "quarantined_source_to_canonical_mappings"
        )
        if not isinstance(trusted_mappings, dict) or not isinstance(
            quarantine_mappings, dict
        ):
            fail(f"{filename} mappings must be objects")
        type_expectations = file_schema.get("type_expectations")
        if not isinstance(type_expectations, dict):
            fail(f"{filename} type_expectations must be an object")
        for field, expectation in type_expectations.items():
            if field not in declared:
                fail(f"{filename} type expectation names unsupported field {field!r}")
            _validate_type_expectation(filename, field, expectation, fail)
            if "value_aliases" in expectation and adapter_id != "declarative-normalization-v2":
                fail(f"{filename} field {field!r} value_aliases requires adapter v2")

        trusted_sources = set(declared_by_category["required_columns"]) | set(
            declared_by_category["optional_columns"]
        )
        for source_field, target in trusted_mappings.items():
            if source_field in forbidden:
                fail(
                    f"{filename} forbidden field {source_field!r} maps to trusted "
                    f"canonical field {target!r}"
                )
            if source_field not in trusted_sources:
                fail(
                    f"{filename} mapping source {source_field!r} is not declared "
                    "required or optional"
                )
            _validate_canonical_mapping_target(
                filename, source_field, target, False, fail
            )
            owner = canonical_targets.setdefault(target, f"{filename}.{source_field}")
            if owner != f"{filename}.{source_field}":
                fail(
                    f"canonical target {target!r} has conflicting mappings from "
                    f"{owner!r} and {filename}.{source_field!r}"
                )
        quarantined_sources = set(declared_by_category["quarantined_columns"])
        for source_field, target in quarantine_mappings.items():
            if source_field in forbidden:
                fail(
                    f"{filename} forbidden field {source_field!r} maps to quarantine "
                    f"field {target!r}"
                )
            if source_field not in quarantined_sources:
                fail(
                    f"{filename} quarantined mapping source {source_field!r} is not "
                    "declared quarantined"
                )
            _validate_canonical_mapping_target(
                filename, source_field, target, True, fail
            )
            owner = quarantine_targets.setdefault(
                target, f"{filename}.{source_field}"
            )
            if owner != f"{filename}.{source_field}":
                fail(
                    f"quarantine target {target!r} has conflicting mappings from "
                    f"{owner!r} and {filename}.{source_field!r}"
                )
        mapped_sources = set(trusted_mappings) | set(quarantine_mappings)
        missing_type_expectations = sorted(mapped_sources - set(type_expectations))
        if missing_type_expectations:
            fail(
                f"{filename} mapped fields lack type expectations: "
                f"{missing_type_expectations}"
            )

    top_forbidden = schema.get("forbidden_trusted_output_fields")
    if not isinstance(top_forbidden, list) or any(
        not isinstance(value, str) for value in top_forbidden
    ):
        fail("forbidden_trusted_output_fields must be a string list")
    if len(top_forbidden) != len(set(top_forbidden)):
        duplicate = next(
            value for value in top_forbidden if top_forbidden.count(value) > 1
        )
        fail(f"field {duplicate!r} is duplicated in forbidden_trusted_output_fields")
    if set(top_forbidden) != set(forbidden_across_files):
        fail(
            "forbidden_trusted_output_fields must exactly match file-level "
            f"forbidden columns {sorted(set(forbidden_across_files))}"
        )
    if xp_declared and "xP" not in top_forbidden:
        fail("xP must be forbidden and cannot map to any trusted expected-points field")
    return schema


def _validate_type_expectation(
    filename: str,
    field: str,
    expectation: object,
    fail: Callable[[str], None],
) -> None:
    if not isinstance(expectation, dict):
        fail(f"{filename} field {field!r} type expectation must be an object")
    allowed_keys = {"type", "nullable", "allowed_values", "value_aliases"}
    unexpected = sorted(set(expectation) - allowed_keys)
    if unexpected:
        fail(
            f"{filename} field {field!r} type expectation has unknown keys "
            f"{unexpected}"
        )
    data_type = expectation.get("type")
    if data_type not in {"integer", "decimal", "boolean", "string", "utc_timestamp"}:
        fail(f"{filename} field {field!r} has unsupported type {data_type!r}")
    if not isinstance(expectation.get("nullable"), bool):
        fail(f"{filename} field {field!r} nullable must be boolean")
    allowed_values = expectation.get("allowed_values")
    if allowed_values is not None:
        if data_type != "string":
            fail(f"{filename} field {field!r} allowed_values requires string type")
        if (
            not isinstance(allowed_values, list)
            or not allowed_values
            or any(not isinstance(value, str) for value in allowed_values)
            or len(allowed_values) != len(set(allowed_values))
        ):
            fail(f"{filename} field {field!r} allowed_values must be unique strings")

    if "value_aliases" in expectation:
        aliases = expectation["value_aliases"]
        if data_type != "string" or allowed_values is None:
            fail(f"{filename} field {field!r} value_aliases requires a string enumeration")
        if (
            not isinstance(aliases, dict) or not aliases
            or any(not isinstance(k, str) or not k or k.strip() in ("None", "null", "")
                   or not isinstance(v, str) or v not in allowed_values
                   or k in allowed_values for k, v in aliases.items())
        ):
            fail(f"{filename} field {field!r} value_aliases must map new labels to allowed values")


def _validate_canonical_mapping_target(
    filename: str,
    source_field: object,
    target: object,
    quarantined: bool,
    fail: Callable[[str], None],
) -> None:
    if not isinstance(source_field, str) or not isinstance(target, str) or "." not in target:
        fail(f"{filename} mapping {source_field!r} -> {target!r} is malformed")
    table, column = target.split(".", 1)
    expected_table = "quarantined_source_metadata" if quarantined else None
    if table not in TABLE_SCHEMAS or column not in column_names(table):
        fail(f"{filename} mapping {source_field!r} has unknown target {target!r}")
    if quarantined and table != expected_table:
        fail(f"{filename} quarantined field {source_field!r} has trusted target {target!r}")
    if not quarantined and table == "quarantined_source_metadata":
        fail(f"{filename} trusted field {source_field!r} has quarantined target {target!r}")


def get_vaastav_source_schema(
    schema_id: str, season: str, configured_version: int | None = None
) -> dict[str, object]:
    """Resolve and validate a season-specific Vaastav source contract."""

    schema = VAASTAV_SOURCE_SCHEMAS.get(schema_id)
    if schema is None:
        supported = ", ".join(sorted(VAASTAV_SOURCE_SCHEMAS))
        raise FPLValidationError(
            f"unknown Vaastav source schema {schema_id!r}; available schema IDs: {supported}; "
            "corrective action: add a reviewed schema definition or select an existing ID"
        )
    validate_vaastav_source_schema(schema, season)
    if schema["schema_id"] != schema_id:
        raise FPLValidationError(
            f"Vaastav source schema registry key {schema_id!r} conflicts with declared "
            f"schema_id {schema['schema_id']!r}; corrective action: make the IDs identical"
        )
    if season not in schema["applicable_seasons"]:
        seasons = ", ".join(schema["applicable_seasons"])
        raise FPLValidationError(
            f"Vaastav source schema {schema_id!r} does not support season {season!r}; "
            f"applicable seasons: {seasons}"
        )
    if configured_version is not None and configured_version != schema["schema_version"]:
        raise FPLValidationError(
            f"Vaastav source schema {schema_id!r} version mismatch: configured "
            f"{configured_version}, registry {schema['schema_version']}"
        )
    return schema
