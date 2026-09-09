"""Offline tests for trinetra/tools/resources.py - pure code, no LLM.

Allocation under scarcity is the part of incident command that must be
reproducible and auditable, so these tests are about invariants rather than
specific numbers: severity ordering, no silent under-allocation, and
determinism.
"""
from __future__ import annotations

import pytest

from trinetra.models import (
    CommandBrief,
    IncidentType,
    InterventionAction,
    InterventionRecommendation,
    ResourceDemand,
    ResourcePool,
    ResponderType,
    RiskLevel,
    SafetyTriage,
    SOSReport,
)
from trinetra.tools.resources import (
    allocate,
    default_resource_pool,
    demands_from_command_brief,
    demands_from_sos,
)


def _demand(demand_id: str, severity: RiskLevel, units: int, urgency: int = 0,
            responder: ResponderType = ResponderType.POLICE) -> ResourceDemand:
    return ResourceDemand(
        demand_id=demand_id, source="test", target_id=demand_id, target_name=demand_id,
        responder_type=responder, units_requested=units, severity=severity,
        urgency_minutes=urgency, rationale="test",
    )


def test_empty_demand_set_is_not_an_error():
    plan = allocate(default_resource_pool(), [])
    assert plan.allocations == []
    assert plan.contended_types == []


def test_critical_is_never_starved_by_a_lower_severity_demand():
    """The load-bearing invariant. A routine demand must never consume units a
    critical one needs, regardless of the order they arrive in."""
    pool = ResourcePool(units={ResponderType.POLICE: 6})
    plan = allocate(pool, [
        _demand("a-routine", RiskLevel.ROUTINE, 6),
        _demand("z-critical", RiskLevel.CRITICAL, 6),
    ])
    by_id = {a.demand_id: a for a in plan.allocations}
    assert by_id["z-critical"].units_granted == 6
    assert by_id["z-critical"].fully_met
    assert by_id["a-routine"].units_granted == 0


def test_tightest_deadline_wins_among_equally_severe_demands():
    pool = ResourcePool(units={ResponderType.POLICE: 3})
    plan = allocate(pool, [
        _demand("later", RiskLevel.CRITICAL, 3, urgency=30),
        _demand("now", RiskLevel.CRITICAL, 3, urgency=0),
    ])
    by_id = {a.demand_id: a for a in plan.allocations}
    assert by_id["now"].units_granted == 3
    assert by_id["later"].units_granted == 0


def test_partial_allocation_always_carries_a_reason():
    """Never under-allocate silently: an operator seeing 4 of 6 units must be
    able to read why the other 2 went elsewhere."""
    pool = ResourcePool(units={ResponderType.ANNOUNCER: 4})
    plan = allocate(pool, [
        _demand("first", RiskLevel.CRITICAL, 4, responder=ResponderType.ANNOUNCER),
        _demand("second", RiskLevel.CRITICAL, 6, responder=ResponderType.ANNOUNCER),
    ])
    short = [a for a in plan.allocations if not a.fully_met]
    assert short
    for a in short:
        assert a.shortfall_reason.strip()
        assert str(a.units_granted) in a.shortfall_reason


def test_unmet_critical_demands_are_lifted_into_their_own_field():
    """These are the calls a human commander has to make personally, so they
    must not be buried in a list of thirty satisfied allocations."""
    pool = ResourcePool(units={ResponderType.RESCUE: 2})
    plan = allocate(pool, [_demand("ramkund", RiskLevel.CRITICAL, 6, responder=ResponderType.RESCUE)])
    assert len(plan.unmet_critical) == 1
    assert "ramkund" in plan.unmet_critical[0]
    assert "human commander must decide" in plan.summary


def test_unmet_elevated_demand_is_not_reported_as_critical():
    pool = ResourcePool(units={ResponderType.POLICE: 1})
    plan = allocate(pool, [_demand("x", RiskLevel.ELEVATED, 3)])
    assert plan.unmet_critical == []
    assert plan.contended_types == [ResponderType.POLICE]


def test_allocation_is_deterministic_across_input_orderings():
    """Same inputs, same result - an allocation an operator cannot reproduce
    is an allocation they cannot audit."""
    pool = ResourcePool(units={ResponderType.POLICE: 7})
    demands = [
        _demand("b", RiskLevel.CRITICAL, 3),
        _demand("a", RiskLevel.CRITICAL, 3),
        _demand("c", RiskLevel.ELEVATED, 3),
    ]
    first = allocate(pool, demands)
    second = allocate(pool, list(reversed(demands)))
    assert [(a.demand_id, a.units_granted) for a in first.allocations] == \
           [(a.demand_id, a.units_granted) for a in second.allocations]


