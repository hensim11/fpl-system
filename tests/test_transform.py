import unittest

from fpl_ai.transform import (
    FIXTURE_COLUMNS,
    PLAYER_COLUMNS,
    TEAM_COLUMNS,
    transform_fixtures,
    transform_players,
    transform_teams,
)
from tests.sample_data import bootstrap_payload, fixtures_payload


class TransformTests(unittest.TestCase):
    def test_player_row_is_enriched_with_team_and_position(self) -> None:
        row = transform_players(bootstrap_payload())[0]

        self.assertEqual(list(row), PLAYER_COLUMNS)
        self.assertEqual(row["team_name"], "North City")
        self.assertEqual(row["position_short_name"], "FWD")
        self.assertEqual(row["expected_goals"], "4.50")

    def test_team_table_has_stable_columns_and_all_teams(self) -> None:
        rows = transform_teams(bootstrap_payload())

        self.assertEqual(len(rows), 2)
        self.assertEqual(list(rows[0]), TEAM_COLUMNS)
        self.assertIsNone(rows[0]["played"])

    def test_fixture_row_has_readable_team_names(self) -> None:
        row = transform_fixtures(fixtures_payload(), bootstrap_payload())[0]

        self.assertEqual(list(row), FIXTURE_COLUMNS)
        self.assertEqual(row["home_team_name"], "North City")
        self.assertEqual(row["away_team_name"], "South United")
        self.assertEqual(row["gameweek"], 3)


if __name__ == "__main__":
    unittest.main()
