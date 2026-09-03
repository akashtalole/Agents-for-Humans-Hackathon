"""Field Inspection Scheduler: turns "these sites are priority" into "here is
your team's route for this week" - pure code, no LLM, same discipline as
glacierwatch/tools/history.py's trend classification.

The gap this closes: watchlist_report.md correctly ranks which sites need
attention, but a real disaster-management field team can only physically
visit a handful of sites in a week, sites are scattered across a mountainous
region, and nothing upstream of this turns a priority list into an actual,
ordered work plan. Deciding which sites fit in a capacity-limited week and in
what order to drive to them is a geometric/logistics optimization problem
over structured numbers (lat/long, a priority ranking, a capacity limit) -
exactly the kind of thing this project's architecture already treats as
plain code's job, not a model's (see history.py:classify_trend).

Same shape as tools/watchlist.py and tools/downstream.py: a plain function,
not `@tool`-decorated, so the orchestrator can hand it and get back the full
structured InspectionSchedule rather than a text summary to re-parse.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from glacierwatch.models import InspectionSchedule, InspectionStop, PriorityLevel, SiteRiskBrief, WatchSite

# Only PRIORITY and ELEVATED sites, plus ROUTINE sites on a rising trend, are
# ever worth sending a field team to. A plain ROUTINE, non-trending site
# never fills spare capacity just because a slot is open - a field team's
# limited time should never be spent confirming nothing is happening
# somewhere nothing indicates anything is happening. That is a deliberate
# design choice: see the module docstring above and GLACIERWATCH.md's Field
# Inspection Scheduler section for the reasoning.
_PRIORITY_TIER = 0
_ELEVATED_TIER = 1
_RISING_ROUTINE_TIER = 2


def _tier_for(brief: SiteRiskBrief, rising_trend_site_ids: frozenset[str]) -> int | None:
    if brief.priority_level == PriorityLevel.PRIORITY:
        return _PRIORITY_TIER
    if brief.priority_level == PriorityLevel.ELEVATED:
        return _ELEVATED_TIER
    if brief.priority_level == PriorityLevel.ROUTINE and brief.site_id in rising_trend_site_ids:
        return _RISING_ROUTINE_TIER
    return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two lat/long points, via the
    haversine formula:

        a = sin²(Δlat/2) + cos(lat1)·cos(lat2)·sin²(Δlon/2)
        distance = 2 · R · asin(√a)

    where R is Earth's mean radius (6371 km). This is straight-line
    ("as the crow flies") distance, not road distance - a mountainous
    region's actual travel time along switchback roads can be far longer
    than this number suggests. It is used here only to produce a sensible
    default visiting order, never as a travel-time estimate; see
    build_inspection_schedule's docstring and GLACIERWATCH.md's Honest
    Limitations for that caveat stated to the reader.
    """
    r_km = 6371.0
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return 2 * r_km * asin(sqrt(a))


def _route_by_nearest_neighbor(stops: list[InspectionStop]) -> list[InspectionStop]:
    """Order `stops` into a visiting route with a greedy nearest-neighbor
    heuristic: start at stops[0] (the highest-priority selected stop), then
    repeatedly jump to whichever remaining stop is closest (haversine
    distance) to the current one, until every stop has been visited.

    Known limitation, stated plainly: this is NOT a true Traveling Salesman
    Problem solve. Greedy nearest-neighbor can produce a visibly suboptimal
    route in some layouts (e.g. it can strand one far-away stop for last
    when visiting it earlier would have shortened the total trip) - finding
    the actual shortest route over N stops is NP-hard in general. For the
    small number of stops a single field team's weekly capacity limit
    implies (a handful, not dozens), "good enough, obviously sensible, and
    computed instantly" comfortably outweighs the cost of an exact solver,
    and a field team lead applying local road knowledge remains free to
    reorder stops themselves - this is a starting point, not a routing
    mandate.
    """
    if len(stops) <= 2:
        return list(stops)

    remaining = list(stops[1:])
    ordered = [stops[0]]
    current = stops[0]
    while remaining:
        nearest = min(
            remaining,
            key=lambda s: _haversine_km(current.latitude, current.longitude, s.latitude, s.longitude),
        )
        ordered.append(nearest)
        remaining.remove(nearest)
        current = nearest
    return ordered


def build_inspection_schedule(
    sites: list[WatchSite],
    briefs: list[SiteRiskBrief],
    max_stops: int,
    rising_trend_site_ids: frozenset[str] = frozenset(),
) -> InspectionSchedule:
    """Build this week's field team inspection route, deterministically.

    Selection: candidates are ranked into three tiers - PRIORITY sites first,
    then ELEVATED sites, then ROUTINE sites whose site_id appears in
    `rising_trend_site_ids` (the trend tracker's early-warning signal, see
    glacierwatch/tools/history.py - a small bonus tier so a site climbing
    toward priority can earn an optional visit before it crosses the
    threshold, capacity allowing). Plain ROUTINE sites with no rising trend
    are never candidates - see the module-level comment on _PRIORITY_TIER
    for why. Within a tier, relative order follows `briefs`' own order.

    Capacity: the ranked candidate list is capped at `max_stops`, dropping
    the lowest-priority overflow (never truncating from the front, and never
    silently including more than `max_stops` stops). `max_stops <= 0` yields
    an empty schedule.

    Routing: the selected stops are then reordered into an actual visiting
    sequence by greedy nearest-neighbor (see _route_by_nearest_neighbor) -
    without this step the output would just be a priority-sorted list that
    ignores geography, which is not a usable route for a team driving
    between scattered mountain sites.

    A `sites` entry with no matching brief, or a `briefs` entry with no
    matching `sites` entry, is silently skipped (defensive - both lists are
    expected to correspond 1:1 for whatever site population the caller
    passed in, but a schedule should degrade gracefully rather than crash on
    a data mismatch).

    Returns an InspectionSchedule with empty `stops` and an honest
    zero-candidates summary when nothing qualifies - never an error.
    """
    sites_by_id = {s.id: s for s in sites}

    candidates: list[tuple[int, SiteRiskBrief]] = []
    for brief in briefs:
        if brief.site_id not in sites_by_id:
            continue
        tier = _tier_for(brief, rising_trend_site_ids)
        if tier is not None:
            candidates.append((tier, brief))

    if not candidates:
        return InspectionSchedule(
            stops=[],
            summary=(
                "No sites needed a field visit this week - no priority or elevated sites, and no "
                "routine site on a rising trend, so no inspection schedule was built."
            ),
        )

    candidates.sort(key=lambda pair: pair[0])
    capacity = max(max_stops, 0)
    selected = candidates[:capacity]

    unrouted_stops = [
        InspectionStop(
            site_id=brief.site_id,
            site_name=brief.site_name,
            priority_level=brief.priority_level,
            why_visit=brief.rationale,
            latitude=sites_by_id[brief.site_id].latitude,
            longitude=sites_by_id[brief.site_id].longitude,
        )
        for _tier, brief in selected
    ]
    ordered_stops = _route_by_nearest_neighbor(unrouted_stops)

    dropped = len(candidates) - len(selected)
    summary = (
        f"{len(ordered_stops)} of {len(candidates)} candidate site(s) scheduled for field visits this week "
        f"(capacity limit: {max_stops})."
    )
    if dropped > 0:
        summary += f" {dropped} lower-priority candidate site(s) did not fit within capacity."

    return InspectionSchedule(stops=ordered_stops, summary=summary)
