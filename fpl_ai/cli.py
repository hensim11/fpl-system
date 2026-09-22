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
    minutes = subparsers.add_parser('minutes', help='build playing-time features or fit the bounded minutes experiment')
    ms = minutes.add_subparsers(dest='minutes_stage', required=True)
    mf = ms.add_parser('features')
    mf.add_argument('--data-dir', type=Path, default=Path('data'))
    mf.add_argument('--artifact-dir', type=Path, default=Path('data/playing_time'))
    mt = ms.add_parser('train')
    mt.add_argument('--features-dir', type=Path, required=True)
    mt.add_argument('--artifact-dir', type=Path, default=Path('data/minutes'))
    mo = ms.add_parser('oos', help='annual expanding chronological backtest; no xPts stacking')
    mo.add_argument('--features-dir', type=Path, required=True)
    mo.add_argument('--model-dir', type=Path, required=True)
    mo.add_argument('--data-dir', type=Path, default=Path('data'))
    mo.add_argument('--artifact-dir', type=Path, default=Path('data/minutes_oos'))
    prospective = subparsers.add_parser('prospective', help='capture, freeze, settle and score genuine future forecasts')
    ps = prospective.add_subparsers(dest='prospective_stage', required=True)
    pc = ps.add_parser('capture')
    pc.add_argument('--season', required=True)
    pc.add_argument('--gameweek', type=int, required=True)
    pc.add_argument('--artifact-dir', type=Path, default=Path('data/prospective_snapshots'))
    pf = ps.add_parser('freeze')
    pf.add_argument('--snapshot-dir', type=Path, required=True)
    pf.add_argument('--model-dir', type=Path, required=True)
    pf.add_argument('--previous-dir', type=Path)
    pf.add_argument('--history-pair', nargs=2, type=Path, action='append', default=[], metavar=('PREDICTION_DIR','SETTLEMENT_DIR'))
    pf.add_argument('--artifact-dir', type=Path, default=Path('data/prospective_predictions'))
    pl = ps.add_parser('settle')
    pl.add_argument('--prediction-dir', type=Path, required=True)
    pl.add_argument('--artifact-dir', type=Path, default=Path('data/prospective_settlements'))
    pe = ps.add_parser('score')
    pe.add_argument('--prediction-dir', type=Path, required=True)
    pe.add_argument('--settlement-dir', type=Path, required=True)
    pe.add_argument('--artifact-dir', type=Path, default=Path('data/prospective_scores'))
    pv = ps.add_parser('verify', help='verify/reuse an existing forecast without rewriting or re-dating it')
    pv.add_argument('--prediction-dir', type=Path, required=True)
    px = ps.add_parser('xpts', help='fixed operational xPts refit, pre-deadline freeze, verification and separate score')
    xs = px.add_subparsers(dest='xpts_stage', required=True)
    xt = xs.add_parser('fit')
    xt.add_argument('--data-dir', type=Path, default=Path('data'))
    xt.add_argument('--artifact-dir', type=Path, default=Path('data/prospective_xpts/models'))
    for stage in ('freeze', 'verify', 'score'):
        xp = xs.add_parser(stage)
        xp.add_argument('--model-dir', type=Path, required=True)
        if stage == 'freeze':
            xp.add_argument('--snapshot-dir', type=Path, required=True)
            xp.add_argument('--minutes-dir', type=Path, required=True)
            xp.add_argument('--history-pair', nargs=2, type=Path, action='append', default=[])
        else:
            xp.add_argument('--forecast-dir', type=Path, required=True)
        if stage == 'score': xp.add_argument('--settlement-dir', type=Path, required=True)
        if stage != 'verify': xp.add_argument('--artifact-dir', type=Path, default=Path('data/prospective_xpts')/('forecasts' if stage=='freeze' else 'scores'))
    decision = subparsers.add_parser('optimise', help='one-GW current-squad transfers over a frozen M4E forecast')
    decision.add_argument('--forecast-dir', type=Path, required=True)
    decision.add_argument('--model-dir', type=Path, required=True, help='trusted local M4E model bundle used to verify the forecast')
    decision.add_argument('--model', choices=('control', 'v2'), required=True)
    decision.add_argument('--squad', type=Path, required=True, help='current-squad-v1 JSON; prices/bank in integer tenths')
    decision.add_argument('--max-transfers', type=int, default=2)
    decision.add_argument('--top-n', type=int, default=3)
    decision.add_argument('--artifact-dir', type=Path, default=Path('data/decisions'))
    projection = subparsers.add_parser('project', help='direct multi-Gameweek projections')
    stages = projection.add_subparsers(dest='projection_stage', required=True)
    fit = stages.add_parser('fit')
    fit.add_argument('--m3-dir', type=Path, required=True)
    fit.add_argument('--artifact-dir', type=Path, default=Path('data/multi_projection/models'))
    for stage in ('freeze', 'verify'):
        command = stages.add_parser(stage)
        command.add_argument('--model-dir', type=Path, required=True)
        command.add_argument('--m4e-model-dir', type=Path, required=True)
        if stage == 'freeze':
            command.add_argument('--forecast-dir', type=Path, required=True)
            command.add_argument('--horizon', type=int, default=5)
            command.add_argument('--artifact-dir', type=Path, default=Path('data/multi_projection/forecasts'))
        else:
            command.add_argument('--projections-dir', type=Path, required=True)
    plan = subparsers.add_parser('plan', help='offline multi-Gameweek transfer paths')
    for name in ('projections-dir', 'model-dir', 'm4e-model-dir', 'squad'):
        plan.add_argument('--'+name, type=Path, required=True)
    plan.add_argument('--horizon', type=int, default=5)
    plan.add_argument('--max-transfers', type=int, default=2)
    plan.add_argument('--top-n', type=int, default=3)
    plan.add_argument('--time-limit', type=float, default=120)
    plan.add_argument('--artifact-dir', type=Path, default=Path('data/transfer_paths'))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command in ('project', 'plan'):
            if any(v is not None for v in (args.current_output_dir, args.current_base_url, args.current_timeout)):
                parser.error('planning commands do not accept current-ingestion options')
            from fpl_ai import multi_projection as mp
            if args.command == 'plan':
                from fpl_ai.transfer_path import build_plan
                out, reused = build_plan(args.projections_dir, args.model_dir, args.m4e_model_dir,
                                         args.squad, args.artifact_dir, horizon=args.horizon,
                                         max_transfers=args.max_transfers, top_n=args.top_n, time_limit=args.time_limit)
                print(f"Plan {'reused' if reused else 'completed'}: {out}")
                print((out/'report.md').read_text())
            elif args.projection_stage == 'fit':
                print(mp.build_models(args.m3_dir, args.artifact_dir))
            elif args.projection_stage == 'freeze':
                print(mp.freeze(args.forecast_dir, args.m4e_model_dir, args.model_dir, args.artifact_dir, horizon=args.horizon))
            else:
                _, manifest = mp.verify_projection(args.projections_dir, args.model_dir, args.m4e_model_dir)
                print('Verified '+manifest['identity_sha256'])
            return 0
        if args.command == 'optimise':
            if any(v is not None for v in (args.current_output_dir, args.current_base_url, args.current_timeout)):
                parser.error('optimise does not accept current-ingestion options')
            from fpl_ai.transfer_optimiser import build_decision
            out, reused = build_decision(args.forecast_dir, args.model_dir, args.model, args.squad,
                                         args.artifact_dir, max_transfers=args.max_transfers, top_n=args.top_n)
            print(f"One-GW decision {'reused' if reused else 'completed'}: {out}")
            print((out / 'report.md').read_text())
            return 0
        if args.command in ('minutes', 'prospective'):
            if any(v is not None for v in (args.current_output_dir, args.current_base_url, args.current_timeout)):
                parser.error('modelling commands do not accept current-ingestion options')
            if args.command == 'minutes':
                if args.minutes_stage == 'oos':
                    from fpl_ai.minutes_oos import build_oos
                    path, reused, score, score_reused = build_oos(args.features_dir, args.model_dir, args.data_dir, args.artifact_dir)
                    print(f'Separate OOS diagnostics: {score} (reused={score_reused})')
                elif args.minutes_stage == 'features':
                    from fpl_ai.playing_time import build_playing_time
                    path, reused = build_playing_time(args.data_dir, args.artifact_dir)
                else:
                    from fpl_ai.minutes import run_minutes
                    path, reused = run_minutes(args.features_dir, args.artifact_dir)
            else:
                from fpl_ai.prospective import capture_snapshot, freeze_predictions, capture_settlement, score_predictions, verify_prediction
                if args.prospective_stage == 'xpts':
                    from fpl_ai import prospective_xpts as xpts
                    if args.xpts_stage == 'fit':
                        path, reused = xpts.fit(args.artifact_dir, args.data_dir)
                    elif args.xpts_stage == 'freeze':
                        path, reused = xpts.freeze(args.snapshot_dir, args.minutes_dir, args.model_dir, args.artifact_dir, history_pairs=args.history_pair)
                    elif args.xpts_stage == 'score':
                        path, reused = xpts.score(args.forecast_dir, args.settlement_dir, args.model_dir, args.artifact_dir)
                    else:
                        xpts.verify_forecast(args.forecast_dir, args.model_dir)
                        path, reused = args.forecast_dir, True
                elif args.prospective_stage == 'capture':
                    path, reused = capture_snapshot(args.season, args.gameweek, args.artifact_dir)
                elif args.prospective_stage == 'freeze':
                    path, reused = freeze_predictions(args.snapshot_dir, args.model_dir, args.artifact_dir,
                                                      previous_dir=args.previous_dir, history_pairs=args.history_pair)
                elif args.prospective_stage == 'settle':
                    path, reused = capture_settlement(args.prediction_dir, args.artifact_dir)
                elif args.prospective_stage == 'score':
                    path, reused = score_predictions(args.prediction_dir, args.settlement_dir, args.artifact_dir)
                else:
                    verify_prediction(args.prediction_dir)
                    path, reused = args.prediction_dir, True
            print(f"Artifacts {'verified/reused' if reused else 'completed'}: {path}")
            return 0
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
