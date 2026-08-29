"""Small representative payloads used by unit tests."""


def bootstrap_payload() -> dict:
    return {
        "elements": [
            {
                "id": 101,
                "first_name": "Ada",
                "second_name": "Striker",
                "web_name": "Ada",
                "team": 1,
                "element_type": 4,
                "status": "a",
                "now_cost": 75,
                "selected_by_percent": "12.3",
                "total_points": 42,
                "event_points": 6,
                "minutes": 720,
                "starts": 8,
                "goals_scored": 5,
                "assists": 2,
                "clean_sheets": 1,
                "goals_conceded": 8,
                "own_goals": 0,
                "penalties_saved": 0,
                "penalties_missed": 0,
                "yellow_cards": 1,
                "red_cards": 0,
                "saves": 0,
                "bonus": 7,
                "bps": 144,
                "influence": "80.0",
                "creativity": "40.0",
                "threat": "120.0",
                "ict_index": "24.0",
                "expected_goals": "4.50",
                "expected_assists": "1.80",
                "expected_goal_involvements": "6.30",
                "expected_goals_conceded": "0.00",
                "chance_of_playing_next_round": None,
                "news": "",
                "news_added": None,
            }
        ],
        "teams": [
            {
                "id": 1,
                "name": "North City",
                "short_name": "NOR",
                "code": 11,
                "strength": 4,
            },
            {
                "id": 2,
                "name": "South United",
                "short_name": "SOU",
                "code": 22,
                "strength": 3,
            },
        ],
        "element_types": [
            {"id": 4, "singular_name": "Forward", "singular_name_short": "FWD"}
        ],
    }


def fixtures_payload() -> list[dict]:
    return [
        {
            "id": 501,
            "code": 9001,
            "event": 3,
            "kickoff_time": "2026-08-29T14:00:00Z",
            "started": False,
            "finished": False,
            "provisional_start_time": False,
            "team_h": 1,
            "team_a": 2,
            "team_h_score": None,
            "team_a_score": None,
            "team_h_difficulty": 2,
            "team_a_difficulty": 4,
            "minutes": 0,
        }
    ]
