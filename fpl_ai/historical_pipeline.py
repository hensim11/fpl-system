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
    TRANSFORMATION_CONTRACT_VERSION,
    column_names,
    get_vaastav_source_schema,
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
    generated_table_count: int
    generated_artifact_count: int
    source_inventory_status: str = "unknown"
    reused: bool = False


class ConsumedSourceTracker:
    """Canonicalize material raw dependencies and verify complete registration."""

    _PROVENANCE_FIELDS = (
        "requested_season",
        "provider_key",
        "provider",
        "repository",
        "configured_ref",
        "resolved_commit_sha",
        "source_path",
        "source_url",
        "retrieved_at_utc",
        "sha256",
        "byte_size",
        "raw_path",
    )

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        self._roles: dict[tuple[str, str], set[str]] = {}

    @staticmethod
    def _key(record: dict[str, Any]) -> tuple[str, str]:
        missing = [
            field
            for field in ConsumedSourceTracker._PROVENANCE_FIELDS
            if field not in record
        ]
        if missing:
            raise FPLValidationError(
                f"consumed source record lacks provenance fields: {missing}"
            )
        return record["provider_key"], record["source_path"]

    def register(self, record: dict[str, Any], role: str) -> None:
        if not isinstance(role, str) or not role:
            raise FPLValidationError("consumed source role must be non-empty")
        key = self._key(record)
        candidate = {
            field: value
            for field, value in record.items()
            if field != "consumption_roles"
        }
        existing = self._records.get(key)
        if existing is not None and existing != candidate:
            differing = sorted(
                field
                for field in set(existing) | set(candidate)
                if existing.get(field) != candidate.get(field)
            )
            raise FPLValidationError(
                "conflicting consumed source registrations for "
                f"provider={key[0]!r}, source_path={key[1]!r}; fields={differing}"
            )
        self._records[key] = candidate
        self._roles.setdefault(key, set()).add(role)

    def finalize(self, expected_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        expected: dict[tuple[str, str], dict[str, Any]] = {}
        for record in expected_records:
            key = self._key(record)
            candidate = {
                field: value
                for field, value in record.items()
                if field != "consumption_roles"
            }
            previous = expected.setdefault(key, candidate)
            if previous != candidate:
                raise FPLValidationError(
                    "conflicting resolved source dependencies for "
                    f"provider={key[0]!r}, source_path={key[1]!r}"
                )
        missing = sorted(set(expected) - set(self._records))
        unexpected = sorted(set(self._records) - set(expected))
        if missing or unexpected:
            raise FPLValidationError(
                "actual consumed sources do not match resolved dependency set; "
                f"missing_consumption={missing}, unexpected_consumption={unexpected}"
            )
        return self.records()

    def records(self) -> list[dict[str, Any]]:
        """Return the currently registered records in identity-stable order."""

        records: list[dict[str, Any]] = []
        for key in sorted(self._records):
            record = dict(self._records[key])
            record["consumption_roles"] = sorted(self._roles[key])
            records.append(record)
        return records


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
    _validate_source_config(season, config)
    schema_version = source_catalogue.get("schema_version", 1)
    source_schema_config = config["vaastav_source_schema"]
    vaastav_source_schema = get_vaastav_source_schema(
        source_schema_config["schema_id"],
        season,
        source_schema_config["schema_version"],
    )
    build_identity = create_build_identity(season, config, schema_version)
    build_identity_sha256 = sha256_bytes(canonical_json_bytes(build_identity))
    vaastav_revision = config["sources"]["vaastav"]["resolved_commit_sha"]
    cache_revision = config["sources"]["fplcache"]["resolved_commit_sha"]
    source_version = f"v{schema_version}-{vaastav_revision[:12]}-{cache_revision[:12]}"
    version = f"{source_version}-build-{build_identity_sha256[:12]}"

    root = Path(output_dir) / "historical"
    raw_dir = root / "raw" / season / source_version
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
        config,
        build_identity,
        build_identity_sha256,
    )
    if existing is not None:
        return existing

    active_fetcher = fetcher or _url_fetcher(timeout)
    source_store = _SourceStore(raw_dir, season, retrieved_at, active_fetcher)
    consumed_sources = ConsumedSourceTracker()
    vaastav_files = _obtain_vaastav_files(config["sources"]["vaastav"], source_store)
    cache_config = config["sources"]["fplcache"]
    tree_bytes, tree_record = source_store.obtain(
        "fplcache",
        cache_config,
        f"git/trees/{cache_config['resolved_commit_sha']}?recursive=1",
        cache_config["tree_url"],
        local_path="github-tree.json",
    )
    consumed_sources.register(tree_record, "snapshot_archive_discovery")
    reference_path = cache_config["reference_snapshot_path"]
    reference_bytes, reference_record = source_store.obtain(
        "fplcache", cache_config, reference_path, _raw_url(cache_config, reference_path)
    )
    consumed_sources.register(reference_record, "gameweek_deadline_reference")
    reference_payload = _decode_snapshot(reference_bytes, reference_path)
    deadlines = _extract_deadlines(reference_payload, config["expected_gameweeks"], reference_path)
    archive_entries = _archive_entries(tree_bytes, cache_config)
    selected = _select_snapshots(
        config["expected_gameweeks"], deadlines, archive_entries, cache_config, source_store
    )
    for _, _, _, record in selected.values():
        consumed_sources.register(record, "accepted_predeadline_snapshot")
    settlement_path = cache_config["points_settlement_snapshot_path"]
    settlement_bytes, settlement_record = source_store.obtain(
        "fplcache",
        cache_config,
        settlement_path,
        _raw_url(cache_config, settlement_path),
    )
    settlement_payload = _decode_snapshot(settlement_bytes, settlement_path)
    consumed_sources.register(settlement_record, "final_points_settlement")
    settlement_capture = _capture_from_path(settlement_path, cache_config)
    final_gameweek = max(config["expected_gameweeks"])
    _validate_points_settlement_snapshot(
        settlement_payload,
        final_gameweek,
        deadlines[final_gameweek],
        settlement_capture,
        settlement_path,
    )
    source_rows: dict[str, list[dict[str, Any]]] = {}
    source_schema_audits: dict[str, dict[str, Any]] = {}
    for name, (value, record) in vaastav_files.items():
        consumed_sources.register(record, f"vaastav_transform:{name}")
        try:
            rows, audit = read_source_csv(
                value,
                name,
                vaastav_source_schema,
                include_schema_audit=True,
            )
        except FPLValidationError as exc:
            source_store.write_manifest()
            failed_records = consumed_sources.records()
            failed_identity = _source_identity(season, config, failed_records)
            failed_identity_sha256 = sha256_bytes(
                canonical_json_bytes(failed_identity)
            )
            _write_failed_quality_report(
                root,
                season,
                version,
                retrieved_at,
                failed_identity_sha256,
                build_identity_sha256,
                {
                    "schema_version": 3,
                    "season": season,
                    "passed": False,
                    "failures": ["vaastav.source_validation"],
                    "source_validation": {
                        "passed": False,
                        "schema_id": vaastav_source_schema["schema_id"],
                        "source_artifact": name,
                        "errors": [str(exc)],
                    },
                    "source_schema_changes": source_schema_audits,
                    "source_identity": failed_identity,
                    "build_identity": build_identity,
                },
            )
            raise
        source_rows[name] = rows
        source_schema_audits[name] = audit
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
            consumed_sources.register(
                settlement_record, "total_points_reconciliation"
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
            consumed_sources.register(
                next_record, "total_points_reconciliation"
            )
    resolved_dependencies = [
        *(record for _, record in vaastav_files.values()),
        tree_record,
        reference_record,
        *(record for _, _, _, record in selected.values()),
        settlement_record,
    ]
    consumed_records = consumed_sources.finalize(resolved_dependencies)
    source_store.write_manifest()
    source_identity = _source_identity(season, config, consumed_records)
    source_identity_sha256 = sha256_bytes(canonical_json_bytes(source_identity))
    reconciliation_policy = config["reconciliation"]["total_points"]
    reconciliation_provenance = create_reconciliation_provenance(
        season,
        config,
        vaastav_source_schema,
        comparison_snapshots,
        source_identity_sha256,
    )
    points_reconciliation = reconcile_total_points(
        facts,
        comparison_snapshots,
        reconciliation_policy,
        reconciliation_provenance,
        artifact_created_at_utc=utc_string(retrieved_at),
        source_identity=source_identity,
        source_identity_sha256=source_identity_sha256,
        build_identity=build_identity,
        build_identity_sha256=build_identity_sha256,
    )

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
        source_schema_audits,
        vaastav_source_schema,
    )
    quality_report["dataset_version"] = version
    quality_report["source_version"] = source_version
    quality_report["source_identity"] = source_identity
    quality_report["source_identity_sha256"] = source_identity_sha256
    quality_report["build_identity"] = build_identity
    quality_report["build_identity_sha256"] = build_identity_sha256
    if not quality_report["passed"]:
        _write_failed_quality_report(
            root,
            season,
            version,
            retrieved_at,
            source_identity_sha256,
            build_identity_sha256,
            quality_report,
        )
        raise_for_quality_failures(quality_report)

    processed_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{version}.", dir=processed_dir.parent
    ) as temporary_name:
        staging = Path(temporary_name)
        for table, rows in tables.items():
            atomic_write_csv(staging / f"{table}.csv", rows, column_names(table))
        atomic_write_json(staging / "schemas.json", schema_document(vaastav_source_schema))
        atomic_write_json(staging / "data_quality_report.json", quality_report)
        atomic_write_json(
            staging / "total_points_reconciliation.json", points_reconciliation
        )
        frozen_inventory = {
            "inventory_schema_version": 2,
            "inventory_scope": "materially_consumed_records_only",
            "season": season,
            "source_version": source_version,
            "source_identity": source_identity,
            "source_identity_sha256": source_identity_sha256,
            "files": consumed_records,
        }
        frozen_inventory_path = staging / "source_inventory.json"
        atomic_write_json(frozen_inventory_path, frozen_inventory)

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
            "source_version": source_version,
            "status": "success",
            "processed_at_utc": utc_string(retrieved_at),
            "source_identity": source_identity,
            "source_identity_sha256": source_identity_sha256,
            "build_identity": build_identity,
            "build_identity_sha256": build_identity_sha256,
            "source_manifest": {
                "path": str(raw_manifest_path.relative_to(root)),
                "sha256": sha256_file(raw_manifest_path),
                "role": "mutable raw-cache inventory; not authoritative for this processed build",
            },
            "frozen_source_inventory": {
                "path": frozen_inventory_path.name,
                "sha256": sha256_file(frozen_inventory_path),
                "source_identity": source_identity,
                "source_identity_sha256": source_identity_sha256,
                "status": "frozen_per_build",
            },
            "source_files": consumed_records,
            "source_discovery_audit": _source_discovery_audit(
                source_store.records, consumed_records
            ),
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
            "artifact_inventory": {
                "table_files": sorted(f"{table}.csv" for table in tables),
                "metadata_files": [
                    "schemas.json",
                    "data_quality_report.json",
                    "total_points_reconciliation.json",
                    "source_inventory.json",
                    "manifest.json",
                ],
                "generated_table_count": len(tables),
                "generated_artifact_count": len(tables) + 5,
            },
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
        value = {
            "schema_version": 2,
            "requested_season": self.season,
            "files": self.records,
        }
        encoded = canonical_json_bytes(value)
        if self.manifest_path.exists() and self.manifest_path.read_bytes() == encoded:
            return
        atomic_write_json(self.manifest_path, value)


