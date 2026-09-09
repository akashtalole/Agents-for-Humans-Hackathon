"""Bhavishya Netra's crowd-dynamics engine - pure deterministic code, no LLM.

Design choice, explained: simulating thousands of individual pilgrims each
via a separate LLM call would be both unaffordable and pointless - crowd
occupancy over time is exactly the kind of thing that should be computed,
not judged by a model. So the actual risk numbers below come entirely from
this module. The LLM layer (agents/foresight_advisor.py) only *interprets*
a finished SimulationReport into recommendations and narrative - it never
recomputes or restates the numbers, so a judge (or NTKMA) can trust the
peak-occupancy figures are the same every time the same scenario runs,
independent of any model's phrasing that day. See CalibrationResult in
models.py and tools/calibration.py for how this gets validated against two
real historical Kumbh stampedes.
"""
from __future__ import annotations

from typing import Callable

from trinetra.models import GhatSimResult, Ghat, Route, RiskLevel, SimulationReport, SimulationScenario

# One snapshot per simulated minute: {ghat_id: {"occupancy": float, "pct_of_capacity": float}}.
# Used by trinetra/api.py to stream a live-updating digital twin over SSE -
# see that module for how this becomes an animated view rather than a
# wait-for-the-final-report one.
TickSnapshot = dict[str, dict[str, float]]
OnTickCallback = Callable[[int, TickSnapshot], None]

# A single access point can safely pass roughly this many people per minute
# before queuing turns into pressure - a conservative planning proxy, not a
# measured figure. Documented here rather than left as a magic number.
_THROUGHPUT_PER_ACCESS_POINT = 35

# Occupancy as a fraction of a ghat's safe_capacity above which risk is
# elevated, then critical. Matches the same "more cautious wins" ordering
# used throughout this repo (see glacierwatch/agents/risk_auditor.py).
_ELEVATED_THRESHOLD = 0.85
_CRITICAL_THRESHOLD = 1.10

# An approach lane this narrow or narrower is treated as a structural
# crush-risk factor in its own right, independent of occupancy math - this
# is what actually happened at Kalaram Mandir Marg in 2003 (see
# trinetra/data/calibration_cases.json).
_NARROW_LANE_THRESHOLD_M = 2.5

# Once occupancy reaches this multiple of a ghat's safe_capacity, this model
# assumes further net inflow is blocked - either by authorities closing
# entry or by the crowd's own physical density preventing more people from
# arriving. Without this cap a sustained-demand scenario produces an
# unbounded queue and nonsensical occupancy percentages (thousands of
# percent) rather than a plateau. This is a deliberate, documented
# simplification, not a measured physical limit - a real deployment should
# replace it with NTKMA's actual gate-closure/admission-control protocol.
# See TRINETRA.md's honest-limitations section.
_ADMISSION_BLOCK_MULTIPLE = 1.5


def _outflow_capacity(ghat: Ghat, routes: list[Route]) -> int:
    """The binding constraint on how fast a ghat can clear: whichever is
    lower, its own access-point throughput or the narrowest connected
    route's stated capacity."""
    access_point_capacity = ghat.access_points * _THROUGHPUT_PER_ACCESS_POINT
    connected_route_capacities = [r.capacity_per_minute for r in routes if ghat.id in r.connects]
    if not connected_route_capacities:
        return access_point_capacity
    return min(access_point_capacity, min(connected_route_capacities))


def _risk_level(peak_pct: float) -> RiskLevel:
    if peak_pct >= _CRITICAL_THRESHOLD:
        return RiskLevel.CRITICAL
    if peak_pct >= _ELEVATED_THRESHOLD:
        return RiskLevel.ELEVATED
    return RiskLevel.ROUTINE


