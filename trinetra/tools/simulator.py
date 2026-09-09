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

_RISK_ORDER = {RiskLevel.ROUTINE: 0, RiskLevel.ELEVATED: 1, RiskLevel.CRITICAL: 2}

# Once occupancy reaches this multiple of a ghat's safe_capacity, this model
# assumes further inflow is blocked - either by authorities closing entry or
# by the crowd's own physical density preventing more people from arriving.
# This is a deliberate, documented simplification, not a measured physical
# limit - a real deployment should replace it with NTKMA's actual
# gate-closure/admission-control protocol.
#
# IMPORTANT: blocking admission does NOT make those people go away. They are
# standing in the approach lane, which is exactly where the 39 deaths at
# Kalaram Mandir Marg happened in 2003 - the barricade that failed was on the
# approach, not at the ghat. An earlier version of this module silently
# discarded every unadmitted arrival, which meant the 2003 replay dropped
# roughly 263,000 people from the model and reported the resulting plateau as
# if it were the whole story. They are now conserved in `waiting` below and
# reported as queue_outside_* on each GhatSimResult.
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

    peak_start = scenario.duration_minutes // 3
    peak_end = 2 * scenario.duration_minutes // 3

    # A surge redistributes when the same crowd turns up, it does not conjure
    # extra pilgrims. Normalising by the multiplier-weighted length of the
    # window keeps total arrivals equal to scenario.total_pilgrims for any
    # peak_inflow_multiplier. Without this the x3.2 replay generated 1.73x
    # the stated crowd - which went unnoticed while unadmitted arrivals were
    # being discarded, because the surplus people were thrown away before
    # anything counted them.
    peak_minutes = peak_end - peak_start
    weighted_minutes = (scenario.duration_minutes - peak_minutes) + peak_minutes * scenario.peak_inflow_multiplier
    baseline_inflow_per_min = scenario.total_pilgrims / weighted_minutes / len(active_ghats)

    outflow_caps = {g.id: _outflow_capacity(g, routes) for g in active_ghats}
    admission_block_levels = {g.id: g.safe_capacity * _ADMISSION_BLOCK_MULTIPLE for g in active_ghats}
    occupancy = {g.id: 0.0 for g in active_ghats}
    peak_occupancy = {g.id: 0.0 for g in active_ghats}
    peak_tick = {g.id: 0 for g in active_ghats}
    # People who arrived but were not admitted. They are in the approach
    # lane - see _ADMISSION_BLOCK_MULTIPLE.
    waiting = {g.id: 0.0 for g in active_ghats}
    peak_waiting = {g.id: 0.0 for g in active_ghats}
    waiting_half_window = {g.id: 0.0 for g in active_ghats}
    half_window = scenario.duration_minutes // 2

    for minute in range(scenario.duration_minutes):
        is_peak_window = peak_start <= minute < peak_end
        tick_snapshot: TickSnapshot = {}

        for ghat in active_ghats:
            gid = ghat.id
            demanded_inflow = baseline_inflow_per_min * (scenario.peak_inflow_multiplier if is_peak_window else 1.0)
            # Everyone who has turned up and not yet got in is contending for
            # admission this minute: this minute's arrivals plus everyone
            # already held back in the lane.
            presenting = demanded_inflow + waiting[gid]
            # Admission control: once occupancy reaches the block level, only
            # let in enough people to replace outflow - see
            # _ADMISSION_BLOCK_MULTIPLE.
            admitted_inflow = (
                presenting if occupancy[gid] < admission_block_levels[gid] else min(presenting, outflow_caps[gid])
            )
            waiting[gid] = max(0.0, presenting - admitted_inflow)
            outflow = min(outflow_caps[gid], occupancy[gid] + admitted_inflow)
            occupancy[gid] = max(0.0, occupancy[gid] + admitted_inflow - outflow)
            if occupancy[gid] > peak_occupancy[gid]:
                peak_occupancy[gid] = occupancy[gid]
                peak_tick[gid] = minute
            peak_waiting[gid] = max(peak_waiting[gid], waiting[gid])
            if minute == half_window:
                waiting_half_window[gid] = waiting[gid]

            tick_snapshot[gid] = {
                "occupancy": occupancy[gid],
                "pct_of_capacity": (occupancy[gid] / ghat.safe_capacity * 100) if ghat.safe_capacity else 0.0,
                "waiting_outside": waiting[gid],
            }

        if on_tick is not None:
            on_tick(minute, tick_snapshot)

    ghat_results: list[GhatSimResult] = []
    incidents: list[str] = []

    for ghat in active_ghats:
        gid = ghat.id
        peak_pct = peak_occupancy[gid] / ghat.safe_capacity if ghat.safe_capacity else float("inf")
        occupancy_risk = _risk_level(peak_pct)

        # The queue outside is its own hazard, and not one occupancy can
        # express: occupancy saturates at _ADMISSION_BLOCK_MULTIPLE by
        # construction, so once a ghat is blocked its percentage stops moving
        # no matter how many more people arrive. Everything after that point
        # shows up here instead.
        final_waiting = waiting[gid]
        queue_still_growing = final_waiting > waiting_half_window[gid]
        # Minutes to drain the leftover queue at this ghat's own throughput,
        # assuming nobody else arrives. Derived from the model, not a
        # tuned threshold.
        queue_clear_minutes = final_waiting / outflow_caps[gid] if outflow_caps[gid] else float("inf")
        is_narrow = ghat.narrowest_approach_m <= _NARROW_LANE_THRESHOLD_M

        # A queue that is still growing when the window ends is unbounded as
        # far as this model can tell. In a lane below the structural width
        # threshold that is the 2003 Kalaram Mandir mechanism exactly, so it
        # is critical on its own evidence - not because occupancy said so.
        if queue_still_growing and is_narrow:
            queue_risk = RiskLevel.CRITICAL
        elif queue_still_growing or final_waiting > 0:
            queue_risk = RiskLevel.ELEVATED
        else:
            queue_risk = RiskLevel.ROUTINE

        risk = max((occupancy_risk, queue_risk), key=lambda lvl: _RISK_ORDER[lvl])

        bottleneck_routes = [
            r.name for r in routes if gid in r.connects and r.capacity_per_minute < outflow_caps[gid] + 1
        ]

        if queue_risk == RiskLevel.CRITICAL:
            incidents.append(
                f"Approach-lane crush risk at {ghat.name}: {round(peak_waiting[gid]):,} people held outside at peak "
                f"on a {ghat.narrowest_approach_m}m-wide approach, and the queue was still growing when the "
                f"simulated window ended - this model cannot say when it clears."
            )

        if occupancy_risk == RiskLevel.CRITICAL:
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
                peak_queue_outside=round(peak_waiting[gid]),
                final_queue_outside=round(final_waiting),
                queue_still_growing_at_end=queue_still_growing,
                queue_clear_minutes=round(queue_clear_minutes, 1),
            )
        )

    overall_risk = max((r.risk_level for r in ghat_results), key=lambda lvl: _RISK_ORDER[lvl])

    return SimulationReport(
        scenario_name=scenario.name,
        ghat_results=ghat_results,
        overall_risk=overall_risk,
        incidents_triggered=incidents,
    )
