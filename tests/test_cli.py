import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fpl_ai.cli import build_parser, main
from fpl_ai.historical_pipeline import HistoricalPipelineResult
from fpl_ai.pipeline import PipelineResult


class HistoricalCliTests(unittest.TestCase):
    def test_historical_arguments_have_unique_destinations(self) -> None:
        args = build_parser().parse_args(
            ["historical", "--season", "2024-25", "--output-dir", "history", "--timeout", "12"]
        )

        self.assertIsNone(args.current_output_dir)
        self.assertIsNone(args.current_timeout)
        self.assertEqual(args.historical_output_dir, Path("history"))
        self.assertEqual(args.historical_timeout, 12.0)

    @patch("fpl_ai.cli.run_historical_pipeline")
    def test_normal_historical_invocation_uses_historical_values(self, run) -> None:
        run.return_value = HistoricalPipelineResult(
            season="2024-25",
            version="v-test",
            raw_dir=Path("raw"),
            processed_dir=Path("processed"),
            row_counts={},
            snapshot_gameweeks=0,
            missing_snapshot_gameweeks=(),
        )
        with redirect_stdout(io.StringIO()):
            result = main(
                ["historical", "--season", "2024-25", "--output-dir", "history", "--timeout", "12"]
            )

        self.assertEqual(result, 0)
        run.assert_called_once_with("2024-25", Path("history"), timeout=12.0)

    def test_conflicting_parent_and_historical_values_are_rejected(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors), self.assertRaisesRegex(SystemExit, "2"):
            main(
                [
                    "--output-dir",
                    "current-data",
                    "historical",
                    "--season",
                    "2024-25",
                    "--output-dir",
                    "historical-data",
                ]
            )

        self.assertIn("conflicting --output-dir values", errors.getvalue())

    def test_parent_output_dir_before_historical_remains_supported(self) -> None:
        args = build_parser().parse_args(
            ["--output-dir", "history", "historical", "--season", "2024-25"]
        )

        self.assertEqual(args.current_output_dir, Path("history"))
        self.assertIsNone(args.historical_output_dir)

    @patch("fpl_ai.cli.FPLClient")
    @patch("fpl_ai.cli.run_pipeline")
    def test_existing_current_invocation_keeps_its_own_arguments(
        self, run, client
    ) -> None:
        run.return_value = PipelineResult(
            snapshot_id="test",
            raw_dir=Path("raw"),
            processed_dir=Path("processed"),
            player_count=1,
            team_count=2,
            fixture_count=3,
        )
        with redirect_stdout(io.StringIO()):
            result = main(["--output-dir", "current", "--timeout", "8"])

        self.assertEqual(result, 0)
        client.assert_called_once_with(
            base_url="https://fantasy.premierleague.com/api", timeout=8.0
        )
        run.assert_called_once_with(Path("current"), client=client.return_value)


if __name__ == "__main__":
    unittest.main()
