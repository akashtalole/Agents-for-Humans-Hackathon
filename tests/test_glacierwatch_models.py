from glacierwatch.models import (
    CurrentConditions,
    PrecipitationReading,
    PriorityLevel,
    SeismicEvent,
    SiteRiskBrief,
    WatchlistReport,
    WatchSite,
)


def test_watch_site_round_trip():
    site = WatchSite(
        id="test-site",
        name="Test Lake",
        state="Himachal Pradesh",
        district="Lahaul and Spiti",
        river_basin="Chandra",
        latitude=32.5,
        longitude=77.2,
        elevation_m=4000,
        status="active_watch",
        static_risk_classification="Test classification",
        static_risk_factors=["factor one"],
        sources=["Test Source"],
    )
    restored = WatchSite.model_validate_json(site.model_dump_json())
    assert restored == site


def test_current_conditions_defaults():
    conditions = CurrentConditions(site_id="test-site", as_of="2026-08-30T00:00:00Z")
    assert conditions.precipitation_recent_days == []
    assert conditions.heavy_rainfall_flag is False
    assert conditions.nearby_seismic_events == []


def test_site_risk_brief_priority_enum():
    brief = SiteRiskBrief(
        site_id="test-site",
        site_name="Test Lake",
        priority_level=PriorityLevel.PRIORITY,
        rationale="Heavy rainfall flag active.",
        active_triggers=["Extremely heavy rainfall: 220.0mm"],
        recommended_action="Prioritize inspection.",
    )
    assert brief.priority_level == PriorityLevel.PRIORITY
    assert brief.priority_level.value == "priority"


def test_watchlist_report_defaults():
    report = WatchlistReport(overall_summary="No sites require priority attention this week.")
    assert report.briefs == []


def test_precipitation_reading_and_seismic_event_construct():
    reading = PrecipitationReading(date="2026-08-30", precipitation_mm=12.3, category="light")
    assert reading.precipitation_mm == 12.3

    event = SeismicEvent(time="2026-08-26T00:16:55Z", magnitude=4.0, distance_km=98.0, place="38 km NE of X")
    assert event.magnitude == 4.0
