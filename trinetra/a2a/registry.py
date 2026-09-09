"""The A2A peer allowlist - pure code, no network.

Registration is an allowlist rather than a directory, and that is a security
decision rather than a convenience one. Open agent discovery means an incident
commander can end up quoting a stranger's number in a control room. Trinetra
will not call a URL that is not listed in data/a2a_peers.json.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from trinetra.models import PeerAgent, TrustLevel

_PEERS_PATH = Path(__file__).resolve().parent.parent / "data" / "a2a_peers.json"


@lru_cache(maxsize=1)
def load_peers(path: Path | None = None) -> dict[str, PeerAgent]:
    raw = json.loads((path or _PEERS_PATH).read_text(encoding="utf-8"))
    return {p["peer_id"]: PeerAgent(**p) for p in raw["peers"]}


def get_peer(peer_id: str) -> PeerAgent | None:
    return load_peers().get(peer_id)


def is_allowed(peer_id: str) -> bool:
    return peer_id in load_peers()


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens with a naive plural fold, so "beds" matches a
    declared capability of "bed availability". Crude on purpose - this is a
    routing hint, and the cost of a false match is one wasted request."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def peers_for_capability(capability: str) -> list[PeerAgent]:
    """Peers that claim they can answer about this topic.

    Token overlap against the peer's own declared capabilities. This routes a
    question to a plausible peer; it does not verify the peer can actually
    answer it. Only the peer's reply shows that.
    """
    needle = _tokens(capability)
    if not needle:
        return []
    return [
        peer for peer in load_peers().values()
        if any(needle & _tokens(c) for c in peer.capabilities)
    ]


def peers_by_trust(minimum: TrustLevel) -> list[PeerAgent]:
    order = {TrustLevel.UNVERIFIED: 0, TrustLevel.KNOWN_PARTNER: 1, TrustLevel.VERIFIED_AUTHORITY: 2}
    return [p for p in load_peers().values() if order[p.trust] >= order[minimum]]