def _obtain_vaastav_files(
    config: dict[str, Any], store: _SourceStore
) -> dict[str, tuple[bytes, dict[str, Any]]]:
    values: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for source_path in config["files"]:
        value, record = store.obtain(
            "vaastav", config, source_path, _raw_url(config, source_path)
        )
        values[Path(source_path).name] = (value, record)
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


def _validate_source_config(season: str, config: dict[str, Any]) -> None:
    try:
        schema_config = config["vaastav_source_schema"]
        get_vaastav_source_schema(
            schema_config["schema_id"], season, schema_config["schema_version"]
        )
        reconciliation = config["reconciliation"]["total_points"]
        mode = reconciliation["mode"]
        threshold = reconciliation["minimum_coverage_ratio"]
        if mode not in {"required", "optional"}:
            raise FPLValidationError(
                "historical total_points reconciliation mode must be 'required' or 'optional'"
            )
        if (
            not isinstance(threshold, (int, float))
            or isinstance(threshold, bool)
            or not 0 <= threshold <= 1
        ):
            raise FPLValidationError(
                "historical total_points minimum_coverage_ratio must be between 0 and 1 inclusive"
            )
        vaastav = config["sources"]["vaastav"]
        cache = config["sources"]["fplcache"]
        canonical = reconciliation["canonical_source"]
        comparison = reconciliation["comparison_source"]
        if canonical["provider_key"] != "vaastav" or canonical["source_path"] not in vaastav["files"]:
            raise FPLValidationError(
                "historical total_points canonical source must name a configured Vaastav file"
            )
        if canonical["field"] != "total_points":
            raise FPLValidationError(
                "historical total_points canonical field must be 'total_points'"
            )
        if comparison["provider_key"] != "fplcache" or comparison["field"] != "elements[].event_points":
            raise FPLValidationError(
                "historical total_points comparison source must be fplcache elements[].event_points"
            )
        if (
            comparison["require_event_finished"] is not True
            or comparison["require_data_checked"] is not True
        ):
            raise FPLValidationError(
                "historical total_points comparison must require finished and data_checked events"
            )
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


