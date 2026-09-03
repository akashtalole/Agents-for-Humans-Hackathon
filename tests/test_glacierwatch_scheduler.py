"""Offline unit tests for the pure-code Field Inspection Scheduler
(glacierwatch/tools/scheduler.py) - known-distance sanity checks, capacity
limiting, empty-input handling, and priority-tier truncation."""
from __future__ import annotations

from glacierwatch.models import PriorityLevel, SiteRiskBrief, WatchSite
from glacierwatch.tools.scheduler import _haversine_km, build_inspection_schedule

# Delhi and Mumbai: real-world coordinates with a well-known approximate
# great-circle distance (~1150-1160 km) - a sanity check the formula, not
# just the implementation, is right.
_DELHI = (28.6139, 77.2090)
_MUMBAI = (19.0760, 72.8777)


def _site(site_id: str, lat: float, lon: float, status: str = "active_watch") -> WatchSite:
    return WatchSite(
        id=site_id,
        name=site_id.title(),
        state="Test State",
        district="Test District",
        river_basin="Test Basin",
        latitude=lat,
        longitude=lon,
        elevation_m=4000,
        status=status,
        static_risk_classification="test",
    )


def _brief(site_id: str, priority: PriorityLevel) -> SiteRiskBrief:
    return SiteRiskBrief(
        site_id=site_id,
        site_name=site_id.title(),
        priority_level=priority,
        rationale=f"rationale for {site_id}",
        recommended_action="test action",
    )


def test_haversine_known_distance_delhi_to_mumbai():
    distance = _haversine_km(*_DELHI, *_MUMBAI)
    assert 1100 <= distance <= 1200


def test_haversine_same_point_is_zero():
    assert _haversine_km(30.0, 77.0, 30.0, 77.0) == 0.0


def test_haversine_one_degree_latitude_is_about_111_km():
    # One degree of latitude is ~111 km everywhere on Earth (longitude
    # varies with latitude, so this check deliberately holds latitude fixed
    # and only varies latitude between the two points).
    distance = _haversine_km(30.0, 77.0, 31.0, 77.0)
    assert 110 <= distance <= 112


def test_empty_input_returns_empty_schedule_not_an_error():
    schedule = build_inspection_schedule(sites=[], briefs=[], max_stops=5)
    assert schedule.stops == []
    assert "no" in schedule.summary.lower()


def test_zero_candidates_all_routine_no_trend_is_graceful():
    sites = [_site("a", 30.0, 77.0)]
    briefs = [_brief("a", PriorityLevel.ROUTINE)]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=5)
    assert schedule.stops == []
    assert "routine" in schedule.summary.lower() or "priority" in schedule.summary.lower()


def test_capacity_limits_stop_count():
    sites = [_site(f"s{i}", 30.0 + i * 0.1, 77.0 + i * 0.1) for i in range(5)]
    briefs = [_brief(f"s{i}", PriorityLevel.PRIORITY) for i in range(5)]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=3)
    assert len(schedule.stops) == 3


def test_capacity_zero_or_negative_yields_no_stops():
    sites = [_site("a", 30.0, 77.0)]
    briefs = [_brief("a", PriorityLevel.PRIORITY)]
    assert build_inspection_schedule(sites=sites, briefs=briefs, max_stops=0).stops == []
    assert build_inspection_schedule(sites=sites, briefs=briefs, max_stops=-1).stops == []


def test_more_priority_sites_than_capacity_drops_lowest_priority_not_first():
    # Five priority sites, only three fit - all five are the same tier
    # (PRIORITY), so the first three in `briefs` order should survive and
    # the schedule must never silently include more than max_stops.
    sites = [_site(f"s{i}", 30.0 + i, 77.0) for i in range(5)]
    briefs = [_brief(f"s{i}", PriorityLevel.PRIORITY) for i in range(5)]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=3)
    assert len(schedule.stops) == 3
    scheduled_ids = {s.site_id for s in schedule.stops}
    assert scheduled_ids == {"s0", "s1", "s2"}
    assert "did not fit within capacity" in schedule.summary