def test_remaining_units_never_go_negative():
    pool = ResourcePool(units={ResponderType.MEDICAL: 2})
    plan = allocate(pool, [_demand(f"d{i}", RiskLevel.CRITICAL, 6, responder=ResponderType.MEDICAL)
                           for i in range(5)])
    assert all(v >= 0 for v in plan.remaining.values())
    granted = sum(a.units_granted for a in plan.allocations)
    assert granted == 2


def test_intervention_action_none_consumes_nobody():
    brief = CommandBrief(
        overall_status=RiskLevel.ROUTINE,
        recommendations=[InterventionRecommendation(
            target_id="ramkund", target_name="Ramkund", current_risk=RiskLevel.ROUTINE,
            action=InterventionAction.NONE, rationale="nothing needed", urgency_minutes=120,
        )],
        summary="quiet",
    )
    assert demands_from_command_brief(brief) == []


def test_public_advisory_consumes_announcers_not_police():
    brief = CommandBrief(
        overall_status=RiskLevel.ELEVATED,
        recommendations=[InterventionRecommendation(
            target_id="ramkund", target_name="Ramkund", current_risk=RiskLevel.ELEVATED,
            action=InterventionAction.PUBLIC_ADVISORY, rationale="tell people", urgency_minutes=10,
        )],
        summary="x",
    )
    demands = demands_from_command_brief(brief)
    assert [d.responder_type for d in demands] == [ResponderType.ANNOUNCER]


@pytest.mark.parametrize("incident", [IncidentType.MEDICAL, IncidentType.CROWD_PRESSURE])
def test_sos_medical_incident_requests_medical_units(incident: IncidentType):
    """Regression test for a real bug: this mapping originally compared
    triage.incident_type.value against the string literals "medical_emergency"
    and "crowd_crush_risk", neither of which is an IncidentType value. The
    medical branch was dead code, so a collapsed pilgrim raised a police
    demand and no ambulance was ever reserved."""
    report = SOSReport(incident_type=incident, reporter_description="collapsed", location="Ramkund")
    triage = SafetyTriage(incident_type=incident, severity=RiskLevel.CRITICAL,
                          immediate_action="a", dispatch_target="medical control room", rationale="r")
    types = {d.responder_type for d in demands_from_sos([(report, triage)])}
    assert ResponderType.MEDICAL in types
    assert ResponderType.AMBULANCE in types
    assert ResponderType.POLICE not in types


def test_sos_non_medical_incident_requests_police():
    report = SOSReport(incident_type=IncidentType.LOST_PERSON, reporter_description="lost child",
                       location="Ramkund")
    triage = SafetyTriage(incident_type=IncidentType.LOST_PERSON, severity=RiskLevel.ELEVATED,
                          immediate_action="a", dispatch_target="Kumbh Rakshak post", rationale="r")
    types = {d.responder_type for d in demands_from_sos([(report, triage)])}
    assert types == {ResponderType.POLICE}


def test_only_one_ambulance_is_requested_per_incident():
    """An incident is one location. Scaling ambulances by severity the way
    personnel are scaled would request six for a single collapsed pilgrim."""
    report = SOSReport(incident_type=IncidentType.MEDICAL, reporter_description="collapsed",
                       location="Ramkund")
    triage = SafetyTriage(incident_type=IncidentType.MEDICAL, severity=RiskLevel.CRITICAL,
                          immediate_action="a", dispatch_target="medical", rationale="r")
    ambulances = [d for d in demands_from_sos([(report, triage)])
                  if d.responder_type == ResponderType.AMBULANCE]
    assert ambulances[0].units_requested == 1


def test_children_or_elderly_escalate_the_demand_severity():
    report = SOSReport(incident_type=IncidentType.LOST_PERSON, reporter_description="lost child",
                       location="Ramkund", involves_children_or_elderly=True)
    triage = SafetyTriage(incident_type=IncidentType.LOST_PERSON, severity=RiskLevel.ELEVATED,
                          immediate_action="a", dispatch_target="post", rationale="r")
    baseline = SOSReport(incident_type=IncidentType.LOST_PERSON, reporter_description="lost adult",
                         location="Ramkund", involves_children_or_elderly=False)
    escalated = demands_from_sos([(report, triage)])[0]
    plain = demands_from_sos([(baseline, triage)])[0]
    assert escalated.units_requested > plain.units_requested