def create_build_identity(
    season: str, config: dict[str, Any], source_catalogue_schema_version: int
) -> dict[str, Any]:
    """Return deterministic build-affecting configuration, excluding run metadata."""

    schema_config = config["vaastav_source_schema"]
    source_schema = get_vaastav_source_schema(
        schema_config["schema_id"], season, schema_config["schema_version"]
    )
    cache = config["sources"]["fplcache"]
    canonical_contract = schema_document()
    return {
        "transformation_contract_version": TRANSFORMATION_CONTRACT_VERSION,
        "source_catalogue_schema_version": source_catalogue_schema_version,
        "season": season,
        "season_contract": {
            "expected_gameweeks": list(config["expected_gameweeks"]),
            "expected_counts": dict(config["expected_counts"]),
        },
        "vaastav_source_schema": {
            "schema_id": source_schema["schema_id"],
            "schema_version": source_schema["schema_version"],
            "contract_sha256": sha256_bytes(canonical_json_bytes(source_schema)),
        },
        "reconciliation": config["reconciliation"],
        "snapshot_selection": {
            "archive_path_pattern": cache["archive_path_pattern"],
            "capture_timezone": cache["capture_timezone"],
            "reference_snapshot_path": cache["reference_snapshot_path"],
            "points_settlement_snapshot_path": cache[
                "points_settlement_snapshot_path"
            ],
        },
        "canonical_schema_contract_sha256": sha256_bytes(
            canonical_json_bytes(canonical_contract)
        ),
        "fixture_context_policy_version": FIXTURE_CONTEXT_AVAILABILITY_POLICY[
            "policy_version"
        ],
    }


