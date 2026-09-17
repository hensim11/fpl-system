"""Operational season status, separate from immutable build configuration."""

import json
from pathlib import Path

from fpl_ai.errors import FPLValidationError


def season_statuses(output_dir, configured_seasons):
    root = Path(output_dir) / "historical"
    path = root / "catalogue.json"
    published = {}
    if path.exists():
        try:
            catalogue = json.loads(path.read_text())
            published = catalogue["seasons"]
            if not isinstance(published, dict):
                raise ValueError("seasons must be an object")
            if set(published) - set(configured_seasons):
                raise ValueError("published catalogue contains unconfigured seasons")
        except (ValueError, KeyError, TypeError) as exc:
            raise FPLValidationError(f"invalid published season catalogue: {exc}") from exc
    return {
        season: ("published" if season in published else
                 "blocked" if any((root / "failed" / season).glob("*.json")) else
                 "investigatory")
        for season in sorted(configured_seasons)
    }
