"""Command-line interface for the FPL data pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from fpl_ai.client import DEFAULT_BASE_URL, FPLClient
from fpl_ai.errors import FPLDataError
from fpl_ai.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fpl-ingest",
        description="Download and prepare a local snapshot of public FPL data.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
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