def create_reconciliation_provenance(
    season: str,
    config: dict[str, Any],
    source_schema: dict[str, object],
    comparison_snapshots: dict[int, tuple[dict[str, Any], str, str]],
    source_identity_sha256: str,
) -> dict[str, Any]:
    policy = config["reconciliation"]["total_points"]
    canonical_policy = policy["canonical_source"]
    comparison_policy = policy["comparison_source"]
    vaastav = config["sources"][canonical_policy["provider_key"]]
    comparison = config["sources"][comparison_policy["provider_key"]]
    return {
        "season": season,
        "canonical_source": {
            "provider": vaastav["provider"],
            "repository": vaastav["repository"],
            "configured_ref": vaastav["configured_ref"],
            "pinned_revision": vaastav["resolved_commit_sha"],
            "source_paths": [canonical_policy["source_path"]],
            "field": canonical_policy["field"],
        },
        "comparison_source": {
            "provider": comparison["provider"],
            "repository": comparison["repository"],
            "configured_ref": comparison["configured_ref"],
            "pinned_revision": comparison["resolved_commit_sha"],
            "source_paths": sorted(
                {source_path for _, source_path, _ in comparison_snapshots.values()}
            ),
            "field": comparison_policy["field"],
        },
        "source_identity_sha256": source_identity_sha256,
        "vaastav_source_schema": {
            "schema_id": source_schema["schema_id"],
            "schema_version": source_schema["schema_version"],
        },
        "reconciliation_policy": policy,
    }


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


