"""Renders a PilgrimGuidance/SafetyTriage response for whatever channel a
pilgrim actually has - not every pilgrim at a 30-50 million person event
has a working smartphone data connection. See TRINETRA.md's
network-resilience section for the reasoning; this module is the part of
that design that's actually implemented (deterministic text formatting),
as opposed to the SMS/USSD gateway integration itself, which needs a real
telecom partner and is explicitly out of scope for this build - see the
module-level honest-limitations note below.

HONEST LIMITATION: this module formats text for SMS/USSD-sized payloads.
It does not send an SMS or serve a USSD session - that requires a telecom
aggregator contract (e.g. an SMS gateway API key) this project has no
access to and cannot fabricate. A real deployment wires the strings this
module produces into that gateway's send API.
"""
from __future__ import annotations

from trinetra.models import NetworkMode, PilgrimGuidance, SafetyTriage

# GSM-7 single-segment SMS is 160 characters; stay under that so a reply
# never silently splits into a second segment a low-end phone might not
# reassemble correctly.
_SMS_CHAR_LIMIT = 160

# A basic USSD screen is conventionally kept to ~182 characters across a
# menu response on most carriers' gateways - kept separate from the SMS
# limit even though they're close, since the two channels have different
# real-world constraints (session timeout vs. store-and-forward).
_USSD_CHAR_LIMIT = 180


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"  # ellipsis


def render_guidance_for_channel(guidance: PilgrimGuidance, mode: NetworkMode) -> str:
    """Renders one PilgrimGuidance for the given delivery channel. The
    underlying agent answer is generated once, regardless of channel -
    this function only controls presentation, so a pilgrim on SMS and a
    pilgrim on the full app get the same underlying judgment, just
    formatted for what their device/connection can actually carry."""
    if mode == NetworkMode.SMS:
        core = guidance.answer
        if guidance.escalate_to_sos:
            core = "EMERGENCY: " + core
        return _truncate(core, _SMS_CHAR_LIMIT)

    if mode == NetworkMode.USSD:
        core = guidance.answer
        if guidance.safety_note:
            core = f"{core} | {guidance.safety_note}"
        return _truncate(core, _USSD_CHAR_LIMIT)

    if mode == NetworkMode.APP_OFFLINE_QUEUED:
        return (
            f"{guidance.answer}\n\n"
            "(This response was generated while you were offline and is queued to sync. "
            "Crowd advisories may be out of date until your connection is restored.)"
        )

    # APP_ONLINE and KIOSK get the full structured response.
    parts = [guidance.answer]
    if guidance.suggested_route:
        parts.append(f"Suggested route: {guidance.suggested_route}")
    if guidance.ghat_crowd_advisory:
        parts.append(f"Crowd status: {guidance.ghat_crowd_advisory}")
    if guidance.safety_note:
        parts.append(f"Safety note: {guidance.safety_note}")
    return "\n".join(parts)


def render_triage_for_channel(triage: SafetyTriage, mode: NetworkMode) -> str:
    if mode in (NetworkMode.SMS, NetworkMode.USSD):
        limit = _SMS_CHAR_LIMIT if mode == NetworkMode.SMS else _USSD_CHAR_LIMIT
        return _truncate(f"{triage.immediate_action} -> {triage.dispatch_target}", limit)

    return (
        f"Severity: {triage.severity.value.upper()}\n"
        f"Do now: {triage.immediate_action}\n"
        f"Routed to: {triage.dispatch_target}\n"
        f"Why: {triage.rationale}"
    )
