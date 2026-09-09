"""Detects directives that are individually correct but cannot both be
executed - pure code, no LLM.

This exists because Trinetra's desks are deliberately independent. The flood
advisor reasons about water and does not know what the crowd desk is seeing;
the crowd desk reasons about density and does not know a dam has opened. That
independence is a feature - it is why the flood advisor's numbers cannot be
talked out of by a crowd argument - but it means nobody was checking whether
the union of their advice is executable.

The conflict that matters most is the 2003 one. Clearing a flooding riverfront
is correct. Pushing that crowd up a 1.8-metre approach lane, or into a
neighbouring ghat that is already at capacity, is how thirty-nine people died
at Kalaram Mandir Marg during an evacuation. Neither desk can see it alone,
because it is a property of the pair.

Every rule here is computed from the bundled route geometry and the desks'
own structured outputs. A conflict is raised as something for a human
commander to resolve, never auto-resolved.
"""
from __future__ import annotations

from trinetra.models import (
    AllocationPlan,
    CommandBrief,
    CompoundRiskAssessment,
    ConflictKind,
    ConflictScanResult,
    CrowdSignal,
    DirectiveConflict,
    Ghat,
    InterventionAction,
    RiskLevel,
    Route,
)

# Kalaram Mandir Marg is 1.8m. Anything at or below this is treated as a lane
# that must never absorb an evacuation surge without explicit crowd control.
_NARROW_LANE_M = 2.0

# Matches the simulator's elevated threshold, so "congested" means the same
# thing in the digital twin and here.
_CONGESTION_THRESHOLD = 0.85


def _neighbours(ghat_id: str, routes: list[Route]) -> list[tuple[str, Route]]:
    """Every ghat reachable from this one, paired with the route that gets
    there. A route listing a single site (a standalone approach) has no
    neighbour and is skipped."""
    out: list[tuple[str, Route]] = []
    for route in routes:
        if ghat_id in route.connects:
            for other in route.connects:
                if other != ghat_id:
                    out.append((other, route))
    return out


def _evacuating_ghats(flood: CompoundRiskAssessment) -> list[tuple[str, str, float]]:
    """(ghat_id, ghat_name, margin) for every ghat the flood desk says needs
    to be cleared under time pressure."""
    return [
        (f.ghat_id, f.ghat_name, f.margin_minutes)
        for f in flood.ghat_feasibility
        if f.risk != RiskLevel.ROUTINE
    ]


def scan_for_conflicts(
    ghats: dict[str, Ghat],
    routes: list[Route],
    flood: CompoundRiskAssessment | None = None,
    brief: CommandBrief | None = None,
    signals: list[CrowdSignal] | None = None,
    allocation: AllocationPlan | None = None,
) -> ConflictScanResult:
    conflicts: list[DirectiveConflict] = []

    occupancy = {s.ghat_id: s.estimated_occupancy for s in (signals or [])}
    closures = {
        rec.target_id: rec
        for rec in (brief.recommendations if brief else [])
        if rec.action in (InterventionAction.GATE_CLOSURE, InterventionAction.CAPACITY_THROTTLE)
    }

    if flood is not None:
        for ghat_id, ghat_name, margin in _evacuating_ghats(flood):
            cannot_clear = margin < 0

            for neighbour_id, route in _neighbours(ghat_id, routes):
                neighbour = ghats.get(neighbour_id)
                if neighbour is None:
                    continue

                # Rule 1: the evacuation route itself is a documented crush lane.
                if route.width_m <= _NARROW_LANE_M:
                    conflicts.append(
                        DirectiveConflict(
                            kind=ConflictKind.NARROW_LANE_EVACUATION,
                            severity=RiskLevel.CRITICAL if cannot_clear else RiskLevel.ELEVATED,
                            target_name=ghat_name,
                            sources=["flood_advisory", "site_geography"],
                            detail=(
                                f"Clearing {ghat_name} routes crowds along {route.name}, which is "
                                f"{route.width_m}m wide - at or below the {_NARROW_LANE_M}m threshold. "
                                f"{neighbour.historical_note or 'This is a documented crush geometry.'} "
                                f"An evacuation that funnels into this lane can kill more people than the "
                                f"water it is escaping."
                            ),
                        )
                    )

                # Rule 2: the place we are sending them is already full.
                current = occupancy.get(neighbour_id)
                if current is not None and neighbour.safe_capacity > 0:
                    pct = current / neighbour.safe_capacity
                    if pct >= _CONGESTION_THRESHOLD:
                        conflicts.append(
                            DirectiveConflict(
                                kind=ConflictKind.EVACUATION_INTO_CONGESTION,
                                severity=RiskLevel.CRITICAL if cannot_clear else RiskLevel.ELEVATED,
                                target_name=neighbour.name,
                                sources=["flood_advisory", "command_brief"],
                                detail=(
                                    f"The flood desk needs {ghat_name} cleared, but the adjacent "
                                    f"{neighbour.name} is already at {pct * 100:.0f}% of its safe capacity "
                                    f"({current:,} of {neighbour.safe_capacity:,}). It cannot absorb an "
                                    f"evacuation surge without becoming the next critical site."
                                ),
                            )
                        )

                # Rule 3: the crowd desk is closing the door the flood desk needs open.
                if neighbour_id in closures:
                    rec = closures[neighbour_id]
                    conflicts.append(
                        DirectiveConflict(
                            kind=ConflictKind.CLOSURE_TRAPS_EVACUATION,
                            severity=RiskLevel.CRITICAL if cannot_clear else RiskLevel.ELEVATED,
                            target_name=neighbour.name,
                            sources=["flood_advisory", "command_brief"],
                            detail=(
                                f"The crowd desk recommends {rec.action.value.replace('_', ' ')} at "
                                f"{neighbour.name}, but it is an egress neighbour of {ghat_name}, which the "
                                f"flood desk needs evacuated"
                                + (f" with a {margin:.0f}-minute deficit" if cannot_clear else "")
                                + ". Executing both removes egress capacity from an evacuation already "
                                "short of time."
                            ),
                        )
                    )

    # Rule 4: contention the allocator could not resolve is a command decision.
    if allocation is not None:
        for line in allocation.unmet_critical:
            conflicts.append(
                DirectiveConflict(
                    kind=ConflictKind.RESOURCE_CONTENTION,
                    severity=RiskLevel.CRITICAL,
                    target_name=line.split(" (")[0],
                    sources=["resource_allocator"],
                    detail=(
                        f"A critical demand could not be met in full: {line} No reallocation inside the "
                        "current pool fixes this - it needs either more units or an accepted risk."
                    ),
                )
            )

    # Identical conflicts can be raised twice when two routes connect the same
    # pair of ghats; collapse them so an operator sees each problem once.
    seen: set[tuple] = set()
    deduped: list[DirectiveConflict] = []
    for c in conflicts:
        key = (c.kind, c.target_name, c.detail)
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    critical = sum(1 for c in deduped if c.severity == RiskLevel.CRITICAL)
    if not deduped:
        summary = "No contradictory directives detected across the active desks."
    else:
        summary = (
            f"{len(deduped)} conflicting directive(s) detected"
            + (f", {critical} critical" if critical else "")
            + ". Each is a call a human commander must make - none is auto-resolved."
        )

    return ConflictScanResult(conflicts=deduped, summary=summary)
