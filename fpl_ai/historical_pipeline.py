"""Pinned, idempotent orchestration for canonical historical FPL data."""

from __future__ import annotations

import json
import lzma
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fpl_ai.client import _verified_ssl_context
from fpl_ai.errors import FPLDownloadError, FPLValidationError
from fpl_ai.historical_io import (
    atomic_write_csv,
    atomic_write_json,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    store_immutable,
)
from fpl_ai.historical_schema import (
    FIXTURE_CONTEXT_AVAILABILITY_POLICY,
    column_names,
    schema_document,
)
from fpl_ai.historical_transform import (
    parse_utc,
    read_source_csv,
    transform_facts,
    transform_fixtures,
    transform_players,
    transform_snapshot_elements,
    transform_teams,
    utc_string,
)
from fpl_ai.historical_validation import (
    build_quality_report,
    raise_for_quality_failures,
    reconcile_total_points,
)

Fetcher = Callable[[str], bytes]


@dataclass(frozen=True)
class HistoricalPipelineResult:
    season: str
    version: str
    raw_dir: Path
    processed_dir: Path
    row_counts: dict[str, int]
    snapshot_gameweeks: int
    missing_snapshot_gameweeks: tuple[int, ...]
    reused: bool = False


def load_source_catalogue(path: Path | None = None) -> dict[str, Any]:
    catalogue_path = path or Path(__file__).with_name("historical_sources.json")
    try:
        value = json.loads(catalogue_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FPLValidationError(f"could not read historical source catalogue: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("seasons"), dict):
        raise FPLValidationError("historical source catalogue has an invalid structure")
    return value


def run_historical_pipeline(
    season: str,
    output_dir: Path | str = Path("data"),
    *,
    timeout: float = 60.0,
    now: datetime | None = None,
    fetcher: Fetcher | None = None,
    source_catalogue_path: Path | None = None,
) -> HistoricalPipelineResult:
    """Download, validate and process one configured historical season."""

    source_catalogue = load_source_catalogue(source_catalogue_path)
    if season not in source_catalogue["seasons"]:
        supported = ", ".join(sorted(source_catalogue["seasons"]))
        raise FPLValidationError(
            f"historical season {season!r} is not configured; supported: {supported}"
        )
    config = source_catalogue["seasons"][season]
    _validate_source_config(config)
    schema_version = source_catalogue.get("schema_version", 1)
    vaastav_revision = config["sources"]["vaastav"]["resolved_commit_sha"]
    cache_revision = config["sources"]["fplcache"]["resolved_commit_sha"]
    version = f"v{schema_version}-{vaastav_revision[:12]}-{cache_revision[:12]}"
    source_identity = _source_identity(season, config)
    source_identity_sha256 = sha256_bytes(canonical_json_bytes(source_identity))

    root = Path(output_dir) / "historical"
    raw_dir = root / "raw" / season / version
    processed_dir = root / "processed" / season / version
    catalogue_path = root / "catalogue.json"
    retrieved_at = now or datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
    retrieved_at = retrieved_at.astimezone(timezone.utc)

    existing = _existing_result(
        season,
        version,
        raw_dir,
        processed_dir,
        catalogue_path,
        retrieved_at,
        source_identity_sha256,
    )
    if existing is not None:
        return existing

    active_fetcher = fetcher or _url_fetcher(timeout)
    source_store = _SourceStore(raw_dir, season, retrieved_at, active_fetcher)
    vaastav_files = _obtain_vaastav_files(config["sources"]["vaastav"], source_store)
    cache_config = config["sources"]["fplcache"]
    tree_bytes, _ = source_store.obtain(
        "fplcache",
        cache_config,
        f"git/trees/{cache_config['resolved_commit_sha']}?recursive=1",
        cache_config["tree_url"],
        local_path="github-tree.json",
    )
    reference_path = cache_config["reference_snapshot_path"]
    reference_bytes, _ = source_store.obtain(
        "fplcache", cache_config, reference_path, _raw_url(cache_config, reference_path)
    )
    reference_payload = _decode_snapshot(reference_bytes, reference_path)
    deadlines = _extract_deadlines(reference_payload, config["expected_gameweeks"], reference_path)
    archive_entries = _archive_entries(tree_bytes, cache_config)
    selected = _select_snapshots(
        config["expected_gameweeks"], deadlines, archive_entries, cache_config, source_store
    )
    settlement_path = cache_config["points_settlement_snapshot_path"]
    settlement_bytes, settlement_record = source_store.obtain(
        "fplcache",
        cache_config,
        settlement_path,
        _raw_url(cache_config, settlement_path),
    )
    settlement_payload = _decode_snapshot(settlement_bytes, settlement_path)
    settlement_capture = _capture_from_path(settlement_path, cache_config)
    final_gameweek = max(config["expected_gameweeks"])
    _validate_points_settlement_snapshot(
        settlement_payload,
        final_gameweek,
        deadlines[final_gameweek],
        settlement_capture,
        settlement_path,
    )
    source_store.write_manifest()

    source_rows = {
        name: read_source_csv(value, name) for name, value in vaastav_files.items()
    }
    players = transform_players(season, source_rows["players_raw.csv"])
    teams = transform_teams(season, source_rows["teams.csv"])
    fixtures = transform_fixtures(season, source_rows["fixtures.csv"])
    facts, quarantined = transform_facts(
        season, source_rows["merged_gw.csv"], players, fixtures
    )

    comparison_snapshots: dict[int, tuple[dict[str, Any], str, str]] = {}
    for gameweek in config["expected_gameweeks"]:
        if gameweek == final_gameweek:
            comparison_snapshots[gameweek] = (
                settlement_payload,
                settlement_path,
                settlement_record["sha256"],
            )
            continue
        next_snapshot = selected.get(gameweek + 1)
        if next_snapshot is not None:
            _, next_path, next_payload, next_record = next_snapshot
            comparison_snapshots[gameweek] = (
                next_payload,
                next_path,
                next_record["sha256"],
            )
    points_reconciliation = reconcile_total_points(facts, comparison_snapshots)

    gameweeks: list[dict[str, Any]] = []
    deadline_snapshots: list[dict[str, Any]] = []
    for gameweek in config["expected_gameweeks"]:
        deadline = deadlines[gameweek]
        accepted = selected.get(gameweek)
        if accepted is None:
            gameweeks.append(
                {
                    "season": season,
                    "gameweek": gameweek,
                    "deadline_time_utc": utc_string(deadline),
                    "selected_snapshot_capture_time_utc": None,
                    "hours_before_deadline": None,
                    "snapshot_source_path": None,
                    "valid_predeadline_snapshot": False,
                }
            )
            continue
        capture, source_path, payload, record = accepted
        hours = (deadline - capture).total_seconds() / 3600
        gameweeks.append(
            {
                "season": season,
                "gameweek": gameweek,
                "deadline_time_utc": utc_string(deadline),
                "selected_snapshot_capture_time_utc": utc_string(capture),
                "hours_before_deadline": f"{hours:.6f}",
                "snapshot_source_path": source_path,
                "valid_predeadline_snapshot": True,
            }
        )
        deadline_snapshots.extend(
            transform_snapshot_elements(
                season,
                gameweek,
                payload,
                capture,
                deadline,
                source_path,
                record["sha256"],
            )
        )

    tables = {
        "gameweeks": gameweeks,
        "players": players,
        "teams": teams,
        "fixtures": fixtures,
        "player_fixture_facts": facts,
        "player_deadline_snapshots": deadline_snapshots,
        "quarantined_source_metadata": quarantined,
    }
    tables = {
        table: [
            {column: row.get(column) for column in column_names(table)}
            for row in rows
        ]
        for table, rows in tables.items()
    }
    source_row_counts = {
        "vaastav.merged_gw.csv": len(source_rows["merged_gw.csv"]),
        "vaastav.players_raw.csv": len(source_rows["players_raw.csv"]),
        "vaastav.teams.csv": len(source_rows["teams.csv"]),
        "vaastav.fixtures.csv": len(source_rows["fixtures.csv"]),
        "fplcache.accepted_snapshots": len(selected),
        "fplcache.accepted_snapshot_elements": len(deadline_snapshots),
        "fplcache.points_settlement_snapshots": 1,
    }
    quality_report = build_quality_report(
        season,
        tables,
        config["expected_gameweeks"],
        config["expected_counts"],
        source_row_counts,
        points_reconciliation,
    )
    quality_report["dataset_version"] = version
    quality_report["source_identity"] = source_identity
    quality_report["source_identity_sha256"] = source_identity_sha256
    if not quality_report["passed"]:
        _write_failed_quality_report(
            root, season, version, retrieved_at, source_identity_sha256, quality_report
        )
        raise_for_quality_failures(quality_report)

    processed_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{version}.", dir=processed_dir.parent
    ) as temporary_name:
        staging = Path(temporary_name)
        for table, rows in tables.items():
            atomic_write_csv(staging / f"{table}.csv", rows, column_names(table))
        atomic_write_json(staging / "schemas.json", schema_document())
        atomic_write_json(staging / "data_quality_report.json", quality_report)

        processed_files: list[dict[str, Any]] = []
        for path in sorted(staging.iterdir()):
            processed_files.append(
                {
                    "path": path.name,
                    "sha256": sha256_file(path),
                    "byte_size": path.stat().st_size,
                    "rows": len(tables[path.stem]) if path.stem in tables else None,
                }
            )
        raw_manifest_path = raw_dir / "source_manifest.json"
        manifest = {
            "schema_version": schema_version,
            "season": season,
            "version": version,
            "status": "success",
            "processed_at_utc": utc_string(retrieved_at),
            "source_identity": source_identity,
            "source_identity_sha256": source_identity_sha256,
            "source_manifest": {
                "path": str(raw_manifest_path.relative_to(root)),
                "sha256": sha256_file(raw_manifest_path),
            },
            "source_files": source_store.records,
            "processed_files": processed_files,
            "row_counts": {table: len(rows) for table, rows in tables.items()},
            "snapshot_coverage": {
                "expected_gameweeks": len(config["expected_gameweeks"]),
                "accepted_gameweeks": len(selected),
                "missing_gameweeks": [
                    gameweek
                    for gameweek in config["expected_gameweeks"]
                    if gameweek not in selected
                ],
            },
            "leakage_boundaries": quality_report["leakage_contract"],
            "fixture_context_availability_policy": FIXTURE_CONTEXT_AVAILABILITY_POLICY,
            "total_points_reconciliation": points_reconciliation,
        }
        atomic_write_json(staging / "manifest.json", manifest)
        if processed_dir.exists():
            raise FileExistsError(f"processed historical version already exists: {processed_dir}")
        os.replace(staging, processed_dir)

    manifest_path = processed_dir / "manifest.json"
    _update_latest_catalogue(
        catalogue_path,
        season,
        version,
        processed_dir,
        manifest_path,
        retrieved_at,
        manifest,
    )
    return _result_from_manifest(season, raw_dir, processed_dir, manifest, False)


class _SourceStore:
    def __init__(
        self,
        root: Path,
        season: str,
        retrieved_at: datetime,
        fetcher: Fetcher,
    ) -> None:
        self.root = root
        self.season = season
        self.retrieved_at = retrieved_at
        self.fetcher = fetcher
        self.manifest_path = root / "source_manifest.json"
        self.records: list[dict[str, Any]] = []
        if self.manifest_path.exists():
            try:
                manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                self.records = manifest["files"]
            except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
                raise FPLValidationError(f"invalid raw source manifest: {exc}") from exc

    def obtain(
        self,
        source_name: str,
        config: dict[str, Any],
        source_path: str,
        url: str,
        *,
        local_path: str | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        relative = Path(source_name) / (local_path or source_path)
        destination = self.root / relative
        existing_record = next(
            (
                record
                for record in self.records
                if record["provider_key"] == source_name
                and record["source_path"] == source_path
            ),
            None,
        )
        if destination.exists():
            digest = sha256_file(destination)
            size = destination.stat().st_size
            if existing_record is not None:
                if digest != existing_record["sha256"] or size != existing_record["byte_size"]:
                    raise FPLValidationError(f"immutable raw file failed checksum: {destination}")
                return destination.read_bytes(), existing_record
            value = destination.read_bytes()
        else:
            value = self.fetcher(url)
            digest, size, _ = store_immutable(destination, value)
        record = {
            "requested_season": self.season,
            "provider_key": source_name,
            "provider": config["provider"],
            "repository": config["repository"],
            "configured_ref": config["configured_ref"],
            "resolved_commit_sha": config["resolved_commit_sha"],
            "source_path": source_path,
            "source_url": url,
            "retrieved_at_utc": utc_string(self.retrieved_at),
            "sha256": digest,
            "byte_size": size,
            "raw_path": str(relative),
        }
        self.records.append(record)
        self.records.sort(key=lambda item: (item["provider_key"], item["source_path"]))
        self.write_manifest()
        return value, record

    def write_manifest(self) -> None:
        atomic_write_json(
            self.manifest_path,
            {
                "schema_version": 2,
                "requested_season": self.season,
                "files": self.records,
            },
        )


def _obtain_vaastav_files(
    config: dict[str, Any], store: _SourceStore
) -> dict[str, bytes]:
    values: dict[str, bytes] = {}
    for source_path in config["files"]:
        value, _ = store.obtain(
            "vaastav", config, source_path, _raw_url(config, source_path)
        )
        values[Path(source_path).name] = value
    return values


def _raw_url(config: dict[str, Any], source_path: str) -> str:
    return f"{config['raw_base_url'].rstrip('/')}/{source_path.lstrip('/')}"


def _url_fetcher(timeout: float) -> Fetcher:
    ssl_context = _verified_ssl_context()

    def fetch(url: str) -> bytes:
        request = Request(
            url,
            headers={"Accept": "*/*", "User-Agent": "fpl-ai-platform/0.2"},
        )
        try:
            with urlopen(  # noqa: S310
                request, timeout=timeout, context=ssl_context
            ) as response:
                return response.read()
        except HTTPError as exc:
            raise FPLDownloadError(f"historical request failed with HTTP {exc.code}: {url}") from exc
        except URLError as exc:
            raise FPLDownloadError(f"could not reach historical source {url}: {exc.reason}") from exc

    return fetch


def _decode_snapshot(value: bytes, source_path: str) -> dict[str, Any]:
    try:
        decoded = lzma.decompress(value).decode("utf-8")
        payload = json.loads(decoded)
    except (lzma.LZMAError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FPLValidationError(f"invalid compressed JSON snapshot {source_path}") from exc
    if not isinstance(payload, dict):
        raise FPLValidationError(f"snapshot {source_path} is not a JSON object")
    return payload


def _extract_deadlines(
    payload: dict[str, Any], expected_gameweeks: list[int], source_path: str
) -> dict[int, datetime]:
    events = payload.get("events")
    if not isinstance(events, list):
        raise FPLValidationError(f"reference snapshot {source_path} has no events array")
    deadlines: dict[int, datetime] = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("id"), int):
            raise FPLValidationError(f"reference snapshot {source_path} has malformed event")
        event_id = event["id"]
        deadline_value = event.get("deadline_time")
        if not isinstance(deadline_value, str):
            raise FPLValidationError(f"event {event_id} has no deadline_time")
        deadlines[event_id] = parse_utc(deadline_value, f"event {event_id} deadline")
    missing = sorted(set(expected_gameweeks) - set(deadlines))
    if missing:
        raise FPLValidationError(f"reference snapshot is missing gameweek deadlines: {missing}")
    return {gameweek: deadlines[gameweek] for gameweek in expected_gameweeks}


def _archive_entries(
    tree_bytes: bytes, config: dict[str, Any]
) -> list[tuple[datetime, str]]:
    try:
        tree = json.loads(tree_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FPLValidationError("fplcache tree response is invalid JSON") from exc
    if not isinstance(tree, dict) or tree.get("truncated") is True or not isinstance(tree.get("tree"), list):
        raise FPLValidationError("fplcache recursive tree is missing, malformed, or truncated")
    pattern = re.compile(config["archive_path_pattern"])
    entries: list[tuple[datetime, str]] = []
    for item in tree["tree"]:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        source_path = item.get("path")
        if not isinstance(source_path, str):
            continue
        if pattern.fullmatch(source_path) is None:
            continue
        capture = _capture_from_path(source_path, config)
        entries.append((capture, source_path))
    if not entries:
        raise FPLValidationError("fplcache tree contains no recognized snapshot paths")
    return sorted(entries)


def _select_snapshots(
    expected_gameweeks: list[int],
    deadlines: dict[int, datetime],
    entries: list[tuple[datetime, str]],
    config: dict[str, Any],
    store: _SourceStore,
) -> dict[int, tuple[datetime, str, dict[str, Any], dict[str, Any]]]:
    selected: dict[int, tuple[datetime, str, dict[str, Any], dict[str, Any]]] = {}
    previous_deadline: datetime | None = None
    for gameweek in expected_gameweeks:
        deadline = deadlines[gameweek]
        candidates = [
            (capture, path)
            for capture, path in entries
            if capture < deadline and (previous_deadline is None or capture > previous_deadline)
        ]
        for capture, source_path in reversed(candidates):
            value, record = store.obtain(
                "fplcache", config, source_path, _raw_url(config, source_path)
            )
            payload = _decode_snapshot(value, source_path)
            if _valid_snapshot(payload, gameweek, deadline, capture):
                selected[gameweek] = (capture, source_path, payload, record)
                break
        previous_deadline = deadline
    return selected


def _valid_snapshot(
    payload: dict[str, Any], gameweek: int, deadline: datetime, capture: datetime
) -> bool:
    if capture >= deadline:
        return False
    events = payload.get("events")
    if not isinstance(events, list):
        return False
    matches = [event for event in events if isinstance(event, dict) and event.get("id") == gameweek]
    if len(matches) != 1 or matches[0].get("is_next") is not True:
        return False
    deadline_value = matches[0].get("deadline_time")
    if not isinstance(deadline_value, str):
        return False
    try:
        snapshot_deadline = parse_utc(deadline_value, f"gameweek {gameweek} deadline")
    except FPLValidationError:
        return False
    return snapshot_deadline == deadline


def _validate_source_config(config: dict[str, Any]) -> None:
    try:
        vaastav = config["sources"]["vaastav"]
        cache = config["sources"]["fplcache"]
        for source in (vaastav, cache):
            configured_ref = source["configured_ref"]
            resolved = source["resolved_commit_sha"]
            if not isinstance(configured_ref, str) or not configured_ref.strip():
                raise FPLValidationError("historical source configured_ref must be non-empty")
            if configured_ref.lower() in {"main", "master", "head"}:
                raise FPLValidationError("historical source configured_ref must not be a moving branch")
            if not isinstance(resolved, str) or re.fullmatch(r"[0-9a-f]{40}", resolved) is None:
                raise FPLValidationError(
                    "historical source resolved_commit_sha must be a 40-character commit SHA"
                )
            if resolved not in source["raw_base_url"]:
                raise FPLValidationError(
                    "historical source raw_base_url must contain resolved_commit_sha"
                )
        if "master" in vaastav["raw_base_url"] or "/main/" in vaastav["raw_base_url"]:
            raise FPLValidationError("historical Vaastav URL is not revision-pinned")
        if "master" in cache["raw_base_url"] or "/main/" in cache["raw_base_url"]:
            raise FPLValidationError("historical fplcache URL is not revision-pinned")
        if not isinstance(cache["points_settlement_snapshot_path"], str):
            raise FPLValidationError("historical fplcache settlement path is required")
        if cache["resolved_commit_sha"] not in cache["tree_url"]:
            raise FPLValidationError(
                "historical fplcache tree_url must contain resolved_commit_sha"
            )
    except KeyError as exc:
        raise FPLValidationError(f"historical source catalogue missing field: {exc}") from exc


def _capture_from_path(source_path: str, config: dict[str, Any]) -> datetime:
    match = re.fullmatch(config["archive_path_pattern"], source_path)
    if match is None:
        raise FPLValidationError(f"unrecognized fplcache snapshot path: {source_path}")
    year, month, day, hour, minute = (int(value) for value in match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError as exc:
        raise FPLValidationError(f"invalid capture timestamp in path {source_path}") from exc


def _validate_points_settlement_snapshot(
    payload: dict[str, Any],
    gameweek: int,
    deadline: datetime,
    capture: datetime,
    source_path: str,
) -> None:
    if capture <= deadline:
        raise FPLValidationError(
            f"points settlement snapshot is not after GW{gameweek} deadline: {source_path}"
        )
    events = payload.get("events")
    event = next(
        (
            value
            for value in events or []
            if isinstance(value, dict) and value.get("id") == gameweek
        ),
        None,
    )
    if (
        event is None
        or event.get("finished") is not True
        or event.get("data_checked") is not True
    ):
        raise FPLValidationError(
            f"points settlement snapshot does not mark GW{gameweek} finished and data_checked: {source_path}"
        )


def _source_identity(season: str, config: dict[str, Any]) -> dict[str, Any]:
    identities: dict[str, Any] = {}
    for key, source in sorted(config["sources"].items()):
        identity = {
            "provider": source["provider"],
            "repository": source["repository"],
            "requested_season": season,
            "configured_ref": source["configured_ref"],
            "resolved_commit_sha": source["resolved_commit_sha"],
        }
        if "files" in source:
            identity["configured_artifacts"] = list(source["files"])
        else:
            identity["tree_url"] = source["tree_url"]
            identity["reference_snapshot_path"] = source["reference_snapshot_path"]
            identity["points_settlement_snapshot_path"] = source[
                "points_settlement_snapshot_path"
            ]
        identities[key] = identity
    return {"requested_season": season, "sources": identities}


def _write_failed_quality_report(
    historical_root: Path,
    season: str,
    version: str,
    attempted_at: datetime,
    source_identity_sha256: str,
    quality_report: dict[str, Any],
) -> Path:
    attempt_id = attempted_at.strftime("%Y%m%dT%H%M%S.%fZ")
    path = (
        historical_root
        / "failed"
        / season
        / f"{version}--{attempt_id}--quality-failed.json"
    )
    value = dict(quality_report)
    value.update(
        {
            "run_status": "failed_quality_validation",
            "attempted_at_utc": utc_string(attempted_at),
            "dataset_version": version,
            "source_identity_sha256": source_identity_sha256,
            "catalogue_updated": False,
        }
    )
    atomic_write_json(path, value)
    return path


def _existing_result(
    season: str,
    version: str,
    raw_dir: Path,
    processed_dir: Path,
    catalogue_path: Path,
    now: datetime,
    source_identity_sha256: str,
) -> HistoricalPipelineResult | None:
    if not processed_dir.exists():
        return None
    manifest_path = processed_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FPLValidationError(f"existing processed manifest is invalid: {exc}") from exc
    if manifest.get("season") != season or manifest.get("version") != version:
        raise FPLValidationError(f"existing processed directory has the wrong identity: {processed_dir}")
    if manifest.get("source_identity_sha256") != source_identity_sha256:
        raise FPLValidationError(
            f"existing processed directory has different source identity: {processed_dir}"
        )
    if catalogue_path.exists():
        try:
            existing_catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
            existing_entry = existing_catalogue.get("seasons", {}).get(season)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise FPLValidationError(f"historical output catalogue is invalid: {exc}") from exc
        if (
            existing_entry is not None
            and existing_entry.get("latest_successful_version") == version
            and existing_entry.get("manifest_sha256") != sha256_file(manifest_path)
        ):
            raise FPLValidationError(f"existing processed manifest failed catalogue checksum: {manifest_path}")
    for record in manifest.get("processed_files", []):
        path = processed_dir / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise FPLValidationError(f"existing processed file failed checksum: {path}")
    source_manifest = raw_dir / "source_manifest.json"
    if not source_manifest.is_file():
        raise FPLValidationError(f"existing version has no raw source manifest: {source_manifest}")
    if sha256_file(source_manifest) != manifest.get("source_manifest", {}).get("sha256"):
        raise FPLValidationError(
            f"existing raw source manifest failed processed-manifest checksum: {source_manifest}"
        )
    try:
        raw_manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
        raw_records = raw_manifest["files"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FPLValidationError(f"existing raw source manifest is invalid: {exc}") from exc
    for record in raw_records:
        raw_path = raw_dir / record["raw_path"]
        if (
            not raw_path.is_file()
            or raw_path.stat().st_size != record["byte_size"]
            or sha256_file(raw_path) != record["sha256"]
        ):
            raise FPLValidationError(f"immutable raw file failed checksum: {raw_path}")
    _update_latest_catalogue(
        catalogue_path, season, version, processed_dir, manifest_path, now, manifest
    )
    return _result_from_manifest(season, raw_dir, processed_dir, manifest, True)


def _update_latest_catalogue(
    path: Path,
    season: str,
    version: str,
    processed_dir: Path,
    manifest_path: Path,
    updated_at: datetime,
    manifest: dict[str, Any],
) -> None:
    if path.exists():
        try:
            catalogue = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FPLValidationError(f"historical output catalogue is invalid: {exc}") from exc
    else:
        catalogue = {"schema_version": 1, "seasons": {}}
    historical_root = path.parent
    entry = {
        "latest_successful_version": version,
        "processed_path": str(processed_dir.relative_to(historical_root)),
        "manifest_path": str(manifest_path.relative_to(historical_root)),
        "manifest_sha256": sha256_file(manifest_path),
        "processed_at_utc": manifest["processed_at_utc"],
        "row_counts": manifest["row_counts"],
        "snapshot_coverage": manifest["snapshot_coverage"],
        "source_identity": manifest["source_identity"],
        "source_identity_sha256": manifest["source_identity_sha256"],
    }
    seasons = catalogue.setdefault("seasons", {})
    if seasons.get(season) == entry:
        return
    catalogue["updated_at_utc"] = utc_string(updated_at)
    seasons[season] = entry
    atomic_write_json(path, catalogue)


def _result_from_manifest(
    season: str,
    raw_dir: Path,
    processed_dir: Path,
    manifest: dict[str, Any],
    reused: bool,
) -> HistoricalPipelineResult:
    coverage = manifest["snapshot_coverage"]
    return HistoricalPipelineResult(
        season=season,
        version=manifest["version"],
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        row_counts=manifest["row_counts"],
        snapshot_gameweeks=coverage["accepted_gameweeks"],
        missing_snapshot_gameweeks=tuple(coverage["missing_gameweeks"]),
        reused=reused,
    )
