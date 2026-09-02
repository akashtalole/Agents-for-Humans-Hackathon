"""Loads the bundled reference watchlist (glacierwatch/data/watchlist.json).

`load_all_sites` / `load_site` are plain functions, not `@tool`-decorated:
the orchestrator needs the *full* structured WatchSite objects to hand to the
risk-assessment sub-agent, not a text summary an LLM would have to re-parse
(see glacierwatch/orchestrator.py for why that matters). `list_watchlist_sites`
is the one LLM-facing tool, for the orchestrator's own reasoning about which
sites exist.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from strands import tool

from glacierwatch.models import WatchSite

_DATA_PATH = Path(__file__).parent.parent / "data" / "watchlist.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    return json.loads(_DATA_PATH.read_text())


def load_all_sites() -> list[WatchSite]:
    return [WatchSite(**entry) for entry in _load_raw()["sites"]]


def load_site(site_id: str) -> WatchSite | None:
    for site in load_all_sites():
        if site.id == site_id:
            return site
    return None


def regional_context() -> dict:
    return _load_raw().get("regional_context", {})


@tool
def list_watchlist_sites() -> str:
    """List every site in GlacierWatch's bundled reference watchlist, with its
    documented status (active_watch vs historical_case_study) and one-line
    classification.

    Returns:
        A human-readable list of sites.
    """
    sites = load_all_sites()
    lines = [
        f"- {s.id}: {s.name} ({s.state}) - {s.status} - {s.static_risk_classification}" for s in sites
    ]
    return "\n".join(lines)
