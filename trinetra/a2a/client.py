"""Consulting third-party agents over A2A.

Every reply that comes back through here is wrapped in a PeerResponse, which
carries who said it, when, at what trust level, and what the deterministic
scan in trust.py made of it. That wrapper is the entire point: it is what
stops a remote assertion from quietly becoming a number Trinetra plans with.

What this module deliberately does NOT do is feed peer output into
tools/hydrology.py, tools/simulator.py or tools/resources.py. Those compute
Trinetra's own safety figures, and they take their inputs from bundled data
and operator entry only. A peer can tell a human commander that the dam is
about to release 24,000 cusecs; a human then types that number in, having
decided to believe it. The alternative - letting a remote agent drive an
evacuation calculation directly - is not an integration, it is a way to have
someone else's outage become your stampede.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from trinetra.a2a.registry import get_peer, load_peers
from trinetra.a2a.trust import scan_peer_reply
from trinetra.models import PeerAgent, PeerConsultation, PeerResponse, TrustLevel

_DEFAULT_TIMEOUT_SECONDS = 20.0


def _wrap(peer: PeerAgent, question: str, text: str = "", error: str = "",
          requested_at: datetime | None = None) -> PeerResponse:
    requested_at = requested_at or datetime.utcnow()
    scan = scan_peer_reply(text, peer.trust, requested_at=requested_at) if text else None
    return PeerResponse(
        peer_id=peer.peer_id, peer_name=peer.name, operator=peer.operator, trust=peer.trust,
        requested_at=requested_at, question=question, text=text, error=error, scan=scan,
    )


async def _ask_one(peer: PeerAgent, question: str, timeout: float) -> PeerResponse:
    """Send one A2A message/send request and return the peer's text reply.

    Uses the a2a-sdk client so this speaks the real protocol - card resolution
    from /.well-known, then a JSON-RPC message/send - rather than a bespoke
    HTTP shape only Trinetra would understand.
    """
    requested_at = datetime.utcnow()
    try:
        from a2a.client import A2ACardResolver, ClientFactory
        from a2a.client.client import ClientConfig
        from a2a.client.helpers import create_text_message_object
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        return _wrap(peer, question, error=f"a2a-sdk is not installed: {exc}", requested_at=requested_at)

    try:
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            card = await A2ACardResolver(http_client, peer.base_url).get_agent_card()
            factory = ClientFactory(ClientConfig(httpx_client=http_client, streaming=False))
            client = factory.create(card)

            chunks: list[str] = []
            async for event in client.send_message(create_text_message_object(content=question)):
                chunks.append(_text_of(event))
            text = "\n".join(c for c in chunks if c).strip()
    except Exception as exc:
        # A peer being down is normal and must never take Trinetra with it -
        # this is decision support that has to keep working when the network
        # at a 30-million-person event does not.
        return _wrap(peer, question, error=f"{type(exc).__name__}: {exc}", requested_at=requested_at)

    return _wrap(peer, question, text=text, requested_at=requested_at)


def _text_of(event: object) -> str:
    """Pull plain text out of whatever the SDK yields, tolerantly.

    The A2A event union covers messages, tasks and status updates, and its
    exact shape varies by SDK version. Rather than pin one, this walks for
    text parts and returns nothing when it finds none - a peer whose reply
    cannot be read is handled as an unusable reply, not a crash.
    """
    seen: list[str] = []

    def walk(node: object, depth: int = 0) -> None:
        if depth > 6 or len(seen) > 50:
            return
        if isinstance(node, str):
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item, depth + 1)
            return
        text = getattr(node, "text", None)
        if isinstance(text, str) and text.strip():
            seen.append(text.strip())
        for attr in ("parts", "message", "artifacts", "status", "result", "root"):
            child = getattr(node, attr, None)
            if child is not None:
                walk(child, depth + 1)

    walk(event)
    return "\n".join(seen)


async def consult_peers_async(
    question: str,
    peer_ids: list[str] | None = None,
    minimum_trust: TrustLevel | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> PeerConsultation:
    """Ask several peers the same question concurrently.

    Concurrent because these are independent external systems and a control
    room cannot wait for four sequential round trips; a slow peer delays only
    itself.
    """
    peers = list(load_peers().values())
    if peer_ids is not None:
        selected = []
        for pid in peer_ids:
            peer = get_peer(pid)
            if peer is None:
                # Refused rather than attempted: an unregistered id is exactly
                # the case the allowlist exists to stop.
                continue
            selected.append(peer)
        peers = selected
    if minimum_trust is not None:
        order = {TrustLevel.UNVERIFIED: 0, TrustLevel.KNOWN_PARTNER: 1, TrustLevel.VERIFIED_AUTHORITY: 2}
        peers = [p for p in peers if order[p.trust] >= order[minimum_trust]]

    if not peers:
        return PeerConsultation(question=question, responses=[],
                                summary="No registered peer matched this request.")

    responses = await asyncio.gather(*(_ask_one(p, question, timeout) for p in peers))
    responses = list(responses)

    reachable = [r for r in responses if not r.error]
    usable = [r for r in responses if r.usable]
    blocked = [r for r in reachable if r.scan and not r.scan.safe_to_surface]

    parts = [f"{len(usable)} of {len(responses)} peers returned a usable answer"]
    if len(reachable) < len(responses):
        parts.append(f"{len(responses) - len(reachable)} unreachable")
    if blocked:
        parts.append(f"{len(blocked)} withheld by the trust scan")
    summary = ", ".join(parts) + ". Every answer below is one organisation's assertion, not a verified fact."

    return PeerConsultation(question=question, responses=responses, summary=summary)


def consult_peers(
    question: str,
    peer_ids: list[str] | None = None,
    minimum_trust: TrustLevel | None = None,
    timeout: float = _DEFAULT_TIMEOUT_SECONDS,
) -> PeerConsultation:
    """Blocking wrapper, for the CLI and for the API's thread-pool executor."""
    return asyncio.run(consult_peers_async(question, peer_ids, minimum_trust, timeout))