def _source_identity(
    season: str, config: dict[str, Any], records: list[dict[str, Any]]
) -> dict[str, Any]:
    identities: dict[str, Any] = {}
    consumed_provider_keys = {record.get("provider_key") for record in records}
    for key, source in sorted(config["sources"].items()):
        if key not in consumed_provider_keys:
            continue
        identity = {
            "provider": source["provider"],
            "repository": source["repository"],
            "requested_season": season,
            "configured_ref": source["configured_ref"],
            "resolved_commit_sha": source["resolved_commit_sha"],
        }
        identities[key] = identity
    artifacts: list[dict[str, Any]] = []
    for record in sorted(
        records, key=lambda item: (item["provider_key"], item["source_path"])
    ):
        source = config["sources"].get(record["provider_key"])
        if source is None:
            raise FPLValidationError(
                f"raw manifest has unknown provider key: {record['provider_key']}"
            )
        for field in (
            "provider",
            "repository",
            "configured_ref",
            "resolved_commit_sha",
        ):
            if record.get(field) != source[field]:
                raise FPLValidationError(
                    f"raw manifest {record['source_path']} has wrong {field}"
                )
        if record.get("requested_season") != season:
            raise FPLValidationError(
                f"raw manifest {record['source_path']} has wrong requested season"
            )
        artifacts.append(
            {
                "provider_key": record["provider_key"],
                "source_path": record["source_path"],
                "source_url": record["source_url"],
                "sha256": record["sha256"],
                "byte_size": record["byte_size"],
                "consumption_roles": sorted(record.get("consumption_roles", [])),
            }
        )
    return {
        "identity_contract_version": 2,
        "requested_season": season,
        "sources": identities,
        "immutable_artifacts": artifacts,
    }


def _source_discovery_audit(
    cached_records: list[dict[str, Any]], consumed_records: list[dict[str, Any]]
) -> dict[str, Any]:
    consumed_keys = {
        (record["provider_key"], record["source_path"])
        for record in consumed_records
    }
    excluded = sorted(
        (
            {
                "provider_key": record["provider_key"],
                "source_path": record["source_path"],
                "classification": "cached_or_inspected_non_contributing",
            }
            for record in cached_records
            if (record["provider_key"], record["source_path"])
            not in consumed_keys
        ),
        key=lambda record: (record["provider_key"], record["source_path"]),
    )
    return {
        "consumed_record_count": len(consumed_records),
        "non_contributing_record_count": len(excluded),
        "non_contributing_records": excluded,
        "rule": (
            "Rejected snapshot candidates and unrelated cache entries may remain in "
            "the mutable raw-cache manifest, but do not enter the frozen consumed "
            "inventory or source identity."
        ),
    }


