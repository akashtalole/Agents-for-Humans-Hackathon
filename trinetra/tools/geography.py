"""Loads Trinetra's bundled, cited Nashik-Trimbakeshwar site data.

See trinetra/data/sites.json's own "_citation_note" field: ghat/route
names and historical_note text are real and sourced; the numeric capacity
figures are Trinetra's own illustrative planning estimates, not official
NTKMA data - never presented as such.
"""
from __future__ import annotations

import json
from pathlib import Path

from trinetra.models import Ghat, Route

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "sites.json"


def load_sites() -> tuple[dict[str, Ghat], list[Route]]:
    raw = json.loads(_DATA_PATH.read_text())
    ghats = {g["id"]: Ghat(**g) for g in raw["ghats"]}
    routes = [Route(**r) for r in raw["routes"]]
    return ghats, routes
