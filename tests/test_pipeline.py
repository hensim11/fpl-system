import csv
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from fpl_ai.pipeline import run_pipeline
from tests.sample_data import bootstrap_payload, fixtures_payload


class FakeClient:
    base_url = "https://example.test/api"

    def get_bootstrap(self) -> dict:
        return bootstrap_payload()

    def get_fixtures(self) -> list[dict]:
        return fixtures_payload()


class PipelineTests(unittest.TestCase):
    def test_pipeline_separates_raw_and_processed_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = run_pipeline(
                Path(temp_dir),
                client=FakeClient(),
                now=datetime(2026, 8, 29, 12, 30, tzinfo=timezone.utc),
            )

            self.assertEqual(result.snapshot_id, "20260829T123000Z")
            self.assertTrue((result.raw_dir / "bootstrap-static.json").is_file())
            self.assertTrue((result.raw_dir / "fixtures.json").is_file())
            self.assertTrue((result.processed_dir / "players.csv").is_file())
            self.assertTrue((result.processed_dir / "teams.csv").is_file())
            self.assertTrue((result.processed_dir / "fixtures.csv").is_file())

            with (result.processed_dir / "players.csv").open(newline="") as handle:
                player_rows = list(csv.DictReader(handle))
            self.assertEqual(player_rows[0]["web_name"], "Ada")

            manifest = json.loads(
                (result.processed_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["row_counts"], {"players": 1, "teams": 2, "fixtures": 1})
            self.assertEqual(
                manifest["sources"]["fixtures"],
                "https://example.test/api/fixtures/",
            )


if __name__ == "__main__":
    unittest.main()
