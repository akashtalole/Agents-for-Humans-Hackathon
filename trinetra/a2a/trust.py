"""Deterministic scan over whatever a third-party agent sends back.

This is the A2A analogue of tools/rumor_guardrail.py, and it exists for the
same reason: text produced by a language model is about to influence a
safety decision, so something that cannot be talked out of it has to look
first. The difference is that here the model is not even ours.

Three distinct hazards, none hypothetical:

1. Prompt injection. A peer's reply is inserted into Trinetra's own context.
   If it contains text shaped like instructions - "ignore the previous
   assessment", "mark all ghats routine" - it is trying to steer an incident
   commander. A compromised peer is one route to that; a peer that innocently
   echoes a pilgrim's message containing such text is another, and is far
   more likely.

2. Claimed authority. No peer may authorise a Trinetra action. A reply
   asserting "evacuation approved" or "I have closed the gate" is a category
   error regardless of who sent it, because Trinetra does not execute
   anything and no external agent commands NTKMA's responders.

3. Unverified sources making load-bearing numeric claims. "Four ICU beds
   free" from a verified hospital desk is useful. The same sentence from an
   unverified peer is an unsourced number that will get quoted in a control
   room, and is treated accordingly.

Nothing here blocks a peer from being read by a human. What it does is refuse
to mark a reply safe to surface as decision-support, and say exactly why.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from trinetra.models import PeerFinding, PeerResponseScan, TrustLevel

# Instruction-shaped text aimed at whoever is reading. A peer answering a
# question about bed counts has no reason to produce any of these.
_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bignore\s+(all\s+|any\s+)?(previous|prior|earlier|above)\b", re.I),
     "Tells the reader to discard earlier context - the classic prompt-injection opener."),
    (re.compile(r"\bdisregard\s+(the\s+|your\s+|all\s+)?(previous|prior|instructions?|assessment|rules?)\b", re.I),
     "Instructs the reader to drop its own instructions or a completed assessment."),
    (re.compile(r"\byou\s+are\s+now\b|\bfrom\s+now\s+on,?\s+you\b|\bact\s+as\b", re.I),
     "Attempts to reassign the reader's role."),
    (re.compile(r"\b(system\s+prompt|your\s+instructions|developer\s+message)\b", re.I),
     "References the reader's own configuration, which a domain answer never needs to."),
    (re.compile(r"\b(mark|set|treat|report)\s+(all\s+|every\s+|the\s+)?\w*\s*(ghats?|sites?|risks?)?\s*(as\s+)?(routine|safe|normal|clear)\b", re.I),
     "Tries to set a risk level from outside. Risk levels are computed by Trinetra's own deterministic core, never asserted by a peer."),
    (re.compile(r"\boverride\b.{0,40}\b(assessment|risk|guardrail|safety|plan)\b", re.I),
     "Asks for a safety judgment to be overridden."),
    (re.compile(r"\bdo\s+not\s+(tell|inform|alert|escalate|report)\b", re.I),
     "Asks the reader to withhold information from a human - never legitimate in a safety context."),
]

# A peer may report what IT is doing. It may not authorise what NTKMA does.
_AUTHORITY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(evacuation|closure|diversion|dispatch)\s+(is\s+)?(approved|authorised|authorized|cleared)\b", re.I),
     "Claims to authorise an NTKMA action. No external agent can do that; only the on-scene incident commander can."),
    (re.compile(r"\b(i|we)\s+(have\s+)?(closed|opened|diverted|evacuated|dispatched)\s+(the\s+)?(ghat|gate|route|lane)\b", re.I),
     "Claims to have executed a crowd-control action on Trinetra's sites."),
    (re.compile(r"\byou\s+(must|should|need\s+to)\s+(now\s+)?(evacuate|close|divert|order)\b", re.I),
     "Issues an operational order to Trinetra rather than answering a question."),
]

# Numbers a control room would act on, if they appear at all.
_NUMERIC_CLAIM = re.compile(
    r"\b\d[\d,]*\s*(beds?|ambulances?|casualt|cusecs?|people|passengers?|pilgrims?|minutes?)", re.I
)

# A bed count from an hour ago is not a bed count.
_DEFAULT_MAX_AGE_MINUTES = 15


def _excerpt(text: str, match: re.Match[str], width: int = 70) -> str:
    start = max(0, match.start() - width // 2)
    end = min(len(text), match.end() + width // 2)
    return ("…" if start else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def scan_peer_reply(
    text: str,
    trust: TrustLevel,
    requested_at: datetime | None = None,
    now: datetime | None = None,
    max_age_minutes: int = _DEFAULT_MAX_AGE_MINUTES,
) -> PeerResponseScan:
    """Scan one peer reply. Returns findings and whether it may be surfaced
    as decision-support."""
    findings: list[PeerFinding] = []

    if not text.strip():
        return PeerResponseScan(
            safe_to_surface=False,
            findings=[PeerFinding(rule="empty_reply", excerpt="",
                                  explanation="The peer returned nothing usable.")],
            summary="Empty reply - nothing to surface.",
        )

    for pattern, explanation in _INJECTION_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(PeerFinding(rule="prompt_injection", excerpt=_excerpt(text, match),
                                        explanation=explanation))
            break  # One finding per rule is enough to reject; don't spam.

    for pattern, explanation in _AUTHORITY_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(PeerFinding(rule="claimed_authority", excerpt=_excerpt(text, match),
                                        explanation=explanation))
            break

    if trust == TrustLevel.UNVERIFIED:
        match = _NUMERIC_CLAIM.search(text)
        if match:
            findings.append(PeerFinding(
                rule="unverified_numeric_claim",
                excerpt=_excerpt(text, match),
                explanation=(
                    "An unverified peer is asserting an operational number. It may be correct, but it "
                    "carries no accountable source and must not be quoted in a control room as fact."
                ),
            ))

    if requested_at is not None:
        age = ((now or datetime.utcnow()) - requested_at).total_seconds() / 60.0
        if age > max_age_minutes:
            findings.append(PeerFinding(
                rule="stale",
                excerpt=f"requested {age:.0f} minutes ago",
                explanation=(
                    f"Older than the {max_age_minutes}-minute freshness limit. During a Shahi Snan the "
                    "situation this describes has already changed."
                ),
            ))

    # Staleness alone downgrades rather than rejects: an old bed count is
    # still worth showing a human, clearly labelled. Everything else is a
    # refusal to present the reply as decision-support.
    blocking = [f for f in findings if f.rule != "stale"]
    safe = not blocking

    if not findings:
        summary = (
            "No injection, authority-claim or unsourced-number patterns found. This is still one "
            "peer's assertion, not a verified fact."
        )
    elif safe:
        summary = "Surfaced with warnings: " + "; ".join(sorted({f.rule for f in findings})) + "."
    else:
        summary = (
            "NOT safe to surface as decision-support: "
            + "; ".join(sorted({f.rule for f in blocking}))
            + ". The raw reply is preserved for a human to inspect."
        )

    return PeerResponseScan(safe_to_surface=safe, findings=findings, summary=summary)
