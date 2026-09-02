import csv
import io
import json
import lzma
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from fpl_ai.errors import FPLValidationError
from fpl_ai.historical_io import (
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
)
from fpl_ai.historical_pipeline import (
    create_build_identity,
    create_reconciliation_provenance,
    load_historical_build,
    run_historical_pipeline,
)
from fpl_ai.historical_schema import (
    POST_EVENT_FIXTURE_CONTEXT_FIELDS,
    SNAPSHOT_COLUMNS,
    VAASTAV_2024_25_SOURCE_COLUMNS,
    get_vaastav_source_schema,
    validate_vaastav_source_schema,
)
from fpl_ai.historical_transform import (
    parse_utc,
    read_source_csv,
    transform_snapshot_elements,
)
from fpl_ai.historical_validation import reconcile_total_points


VAASTAV_REVISION = "a" * 40
CACHE_REVISION = "b" * 40


def csv_bytes(filename: str, rows: list[dict[str, object]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream, fieldnames=VAASTAV_2024_25_SOURCE_COLUMNS[filename]
    )
    writer.writeheader()
    for row in rows:
        full = {field: "" for field in VAASTAV_2024_25_SOURCE_COLUMNS[filename]}
        full.update(row)
        writer.writerow(full)
    return stream.getvalue().encode()


def snapshot_bytes(
    *,
    gameweek_one_deadline: str = "2024-08-16T18:00:00Z",
    next_gameweek: int | None = 1,
    finished_and_checked: tuple[int, ...] = (),
    element_101_team: int = 1,
    element_101_position: int = 4,
    element_101_event_points: int = 2,
) -> bytes:
    payload = {
        "events": [
            {
                "id": 1,
                "deadline_time": gameweek_one_deadline,
                "is_next": next_gameweek == 1,
                "finished": 1 in finished_and_checked,
                "data_checked": 1 in finished_and_checked,
            },
            {
                "id": 2,
                "deadline_time": "2024-08-23T18:00:00Z",
                "is_next": next_gameweek == 2,
                "finished": 2 in finished_and_checked,
                "data_checked": 2 in finished_and_checked,
            },
            {
                "id": 3,
                "deadline_time": "2024-08-30T18:00:00Z",
                "is_next": next_gameweek == 3,
                "finished": 3 in finished_and_checked,
                "data_checked": 3 in finished_and_checked,
            },
        ],
        "teams": [
            {"id": 1, "code": 11, "name": "North", "short_name": "NOR"},
            {"id": 2, "code": 22, "name": "South", "short_name": "SOU"},
        ],
        "element_types": [
            {"id": 1, "singular_name": "Goalkeeper", "singular_name_short": "GK"},
            {"id": 3, "singular_name": "Midfielder", "singular_name_short": "MID"},
            {"id": 4, "singular_name": "Forward", "singular_name_short": "FWD"},
        ],
        "elements": [
            {
                "id": 101,
                "code": 1001,
                "team": element_101_team,
                "element_type": element_101_position,
                "event_points": element_101_event_points,
                "now_cost": 75,
                "selected_by_percent": "10.5",
                "transfers_in_event": 25,
                "transfers_out_event": 3,
                "status": "a",
                "chance_of_playing_this_round": None,
                "chance_of_playing_next_round": None,
                "news": "",
                "news_added": None,
                "ep_next": "4.2",
                "corners_and_indirect_freekicks_order": 2,
                "direct_freekicks_order": None,
                "penalties_order": 1,
            },
            {
                "id": 102,
                "code": 1002,
                "team": 2,
                "element_type": 1,
                "event_points": 2,
                "now_cost": 50,
                "selected_by_percent": None,
                "transfers_in_event": None,
                "transfers_out_event": None,
                "status": "i",
                "chance_of_playing_this_round": None,
                "chance_of_playing_next_round": 0,
                "news": "Injured",
                "news_added": "2024-08-15T12:00:00Z",
                "ep_next": None,
            },
        ],
    }
    return lzma.compress(json.dumps(payload).encode())


def fixture_row(fixture: int, kickoff: str, home: int, away: int) -> dict[str, object]:
    return {
        "code": 9000 + fixture,
        "event": 1,
        "finished": True,
        "finished_provisional": True,
        "id": fixture,
        "kickoff_time": kickoff,
        "minutes": 90,
        "provisional_start_time": False,
        "started": True,
        "team_a": away,
        "team_a_score": 0,
        "team_h": home,
        "team_h_score": 1,
        "stats": "[]",
        "team_h_difficulty": 2,
        "team_a_difficulty": 4,
        "pulse_id": fixture,
    }


def fact_row(
    element: int,
    fixture: int,
    kickoff: str,
    was_home: bool,
    opponent: int,
    position: str,
    minutes: int,
) -> dict[str, object]:
    return {
        "name": f"Player {element}",
        "position": position,
        "team": "North" if element == 101 else "South",
        "xP": "99.9",
        "assists": 0,
        "bonus": 0,
        "bps": 5,
        "clean_sheets": 0,
        "creativity": "0.0",
        "element": element,
        "expected_assists": "0.0",
        "expected_goal_involvements": "0.0",
        "expected_goals": "0.0",
        "expected_goals_conceded": "0.0",
        "fixture": fixture,
        "goals_conceded": 0,
        "goals_scored": 0,
        "ict_index": "0.0",
        "influence": "0.0",
        "kickoff_time": kickoff,
        "minutes": minutes,
        "modified": False,
        "opponent_team": opponent,
        "own_goals": 0,
        "penalties_missed": 0,
        "penalties_saved": 0,
        "red_cards": 0,
        "round": 1,
        "saves": 0,
        "selected": 100,
        "starts": 1 if minutes else 0,
        "team_a_score": 0,
        "team_h_score": 1,
        "threat": "0.0",
        "total_points": 2 if minutes else 0,
        "transfers_balance": 1,
        "transfers_in": 2,
        "transfers_out": 1,
        "value": 75,
        "was_home": was_home,
        "yellow_cards": 0,
        "GW": 1,
    }


def synthetic_sources() -> tuple[dict[str, bytes], dict]:
    paths = {
        "merged": "data/2024-25/gws/merged_gw.csv",
        "players": "data/2024-25/players_raw.csv",
        "teams": "data/2024-25/teams.csv",
        "fixtures": "data/2024-25/fixtures.csv",
    }
    kickoff_one = "2024-08-17T14:00:00Z"
    kickoff_two = "2024-08-20T18:45:00Z"
    players = [
        {
            "id": 101,
            "code": 1001,
            "first_name": "Ada",
            "second_name": "Forward",
            "web_name": "Ada",
            "element_type": 4,
            "team": 1,
        },
        {
            "id": 102,
            "code": 1002,
            "first_name": "Bea",
            "second_name": "Keeper",
            "web_name": "Bea",
            "element_type": 1,
            "team": 2,
        },
    ]
    teams = [
        {"id": 1, "code": 11, "name": "North", "short_name": "NOR"},
        {"id": 2, "code": 22, "name": "South", "short_name": "SOU"},
    ]
    fixtures = [
        fixture_row(501, kickoff_one, 1, 2),
        fixture_row(502, kickoff_two, 2, 1),
    ]
    facts = [
        fact_row(101, 501, kickoff_one, True, 2, "FWD", 90),
        fact_row(101, 502, kickoff_two, False, 2, "FWD", 0),
        fact_row(102, 501, kickoff_one, False, 1, "GK", 90),
    ]
    valid_path = "cache/2024/8/16/1600.json.xz"
    wrong_deadline_path = "cache/2024/8/16/1700.json.xz"
    gameweek_two_path = "cache/2024/8/23/1700.json.xz"
    missing_gw_path = "cache/2024/8/30/1700.json.xz"
    post_deadline_path = "cache/2024/8/30/1900.json.xz"
    settlement_path = "cache/2024/8/31/0200.json.xz"
    tree = {
        "truncated": False,
        "tree": [
            {"path": path, "type": "blob"}
            for path in (
                valid_path,
                wrong_deadline_path,
                gameweek_two_path,
                post_deadline_path,
                missing_gw_path,
            )
        ],
    }
    config = {
        "schema_version": 7,
        "seasons": {
            "2024-25": {
                "vaastav_source_schema": {
                    "schema_id": "vaastav-2024-25-v1",
                    "schema_version": 1,
                },
                "reconciliation": {
                    "total_points": {
                        "policy_version": 2,
                        "mode": "required",
                        "minimum_coverage_ratio": 1.0,
                        "canonical_source": {
                            "provider_key": "vaastav",
                            "source_path": paths["merged"],
                            "field": "total_points",
                            "grain": "player_fixture",
                            "gameweek_aggregation": "sum_by_season_gameweek_element",
                        },
                        "comparison_source": {
                            "provider_key": "fplcache",
                            "field": "elements[].event_points",
                            "settlement_strategy": "next_accepted_deadline_snapshot_plus_final_settlement",
                            "require_event_finished": True,
                            "require_data_checked": True,
                        },
                    }
                },
                "expected_gameweeks": [1, 2, 3],
                "expected_counts": {
                    "fixtures": 2,
                    "player_fixture_facts": 3,
                    "distinct_fact_elements": 2,
                    "fixture_gameweeks": 1,
                },
                "sources": {
                    "vaastav": {
                        "provider": "Synthetic Vaastav",
                        "repository": "https://example.test/vaastav",
                        "configured_ref": VAASTAV_REVISION,
                        "resolved_commit_sha": VAASTAV_REVISION,
                        "raw_base_url": f"https://example.test/vaastav/{VAASTAV_REVISION}",
                        "files": list(paths.values()),
                    },
                    "fplcache": {
                        "provider": "Synthetic fplcache",
                        "repository": "https://example.test/fplcache",
                        "configured_ref": CACHE_REVISION,
                        "resolved_commit_sha": CACHE_REVISION,
                        "tree_url": f"https://example.test/fplcache/tree/{CACHE_REVISION}",
                        "raw_base_url": f"https://example.test/fplcache/{CACHE_REVISION}",
                        "archive_path_pattern": "^cache/(\\d{4})/(\\d{1,2})/(\\d{1,2})/(\\d{2})(\\d{2})\\.json\\.xz$",
                        "capture_timezone": "UTC",
                        "reference_snapshot_path": valid_path,
                        "points_settlement_snapshot_path": settlement_path,
                    },
                },
            }
        },
    }
    values = {
        f"https://example.test/vaastav/{VAASTAV_REVISION}/{paths['merged']}": csv_bytes("merged_gw.csv", facts),
        f"https://example.test/vaastav/{VAASTAV_REVISION}/{paths['players']}": csv_bytes("players_raw.csv", players),
        f"https://example.test/vaastav/{VAASTAV_REVISION}/{paths['teams']}": csv_bytes("teams.csv", teams),
        f"https://example.test/vaastav/{VAASTAV_REVISION}/{paths['fixtures']}": csv_bytes("fixtures.csv", fixtures),
        f"https://example.test/fplcache/tree/{CACHE_REVISION}": json.dumps(tree).encode(),
        f"https://example.test/fplcache/{CACHE_REVISION}/{valid_path}": snapshot_bytes(),
        f"https://example.test/fplcache/{CACHE_REVISION}/{wrong_deadline_path}": snapshot_bytes(
            gameweek_one_deadline="2024-08-16T17:59:00Z"
        ),
        f"https://example.test/fplcache/{CACHE_REVISION}/{gameweek_two_path}": snapshot_bytes(
            next_gameweek=2,
            finished_and_checked=(1,),
            element_101_team=2,
            element_101_position=3,
        ),
        f"https://example.test/fplcache/{CACHE_REVISION}/{post_deadline_path}": snapshot_bytes(),
        f"https://example.test/fplcache/{CACHE_REVISION}/{missing_gw_path}": snapshot_bytes(
            next_gameweek=None
        ),
        f"https://example.test/fplcache/{CACHE_REVISION}/{settlement_path}": snapshot_bytes(
            next_gameweek=None,
            finished_and_checked=(3,),
        ),
    }
    return values, config


def reconciliation_policy(
    *, mode: str = "required", threshold: float = 1.0
) -> dict[str, object]:
    return {
        "policy_version": 2,
        "mode": mode,
        "minimum_coverage_ratio": threshold,
        "canonical_source": {
            "provider_key": "vaastav",
            "source_path": "data/synthetic/gws/merged_gw.csv",
            "field": "total_points",
            "grain": "player_fixture",
            "gameweek_aggregation": "sum_by_season_gameweek_element",
        },
        "comparison_source": {
            "provider_key": "fplcache",
            "field": "elements[].event_points",
            "settlement_strategy": "synthetic",
            "require_event_finished": True,
            "require_data_checked": True,
        },
    }


def reconcile_for_test(
    facts: list[dict[str, object]],
    snapshots: dict[int, tuple[dict, str, str]],
    *,
    mode: str = "required",
    threshold: float = 1.0,
) -> dict[str, object]:
    policy = reconciliation_policy(mode=mode, threshold=threshold)
    source_identity = {"requested_season": "synthetic", "immutable_artifacts": []}
    build_identity = {"transformation_contract_version": "test"}
    return reconcile_total_points(
        facts,
        snapshots,
        policy,
        {
            "season": "synthetic",
            "canonical_source": {"source_paths": ["data/synthetic/gws/merged_gw.csv"]},
            "comparison_source": {
                "source_paths": sorted(path for _, path, _ in snapshots.values())
            },
            "vaastav_source_schema": {"schema_id": "synthetic", "schema_version": 1},
            "reconciliation_policy": policy,
        },
        artifact_created_at_utc="2025-06-01T00:00:00Z",
        source_identity=source_identity,
        source_identity_sha256=sha256_bytes(canonical_json_bytes(source_identity)),
        build_identity=build_identity,
        build_identity_sha256=sha256_bytes(canonical_json_bytes(build_identity)),
    )


class HistoricalPipelineTests(unittest.TestCase):
    def run_synthetic(self, root: Path):
        values, config = synthetic_sources()
        config_path = root / "sources.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        calls: list[str] = []

        def fetch(url: str) -> bytes:
            calls.append(url)
            return values[url]

        result = run_historical_pipeline(
            "2024-25",
            root / "data",
            fetcher=fetch,
            source_catalogue_path=config_path,
            now=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        return result, calls, config_path

    def test_pipeline_provenance_leakage_and_snapshot_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result, calls, _ = self.run_synthetic(Path(temporary))

            self.assertEqual(result.row_counts["player_fixture_facts"], 3)
            self.assertEqual(result.source_inventory_status, "frozen_per_build")
            self.assertEqual(result.snapshot_gameweeks, 2)
            self.assertEqual(result.missing_snapshot_gameweeks, (3,))

            with (result.processed_dir / "player_fixture_facts.csv").open(newline="") as handle:
                facts = list(csv.DictReader(handle))
                self.assertNotIn("xP", handle.readline() if False else facts[0])
            zero_minute = next(row for row in facts if row["fixture"] == "502")
            self.assertEqual(zero_minute["minutes"], "0")
            self.assertEqual(zero_minute["team_id_at_fixture"], "1")
            self.assertEqual(zero_minute["opponent_team_id_at_fixture"], "2")

            with (result.processed_dir / "player_deadline_snapshots.csv").open(newline="") as handle:
                snapshots = list(csv.DictReader(handle))
            self.assertEqual(len(snapshots), 4)
            self.assertEqual(
                {row["capture_time_utc"] for row in snapshots},
                {"2024-08-16T16:00:00Z", "2024-08-23T17:00:00Z"},
            )
            before_transfer = next(
                row for row in snapshots if row["element"] == "101" and row["gameweek"] == "1"
            )
            after_transfer = next(
                row for row in snapshots if row["element"] == "101" and row["gameweek"] == "2"
            )
            self.assertEqual(before_transfer["deadline_team_id"], "1")
            self.assertEqual(before_transfer["deadline_team_name"], "North")
            self.assertEqual(before_transfer["deadline_position"], "FWD")
            self.assertEqual(after_transfer["deadline_team_id"], "2")
            self.assertEqual(after_transfer["deadline_team_name"], "South")
            self.assertEqual(after_transfer["deadline_position"], "MID")
            injured = next(
                row for row in snapshots if row["element"] == "102" and row["gameweek"] == "1"
            )
            self.assertEqual(injured["selected_by_percent"], "")
            self.assertEqual(injured["expected_points_next_gameweek"], "")

            with (result.processed_dir / "gameweeks.csv").open(newline="") as handle:
                gameweeks = list(csv.DictReader(handle))
            self.assertEqual(gameweeks[2]["valid_predeadline_snapshot"], "False")
            self.assertEqual(gameweeks[2]["hours_before_deadline"], "")
            self.assertFalse(any("1900.json.xz" in url for url in calls))
            self.assertTrue(any("1700.json.xz" in url for url in calls))

            manifest = json.loads((result.processed_dir / "manifest.json").read_text())
            vaastav_identity = manifest["source_identity"]["sources"]["vaastav"]
            self.assertEqual(vaastav_identity["configured_ref"], VAASTAV_REVISION)
            self.assertEqual(vaastav_identity["resolved_commit_sha"], VAASTAV_REVISION)
            self.assertEqual(vaastav_identity["requested_season"], "2024-25")
            self.assertEqual(len(manifest["source_identity_sha256"]), 64)
            self.assertEqual(len(manifest["build_identity_sha256"]), 64)
            self.assertNotEqual(
                manifest["source_identity_sha256"], manifest["build_identity_sha256"]
            )
            self.assertEqual(manifest["artifact_inventory"]["generated_table_count"], 7)
            self.assertEqual(
                manifest["artifact_inventory"]["generated_artifact_count"],
                len(list(result.processed_dir.iterdir())),
            )
            for record in manifest["source_files"]:
                self.assertEqual(len(record["sha256"]), 64)
                self.assertGreater(record["byte_size"], 0)
                self.assertIn("retrieved_at_utc", record)
                self.assertIn("source_url", record)
                self.assertEqual(record["requested_season"], "2024-25")
                self.assertEqual(len(record["resolved_commit_sha"]), 40)
            catalogue = json.loads(
                (Path(temporary) / "data" / "historical" / "catalogue.json").read_text()
            )
            latest = catalogue["seasons"]["2024-25"]
            self.assertEqual(
                latest["source_identity_sha256"], manifest["source_identity_sha256"]
            )
            self.assertEqual(
                latest["build_identity_sha256"], manifest["build_identity_sha256"]
            )
            self.assertEqual(
                latest["source_identity"]["sources"]["fplcache"]["resolved_commit_sha"],
                CACHE_REVISION,
            )
            report = json.loads((result.processed_dir / "data_quality_report.json").read_text())
            self.assertTrue(report["passed"])
            self.assertEqual(report["duplicate_counts"]["player_fixture_facts"], 0)
            self.assertEqual(report["leakage_contract"]["vaastav_xP"], "excluded from every output table")
            self.assertEqual(report["total_points_reconciliation"]["compared_records"], 2)
            self.assertEqual(report["total_points_reconciliation"]["mismatching_records"], 0)
            self.assertEqual(report["build_identity_sha256"], manifest["build_identity_sha256"])
            reconciliation_artifact = json.loads(
                (result.processed_dir / "total_points_reconciliation.json").read_text()
            )
            reconciliation_file = next(
                item
                for item in manifest["processed_files"]
                if item["path"] == "total_points_reconciliation.json"
            )
            self.assertEqual(len(reconciliation_file["sha256"]), 64)
            self.assertEqual(reconciliation_artifact["eligible_row_count"], 2)
            self.assertEqual(reconciliation_artifact["compared_row_count"], 2)
            self.assertEqual(reconciliation_artifact["unmatched_row_count"], 0)
            self.assertEqual(reconciliation_artifact["coverage_ratio"], 1.0)
            self.assertEqual(reconciliation_artifact["minimum_coverage_ratio"], 1.0)
            self.assertEqual(
                reconciliation_artifact["source_identity_sha256"],
                manifest["source_identity_sha256"],
            )
            self.assertEqual(
                reconciliation_artifact["build_identity_sha256"],
                manifest["build_identity_sha256"],
            )
            frozen_reference = manifest["frozen_source_inventory"]
            frozen_path = result.processed_dir / frozen_reference["path"]
            self.assertEqual(frozen_reference["sha256"], sha256_file(frozen_path))
            self.assertEqual(
                frozen_reference["source_identity_sha256"],
                manifest["source_identity_sha256"],
            )
            snapshot_column_names = {column.name for column in SNAPSHOT_COLUMNS}
            self.assertFalse(snapshot_column_names.intersection(POST_EVENT_FIXTURE_CONTEXT_FIELDS))
            self.assertFalse(
                {
                    column.name
                    for column in SNAPSHOT_COLUMNS
                    if column.information_class in {"post_event_fixture_context", "realised_outcome"}
                }
            )
            self.assertNotIn("home_score", snapshot_column_names)
            self.assertNotIn("finished", snapshot_column_names)

    def test_idempotent_rerun_uses_catalogue_without_network_or_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, _, config_path = self.run_synthetic(root)
            catalogue = root / "data" / "historical" / "catalogue.json"
            before = catalogue.read_bytes()
            manifest_before = (first.processed_dir / "manifest.json").read_bytes()

            def no_network(url: str) -> bytes:
                self.fail(f"idempotent rerun unexpectedly fetched {url}")

            second = run_historical_pipeline(
                "2024-25",
                root / "data",
                fetcher=no_network,
                source_catalogue_path=config_path,
                now=datetime(2025, 6, 2, tzinfo=timezone.utc),
            )
            self.assertTrue(second.reused)
            self.assertEqual(before, catalogue.read_bytes())
            self.assertEqual(manifest_before, (second.processed_dir / "manifest.json").read_bytes())

    def test_rerun_rejects_changed_immutable_raw_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result, _, config_path = self.run_synthetic(root)
            raw_file = next((result.raw_dir / "vaastav").rglob("merged_gw.csv"))
            raw_file.write_bytes(b"changed")
            with self.assertRaisesRegex(FPLValidationError, "failed checksum"):
                run_historical_pipeline(
                    "2024-25",
                    root / "data",
                    fetcher=lambda url: b"",
                    source_catalogue_path=config_path,
                )

    def test_duplicate_fact_key_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values, config = synthetic_sources()
            merged_url = next(url for url in values if url.endswith("merged_gw.csv"))
            rows = read_source_csv(
                values[merged_url],
                "merged_gw.csv",
                get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1),
            )
            rows.append(dict(rows[0]))
            values[merged_url] = csv_bytes("merged_gw.csv", rows)
            config_path = root / "sources.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(FPLValidationError, "duplicate player-fixture key"):
                run_historical_pipeline(
                    "2024-25",
                    root / "data",
                    fetcher=lambda url: values[url],
                    source_catalogue_path=config_path,
                )

    def test_source_schema_addition_is_rejected(self) -> None:
        original = csv_bytes("teams.csv", [{"id": 1, "code": 1, "name": "A", "short_name": "A"}])
        header, body = original.split(b"\r\n", 1)
        changed = header + b",new_field\r\n" + body.replace(b"\r\n", b",value\r\n")
        with self.assertRaisesRegex(FPLValidationError, "unexpected columns"):
            read_source_csv(
                changed,
                "teams.csv",
                get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1),
            )

    def test_moving_source_ref_is_rejected_before_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, config = synthetic_sources()
            config["seasons"]["2024-25"]["sources"]["vaastav"]["configured_ref"] = "main"
            config_path = root / "sources.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(FPLValidationError, "moving branch"):
                run_historical_pipeline(
                    "2024-25",
                    root / "data",
                    fetcher=lambda url: self.fail(f"unexpected download: {url}"),
                    source_catalogue_path=config_path,
                )

    def test_missing_deadline_identity_stays_null_without_season_end_fallback(self) -> None:
        payload = json.loads(lzma.decompress(snapshot_bytes()))
        del payload["elements"][0]["team"]
        del payload["elements"][0]["element_type"]
        rows = transform_snapshot_elements(
            "2024-25",
            1,
            payload,
            parse_utc("2024-08-16T16:00:00Z", "capture"),
            parse_utc("2024-08-16T18:00:00Z", "deadline"),
            "cache/example.json.xz",
            "c" * 64,
        )

        row = next(value for value in rows if value["element"] == 101)
        self.assertIsNone(row["deadline_team_id"])
        self.assertIsNone(row["deadline_team_name"])
        self.assertIsNone(row["deadline_position_id"])
        self.assertIsNone(row["deadline_position"])

    def test_total_points_disagreement_fails_quality_and_writes_identified_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values, config = synthetic_sources()
            comparison_url = next(
                url for url in values if url.endswith("cache/2024/8/23/1700.json.xz")
            )
            values[comparison_url] = snapshot_bytes(
                next_gameweek=2,
                finished_and_checked=(1,),
                element_101_team=2,
                element_101_position=3,
                element_101_event_points=3,
            )
            config_path = root / "sources.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            attempted_at = datetime(2025, 6, 1, 12, 30, tzinfo=timezone.utc)

            with self.assertRaisesRegex(
                FPLValidationError, "total_points.cross_source_reconciliation"
            ):
                run_historical_pipeline(
                    "2024-25",
                    root / "data",
                    fetcher=lambda url: values[url],
                    source_catalogue_path=config_path,
                    now=attempted_at,
                )

            failed = list((root / "data" / "historical" / "failed" / "2024-25").glob("*.json"))
            self.assertEqual(len(failed), 1)
            self.assertIn("20250601T123000.000000Z--quality-failed", failed[0].name)
            report = json.loads(failed[0].read_text())
            self.assertEqual(report["run_status"], "failed_quality_validation")
            self.assertFalse(report["catalogue_updated"])
            self.assertEqual(report["total_points_reconciliation"]["mismatching_records"], 1)
            mismatch = report["total_points_reconciliation"]["mismatches"][0]
            self.assertEqual(mismatch["canonical_vaastav_total_points"], 2)
            self.assertEqual(mismatch["comparison_fplcache_event_points"], 3)
            self.assertFalse((root / "data" / "historical" / "catalogue.json").exists())

    def test_reconciliation_sums_double_gameweek_fixture_points(self) -> None:
        facts = [
            {"season": "2024-25", "gameweek": 1, "element": 101, "total_points": 2},
            {"season": "2024-25", "gameweek": 1, "element": 101, "total_points": 0},
        ]
        payload = json.loads(
            lzma.decompress(snapshot_bytes(finished_and_checked=(1,)))
        )
        report = reconcile_for_test(
            facts, {1: (payload, "cache/settled.json.xz", "d" * 64)}
        )

        self.assertTrue(report["passed"])
        self.assertEqual(report["expected_records"], 1)
        self.assertEqual(report["matching_records"], 1)

    def test_required_reconciliation_unavailable_fails(self) -> None:
        facts = [
            {"season": "synthetic", "gameweek": 1, "element": 101, "total_points": 2}
        ]

        report = reconcile_for_test(facts, {})

        self.assertFalse(report["passed"])
        self.assertEqual(report["status"], "failed_unavailable")
        self.assertEqual(report["eligible_row_count"], 1)
        self.assertEqual(report["compared_row_count"], 0)
        self.assertEqual(report["unmatched_row_count"], 1)
        self.assertEqual(report["coverage_ratio"], 0.0)
        self.assertEqual(
            report["reasons_for_exclusion_or_unavailability"],
            {"no settled comparison snapshot": 1},
        )

    def test_optional_reconciliation_is_explicitly_skipped(self) -> None:
        facts = [
            {"season": "synthetic", "gameweek": 1, "element": 101, "total_points": 2}
        ]

        report = reconcile_for_test(facts, {}, mode="optional")

        self.assertTrue(report["passed"])
        self.assertEqual(report["configured_mode"], "optional")
        self.assertEqual(report["status"], "skipped_optional")
        self.assertIsNone(report["coverage_passed"])

    def test_reconciliation_threshold_boundary_and_counts(self) -> None:
        facts = [
            {"season": "synthetic", "gameweek": 1, "element": 101, "total_points": 2},
            {"season": "synthetic", "gameweek": 1, "element": 102, "total_points": 2},
        ]
        payload = json.loads(lzma.decompress(snapshot_bytes(finished_and_checked=(1,))))
        payload["elements"] = [payload["elements"][0]]
        snapshots = {1: (payload, "cache/settled.json.xz", "d" * 64)}

        below = reconcile_for_test(facts, snapshots, threshold=0.75)
        boundary = reconcile_for_test(facts, snapshots, threshold=0.5)

        self.assertEqual(below["eligible_row_count"], 2)
        self.assertEqual(below["compared_row_count"], 1)
        self.assertEqual(below["unmatched_row_count"], 1)
        self.assertEqual(below["coverage_ratio"], 0.5)
        self.assertFalse(below["coverage_passed"])
        self.assertFalse(below["passed"])
        self.assertEqual(below["status"], "failed_coverage")
        self.assertTrue(boundary["coverage_passed"])
        self.assertTrue(boundary["passed"])
        self.assertEqual(boundary["status"], "passed_partial")

    def test_invalid_reconciliation_threshold_fails_before_download(self) -> None:
        for threshold in (-0.01, 1.01, True):
            with self.subTest(threshold=threshold), tempfile.TemporaryDirectory() as temporary:
                _, config = synthetic_sources()
                config["seasons"]["2024-25"]["reconciliation"]["total_points"][
                    "minimum_coverage_ratio"
                ] = threshold
                config_path = Path(temporary) / "sources.json"
                config_path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaisesRegex(FPLValidationError, "between 0 and 1"):
                    run_historical_pipeline(
                        "2024-25",
                        Path(temporary) / "data",
                        source_catalogue_path=config_path,
                        fetcher=lambda url: self.fail(f"unexpected download: {url}"),
                    )

    def test_reconciliation_provenance_uses_selected_season_configuration(self) -> None:
        _, first_catalogue = synthetic_sources()
        first = first_catalogue["seasons"]["2024-25"]
        second = deepcopy(first)
        second["sources"]["vaastav"].update(
            {
                "provider": "Second outcomes",
                "repository": "https://second.test/outcomes",
                "configured_ref": "c" * 40,
                "resolved_commit_sha": "c" * 40,
            }
        )
        second["sources"]["fplcache"].update(
            {
                "provider": "Second cache",
                "repository": "https://second.test/cache",
                "configured_ref": "d" * 40,
                "resolved_commit_sha": "d" * 40,
            }
        )
        second["reconciliation"]["total_points"]["canonical_source"][
            "source_path"
        ] = "archive/2099-00/merged.csv"
        fake_schema = {
            "schema_id": "vaastav-2099-00-test-v1",
            "schema_version": 1,
        }

        first_provenance = create_reconciliation_provenance(
            "2024-25",
            first,
            {"schema_id": "synthetic-first-v1", "schema_version": 1},
            {1: ({}, "cache/first/settled.json.xz", "e" * 64)},
            "a" * 64,
        )
        provenance = create_reconciliation_provenance(
            "2099-00",
            second,
            fake_schema,
            {1: ({}, "cache/2099/settled.json.xz", "e" * 64)},
            "f" * 64,
        )

        encoded = json.dumps(provenance, sort_keys=True)
        self.assertEqual(first_provenance["season"], "2024-25")
        self.assertEqual(
            first_provenance["canonical_source"]["pinned_revision"],
            VAASTAV_REVISION,
        )
        self.assertNotEqual(
            first_provenance["canonical_source"]["source_paths"],
            provenance["canonical_source"]["source_paths"],
        )
        self.assertEqual(provenance["season"], "2099-00")
        self.assertEqual(
            provenance["canonical_source"]["source_paths"],
            ["archive/2099-00/merged.csv"],
        )
        self.assertEqual(provenance["canonical_source"]["pinned_revision"], "c" * 40)
        self.assertEqual(
            provenance["comparison_source"]["source_paths"],
            ["cache/2099/settled.json.xz"],
        )
        self.assertNotIn("2024-25", encoded)
        self.assertNotIn(VAASTAV_REVISION, encoded)
        self.assertNotIn(CACHE_REVISION, encoded)

    def test_real_2024_25_source_schema_accepts_known_shape(self) -> None:
        schema = get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
        for filename in VAASTAV_2024_25_SOURCE_COLUMNS:
            with self.subTest(filename=filename):
                rows, audit = read_source_csv(
                    csv_bytes(filename, [{}]),
                    filename,
                    schema,
                    include_schema_audit=True,
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(audit["unexpected_additions"], [])
                self.assertEqual(audit["missing_required_columns"], [])
                self.assertTrue(audit["known_column_order_matches"])

    def test_missing_required_source_column_fails_clearly(self) -> None:
        columns = [
            column
            for column in VAASTAV_2024_25_SOURCE_COLUMNS["teams.csv"]
            if column != "id"
        ]
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerow({column: "" for column in columns})
        value = stream.getvalue().encode()
        with self.assertRaisesRegex(FPLValidationError, "missing required columns=.*id"):
            read_source_csv(
                value,
                "teams.csv",
                get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1),
            )

    def test_missing_optional_metric_is_reported_and_remains_null(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values, config = synthetic_sources()
            merged_url = next(url for url in values if url.endswith("merged_gw.csv"))
            schema = get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
            rows = read_source_csv(values[merged_url], "merged_gw.csv", schema)
            columns = [
                column
                for column in VAASTAV_2024_25_SOURCE_COLUMNS["merged_gw.csv"]
                if column != "expected_goals"
            ]
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            values[merged_url] = stream.getvalue().encode()
            config_path = root / "sources.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            result = run_historical_pipeline(
                "2024-25",
                root / "data",
                source_catalogue_path=config_path,
                fetcher=lambda url: values[url],
                now=datetime(2025, 6, 1, tzinfo=timezone.utc),
            )

            with (result.processed_dir / "player_fixture_facts.csv").open(
                newline=""
            ) as handle:
                fact = next(csv.DictReader(handle))
            report = json.loads(
                (result.processed_dir / "data_quality_report.json").read_text()
            )
            self.assertEqual(fact["expected_goals"], "")
            self.assertEqual(
                report["source_schema_changes"]["merged_gw.csv"][
                    "missing_optional_columns"
                ],
                ["expected_goals"],
            )

    def test_unexpected_source_column_is_preserved_in_failed_quality_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values, config = synthetic_sources()
            teams_url = next(url for url in values if url.endswith("teams.csv"))
            text = values[teams_url].decode()
            lines = text.splitlines()
            lines[0] += ",new_field"
            lines[1:] = [line + ",value" for line in lines[1:]]
            values[teams_url] = ("\r\n".join(lines) + "\r\n").encode()
            config_path = root / "sources.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")

            with self.assertRaisesRegex(FPLValidationError, "vaastav.season_source_schema"):
                run_historical_pipeline(
                    "2024-25",
                    root / "data",
                    source_catalogue_path=config_path,
                    fetcher=lambda url: values[url],
                    now=datetime(2025, 6, 1, tzinfo=timezone.utc),
                )

            failed = next(
                (root / "data" / "historical" / "failed" / "2024-25").glob("*.json")
            )
            report = json.loads(failed.read_text())
            self.assertEqual(
                report["source_schema_changes"]["teams.csv"]["unexpected_additions"],
                ["new_field"],
            )

    def test_unknown_or_wrong_season_source_schema_fails_actionably(self) -> None:
        with self.assertRaisesRegex(FPLValidationError, "unknown Vaastav source schema"):
            get_vaastav_source_schema("missing-schema", "2024-25", 1)
        with self.assertRaisesRegex(FPLValidationError, "does not support season"):
            get_vaastav_source_schema("vaastav-2024-25-v1", "2023-24", 1)

    def test_forbidden_field_cannot_map_to_trusted_output(self) -> None:
        schema = deepcopy(
            get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
        )
        schema["files"]["merged_gw.csv"]["source_to_canonical_mappings"][
            "xP"
        ] = "player_deadline_snapshots.expected_points_next_gameweek"

        with self.assertRaisesRegex(
            FPLValidationError,
            "vaastav-2024-25-v1.*2024-25.*forbidden field 'xP'.*expected_points",
        ):
            validate_vaastav_source_schema(schema, "2024-25")

    def test_forbidden_required_or_optional_overlap_is_rejected(self) -> None:
        for category in ("required_columns", "optional_columns"):
            with self.subTest(category=category):
                schema = deepcopy(
                    get_vaastav_source_schema(
                        "vaastav-2024-25-v1", "2024-25", 1
                    )
                )
                schema["files"]["merged_gw.csv"][category].append("xP")
                with self.assertRaisesRegex(
                    FPLValidationError,
                    f"field 'xP'.*{category}.*forbidden_columns",
                ):
                    validate_vaastav_source_schema(schema, "2024-25")

    def test_schema_rejects_unknown_mapping_source_and_conflicting_target(self) -> None:
        unknown_source = deepcopy(
            get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
        )
        unknown_source["files"]["merged_gw.csv"][
            "source_to_canonical_mappings"
        ]["name"] = "player_fixture_facts.total_points"
        with self.assertRaisesRegex(
            FPLValidationError, "mapping source 'name' is not declared required or optional"
        ):
            validate_vaastav_source_schema(unknown_source, "2024-25")

        conflicting_target = deepcopy(
            get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
        )
        mappings = conflicting_target["files"]["merged_gw.csv"][
            "source_to_canonical_mappings"
        ]
        mappings["assists"] = mappings["goals_scored"]
        with self.assertRaisesRegex(
            FPLValidationError, "canonical target.*conflicting mappings"
        ):
            validate_vaastav_source_schema(conflicting_target, "2024-25")

    def test_schema_rejects_duplicate_declarations_and_malformed_definition(self) -> None:
        duplicate = deepcopy(
            get_vaastav_source_schema("vaastav-2024-25-v1", "2024-25", 1)
        )
        duplicate["files"]["merged_gw.csv"]["required_columns"].append(
            "element"
        )
        with self.assertRaisesRegex(
            FPLValidationError, "field 'element' is duplicated in required_columns"
        ):
            validate_vaastav_source_schema(duplicate, "2024-25")
        with self.assertRaisesRegex(FPLValidationError, "malformed.*expected an object"):
            validate_vaastav_source_schema([], "2024-25")

    def test_build_identity_is_deterministic_and_semantic(self) -> None:
        _, catalogue = synthetic_sources()
        config = catalogue["seasons"]["2024-25"]
        reordered = json.loads(json.dumps(config, sort_keys=True))
        with_metadata = deepcopy(reordered)
        with_metadata["retrieved_at_utc"] = "2099-01-01T00:00:00Z"
        with_metadata["output_dir"] = "/different/absolute/path"
        changed = deepcopy(config)
        changed["reconciliation"]["total_points"]["minimum_coverage_ratio"] = 0.5

        first = create_build_identity("2024-25", config, 7)
        same = create_build_identity("2024-25", reordered, 7)
        timestamp_only = create_build_identity("2024-25", with_metadata, 7)
        different = create_build_identity("2024-25", changed, 7)

        first_hash = sha256_bytes(canonical_json_bytes(first))
        self.assertEqual(first_hash, sha256_bytes(canonical_json_bytes(same)))
        self.assertEqual(first_hash, sha256_bytes(canonical_json_bytes(timestamp_only)))
        self.assertNotEqual(first_hash, sha256_bytes(canonical_json_bytes(different)))

    def test_same_sources_with_different_build_identity_do_not_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, _, config_path = self.run_synthetic(root)
            config = json.loads(config_path.read_text())
            config["seasons"]["2024-25"]["reconciliation"]["total_points"][
                "minimum_coverage_ratio"
            ] = 0.5
            config_path.write_text(json.dumps(config), encoding="utf-8")

            second = run_historical_pipeline(
                "2024-25",
                root / "data",
                source_catalogue_path=config_path,
                fetcher=lambda url: self.fail(f"existing raw data should satisfy {url}"),
                now=datetime(2025, 6, 2, tzinfo=timezone.utc),
            )

            self.assertNotEqual(first.version, second.version)
            self.assertNotEqual(first.processed_dir, second.processed_dir)
            self.assertTrue(first.processed_dir.is_dir())
            self.assertTrue(second.processed_dir.is_dir())
            first_manifest = json.loads((first.processed_dir / "manifest.json").read_text())
            second_manifest = json.loads((second.processed_dir / "manifest.json").read_text())
            self.assertEqual(
                first_manifest["source_identity_sha256"],
                second_manifest["source_identity_sha256"],
            )
            self.assertNotEqual(
                first_manifest["build_identity_sha256"],
                second_manifest["build_identity_sha256"],
            )

    def test_each_build_freezes_its_source_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_a, _, config_path = self.run_synthetic(root)
            manifest_a = json.loads((build_a.processed_dir / "manifest.json").read_text())
            inventory_a_path = (
                build_a.processed_dir
                / manifest_a["frozen_source_inventory"]["path"]
            )
            inventory_a_bytes = inventory_a_path.read_bytes()
            inventory_a_hash = sha256_file(inventory_a_path)

            shared_path = build_a.raw_dir / "source_manifest.json"
            shared = json.loads(shared_path.read_text())
            extra_bytes = b"later independently inventoried raw artifact\n"
            extra_relative = Path("vaastav/audit/later.txt")
            extra_path = build_a.raw_dir / extra_relative
            extra_path.parent.mkdir(parents=True, exist_ok=True)
            extra_path.write_bytes(extra_bytes)
            extra_record = {
                **shared["files"][0],
                "source_path": "audit/later.txt",
                "source_url": f"https://example.test/vaastav/{VAASTAV_REVISION}/audit/later.txt",
                "sha256": sha256_bytes(extra_bytes),
                "byte_size": len(extra_bytes),
                "raw_path": str(extra_relative),
            }
            shared["files"].append(extra_record)
            shared["files"].sort(
                key=lambda item: (item["provider_key"], item["source_path"])
            )
            atomic_write_json(shared_path, shared)

            config = json.loads(config_path.read_text())
            config["seasons"]["2024-25"]["reconciliation"]["total_points"][
                "minimum_coverage_ratio"
            ] = 0.5
            config_path.write_text(json.dumps(config), encoding="utf-8")
            build_b = run_historical_pipeline(
                "2024-25",
                root / "data",
                source_catalogue_path=config_path,
                fetcher=lambda url: self.fail(f"existing raw data should satisfy {url}"),
                now=datetime(2025, 6, 2, tzinfo=timezone.utc),
            )
            manifest_b = json.loads((build_b.processed_dir / "manifest.json").read_text())
            inventory_b_path = (
                build_b.processed_dir
                / manifest_b["frozen_source_inventory"]["path"]
            )
            inventory_b = json.loads(inventory_b_path.read_text())

            resolved_a_once = load_historical_build(
                "2024-25", build_a.version, root / "data"
            )
            resolved_a_twice = load_historical_build(
                "2024-25", build_a.version, root / "data"
            )
            resolved_b = load_historical_build(
                "2024-25", build_b.version, root / "data"
            )
            catalogue = json.loads(
                (root / "data" / "historical" / "catalogue.json").read_text()
            )
            recorded_builds = catalogue["seasons"]["2024-25"]["builds"]

            self.assertNotEqual(build_a.version, build_b.version)
            self.assertEqual(inventory_a_path.read_bytes(), inventory_a_bytes)
            self.assertEqual(sha256_file(inventory_a_path), inventory_a_hash)
            self.assertNotEqual(
                manifest_a["source_identity_sha256"],
                manifest_b["source_identity_sha256"],
            )
            self.assertTrue(
                any(item["source_path"] == "audit/later.txt" for item in inventory_b["files"])
            )
            self.assertEqual(resolved_a_once.source_inventory_status, "frozen_per_build")
            self.assertEqual(resolved_a_twice.processed_dir, build_a.processed_dir)
            self.assertEqual(resolved_b.source_inventory_status, "frozen_per_build")
            self.assertIn(build_a.version, recorded_builds)
            self.assertIn(build_b.version, recorded_builds)
            self.assertEqual(
                recorded_builds[build_a.version]["frozen_source_inventory"]["sha256"],
                inventory_a_hash,
            )

    def test_legacy_build_lookup_is_read_only_and_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build, _, _ = self.run_synthetic(root)
            manifest_path = build.processed_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            inventory_path = (
                build.processed_dir / manifest["frozen_source_inventory"]["path"]
            )
            inventory_path.unlink()
            manifest.pop("frozen_source_inventory")
            manifest["processed_files"] = [
                record
                for record in manifest["processed_files"]
                if record["path"] != "source_inventory.json"
            ]
            manifest["artifact_inventory"]["metadata_files"].remove(
                "source_inventory.json"
            )
            manifest["artifact_inventory"]["generated_artifact_count"] -= 1
            atomic_write_json(manifest_path, manifest)

            catalogue_path = root / "data" / "historical" / "catalogue.json"
            catalogue = json.loads(catalogue_path.read_text())
            season_entry = catalogue["seasons"]["2024-25"]
            for entry in (season_entry, season_entry["builds"][build.version]):
                entry.pop("frozen_source_inventory", None)
                entry["manifest_sha256"] = sha256_file(manifest_path)
                entry["source_inventory_status"] = "legacy_shared_raw_inventory"
            atomic_write_json(catalogue_path, catalogue)
            manifest_before = manifest_path.read_bytes()

            first = load_historical_build("2024-25", build.version, root / "data")
            second = load_historical_build("2024-25", build.version, root / "data")

            self.assertEqual(first.source_inventory_status, "legacy_shared_raw_inventory")
            self.assertTrue(first.reused)
            self.assertEqual(second.processed_dir, first.processed_dir)
            self.assertEqual(manifest_path.read_bytes(), manifest_before)


if __name__ == "__main__":
    unittest.main()
