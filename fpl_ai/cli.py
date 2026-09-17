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
        dest="current_output_dir",
        type=Path,
        default=None,
        help="data root for raw/ and processed/ snapshots (default: data)",
    )
    parser.add_argument(
        "--base-url",
        dest="current_base_url",
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--timeout",
        dest="current_timeout",
        type=float,
        default=None,
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
        help="configured season in YYYY-YY form (currently: 2023-24, 2024-25)",
    )
    historical.add_argument(
        "--output-dir",
        dest="historical_output_dir",
        type=Path,
        default=None,
        help="data root for historical raw/processed data (default: data)",
    )
    historical.add_argument(
        "--timeout",
        dest="historical_timeout",
        type=float,
        default=None,
        help="per-request HTTP timeout in seconds (default: 60)",
    )
    features = subparsers.add_parser('features', help='build offline deadline-safe features and evaluate baselines')
    features.add_argument('--data-dir', type=Path, default=Path('data'))
    features.add_argument('--artifact-dir', type=Path, default=None)
    features.add_argument('--builds-from', type=Path, help='prior modelling manifest whose exact historical builds to reuse')
    experiment = subparsers.add_parser('experiment', help='train/validate or evaluate a frozen M4 model')
    experiment.add_argument('stage', choices=('validate','holdout'))
    experiment.add_argument('--m3-dir', type=Path, required=True, help='exact frozen M3 artifact directory')
    experiment.add_argument('--frozen-dir', type=Path, help='published validation-freeze directory; required for holdout')
    experiment.add_argument('--artifact-dir', type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == 'experiment':
            from fpl_ai.experiments import run_validation, run_holdout
            if any(v is not None for v in (args.current_output_dir,args.current_base_url,args.current_timeout)):
                parser.error('experiment uses --m3-dir and --artifact-dir, not ingestion options')
            if args.stage == 'validate':
                if args.frozen_dir:
                    parser.error('--frozen-dir is only valid for holdout')
                path, reused = run_validation(args.m3_dir,args.artifact_dir or Path('data/experiments'))
            else:
                if not args.frozen_dir:
                    parser.error('holdout requires --frozen-dir')
                path, reused = run_holdout(args.m3_dir,args.frozen_dir,args.artifact_dir or Path('data/experiment_holdouts'))
            print(f"Experiment {'reused' if reused else 'completed'}: {path}")
            return 0
        if args.command == 'features':
            from fpl_ai.modelling import run_modelling
            import json
            if any(v is not None for v in (args.current_output_dir, args.current_base_url, args.current_timeout)):
                parser.error('features uses --data-dir and --artifact-dir, not ingestion options')
            builds = None
            if args.builds_from:
                prior = json.loads(args.builds_from.read_text())
                builds = {s: v['version'] for s, v in prior['identity']['sources'].items()}
            path, reused = run_modelling(args.data_dir, args.artifact_dir, builds)
            print(f"Modelling artifacts {'reused' if reused else 'completed'}: {path}")
            return 0
        if args.command == "historical":
            if args.current_base_url is not None:
                parser.error("--base-url is only valid for current ingestion")
            output_dir = _resolve_shared_option(
                parser,
                "--output-dir",
                args.current_output_dir,
                args.historical_output_dir,
                Path("data"),
            )
            timeout = _resolve_shared_option(
                parser,
                "--timeout",
                args.current_timeout,
                args.historical_timeout,
                60.0,
            )
            result = run_historical_pipeline(
                args.season,
                output_dir,
                timeout=timeout,
            )
            action = "reused" if result.reused else "completed"
            print(
                f"Historical FPL season {result.season} {action} successfully "
                f"({result.version})"
            )
            print(f"  generated CSV tables: {result.generated_table_count}")
            for table, count in result.row_counts.items():
                print(f"  {table}: {count}")
            print(f"  processed artifacts: {result.generated_artifact_count}")
            print(f"  source inventory: {result.source_inventory_status}")
            print(
                f"  accepted pre-deadline snapshots: {result.snapshot_gameweeks} gameweeks"
            )
            if result.missing_snapshot_gameweeks:
                missing = ", ".join(str(value) for value in result.missing_snapshot_gameweeks)
                print(f"  missing pre-deadline snapshots: {missing}")
            print(f"  raw data:       {result.raw_dir.resolve()}")
            print(f"  processed data: {result.processed_dir.resolve()}")
            return 0
        output_dir = args.current_output_dir or Path("data")
        timeout = args.current_timeout if args.current_timeout is not None else 30.0
        base_url = args.current_base_url or DEFAULT_BASE_URL
        result = run_pipeline(
            output_dir,
            client=FPLClient(base_url=base_url, timeout=timeout),
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


def _resolve_shared_option(
    parser: argparse.ArgumentParser,
    option: str,
    parent_value: object | None,
    historical_value: object | None,
    default: object,
) -> object:
    if (
        parent_value is not None
        and historical_value is not None
        and parent_value != historical_value
    ):
        parser.error(
            f"conflicting {option} values before and after 'historical': "
            f"{parent_value!s} != {historical_value!s}"
        )
    if historical_value is not None:
        return historical_value
    if parent_value is not None:
        return parent_value
    return default
