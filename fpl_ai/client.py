"""Small HTTP client for public Fantasy Premier League data endpoints."""

from __future__ import annotations

import json
import ssl
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fpl_ai.errors import FPLDownloadError

DEFAULT_BASE_URL = "https://fantasy.premierleague.com/api"
BOOTSTRAP_PATH = "bootstrap-static/"
FIXTURES_PATH = "fixtures/"


class FPLClient:
    """Retrieve public, unauthenticated FPL JSON resources."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.ssl_context = _verified_ssl_context()

    def get_bootstrap(self) -> dict[str, Any]:
        payload = self._get_json(BOOTSTRAP_PATH)
        if not isinstance(payload, dict):
            raise FPLDownloadError("bootstrap-static response was not a JSON object")
        return payload

    def get_fixtures(self) -> list[dict[str, Any]]:
        payload = self._get_json(FIXTURES_PATH)
        if not isinstance(payload, list):
            raise FPLDownloadError("fixtures response was not a JSON array")
        return payload

    def get_event_live(self, gameweek: int) -> dict[str, Any]:
        if type(gameweek) is not int or not 1 <= gameweek <= 38:
            raise ValueError("invalid gameweek")
        payload = self._get_json(f"event/{gameweek}/live/")
        if not isinstance(payload, dict):
            raise FPLDownloadError("event live response was not a JSON object")
        return payload

    def _get_json(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "fpl-ai-platform/0.1",
            },
        )
        try:
            with urlopen(  # noqa: S310
                request, timeout=self.timeout, context=self.ssl_context
            ) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except HTTPError as exc:
            raise FPLDownloadError(
                f"FPL request failed with HTTP {exc.code}: {url}"
            ) from exc
        except URLError as exc:
            raise FPLDownloadError(f"Could not reach FPL endpoint {url}: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FPLDownloadError(f"FPL endpoint returned invalid JSON: {url}") from exc


def _verified_ssl_context() -> ssl.SSLContext:
    """Build a verified context, including a safe macOS Framework Python fallback."""

    context = ssl.create_default_context()
    if context.cert_store_stats()["x509_ca"]:
        return context

    # Some python.org macOS installs have no bundled CAs until their optional
    # certificate installer is run. Prefer the OS bundle when it exists; never
    # disable certificate verification.
    for candidate in (Path("/etc/ssl/cert.pem"), Path("/private/etc/ssl/cert.pem")):
        if candidate.is_file():
            return ssl.create_default_context(cafile=str(candidate))
    return context
