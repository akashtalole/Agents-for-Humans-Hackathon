"""Loads the bundled illustrative downstream-exposure reference data
(glacierwatch/data/downstream_exposure.json).

Same shape as tools/watchlist.py: `load_downstream_exposure` is a plain
function, not `@tool`-decorated, so the orchestrator can hand the alert
drafter sub-agent full structured DownstreamSettlement objects rather than a
text summary it would have to re-parse. A site id with no documented entry
returns an empty list rather than erroring - not every watchlist site
necessarily has downstream data yet, and that's a fact for the alert drafter
to state plainly, not a pipeline failure.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from glacierwatch.models import DownstreamSettlement

_DATA_PATH = Path(__file__).parent.parent / "data" / "downstream_exposure.json"


@lru_cache(maxsize=1)
def _load_raw() -> dict:
    return json.loads(_DATA_PATH.read_text())


def load_downstream_exposure(site_id: str) -> list[DownstreamSettlement]:
    entries = _load_raw().get("sites", {}).get(site_id, [])
    return [DownstreamSettlement(**entry) for entry in entries]


def data_caveat() -> str:
    return _load_raw().get("data_caveat", "")
