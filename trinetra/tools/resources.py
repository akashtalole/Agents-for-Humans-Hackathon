"""Finite-responder allocation under contention - pure code, no LLM.

Why this is code and not a model's judgment: allocation under scarcity is
arithmetic with a policy, and both halves must be auditable after the fact.
An NTKMA commander who is told "Ramkund got 6 of the 10 units it asked for"
needs to be able to see exactly why the other 4 went elsewhere, and get the
same answer twice from the same inputs. A model asked to divide 40 police
units across nine competing demands would produce something plausible and
unreproducible.

The one thing this module refuses to do is under-allocate quietly. Every
demand that is partially met or not met at all carries an explicit reason,
and unmet CRITICAL demands are lifted into their own field, because those
are precisely the calls a human commander has to make personally.

Priority policy, stated so it can be argued with:
  1. Severity descending  - critical before elevated before routine.
  2. Urgency ascending    - among equally severe demands, the tightest
                            response window first.
  3. Units descending     - among demands equal on both, the larger request
                            first. At equal severity and urgency, size is the
                            best available proxy for how many people are
                            exposed; the alternative (smallest-first, which
                            maximizes the *count* of satisfied demands) would
                            let several small incidents starve one big one.
  4. demand_id ascending  - determinism, so the same inputs always allocate
                            identically.
"""
from __future__ import annotations

from trinetra.models import (
    AllocationPlan,
    CommandBrief,
    CompoundRiskAssessment,
    HydrologyAdvisory,
    IncidentType,
    InterventionAction,
    ResourceAllocation,
    ResourceDemand,
    ResourcePool,
    ResponderType,
    RiskLevel,
    RumorAssessment,
    SafetyTriage,
    SOSReport,
)

_RISK_ORDER = {RiskLevel.ROUTINE: 0, RiskLevel.ELEVATED: 1, RiskLevel.CRITICAL: 2}

# Incident types that consume medical rather than crowd-control units.
_MEDICAL_INCIDENTS = {IncidentType.MEDICAL, IncidentType.CROWD_PRESSURE}

# Illustrative per-shift strength. See ResourcePool's docstring.
_DEFAULT_POOL = {
    ResponderType.POLICE: 40,
    ResponderType.MEDICAL: 12,
    ResponderType.AMBULANCE: 8,
    ResponderType.RESCUE: 6,
    ResponderType.ANNOUNCER: 10,
}

# How many units one recommendation asks for, by severity. Deliberately small
# integers: this is a planning-scale model, not a staffing formula.
_UNITS_BY_SEVERITY = {RiskLevel.ROUTINE: 1, RiskLevel.ELEVATED: 3, RiskLevel.CRITICAL: 6}

# Which responder type each intervention actually consumes.
_ACTION_RESPONDER = {
    InterventionAction.DEPLOY_PERSONNEL: ResponderType.POLICE,
    InterventionAction.GATE_CLOSURE: ResponderType.POLICE,
    InterventionAction.CAPACITY_THROTTLE: ResponderType.POLICE,
    InterventionAction.ROUTE_DIVERSION: ResponderType.POLICE,
    InterventionAction.PUBLIC_ADVISORY: ResponderType.ANNOUNCER,
}


def default_resource_pool() -> ResourcePool:
    return ResourcePool(units=dict(_DEFAULT_POOL))


def demands_from_command_brief(brief: CommandBrief) -> list[ResourceDemand]:
    demands: list[ResourceDemand] = []
    for i, rec in enumerate(brief.recommendations):
        responder = _ACTION_RESPONDER.get(rec.action)
        if responder is None:  # InterventionAction.NONE consumes nobody.
            continue
        demands.append(
            ResourceDemand(
                demand_id=f"crowd-{i:02d}",
                source="command_brief",
                target_id=rec.target_id,
                target_name=rec.target_name,
                responder_type=responder,
                units_requested=_UNITS_BY_SEVERITY[rec.current_risk],
                severity=rec.current_risk,
                urgency_minutes=rec.urgency_minutes,
                rationale=rec.rationale,
            )
        )
    return demands


def demands_from_flood(
    assessment: CompoundRiskAssessment, advisory: HydrologyAdvisory | None = None
) -> list[ResourceDemand]:
    """A ghat that cannot be cleared in time needs three different things at
    once: rescue units for the water, police to keep the egress orderly, and
    an announcer, because an unannounced evacuation of a packed ghat is
    itself a crush risk."""
    demands: list[ResourceDemand] = []
    for i, feasibility in enumerate(assessment.ghat_feasibility):
        if feasibility.risk == RiskLevel.ROUTINE:
            continue
        cannot_clear = feasibility.margin_minutes < 0
        needed = [ResponderType.POLICE, ResponderType.ANNOUNCER]
        if cannot_clear:
            needed.append(ResponderType.RESCUE)
        for responder in needed:
            demands.append(
                ResourceDemand(
                    demand_id=f"flood-{i:02d}-{responder.value}",
                    source="flood_advisory",
                    target_id=feasibility.ghat_id,
                    target_name=feasibility.ghat_name,
                    responder_type=responder,
                    units_requested=_UNITS_BY_SEVERITY[feasibility.risk],
                    severity=feasibility.risk,
                    # The water sets the deadline, not an operator's preference.
                    urgency_minutes=0 if cannot_clear else max(0, int(feasibility.margin_minutes)),
                    rationale=(
                        f"{feasibility.ghat_name} holds {feasibility.occupancy:,} people and "
                        f"{'CANNOT be cleared before the water arrives' if cannot_clear else 'has a thin clearance margin'} "
                        f"({feasibility.margin_minutes:.0f} min margin)."
                    ),
                )
            )
    return demands


