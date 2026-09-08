"""Offline tests for trinetra/api.py using FastAPI's TestClient.

Same discipline as the other three projects' test_*_api.py: agent-calling
functions are monkeypatched on the trinetra.api module (where they were
imported), so these run with no API key and no network. The simulation
engine itself (simulate_scenario) is real and deterministic - only the LLM
advisor layer is mocked, matching the actual architecture.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import trinetra.api as api_module
from trinetra.models import (
    CommandBrief,
    IncidentType,
    InterventionAction,
    InterventionRecommendation,
    NTKMAAdvisory,
    PilgrimGuidance,
    RiskLevel,
    SafetyTriage,
)


@pytest.fixture(autouse=True)
def _clean_job_store():
    api_module._jobs.clear()
    yield
    api_module._jobs.clear()


@pytest.fixture()
def client():
    return TestClient(api_module.app)


def _fake_guidance(*args, **kwargs) -> PilgrimGuidance:
    return PilgrimGuidance(answer="fake answer", escalate_to_sos=False)


def _fake_triage(*args, **kwargs) -> SafetyTriage:
    return SafetyTriage(
        incident_type=IncidentType.LOST_PERSON,
        severity=RiskLevel.ELEVATED,
        immediate_action="fake action",
        dispatch_target="fake post",
        rationale="fake rationale",
    )


def _fake_brief(*args, **kwargs) -> CommandBrief:
    return CommandBrief(
        overall_status=RiskLevel.ROUTINE,
        recommendations=[
            InterventionRecommendation(
                target_id="ramkund", target_name="Ramkund", current_risk=RiskLevel.ROUTINE,
                action=InterventionAction.NONE, rationale="fake", urgency_minutes=120,
            )
        ],
        summary="fake summary",
    )


def _fake_advisory(*args, **kwargs) -> NTKMAAdvisory:
    return NTKMAAdvisory(top_concerns=["fake concern"], recommended_capacity_changes=[], narrative_summary="fake narrative")


def test_status_endpoint_shape(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "status_text" in body
    assert "ready" in body


def test_sites_endpoint_returns_real_bundled_geography(client):
    resp = client.get("/api/sites")
    assert resp.status_code == 200
    body = resp.json()
    ghat_ids = {g["id"] for g in body["ghats"]}
    assert "ramkund" in ghat_ids
    assert "kushavarta" in ghat_ids
    assert len(body["routes"]) > 0


def test_calibration_endpoint_both_cases_pass_no_mocking_needed(client):
    resp = client.get("/api/calibration")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert all(r["correctly_flagged"] for r in results)


def test_pilgrim_ask_wiring(client, monkeypatch):
    monkeypatch.setattr(api_module, "answer_pilgrim_query", _fake_guidance)
    resp = client.post("/api/pilgrim/ask", json={"text": "where is Ramkund", "language": "english"})
    assert resp.status_code == 200
    assert resp.json()["answer"] == "fake answer"


def test_pilgrim_ask_requires_text(client):
    resp = client.post("/api/pilgrim/ask", json={"text": "  "})
    assert resp.status_code == 400


def test_sos_wiring(client, monkeypatch):
    monkeypatch.setattr(api_module, "triage_sos_report", _fake_triage)
    resp = client.post(
        "/api/sos",
        json={"description": "lost my father", "location": "Ramkund", "incident_type": "lost_person"},
    )
    assert resp.status_code == 200
    assert resp.json()["dispatch_target"] == "fake post"


def test_sos_requires_description_and_location(client):
    resp = client.post("/api/sos", json={"description": "", "location": "Ramkund"})
    assert resp.status_code == 400


def test_admin_brief_wiring(client, monkeypatch):
    monkeypatch.setattr(api_module, "advise_on_crowd_signals", _fake_brief)
    resp = client.post(
        "/api/admin/brief",
        json={"signals": [{"ghat_id": "ramkund", "estimated_occupancy": 5000, "inflow_rate_per_min": 100, "outflow_rate_per_min": 90}]},
    )
    assert resp.status_code == 200
    assert resp.json()["overall_status"] == "routine"


def test_admin_brief_unknown_ghat_id_rejected(client):
    resp = client.post(
        "/api/admin/brief",
        json={"signals": [{"ghat_id": "not_a_real_ghat", "estimated_occupancy": 100, "inflow_rate_per_min": 1, "outflow_rate_per_min": 1}]},
    )
    assert resp.status_code == 400


def test_admin_brief_requires_at_least_one_signal(client):
    resp = client.post("/api/admin/brief", json={"signals": []})
    assert resp.status_code == 400


def test_simulation_lifecycle_real_engine_fake_advisor(client, monkeypatch):
    monkeypatch.setattr(api_module, "advise_on_simulation", _fake_advisory)

    # Low enough demand at kushavarta (no bottleneck route, access-point
    # outflow cap ~105/min) to stay ROUTINE - see test_trinetra_simulator.py's
    # routine-scenario test for the same math.
    create_resp = client.post(
        "/api/simulations",
        json={
            "name": "test scenario",
            "total_pilgrims": 3000,
            "duration_minutes": 30,
            "peak_inflow_multiplier": 1.0,
            "active_ghat_ids": ["kushavarta"],
        },
    )
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    # Drain the SSE stream to completion.
    with client.stream("GET", f"/api/simulations/{job_id}/events") as stream:
        events = []
        for line in stream.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
            if events and events[-1].get("type") == "done":
                break

    tick_events = [e for e in events if e["type"] == "tick"]
    assert len(tick_events) == 30
    assert any(e["type"] == "report" for e in events)
    assert any(e["type"] == "advisory" for e in events)

    status_resp = client.get(f"/api/simulations/{job_id}")
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["status"] == "completed"
    assert body["report"]["overall_risk"] == "routine"
    assert body["advisory"]["narrative_summary"] == "fake narrative"


def test_simulation_invalid_scenario_rejected(client):
    resp = client.post("/api/simulations", json={"name": "bad", "total_pilgrims": 1000})
    assert resp.status_code == 400


def test_get_unknown_simulation_job_returns_404(client):
    resp = client.get("/api/simulations/does-not-exist")
    assert resp.status_code == 404