def _write_failed_quality_report(
    historical_root: Path,
    season: str,
    version: str,
    attempted_at: datetime,
    source_identity_sha256: str,
    build_identity_sha256: str,
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
            "build_identity_sha256": build_identity_sha256,
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
    config: dict[str, Any],
    build_identity: dict[str, Any],
    build_identity_sha256: str,
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
    if manifest.get("build_identity_sha256") != build_identity_sha256:
        raise FPLValidationError(
            f"existing processed directory has different build identity: {processed_dir}"
        )
    if manifest.get("build_identity") != build_identity:
        raise FPLValidationError(
            f"existing processed manifest build contract does not match: {processed_dir}"
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
    raw_records, inventory_status = _load_build_source_inventory(
        processed_dir, raw_dir, manifest
    )
    source_identity = _source_identity(season, config, raw_records)
    source_identity_sha256 = sha256_bytes(canonical_json_bytes(source_identity))
    if manifest.get("source_identity_sha256") != source_identity_sha256:
        raise FPLValidationError(
            f"existing processed directory has different source identity: {processed_dir}"
        )
    if manifest.get("source_identity") != source_identity:
        raise FPLValidationError(
            f"existing processed manifest source identity does not match: {processed_dir}"
        )
    _update_latest_catalogue(
        catalogue_path, season, version, processed_dir, manifest_path, now, manifest
    )
    return _result_from_manifest(
        season, raw_dir, processed_dir, manifest, True, inventory_status
    )


def _load_build_source_inventory(
    processed_dir: Path,
    raw_dir: Path,
    manifest: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    frozen = manifest.get("frozen_source_inventory")
    if frozen is not None:
        if not isinstance(frozen, dict):
            raise FPLValidationError("processed manifest frozen source inventory is malformed")
        relative = Path(frozen.get("path", ""))
        if not relative.parts or relative.is_absolute() or ".." in relative.parts:
            raise FPLValidationError(
                "processed manifest frozen source inventory path must be portable and relative"
            )
        inventory_path = processed_dir / relative
        if not inventory_path.is_file() or sha256_file(inventory_path) != frozen.get(
            "sha256"
        ):
            raise FPLValidationError(
                f"frozen source inventory failed checksum: {inventory_path}"
            )
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            records = inventory["files"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise FPLValidationError(f"frozen source inventory is invalid: {exc}") from exc
        if (
            inventory.get("season") != manifest.get("season")
            or inventory.get("source_version") != manifest.get("source_version")
            or inventory.get("source_identity") != manifest.get("source_identity")
            or inventory.get("source_identity_sha256")
            != manifest.get("source_identity_sha256")
            or frozen.get("source_identity") != manifest.get("source_identity")
            or frozen.get("source_identity_sha256")
            != manifest.get("source_identity_sha256")
        ):
            raise FPLValidationError(
                f"frozen source inventory identity does not match build manifest: {inventory_path}"
            )
        if sha256_bytes(canonical_json_bytes(inventory["source_identity"])) != inventory[
            "source_identity_sha256"
        ]:
            raise FPLValidationError(
                f"frozen source inventory has an invalid source identity hash: {inventory_path}"
            )
        status = "frozen_per_build"
    else:
        source_manifest = raw_dir / "source_manifest.json"
        if not source_manifest.is_file():
            raise FPLValidationError(
                f"legacy build has no shared raw source inventory: {source_manifest}"
            )
        if sha256_file(source_manifest) != manifest.get("source_manifest", {}).get(
            "sha256"
        ):
            raise FPLValidationError(
                "legacy build depends on a shared raw inventory whose checksum has changed: "
                f"{source_manifest}"
            )
        try:
            shared_inventory = json.loads(source_manifest.read_text(encoding="utf-8"))
            shared_records = shared_inventory["files"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise FPLValidationError(
                f"legacy shared raw source inventory is invalid: {exc}"
            ) from exc
        records = manifest.get("source_files")
        if not isinstance(shared_records, list) or not isinstance(records, list):
            raise FPLValidationError("legacy source inventory files must be arrays")
        shared_by_key = {
            (record.get("provider_key"), record.get("source_path")): record
            for record in shared_records
            if isinstance(record, dict)
        }
        for record in records:
            if not isinstance(record, dict):
                raise FPLValidationError(
                    "legacy processed manifest contains malformed source record"
                )
            shared_record = shared_by_key.get(
                (record.get("provider_key"), record.get("source_path"))
            )
            comparable = {
                key: value
                for key, value in record.items()
                if key != "consumption_roles"
            }
            if shared_record != comparable:
                raise FPLValidationError(
                    "legacy processed source record does not match shared raw inventory: "
                    f"{record.get('source_path')}"
                )
        status = "legacy_shared_raw_inventory"

    if not isinstance(records, list):
        raise FPLValidationError("source inventory files must be an array")
    if manifest.get("source_files") != records:
        raise FPLValidationError(
            "source inventory file records do not match the processed manifest"
        )
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("raw_path"), str):
            raise FPLValidationError("source inventory contains a malformed file record")
        relative_raw_path = Path(record["raw_path"])
        if relative_raw_path.is_absolute() or ".." in relative_raw_path.parts:
            raise FPLValidationError("source inventory raw_path must be portable and relative")
        raw_path = raw_dir / relative_raw_path
        if (
            not raw_path.is_file()
            or raw_path.stat().st_size != record.get("byte_size")
            or sha256_file(raw_path) != record.get("sha256")
        ):
            raise FPLValidationError(f"immutable raw file failed checksum: {raw_path}")
    return records, status


def load_historical_build(
    season: str,
    version: str,
    output_dir: Path | str = Path("data"),
) -> HistoricalPipelineResult:
    """Resolve and checksum-verify a recorded historical build without rebuilding it."""

    root = Path(output_dir) / "historical"
    catalogue_path = root / "catalogue.json"
    try:
        catalogue = json.loads(catalogue_path.read_text(encoding="utf-8"))
        season_entry = catalogue["seasons"][season]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FPLValidationError(f"historical catalogue lookup failed: {exc}") from exc
    build_entry = season_entry.get("builds", {}).get(version)
    if build_entry is None and season_entry.get("latest_successful_version") == version:
        build_entry = season_entry
    if not isinstance(build_entry, dict):
        raise FPLValidationError(
            f"historical build {version!r} is not recorded for season {season!r}"
        )
    processed_relative = Path(build_entry["processed_path"])
    manifest_relative = Path(build_entry["manifest_path"])
    if (
        processed_relative.is_absolute()
        or manifest_relative.is_absolute()
        or ".." in processed_relative.parts
        or ".." in manifest_relative.parts
    ):
        raise FPLValidationError("historical catalogue build paths must be portable and relative")
    processed_dir = root / processed_relative
    manifest_path = root / manifest_relative
    if not manifest_path.is_file() or sha256_file(manifest_path) != build_entry.get(
        "manifest_sha256"
    ):
        raise FPLValidationError(
            f"historical build manifest failed catalogue checksum: {manifest_path}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FPLValidationError(f"historical build manifest is invalid: {exc}") from exc
    if manifest.get("season") != season or manifest.get("version") != version:
        raise FPLValidationError("historical build manifest identity does not match lookup")
    for record in manifest.get("processed_files", []):
        path = processed_dir / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise FPLValidationError(f"historical build file failed checksum: {path}")
    source_version = manifest.get("source_version", version)
    raw_dir = root / "raw" / season / source_version
    _, inventory_status = _load_build_source_inventory(processed_dir, raw_dir, manifest)
    return _result_from_manifest(
        season, raw_dir, processed_dir, manifest, True, inventory_status
    )


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
        catalogue = {"schema_version": 2, "seasons": {}}
    historical_root = path.parent
    build_entry = {
        "version": version,
        "processed_path": str(processed_dir.relative_to(historical_root)),
        "manifest_path": str(manifest_path.relative_to(historical_root)),
        "manifest_sha256": sha256_file(manifest_path),
        "processed_at_utc": manifest["processed_at_utc"],
        "row_counts": manifest["row_counts"],
        "snapshot_coverage": manifest["snapshot_coverage"],
        "source_identity": manifest["source_identity"],
        "source_identity_sha256": manifest["source_identity_sha256"],
        "build_identity": manifest["build_identity"],
        "build_identity_sha256": manifest["build_identity_sha256"],
        "source_inventory_status": (
            "frozen_per_build"
            if "frozen_source_inventory" in manifest
            else "legacy_shared_raw_inventory"
        ),
    }
    if "frozen_source_inventory" in manifest:
        build_entry["frozen_source_inventory"] = manifest[
            "frozen_source_inventory"
        ]
    seasons = catalogue.setdefault("seasons", {})
    previous = seasons.get(season, {})
    builds = dict(previous.get("builds", {})) if isinstance(previous, dict) else {}
    if isinstance(previous, dict) and previous.get("latest_successful_version"):
        previous_version = previous["latest_successful_version"]
        if previous_version not in builds:
            previous_build = {
                key: value
                for key, value in previous.items()
                if key not in {"latest_successful_version", "builds"}
            }
            previous_build["version"] = previous_version
            previous_build.setdefault(
                "source_inventory_status", "legacy_shared_raw_inventory"
            )
            builds[previous_version] = previous_build
    for candidate_manifest_path in sorted(
        processed_dir.parent.glob("*/manifest.json")
    ):
        candidate_version = candidate_manifest_path.parent.name
        if candidate_version in builds or candidate_version == version:
            continue
        try:
            candidate_manifest = json.loads(
                candidate_manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise FPLValidationError(
                f"legacy processed manifest is invalid: {candidate_manifest_path}: {exc}"
            ) from exc
        if (
            candidate_manifest.get("season") != season
            or candidate_manifest.get("version") != candidate_version
        ):
            raise FPLValidationError(
                f"legacy processed manifest has wrong identity: {candidate_manifest_path}"
            )
        candidate_entry = {
            "version": candidate_version,
            "processed_path": str(
                candidate_manifest_path.parent.relative_to(historical_root)
            ),
            "manifest_path": str(
                candidate_manifest_path.relative_to(historical_root)
            ),
            "manifest_sha256": sha256_file(candidate_manifest_path),
            "processed_at_utc": candidate_manifest.get("processed_at_utc"),
            "row_counts": candidate_manifest.get("row_counts", {}),
            "snapshot_coverage": candidate_manifest.get("snapshot_coverage", {}),
            "source_identity": candidate_manifest.get("source_identity"),
            "source_identity_sha256": candidate_manifest.get(
                "source_identity_sha256"
            ),
            "build_identity": candidate_manifest.get("build_identity"),
            "build_identity_sha256": candidate_manifest.get(
                "build_identity_sha256"
            ),
            "source_inventory_status": (
                "frozen_per_build"
                if "frozen_source_inventory" in candidate_manifest
                else "legacy_shared_raw_inventory"
            ),
        }
        if "frozen_source_inventory" in candidate_manifest:
            candidate_entry["frozen_source_inventory"] = candidate_manifest[
                "frozen_source_inventory"
            ]
        builds[candidate_version] = candidate_entry
    builds[version] = build_entry
    entry = {
        "latest_successful_version": version,
        **{key: value for key, value in build_entry.items() if key != "version"},
        "builds": {key: builds[key] for key in sorted(builds)},
    }
    if seasons.get(season) == entry:
        return
    catalogue["schema_version"] = 2
    catalogue["updated_at_utc"] = utc_string(updated_at)
    seasons[season] = entry
    atomic_write_json(path, catalogue)


def _result_from_manifest(
    season: str,
    raw_dir: Path,
    processed_dir: Path,
    manifest: dict[str, Any],
    reused: bool,
    inventory_status: str | None = None,
) -> HistoricalPipelineResult:
    coverage = manifest["snapshot_coverage"]
    artifact_inventory = manifest.get("artifact_inventory")
    if not isinstance(artifact_inventory, dict):
        artifact_inventory = {
            "generated_table_count": len(manifest.get("row_counts", {})),
            "generated_artifact_count": len(manifest.get("processed_files", [])) + 1,
        }
    return HistoricalPipelineResult(
        season=season,
        version=manifest["version"],
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        row_counts=manifest["row_counts"],
        snapshot_gameweeks=coverage["accepted_gameweeks"],
        missing_snapshot_gameweeks=tuple(coverage["missing_gameweeks"]),
        generated_table_count=artifact_inventory["generated_table_count"],
        generated_artifact_count=artifact_inventory[
            "generated_artifact_count"
        ],
        source_inventory_status=(
            inventory_status
            or (
                "frozen_per_build"
                if "frozen_source_inventory" in manifest
                else "legacy_shared_raw_inventory"
            )
        ),
        reused=reused,
    )