def simulate_scenario(
    scenario: SimulationScenario,
    ghats: dict[str, Ghat],
    routes: list[Route],
    on_tick: OnTickCallback | None = None,
) -> SimulationReport:
    """Tick-by-tick (one tick = one minute) occupancy simulation for every
    active ghat in the scenario, advancing all ghats together minute by
    minute (not one ghat fully simulated before the next) so that a caller
    watching via on_tick sees a single, internally-consistent snapshot of
    the whole site at each moment - what a real digital twin needs to
    animate meaningfully. Demand is split evenly across active ghats as a
    simplifying assumption - a real deployment would weight this by
    NTKMA's own historical footfall-distribution data; see
    TRINETRA.md's honest-limitations section.

    on_tick, if given, is called once per simulated minute with
    (minute, {ghat_id: {"occupancy": ..., "pct_of_capacity": ...}}) for
    every active ghat's state at that minute - purely an observation hook,
    it cannot influence the simulation. The returned SimulationReport is
    identical whether or not on_tick is supplied.
    """
    active_ghats = [ghats[gid] for gid in scenario.active_ghat_ids if gid in ghats]
    if not active_ghats:
        raise ValueError(f"No known ghats among {scenario.active_ghat_ids}")

    baseline_inflow_per_min = scenario.total_pilgrims / scenario.duration_minutes / len(active_ghats)
    peak_start = scenario.duration_minutes // 3
    peak_end = 2 * scenario.duration_minutes // 3

    outflow_caps = {g.id: _outflow_capacity(g, routes) for g in active_ghats}
    admission_block_levels = {g.id: g.safe_capacity * _ADMISSION_BLOCK_MULTIPLE for g in active_ghats}
    occupancy = {g.id: 0.0 for g in active_ghats}
    peak_occupancy = {g.id: 0.0 for g in active_ghats}
    peak_tick = {g.id: 0 for g in active_ghats}

    for minute in range(scenario.duration_minutes):
        is_peak_window = peak_start <= minute < peak_end
        tick_snapshot: TickSnapshot = {}

        for ghat in active_ghats:
            gid = ghat.id
            demanded_inflow = baseline_inflow_per_min * (scenario.peak_inflow_multiplier if is_peak_window else 1.0)
            # Admission control: once occupancy reaches the block level, only
            # let in enough new arrivals to replace outflow, rather than
            # letting the queue grow without bound - see _ADMISSION_BLOCK_MULTIPLE.
            admitted_inflow = (
                demanded_inflow if occupancy[gid] < admission_block_levels[gid] else min(demanded_inflow, outflow_caps[gid])
            )
            outflow = min(outflow_caps[gid], occupancy[gid] + admitted_inflow)
            occupancy[gid] = max(0.0, occupancy[gid] + admitted_inflow - outflow)
            if occupancy[gid] > peak_occupancy[gid]:
                peak_occupancy[gid] = occupancy[gid]
                peak_tick[gid] = minute

            tick_snapshot[gid] = {
                "occupancy": occupancy[gid],
                "pct_of_capacity": (occupancy[gid] / ghat.safe_capacity * 100) if ghat.safe_capacity else 0.0,
            }

        if on_tick is not None:
            on_tick(minute, tick_snapshot)

    ghat_results: list[GhatSimResult] = []
    incidents: list[str] = []

    for ghat in active_ghats:
        gid = ghat.id
        peak_pct = peak_occupancy[gid] / ghat.safe_capacity if ghat.safe_capacity else float("inf")
        risk = _risk_level(peak_pct)

        bottleneck_routes = [
            r.name for r in routes if gid in r.connects and r.capacity_per_minute < outflow_caps[gid] + 1
        ]

        if risk == RiskLevel.CRITICAL:
            structural_note = (
                f" on a {ghat.narrowest_approach_m}m-wide approach (below the "
                f"{_NARROW_LANE_THRESHOLD_M}m structural crush-risk threshold)"
                if ghat.narrowest_approach_m <= _NARROW_LANE_THRESHOLD_M
                else ""
            )
            incidents.append(
                f"Crowd crush risk at {ghat.name}: peak occupancy {peak_pct * 100:.0f}% of safe capacity"
                f"{structural_note} at minute {peak_tick[gid]} of the simulated window."
            )

        ghat_results.append(
            GhatSimResult(
                ghat_id=gid,
                ghat_name=ghat.name,
                peak_occupancy=round(peak_occupancy[gid]),
                peak_occupancy_pct_of_safe_capacity=round(peak_pct * 100, 1),
                peak_tick_minute=peak_tick[gid],
                risk_level=risk,
                bottleneck_routes=bottleneck_routes,
            )
        )

    order = {RiskLevel.ROUTINE: 0, RiskLevel.ELEVATED: 1, RiskLevel.CRITICAL: 2}
    overall_risk = max((r.risk_level for r in ghat_results), key=lambda lvl: order[lvl])

    return SimulationReport(
        scenario_name=scenario.name,
        ghat_results=ghat_results,
        overall_risk=overall_risk,
        incidents_triggered=incidents,
    )
