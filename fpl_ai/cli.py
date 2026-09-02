"""Command-line interface for the FPL data pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from fpl_ai.client import DEFAULT_BASE_URL, FPLClient
from fpl_ai.errors import FPLDataError
from fpl_ai.historical_pipeline import run_historical_pipeline
from fpl_ai.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fpl-ingest",
        description="Download and prepare current or pinned historical FPL data.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="data root for raw/ and processed/ snapshots (default: data)",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    subparsers = parser.add_subparsers(dest="command")
    historical = subparsers.add_parser(
        "historical",
        help="download and process a configured pinned historical season",
    )
    historical.add_argument(
        "--season",
        required=True,
        help="configured season in YYYY-YY form (currently: 2024-25)",
    )
    historical.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="data root for historical raw/processed data (default: data)",
    )
    historical.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="per-request HTTP timeout in seconds (default: 60)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "historical":
            result = run_historical_pipeline(
                args.season,
                args.output_dir,
                timeout=args.timeout,
            )
            action = "reused" if result.reused else "completed"
            print(
                f"Historical FPL season {result.season} {action} successfully "
                f"({result.version})"
            )
            for table, count in result.row_counts.items():
                print(f"  {table}: {count}")
            print(
                f"  accepted pre-deadline snapshots: {result.snapshot_gameweeks} gameweeks"
            )
            if result.missing_snapshot_gameweeks:
                missing = ", ".join(str(value) for value in result.missing_snapshot_gameweeks)
                print(f"  missing pre-deadline snapshots: {missing}")
            print(f"  raw data:       {result.raw_dir.resolve()}")
            print(f"  processed data: {result.processed_dir.resolve()}")
            return 0
        result = run_pipeline(
            args.output_dir,
            client=FPLClient(base_url=args.base_url, timeout=args.timeout),
        )
    except (FPLDataError, OSError, ValueError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1

    print(f"FPL snapshot {result.snapshot_id} completed successfully")
    print(f"  players:  {result.player_count}")
    print(f"  teams:    {result.team_count}")
    print(f"  fixtures: {result.fixture_count}")
    print(f"  raw data:       {result.raw_dir.resolve()}")
    print(f"  processed data: {result.processed_dir.resolve()}")
    return 0