def test_priority_tier_beats_elevated_and_elevated_beats_routine_bonus():
    sites = [
        _site("routine-rising", 30.0, 77.0),
        _site("elevated", 30.1, 77.1),
        _site("priority", 30.2, 77.2),
    ]
    briefs = [
        _brief("routine-rising", PriorityLevel.ROUTINE),
        _brief("elevated", PriorityLevel.ELEVATED),
        _brief("priority", PriorityLevel.PRIORITY),
    ]
    schedule = build_inspection_schedule(
        sites=sites,
        briefs=briefs,
        max_stops=2,
        rising_trend_site_ids=frozenset({"routine-rising"}),
    )
    # Capacity 2: PRIORITY and ELEVATED both fit; the routine-but-rising
    # bonus tier is the lowest priority and gets dropped.
    scheduled_ids = {s.site_id for s in schedule.stops}
    assert scheduled_ids == {"priority", "elevated"}


def test_rising_routine_site_included_as_bonus_tier_when_capacity_allows():
    sites = [_site("routine-rising", 30.0, 77.0), _site("priority", 30.1, 77.1)]
    briefs = [
        _brief("routine-rising", PriorityLevel.ROUTINE),
        _brief("priority", PriorityLevel.PRIORITY),
    ]
    schedule = build_inspection_schedule(
        sites=sites,
        briefs=briefs,
        max_stops=5,
        rising_trend_site_ids=frozenset({"routine-rising"}),
    )
    scheduled_ids = {s.site_id for s in schedule.stops}
    assert scheduled_ids == {"priority", "routine-rising"}


def test_routine_site_with_no_rising_trend_never_included():
    sites = [_site("routine-flat", 30.0, 77.0), _site("priority", 30.1, 77.1)]
    briefs = [
        _brief("routine-flat", PriorityLevel.ROUTINE),
        _brief("priority", PriorityLevel.PRIORITY),
    ]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=5)
    scheduled_ids = {s.site_id for s in schedule.stops}
    assert scheduled_ids == {"priority"}


def test_route_starts_at_highest_priority_site():
    # priority site is geographically farthest from the other two, but it
    # must still be stop 1 because routing starts at the highest-priority
    # selected stop, not the geographically-convenient one.
    sites = [
        _site("priority", 40.0, 90.0),
        _site("elevated-near", 30.0, 77.0),
        _site("elevated-far", 30.5, 77.5),
    ]
    briefs = [
        _brief("priority", PriorityLevel.PRIORITY),
        _brief("elevated-near", PriorityLevel.ELEVATED),
        _brief("elevated-far", PriorityLevel.ELEVATED),
    ]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=3)
    assert schedule.stops[0].site_id == "priority"


def test_route_visits_nearest_unvisited_next():
    # A cluster of two close-together sites plus one far outlier; nearest-
    # neighbor from the priority site should visit the near site before the
    # outlier, not the reverse.
    sites = [
        _site("priority", 30.0, 77.0),
        _site("near", 30.05, 77.05),
        _site("far", 35.0, 82.0),
    ]
    briefs = [
        _brief("priority", PriorityLevel.PRIORITY),
        _brief("near", PriorityLevel.ELEVATED),
        _brief("far", PriorityLevel.ELEVATED),
    ]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=3)
    ids_in_order = [s.site_id for s in schedule.stops]
    assert ids_in_order == ["priority", "near", "far"]


def test_stop_carries_rationale_and_coordinates_from_source_data():
    sites = [_site("a", 30.5, 77.5)]
    briefs = [_brief("a", PriorityLevel.PRIORITY)]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=5)
    stop = schedule.stops[0]
    assert stop.why_visit == "rationale for a"
    assert stop.latitude == 30.5
    assert stop.longitude == 77.5
    assert stop.site_name == "A"
    assert stop.priority_level == PriorityLevel.PRIORITY


def test_brief_with_no_matching_site_is_skipped_not_a_crash():
    sites = [_site("a", 30.0, 77.0)]
    briefs = [_brief("a", PriorityLevel.PRIORITY), _brief("missing-site", PriorityLevel.PRIORITY)]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=5)
    assert {s.site_id for s in schedule.stops} == {"a"}


def test_summary_reports_candidate_and_capacity_counts():
    sites = [_site(f"s{i}", 30.0 + i, 77.0) for i in range(4)]
    briefs = [_brief(f"s{i}", PriorityLevel.PRIORITY) for i in range(4)]
    schedule = build_inspection_schedule(sites=sites, briefs=briefs, max_stops=2)
    assert "2 of 4 candidate site(s)" in schedule.summary
    assert "capacity limit: 2" in schedule.summary
