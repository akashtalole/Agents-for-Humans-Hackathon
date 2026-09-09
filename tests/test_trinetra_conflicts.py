"""Offline tests for trinetra/tools/conflicts.py - pure code, no LLM.

The conflicts this module finds are properties of a PAIR of desks, which is
exactly why no single desk can be tested into finding them. These tests use
the real bundled geography, because the 1.8m Kalaram Mandir Marg lane is the
whole reason the module exists.
"""
from __future__ import annotations

from datetime import datetime

from trinetra.models import (
    AllocationPlan,
    CommandBrief,
    ConflictKind,
    CrowdSignal,
    DamRelease,
    InterventionAction,
    InterventionRecommendation,
    MobilityProfile,
    ResponderType,
    RiskLevel,
)
from trinetra.tools.conflicts import scan_for_conflicts
from trinetra.tools.geography import load_sites
from trinetra.tools.hydrology import assess_compound_risk

_ELDERLY_MIX = {MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: 0.4, MobilityProfile.STANDARD: 0.6}


def _critical_ramkund_flood():
    ghats, routes = load_sites()
    flood = assess_compound_risk(
        DamRelease(discharge_cusecs=22000), ghats, {"ramkund": 8000}, mobility_mix=_ELDERLY_MIX
    )
    return ghats, routes, flood


def _signal(ghat_id: str, occupancy: int) -> CrowdSignal:
    return CrowdSignal(ghat_id=ghat_id, timestamp=datetime.utcnow(), estimated_occupancy=occupancy,
                       inflow_rate_per_min=0, outflow_rate_per_min=0)


def test_quiet_board_reports_no_conflicts():
    ghats, routes = load_sites()
    result = scan_for_conflicts(ghats, routes)
    assert result.conflicts == []
    assert "No contradictory directives" in result.summary


def test_ramkund_evacuation_flags_the_1_8m_kalaram_lane():
    """The 2003 failure mode, and the single most important thing this module
    detects: clearing Ramkund routes people into the lane where 39 died."""
    ghats, routes, flood = _critical_ramkund_flood()
    result = scan_for_conflicts(ghats, routes, flood=flood)
    narrow = [c for c in result.conflicts if c.kind == ConflictKind.NARROW_LANE_EVACUATION]
    assert narrow
    assert narrow[0].severity == RiskLevel.CRITICAL
    assert "1.8m" in narrow[0].detail
    # The citation must travel with the warning - an operator overriding this
    # needs to see what it is grounded in.
    assert "2003" in narrow[0].detail


def test_evacuating_into_a_full_neighbour_is_flagged():
    ghats, routes, flood = _critical_ramkund_flood()
    result = scan_for_conflicts(
        ghats, routes, flood=flood, signals=[_signal("panchavati_godavari", 4800)]
    )
    congestion = [c for c in result.conflicts if c.kind == ConflictKind.EVACUATION_INTO_CONGESTION]
    assert congestion
    assert "96%" in congestion[0].detail


def test_evacuating_into_an_empty_neighbour_is_not_flagged_as_congestion():
    ghats, routes, flood = _critical_ramkund_flood()
    result = scan_for_conflicts(
        ghats, routes, flood=flood, signals=[_signal("panchavati_godavari", 200)]
    )
    assert not [c for c in result.conflicts if c.kind == ConflictKind.EVACUATION_INTO_CONGESTION]


def test_closing_a_gate_the_evacuation_needs_is_flagged():
    """Both desks are individually right. Executing both traps the evacuation."""
    ghats, routes, flood = _critical_ramkund_flood()
    brief = CommandBrief(
        overall_status=RiskLevel.ELEVATED,
        recommendations=[InterventionRecommendation(
            target_id="panchavati_godavari", target_name="Panchavati Godavari Ghat corridor",
            current_risk=RiskLevel.ELEVATED, action=InterventionAction.GATE_CLOSURE,
            rationale="density rising", urgency_minutes=0,
        )],
        summary="x",
    )
    result = scan_for_conflicts(ghats, routes, flood=flood, brief=brief)
    trapped = [c for c in result.conflicts if c.kind == ConflictKind.CLOSURE_TRAPS_EVACUATION]
    assert trapped
    assert trapped[0].severity == RiskLevel.CRITICAL


def test_a_gate_closure_far_from_any_evacuation_is_not_flagged():
    """Kushavarta is at Trimbakeshwar and is not an egress neighbour of any
    flood-exposed ghat, so closing it traps nothing."""
    ghats, routes, flood = _critical_ramkund_flood()
    brief = CommandBrief(
        overall_status=RiskLevel.ELEVATED,
        recommendations=[InterventionRecommendation(
            target_id="kushavarta", target_name="Kushavarta Ghat", current_risk=RiskLevel.ELEVATED,
            action=InterventionAction.GATE_CLOSURE, rationale="crowded", urgency_minutes=0,
        )],
        summary="x",
    )
    result = scan_for_conflicts(ghats, routes, flood=flood, brief=brief)
    assert not [c for c in result.conflicts if c.kind == ConflictKind.CLOSURE_TRAPS_EVACUATION]


def test_unmet_critical_allocation_becomes_a_conflict():
    ghats, routes = load_sites()
    allocation = AllocationPlan(
        pool={ResponderType.RESCUE: 2}, allocations=[], remaining={ResponderType.RESCUE: 0},
        contended_types=[ResponderType.RESCUE],
        unmet_critical=["Ramkund (flood_advisory): asked for 6 rescue, got 2."],
        summary="short",
    )
    result = scan_for_conflicts(ghats, routes, allocation=allocation)
    contention = [c for c in result.conflicts if c.kind == ConflictKind.RESOURCE_CONTENTION]
    assert len(contention) == 1
    assert contention[0].severity == RiskLevel.CRITICAL
    assert contention[0].target_name == "Ramkund"


def test_a_routine_river_raises_no_evacuation_conflicts():
    ghats, routes = load_sites()
    flood = assess_compound_risk(DamRelease(discharge_cusecs=1000), ghats, {"ramkund": 2000})
    result = scan_for_conflicts(ghats, routes, flood=flood, signals=[_signal("panchavati_godavari", 4900)])
    assert result.conflicts == []


def test_identical_conflicts_are_reported_once():
    """Two routes can connect the same pair of ghats; an operator should see
    each problem once, not once per route."""
    ghats, routes, flood = _critical_ramkund_flood()
    doubled = routes + [r.model_copy(update={"id": r.id + "_dup"}) for r in routes]
    once = scan_for_conflicts(ghats, routes, flood=flood)
    twice = scan_for_conflicts(ghats, doubled, flood=flood)
    assert len(once.conflicts) == len(twice.conflicts)


def test_has_critical_reflects_the_worst_conflict():
    ghats, routes, flood = _critical_ramkund_flood()
    assert scan_for_conflicts(ghats, routes, flood=flood).has_critical
    assert not scan_for_conflicts(ghats, routes).has_critical


def test_summary_states_that_nothing_is_auto_resolved():
    """These are command decisions. The summary must never read as though the
    tool has already handled them."""
    ghats, routes, flood = _critical_ramkund_flood()
    result = scan_for_conflicts(ghats, routes, flood=flood)
    assert "human commander" in result.summary
    assert "auto-resolved" in result.summary