def demands_from_sos(triages: list[tuple[SOSReport, SafetyTriage]]) -> list[ResourceDemand]:
    """Medical incidents consume medical and ambulance units; everything else
    consumes police. A medical emergency involving children or the elderly is
    escalated one step, matching how the triage agent is instructed to treat
    them."""
    demands: list[ResourceDemand] = []
    for i, (report, triage) in enumerate(triages):
        severity = triage.severity
        if report.involves_children_or_elderly and severity != RiskLevel.CRITICAL:
            severity = RiskLevel.CRITICAL if severity == RiskLevel.ELEVATED else RiskLevel.ELEVATED

        # Compared as enum members, never as string literals - an earlier
        # version matched on "medical_emergency"/"crowd_crush_risk", which
        # are not IncidentType values, so the medical branch was dead code
        # and a collapsed pilgrim silently raised a police demand instead of
        # an ambulance. See test_sos_medical_incident_requests_medical_units.
        types = (
            [ResponderType.MEDICAL, ResponderType.AMBULANCE]
            if triage.incident_type in _MEDICAL_INCIDENTS
            else [ResponderType.POLICE]
        )
        for responder in types:
            demands.append(
                ResourceDemand(
                    demand_id=f"sos-{i:02d}-{responder.value}",
                    source="sos_triage",
                    target_id=report.location,
                    target_name=report.location,
                    responder_type=responder,
                    # An incident is one location: 1 ambulance, not six.
                    units_requested=1 if responder == ResponderType.AMBULANCE else _UNITS_BY_SEVERITY[severity],
                    severity=severity,
                    urgency_minutes=0,
                    rationale=f"{triage.incident_type.value}: {triage.dispatch_target}",
                )
            )
    return demands


def demands_from_rumor(assessment: RumorAssessment, location: str) -> list[ResourceDemand]:
    """A rumor is countered with announcers, not batons."""
    return [
        ResourceDemand(
            demand_id="rumor-00-announcer",
            source="rumor_desk",
            target_id=location,
            target_name=location,
            responder_type=ResponderType.ANNOUNCER,
            units_requested=_UNITS_BY_SEVERITY[assessment.crush_risk],
            severity=assessment.crush_risk,
            urgency_minutes=0,
            rationale=f"Counter-messaging for: {assessment.category}",
        )
    ]


def _sort_key(demand: ResourceDemand) -> tuple:
    return (
        -_RISK_ORDER[demand.severity],
        demand.urgency_minutes,
        -demand.units_requested,
        demand.demand_id,
    )


def allocate(pool: ResourcePool, demands: list[ResourceDemand]) -> AllocationPlan:
    """Greedy allocation in documented priority order. Partial fills are
    allowed - sending three of five requested units is a real operational
    outcome - but never silent."""
    remaining = dict(pool.units)
    requested_by_type: dict[ResponderType, int] = {}
    allocations: list[ResourceAllocation] = []
    unmet_critical: list[str] = []

    for demand in sorted(demands, key=_sort_key):
        requested_by_type[demand.responder_type] = (
            requested_by_type.get(demand.responder_type, 0) + demand.units_requested
        )
        available = remaining.get(demand.responder_type, 0)
        granted = min(demand.units_requested, available)
        remaining[demand.responder_type] = available - granted

        fully_met = granted == demand.units_requested
        reason = ""
        if not fully_met:
            reason = (
                f"Only {granted} of {demand.units_requested} {demand.responder_type.value} units available - "
                f"the rest were already committed to higher-priority demands."
            )
            if demand.severity == RiskLevel.CRITICAL:
                unmet_critical.append(
                    f"{demand.target_name} ({demand.source}): asked for {demand.units_requested} "
                    f"{demand.responder_type.value}, got {granted}. {demand.rationale}"
                )

        allocations.append(
            ResourceAllocation(
                demand_id=demand.demand_id,
                source=demand.source,
                target_name=demand.target_name,
                responder_type=demand.responder_type,
                units_requested=demand.units_requested,
                units_granted=granted,
                severity=demand.severity,
                fully_met=fully_met,
                shortfall_reason=reason,
            )
        )

    contended = sorted(
        (t for t, total in requested_by_type.items() if total > pool.units.get(t, 0)),
        key=lambda t: t.value,
    )

    if not allocations:
        summary = "No responder demands were raised by any desk."
    elif not contended:
        summary = f"All {len(allocations)} demands met in full; no responder type is over-subscribed."
    else:
        names = ", ".join(t.value for t in contended)
        summary = (
            f"{sum(1 for a in allocations if not a.fully_met)} of {len(allocations)} demands could not be "
            f"met in full. Over-subscribed: {names}."
        )
        if unmet_critical:
            summary += f" {len(unmet_critical)} CRITICAL demand(s) are short - a human commander must decide."

    return AllocationPlan(
        pool=dict(pool.units),
        allocations=allocations,
        remaining=remaining,
        contended_types=contended,
        unmet_critical=unmet_critical,
        summary=summary,
    )
