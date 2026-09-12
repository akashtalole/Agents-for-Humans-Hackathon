"""Wiring tests for Trinetra's direct-API orchestrator functions - agent
calls are mocked so this stays fully offline, no API key required. Same
discipline as the other three projects' orchestrator wiring tests.
"""
from __future__ import annotations

import trinetra.orchestrator as orchestrator_module
from trinetra.models import (
    CommandBrief,
    CrowdSignal,
    IncidentType,
    IndianLanguage,
    InterventionRecommendation,
    InterventionAction,
    NTKMAAdvisory,
    PilgrimGuidance,
    RiskLevel,
    SafetyTriage,
    SimulationScenario,
    SOSReport,
)
from trinetra.orchestrator import (
    TrinetraSession,
    ask_pilgrim,
    get_command_brief,
    monitor_live,
    report_sos,
    run_calibration,
    run_simulation,
)


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


def _fake_command_brief(*args, **kwargs) -> CommandBrief:
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


def test_ask_pilgrim_wiring(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "answer_pilgrim_query", _fake_guidance)
    session = TrinetraSession()
    guidance = ask_pilgrim(session, "where is Ramkund", language=IndianLanguage.ENGLISH)
    assert guidance.answer == "fake answer"
    assert session.last_guidance is guidance


def test_report_sos_wiring(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "triage_sos_report", _fake_triage)
    session = TrinetraSession()
    report = SOSReport(incident_type=IncidentType.LOST_PERSON, reporter_description="test", location="Ramkund")
    triage = report_sos(session, report)
    assert triage.dispatch_target == "fake post"
    assert session.last_triage is triage


def test_get_command_brief_wiring(monkeypatch):
    monkeypatch.setattr(orchestrator_module, "advise_on_crowd_signals", _fake_command_brief)
    session = TrinetraSession()
    signal = CrowdSignal(ghat_id="ramkund", timestamp=__import__("datetime").datetime.utcnow(),
                          estimated_occupancy=1000, inflow_rate_per_min=10, outflow_rate_per_min=10)
    brief = get_command_brief(session, [signal])
    assert brief.overall_status == RiskLevel.ROUTINE
    assert session.last_command_brief is brief


def test_run_simulation_wiring_uses_real_deterministic_engine_and_fake_advisor(monkeypatch):
    """The simulation engine itself (simulate_scenario) is real/deterministic
    - only the LLM advisor layer is mocked, matching the actual
    architecture (see simulator.py's module docstring)."""
    monkeypatch.setattr(orchestrator_module, "advise_on_simulation", _fake_advisory)
    session = TrinetraSession()
    # kushavarta at this low volume, no bottleneck route, low enough demand
    # to stay under its own access-point outflow capacity - see
    # test_trinetra_simulator.py's routine-scenario test for the same math.
    scenario = SimulationScenario(
        name="test", description="test", total_pilgrims=15000, duration_minutes=180,
        peak_inflow_multiplier=1.0, active_ghat_ids=["kushavarta"],
    )
    report, advisory = run_simulation(session, scenario)
    assert report.scenario_name == "test"
    assert report.overall_risk == RiskLevel.ROUTINE
    assert advisory.narrative_summary == "fake narrative"
    assert session.last_simulation is report
    assert session.last_advisory is advisory


def test_run_calibration_uses_real_deterministic_engine_no_mocking_needed():
    """Calibration never touches an LLM at all - this should just work
    directly, no monkeypatching required."""
    session = TrinetraSession()
    results = run_calibration(session)
    assert len(results) >= 2
    assert all(r.correctly_flagged for r in results)
    assert any(not r.expect_critical for r in results), "no negative controls reached the orchestrator"


def test_session_loads_real_bundled_geography_by_default():
    session = TrinetraSession()
    assert "ramkund" in session.ghats
    assert "kushavarta" in session.ghats
    assert len(session.routes) > 0


def test_monitor_live_wiring(monkeypatch):
    """monitor_live delegates to agents.live_monitor.monitor_ghat (mocked
    here, since it's a real tool-calling agent and needs an API key to run
    for real) and records the result on the session - same shape as every
    other module-level orchestrator function."""
    from datetime import datetime

    from trinetra.models import MonitoringBrief, MonitoringFinding

    def _fake_monitor_ghat(ghat_id, question=None):
        assert ghat_id == "ramkund"
        assert question == "check crowd"
        return MonitoringBrief(
            generated_at=datetime.utcnow(),
            overall_status=RiskLevel.ELEVATED,
            findings=[MonitoringFinding(signal_source="thingsboard:ramkund", observation="LOS grade E", severity=RiskLevel.ELEVATED)],
            checked_signals=["get_live_ghat_crowd_signal(ramkund)"],
            data_gaps=[],
            recommended_action="Deploy additional personnel.",
            summary="Elevated crowd density at Ramkund.",
        )

    monkeypatch.setattr(orchestrator_module, "monitor_ghat", _fake_monitor_ghat)
    session = TrinetraSession()
    brief = monitor_live(session, "ramkund", question="check crowd")
    assert brief.overall_status == RiskLevel.ELEVATED
    assert session.last_monitoring_brief is brief
