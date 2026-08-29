"""Orchestration and local persistence for an FPL data snapshot."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fpl_ai.client import BOOTSTRAP_PATH, FIXTURES_PATH, FPLClient
from fpl_ai.transform import (
    FIXTURE_COLUMNS,
    PLAYER_COLUMNS,
    TEAM_COLUMNS,
    transform_fixtures,
    transform_players,
    transform_teams,
)
from fpl_ai.validation import validate_payloads


@dataclass(frozen=True)
class PipelineResult:
    """Paths and counts produced by one successful pipeline run."""

    snapshot_id: str
    raw_dir: Path
    processed_dir: Path
    player_count: int
    team_count: int
    fixture_count: int


def run_pipeline(
    output_dir: Path | str = Path("data"),
    *,
    client: FPLClient | None = None,
    now: datetime | None = None,
) -> PipelineResult:
    """Download, validate, transform, and persist a timestamped data snapshot."""

    active_client = client or FPLClient()
    retrieved_at = now or datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
    retrieved_at = retrieved_at.astimezone(timezone.utc)
    snapshot_id = retrieved_at.strftime("%Y%m%dT%H%M%SZ")

    bootstrap = active_client.get_bootstrap()
    fixtures = active_client.get_fixtures()
    validate_payloads(bootstrap, fixtures)

    players = transform_players(bootstrap)
    teams = transform_teams(bootstrap)
    fixture_rows = transform_fixtures(fixtures, bootstrap)

    root = Path(output_dir)
    raw_dir = root / "raw" / snapshot_id
    processed_dir = root / "processed" / snapshot_id
    if raw_dir.exists() or processed_dir.exists():
        raise FileExistsError(f"snapshot already exists: {snapshot_id}")
    raw_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)

    _write_json(raw_dir / "bootstrap-static.json", bootstrap)
    _write_json(raw_dir / "fixtures.json", fixtures)
    _write_csv(processed_dir / "players.csv", players, PLAYER_COLUMNS)
    _write_csv(processed_dir / "teams.csv", teams, TEAM_COLUMNS)
    _write_csv(processed_dir / "fixtures.csv", fixture_rows, FIXTURE_COLUMNS)

    manifest = {
        "snapshot_id": snapshot_id,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "sources": {
            "bootstrap": f"{active_client.base_url}/{BOOTSTRAP_PATH}",
            "fixtures": f"{active_client.base_url}/{FIXTURES_PATH}",
        },
        "raw_files": ["bootstrap-static.json", "fixtures.json"],
        "processed_files": ["players.csv", "teams.csv", "fixtures.csv"],
        "row_counts": {
            "players": len(players),
            "teams": len(teams),
            "fixtures": len(fixture_rows),
        },
    }
    _write_json(processed_dir / "manifest.json", manifest)

    return PipelineResult(
        snapshot_id=snapshot_id,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        player_count=len(players),
        team_count=len(teams),
        fixture_count=len(fixture_rows),
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
