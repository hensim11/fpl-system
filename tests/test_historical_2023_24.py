"""Pinned 2023/24 shapes and cross-season pipeline regression checks (offline)."""

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import canonical_json_bytes, sha256_bytes
from fpl_ai.historical_pipeline import (
    _validate_points_settlement_snapshot,
    create_build_identity,
    load_source_catalogue,
    run_historical_pipeline,
)
from fpl_ai.historical_schema import get_vaastav_source_schema
from fpl_ai.historical_transform import parse_utc, read_source_csv
from tests.test_historical_pipeline import synthetic_sources

FIXTURES = Path(__file__).parent / "fixtures" / "historical_2023_24"


def csv_data(columns, rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode()


class Historical202324Tests(unittest.TestCase):
    def setUp(self):
        self.schema = get_vaastav_source_schema("vaastav-2023-24-v1", "2023-24", 1)

    def test_real_headers_and_rows_execute_without_schema_drift(self):
        for filename, contract in self.schema["files"].items():
            with self.subTest(filename=filename):
                data = (FIXTURES / filename).read_bytes()
                rows, audit = read_source_csv(data, filename, self.schema, include_schema_audit=True)
                header = next(csv.reader(io.StringIO(data.decode())))
                self.assertEqual(header, contract["known_column_order"])
                self.assertEqual(len(rows), 1)
                self.assertEqual(audit["unexpected_columns"], [])
                self.assertEqual(audit["required_columns_missing"], [])
                self.assertTrue(audit["known_column_order_matches"])
                self.assertNotIn("xP", rows[0]["trusted"])
                self.assertNotIn("xP", rows[0]["quarantined"])
        contract = self.schema["files"]["merged_gw.csv"]
        self.assertNotIn("modified", contract["quarantined_columns"])
        self.assertFalse(any(c.startswith("mng_") for c in contract["known_column_order"]))

    def test_missing_optional_values_stay_null_and_xp_stays_forbidden(self):
        filename = "merged_gw.csv"
        with (FIXTURES / filename).open() as stream:
            raw = list(csv.DictReader(stream))
        columns = [c for c in raw[0] if c != "expected_goals"]
        raw[0]["xP"] = "not a trusted number"
        rows, audit = read_source_csv(csv_data(columns, raw), filename, self.schema, include_schema_audit=True)
        self.assertIsNone(rows[0]["trusted"]["expected_goals"])
        self.assertEqual(audit["optional_columns_absent"], ["expected_goals"])
        self.assertEqual(audit["forbidden_columns_encountered"], ["xP"])
        self.assertNotIn("modified", rows[0]["quarantined"])

    def test_real_shape_rejects_manager_positions_invalid_types_and_missing_required(self):
        filename = "merged_gw.csv"
        with (FIXTURES / filename).open() as stream:
            row = next(csv.DictReader(stream))
        for field, value in [("position", "AM"), ("minutes", "1.5"), ("was_home", "yes"), ("expected_goals", "NaN")]:
            with self.subTest(field=field):
                changed = dict(row, **{field: value})
                with self.assertRaises(FPLValidationError):
                    read_source_csv(csv_data(list(row), [changed]), filename, self.schema)
        with self.assertRaisesRegex(FPLValidationError, "missing required"):
            read_source_csv(csv_data([c for c in row if c != "fixture"], [row]), filename, self.schema)

    def test_newer_columns_remain_unexpected_in_older_schema(self):
        filename = "merged_gw.csv"
        with (FIXTURES / filename).open() as stream:
            row = next(csv.DictReader(stream))
        for field in ["modified", "mng_win", "unknown_stat"]:
            with self.subTest(field=field), self.assertRaisesRegex(FPLValidationError, "unexpected columns"):
                read_source_csv(csv_data([*row, field], [dict(row, **{field: "0"})]), filename, self.schema)

    def test_schema_is_season_scoped_and_2024_build_contract_is_unchanged(self):
        with self.assertRaises(FPLValidationError):
            get_vaastav_source_schema("vaastav-2023-24-v1", "2024-25", 1)
        catalogue = load_source_catalogue()
        identity = create_build_identity("2024-25", catalogue["seasons"]["2024-25"], catalogue["schema_version"])
        self.assertEqual(sha256_bytes(canonical_json_bytes(identity)), "1fbdcc84c93d92367c3f6f2a0b39d039dc04403980bb100491410523c62f9d86")
        baseline = get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
        self.assertIn("modified", baseline["files"]["merged_gw.csv"]["quarantined_columns"])
        self.assertIn("AM", baseline["files"]["merged_gw.csv"]["type_expectations"]["position"]["allowed_values"])

    def test_observed_final_settlement_requires_later_capture(self):
        evidence = json.loads((FIXTURES / "settlement_events.json").read_text())
        deadline = parse_utc("2024-05-19T13:30:00Z", "deadline")
        for capture in evidence:
            path = capture["path"]
            args = (capture["payload"], 38, deadline, parse_utc(capture["capture"], "capture"), path)
            if path.endswith("0121.json.xz"):
                with self.assertRaisesRegex(FPLValidationError, "finished and data_checked"):
                    _validate_points_settlement_snapshot(*args)
            else:
                _validate_points_settlement_snapshot(*args)
        config = load_source_catalogue()["seasons"]["2023-24"]
        self.assertEqual(config["sources"]["fplcache"]["points_settlement_snapshot_path"], evidence[1]["path"])
        self.assertEqual(config["reconciliation"]["total_points"]["minimum_coverage_ratio"], 1.0)

    def test_older_shape_runs_generic_pipeline_and_reuses_without_writes(self):
        values, catalogue = synthetic_sources()
        config = catalogue["seasons"].pop("2024-25")
        catalogue["seasons"]["2023-24"] = config
        config["vaastav_source_schema"]["schema_id"] = "vaastav-2023-24-v1"
        catalogue = json.loads(json.dumps(catalogue).replace("data/2024-25/", "data/2023-24/"))
        converted = {}
        for url, data in values.items():
            url = url.replace("data/2024-25/", "data/2023-24/")
            if url.endswith(".csv"):
                name = url.rsplit("/", 1)[1]
                data = csv_data(self.schema["files"][name]["known_column_order"], list(csv.DictReader(io.StringIO(data.decode()))))
            converted[url] = data
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "sources.json"
            path.write_text(json.dumps(catalogue))
            result = run_historical_pipeline("2023-24", root, fetcher=converted.__getitem__, source_catalogue_path=path)
            with (result.processed_dir / "quarantined_source_metadata.csv").open() as stream:
                self.assertTrue(all(row["modified"] == "" for row in csv.DictReader(stream)))
            report = json.loads((result.processed_dir / "total_points_reconciliation.json").read_text())
            self.assertEqual(report["coverage_ratio"], 1.0)
            self.assertEqual(report["mismatching_row_count"], 0)
            before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}
            def no_network(url):
                self.fail(f"unexpected fetch: {url}")
            reused = run_historical_pipeline("2023-24", root, fetcher=no_network, source_catalogue_path=path)
            self.assertTrue(reused.reused)
            self.assertEqual(before, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()})
