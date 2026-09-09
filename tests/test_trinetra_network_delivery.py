"""Offline tests for trinetra/tools/network_delivery.py's channel-aware
text formatting - no LLM."""
from __future__ import annotations

from trinetra.models import NetworkMode, PilgrimGuidance, RiskLevel, SafetyTriage, IncidentType
from trinetra.tools.network_delivery import render_guidance_for_channel, render_triage_for_channel


def test_sms_output_never_exceeds_160_chars():
    guidance = PilgrimGuidance(
        answer="A" * 300,
        suggested_route="some very long route description " * 5,
    )
    rendered = render_guidance_for_channel(guidance, NetworkMode.SMS)
    assert len(rendered) <= 160


def test_ussd_output_never_exceeds_180_chars():
    guidance = PilgrimGuidance(answer="B" * 300, safety_note="C" * 100)
    rendered = render_guidance_for_channel(guidance, NetworkMode.USSD)
    assert len(rendered) <= 180


def test_sms_prefixes_emergency_when_escalated():
    guidance = PilgrimGuidance(answer="stay calm", escalate_to_sos=True)
    rendered = render_guidance_for_channel(guidance, NetworkMode.SMS)
    assert rendered.startswith("EMERGENCY:")


def test_app_online_includes_full_structured_fields():
    guidance = PilgrimGuidance(
        answer="Here is your answer",
        suggested_route="Route A",
        ghat_crowd_advisory="Moderately busy",
        safety_note="Watch your belongings",
    )
    rendered = render_guidance_for_channel(guidance, NetworkMode.APP_ONLINE)
    assert "Route A" in rendered
    assert "Moderately busy" in rendered
    assert "Watch your belongings" in rendered


def test_offline_queued_mentions_sync_status():
    guidance = PilgrimGuidance(answer="answer")
    rendered = render_guidance_for_channel(guidance, NetworkMode.APP_OFFLINE_QUEUED)
    assert "queued" in rendered.lower() or "offline" in rendered.lower()


def test_triage_sms_short_and_actionable():
    triage = SafetyTriage(
        incident_type=IncidentType.MEDICAL,
        severity=RiskLevel.CRITICAL,
        immediate_action="Stay where you are, raise your hand",
        dispatch_target="nearest Kumbh Rakshak medical post",
        rationale="a very long rationale " * 10,
    )
    rendered = render_triage_for_channel(triage, NetworkMode.SMS)
    assert len(rendered) <= 160
    assert "nearest Kumbh Rakshak medical post" in rendered or "medical post" in rendered
