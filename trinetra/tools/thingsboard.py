"""Thin REST client for a live ThingsBoard tenant (e.g. demo.thingsboard.io).

Pure code, no LLM - same discipline as rainfall.py's Open-Meteo client: on
failure this says so honestly and returns None, it never fabricates a
plausible-looking telemetry value. A fabricated crowd-density reading feeding
an evacuation decision is exactly the failure mode this repo refuses
everywhere else.

Credentials come from the environment only - THINGSBOARD_URL,
THINGSBOARD_USERNAME, THINGSBOARD_PASSWORD (or THINGSBOARD_API_KEY for
ThingsBoard 4.3+ API-key auth). Nothing here ever logs, prints, or returns a
credential value; error messages are truncated before being surfaced so a
stack trace can't leak a token. Mirrors the TB_URL/TB_USER/TB_PASSWORD
convention used by github.com/akashtalole/KumbhDigiTwin's own
provision.py, so the same environment works against either tool.

This module intentionally does NOT depend on the official ThingsBoard MCP
server (github.com/thingsboard/thingsboard-mcp) even though one exists: that
project is for driving ThingsBoard from an interactive assistant session, not
for a deployed FastAPI backend calling out to it on every request. Trinetra's
tools are plain Python functions hitting HTTP APIs directly (see rainfall.py,
network_delivery.py) precisely so a live client works the same way whether or
not the MCP server happens to be installed - the "code computes, models
interpret" boundary does not want an assistant-protocol layer in the middle
of it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from trinetra.tools._http import get_with_retries

DEFAULT_BASE_URL = "https://demo.thingsboard.io"
_LOGIN_PATH = "/api/auth/login"
_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class ThingsBoardConfig:
    """Connection details for one ThingsBoard tenant. Never logged or
    serialized - callers should not include this in any model_dump_json()
    output, structured_output payload, or rendered Markdown."""

    base_url: str
    username: str | None = None
    password: str | None = None
    api_key: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key or (self.username and self.password))


def load_config_from_env() -> ThingsBoardConfig:
    """Reads THINGSBOARD_URL / THINGSBOARD_USERNAME / THINGSBOARD_PASSWORD /
    THINGSBOARD_API_KEY. Returns a config with configured=False if neither
    credential form is present - callers must check that before calling
    anything else in this module, and must surface the honest "not
    configured" message rather than silently skipping the live check."""
    return ThingsBoardConfig(
        base_url=os.environ.get("THINGSBOARD_URL", DEFAULT_BASE_URL).rstrip("/"),
        username=os.environ.get("THINGSBOARD_USERNAME") or None,
        password=os.environ.get("THINGSBOARD_PASSWORD") or None,
        api_key=os.environ.get("THINGSBOARD_API_KEY") or None,
    )


class ThingsBoardError(Exception):
    """Raised for any ThingsBoard call that failed. The message is safe to
    log and display - see _safe_detail below."""


def _safe_detail(exc: Exception) -> str:
    """A short, credential-free description of an HTTP failure. httpx error
    messages can echo the request URL (which never contains a credential in
    this module - the token/key goes in a header, not a query string) but we
    still cap the length and never include response bodies verbatim, since a
    ThingsBoard error page could in principle echo back a header."""
    return f"{type(exc).__name__}: {str(exc)[:200]}"


def _auth_headers(config: ThingsBoardConfig, token: str | None) -> dict[str, str]:
    if config.api_key:
        return {"X-Authorization": f"ApiKey {config.api_key}"}
    if token:
        return {"X-Authorization": f"Bearer {token}"}
    return {}


def login(config: ThingsBoardConfig) -> str | None:
    """Returns a JWT, or None if API-key auth is configured instead (in
    which case no login call is needed - see _auth_headers)."""
    if config.api_key:
        return None
    if not (config.username and config.password):
        raise ThingsBoardError("no THINGSBOARD_USERNAME/PASSWORD or THINGSBOARD_API_KEY configured")
    response = get_with_retries(
        lambda: httpx.post(
            f"{config.base_url}{_LOGIN_PATH}",
            json={"username": config.username, "password": config.password},
            timeout=_TIMEOUT_SECONDS,
        )
    )
    if response.status_code != 200:
        raise ThingsBoardError(f"login failed with HTTP {response.status_code}")
    token = response.json().get("token")
    if not token:
        raise ThingsBoardError("login response had no token field")
    return token


def _get(config: ThingsBoardConfig, token: str | None, path: str, params: dict | None = None) -> dict | list:
    response = get_with_retries(
        lambda: httpx.get(
            f"{config.base_url}{path}",
            params=params,
            headers=_auth_headers(config, token),
            timeout=_TIMEOUT_SECONDS,
        )
    )
    if response.status_code != 200:
        raise ThingsBoardError(f"GET {path} -> HTTP {response.status_code}")
    return response.json()


def find_entity_id(
    config: ThingsBoardConfig, token: str | None, entity_type: str, name: str
) -> str | None:
    """entity_type is "ASSET" or "DEVICE". Pages the tenant's entities
    looking for an exact name match - ThingsBoard's textSearch is a substring
    match and this repo needs an exact one (e.g. "Ramkund" must not
    accidentally match "Ramkund and near by Ghats" or vice versa).

    Returns None if not found - this is an expected, honest outcome (see
    live_signals.py's GHAT_ID_TO_THINGSBOARD_ASSET mapping, which documents
    that most of Trinetra's ghats have no ThingsBoard counterpart in the
    current KumbhDigiTwin provisioning), not an error.
    """
    list_path = "/api/tenant/assets" if entity_type == "ASSET" else "/api/tenant/devices"
    page = 0
    while True:
        payload = _get(config, token, list_path, params={"pageSize": 100, "page": page})
        for entity in payload.get("data", []):
            if entity.get("name") == name:
                return entity["id"]["id"]
        if not payload.get("hasNext"):
            return None
        page += 1
        if page > 50:  # a runaway pagination loop must not hang a request forever
            return None


def get_latest_telemetry(
    config: ThingsBoardConfig, token: str | None, entity_type: str, entity_id: str, keys: list[str]
) -> dict[str, tuple[float | str, datetime]]:
    """Latest value + timestamp per key. Non-numeric values (e.g. losGrade,
    which is a letter grade) are returned as strings; callers that expect a
    number should coerce and catch ValueError rather than assuming."""
    payload = _get(
        config,
        token,
        f"/api/plugins/telemetry/{entity_type}/{entity_id}/values/timeseries",
        params={"keys": ",".join(keys)},
    )
    result: dict[str, tuple[float | str, datetime]] = {}
    for key, points in payload.items():
        if not points:
            continue
        latest = points[0]
        raw_value = latest["value"]
        ts = datetime.fromtimestamp(latest["ts"] / 1000, tz=timezone.utc)
        try:
            result[key] = (float(raw_value), ts)
        except (TypeError, ValueError):
            result[key] = (raw_value, ts)
    return result


def get_server_attributes(
    config: ThingsBoardConfig, token: str | None, entity_type: str, entity_id: str, keys: list[str]
) -> dict[str, float | str]:
    payload = _get(
        config,
        token,
        f"/api/plugins/telemetry/{entity_type}/{entity_id}/values/attributes/SERVER_SCOPE",
        params={"keys": ",".join(keys)},
    )
    result: dict[str, float | str] = {}
    for entry in payload:
        value = entry["value"]
        try:
            result[entry["key"]] = float(value)
        except (TypeError, ValueError):
            result[entry["key"]] = value
    return result
