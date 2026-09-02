from glacierwatch.models import (
    CurrentConditions,
    PrecipitationReading,
    PriorityLevel,
    SeismicEvent,
    SiteRiskBrief,
    WatchlistReport,
    WatchSite,
)
from glacierwatch.rendering import (
    DISCLAIMER,
    render_conditions_md,
    render_site_profile_md,
    render_watchlist_report_md,
)

SITE = WatchSite(
    id="test-site",
    name="Test Lake",
    also_known_as=["Alt Name"],
    state="Himachal Pradesh",
    district="Lahaul and Spiti",
    river_basin="Chandra",
    latitude=32.5,
    longitude=77.2,
    elevation_m=4000,
    status="active_watch",
    static_risk_classification="Highly vulnerable",
    static_risk_factors=["Rapid area growth"],
    downstream_exposure="Threatens the village of Testville.",
    sources=["Test Journal, 2026"],
)


def test_render_site_profile_md_includes_key_facts():
    md = render_site_profile_md(SITE)
    assert "Test Lake" in md
    assert "Alt Name" in md
    assert "Himachal Pradesh" in md
    assert "Highly vulnerable" in md
    assert "Testville" in md
    assert "Test Journal, 2026" in md


def test_render_conditions_md_shows_heavy_rainfall_warning():
    conditions = CurrentConditions(
        site_id="test-site",
        as_of="2026-08-30T00:00:00Z",
        precipitation_recent_days=[PrecipitationReading(date="2026-08-30", precipitation_mm=220.0, category="extremely heavy")],
        max_daily_precipitation_mm=220.0,
        heavy_rainfall_flag=True,
        nearby_seismic_events=[SeismicEvent(time="2026-08-26T00:00:00Z", magnitude=4.0, distance_km=98.0, place="near X")],
        weather_source_note="Open-Meteo test",
        seismic_source_note="USGS test",
    )
    md = render_conditions_md(conditions)
    assert "220.0 mm" in md
    assert "Heavy rainfall threshold met or exceeded" in md
    assert "M4.0" in md
    assert "near X" in md


def test_render_conditions_md_no_events_says_so():
    conditions = CurrentConditions(site_id="test-site", as_of="2026-08-30T00:00:00Z")
    md = render_conditions_md(conditions)
    assert "No seismic events matching" in md
    assert "No heavy-rainfall threshold crossed" in md


def test_render_watchlist_report_md_orders_priority_first():
    briefs = [
        SiteRiskBrief(
            site_id="routine-site", site_name="Routine Lake", priority_level=PriorityLevel.ROUTINE,
            rationale="Historical case study.", recommended_action="None beyond reference.",
        ),
        SiteRiskBrief(
            site_id="priority-site", site_name="Priority Lake", priority_level=PriorityLevel.PRIORITY,
            rationale="Extreme rainfall flag active.", active_triggers=["220mm rain"],
            recommended_action="Prioritize field inspection.",
        ),
        SiteRiskBrief(
            site_id="elevated-site", site_name="Elevated Lake", priority_level=PriorityLevel.ELEVATED,
            rationale="High baseline risk, no active trigger.", recommended_action="Continue scheduled monitoring.",
        ),
    ]
    report = WatchlistReport(briefs=briefs, overall_summary="1 site at priority level this week.")
    md = render_watchlist_report_md(report)

    assert DISCLAIMER in md
    priority_pos = md.index("Priority Lake")
    elevated_pos = md.index("Elevated Lake")
    routine_pos = md.index("Routine Lake")
    assert priority_pos < elevated_pos < routine_pos
    assert "Prioritize field inspection." in md


def test_render_watchlist_report_md_always_includes_disclaimer_even_when_empty():
    report = WatchlistReport(overall_summary="No sites assessed.")
    md = render_watchlist_report_md(report)
    assert DISCLAIMER in md
