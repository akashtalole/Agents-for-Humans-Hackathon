"""Wiring tests for GlacierWatch's orchestrator - same discipline as the
other two projects' orchestrator wiring tests: use `agent.tool.<name>(...)`
(Strands' documented direct-call interface) to exercise the real tool-call
plumbing without hitting a live model. HTTP calls are mocked so this stays
fully offline.
"""
from __future__ import annotations

from pathlib import Path

import httpx

import glacierwatch.orchestrator as orchestrator_module
from glacierwatch.models import (
    CommunityAlertBulletin,
    CurrentConditions,
    DownstreamSettlement,
    HistoryEntry,
    PriorityLevel,
    RunHistory,
    SeismicEvent,
    SiteRiskBrief,
    WatchlistReport,
)
from glacierwatch.orchestrator import WatchRun, build_orchestrator
from glacierwatch.tools.history import save_history

FAKE_OPEN_METEO_RESPONSE = {
    "daily": {
        "time": ["2026-08-29", "2026-08-30"],
        "precipitation_sum": [0.0, 210.0],
    }
}
FAKE_USGS_RESPONSE = {"features": []}


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


def _tool_text(result) -> str:
    return result["content"][0]["text"]


def _fake_assess_site(site, conditions):
    priority = PriorityLevel.PRIORITY if conditions.heavy_rainfall_flag else (
        PriorityLevel.ELEVATED if site.status == "active_watch" else PriorityLevel.ROUTINE
    )
    return SiteRiskBrief(
        site_id=site.id,
        site_name=site.name,
        priority_level=priority,
        rationale=f"fake rationale for {site.id}",
        active_triggers=["fake trigger"] if priority == PriorityLevel.PRIORITY else [],
        recommended_action="fake action",
    )


def _fake_draft_report(briefs):
    priority_count = sum(1 for b in briefs if b.priority_level == PriorityLevel.PRIORITY)
    return WatchlistReport(briefs=briefs, overall_summary=f"{priority_count} site(s) at priority level.")


def test_full_pipeline_wiring_writes_all_expected_files(tmp_path: Path, monkeypatch):
    # weather.py and seismic.py both call the same global httpx.get - a single
    # patch has to route to the right fixture by URL, or the second setattr
    # silently clobbers the first (they're the same underlying attribute).
    def _fake_get(url, **kwargs):
        if "open-meteo" in url:
            return _FakeResponse(FAKE_OPEN_METEO_RESPONSE)
        if "usgs.gov" in url:
            return _FakeResponse(FAKE_USGS_RESPONSE)
        raise AssertionError(f"unexpected URL in test: {url}")

    monkeypatch.setattr("httpx.get", _fake_get)
    monkeypatch.setattr(orchestrator_module, "assess_site", _fake_assess_site)
    monkeypatch.setattr(orchestrator_module, "draft_watchlist_report", _fake_draft_report)

    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)

    assert "Loaded 4 site(s)" in _tool_text(orchestrator.tool.load_watchlist())

    active_sites = [s for s in run.sites if s.status == "active_watch"]
    assert len(active_sites) == 2
    for site in active_sites:
        result = _tool_text(orchestrator.tool.fetch_current_conditions(site_id=site.id))
        assert "Error" not in result

    for site in run.sites:
        result = _tool_text(orchestrator.tool.assess_site_risk(site_id=site.id))
        assert "Error" not in result

    report_result = _tool_text(orchestrator.tool.draft_watchlist_report_tool())
    assert "watchlist_report.md" in report_result

    assert (tmp_path / "watchlist_report.md").exists()
    for site in run.sites:
        assert (tmp_path / f"site_profile_{site.id}.md").exists()
    for site in active_sites:
        assert (tmp_path / f"site_conditions_{site.id}.md").exists()

    assert len(run.briefs) == 4
    assert run.report is not None

    # The active sites got 210mm rain in our fixture (extremely heavy) -> priority.
    # The historical sites never had conditions fetched -> routine.
    briefs_by_id = {b.site_id: b for b in run.briefs}
    for site in active_sites:
        assert briefs_by_id[site.id].priority_level == PriorityLevel.PRIORITY
    for site in run.sites:
        if site.status != "active_watch":
            assert briefs_by_id[site.id].priority_level == PriorityLevel.ROUTINE

    report_md = (tmp_path / "watchlist_report.md").read_text()
    assert "decision-support triage tool, not a prediction system" in report_md


def test_fetch_conditions_unknown_site_returns_error(tmp_path: Path):
    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    orchestrator.tool.load_watchlist()
    result = orchestrator.tool.fetch_current_conditions(site_id="does-not-exist")
    assert "Error" in _tool_text(result)


def test_assess_site_before_load_returns_error(tmp_path: Path):
    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    result = orchestrator.tool.assess_site_risk(site_id="gepang-gath")
    assert "Error" in _tool_text(result)


def test_draft_report_before_any_assessment_returns_error(tmp_path: Path):
    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    orchestrator.tool.load_watchlist()
    result = orchestrator.tool.draft_watchlist_report_tool()
    assert "Error" in _tool_text(result)


def test_fetch_conditions_http_failure_returns_honest_error_not_fabrication(tmp_path: Path, monkeypatch):
    def _raise(*a, **k):
        raise httpx.ConnectTimeout("simulated timeout")

    monkeypatch.setattr("httpx.get", _raise)
    monkeypatch.setattr("glacierwatch.tools._http.time.sleep", lambda *_: None)

    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    orchestrator.tool.load_watchlist()
    result = orchestrator.tool.fetch_current_conditions(site_id="gepang-gath")
    assert "Error" in _tool_text(result)
    assert "gepang-gath" not in run.conditions_by_site


def test_explicit_none_callback_handler_is_actually_silent(tmp_path: Path):
    from strands.handlers.callback_handler import null_callback_handler

    run = WatchRun(output_dir=str(tmp_path))
    quiet_orchestrator = build_orchestrator(run, callback_handler=None)
    assert quiet_orchestrator.callback_handler is null_callback_handler


def _fake_draft_community_alert(brief, settlements):
    return CommunityAlertBulletin(
        site_id=brief.site_id,
        site_name=brief.site_name,
        priority_level=brief.priority_level,
        situation_summary=f"fake situation summary for {brief.site_id}",
        recommended_actions=["Review local evacuation routes."],
        settlements_to_notify=settlements,
        alert_text_en="fake alert text",
        alert_text_local="[Needs local-language review - no confident translation available]",
    )


def test_draft_community_alerts_happy_path_writes_expected_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "draft_community_alert", _fake_draft_community_alert)

    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    run.briefs = [
        SiteRiskBrief(
            site_id="gepang-gath", site_name="Gepang Gath Lake", priority_level=PriorityLevel.PRIORITY,
            rationale="fake rationale", active_triggers=["fake trigger"], recommended_action="fake action",
        ),
        SiteRiskBrief(
            site_id="chorabari", site_name="Chorabari Lake (Gandhi Sarovar)", priority_level=PriorityLevel.ROUTINE,
            rationale="fake rationale", recommended_action="fake action",
        ),
    ]

    result = _tool_text(orchestrator.tool.draft_community_alerts())
    assert "Drafted 1 community alert bulletin" in result
    assert "community_alerts_index.md" in result

    assert (tmp_path / "community_alert_gepang-gath.md").exists()
    assert not (tmp_path / "community_alert_chorabari.md").exists()
    assert (tmp_path / "community_alerts_index.md").exists()

    alert_md = (tmp_path / "community_alert_gepang-gath.md").read_text()
    assert "Sissu" in alert_md
    assert "decision-support triage tool, not a prediction system" in alert_md

    index_md = (tmp_path / "community_alerts_index.md").read_text()
    assert "Gepang Gath Lake" in index_md
    assert "Chorabari" not in index_md

    assert len(run.alerts) == 1
    assert run.alerts[0].site_id == "gepang-gath"


def test_draft_community_alerts_zero_priority_sites_is_graceful_noop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "draft_community_alert", _fake_draft_community_alert)

    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    run.briefs = [
        SiteRiskBrief(
            site_id="south-lhonak", site_name="South Lhonak Lake", priority_level=PriorityLevel.ROUTINE,
            rationale="fake rationale", recommended_action="fake action",
        ),
    ]

    result = _tool_text(orchestrator.tool.draft_community_alerts())
    assert "no priority sites this week" in result.lower()
    assert "no community alert bulletins drafted" in result.lower()

    assert not (tmp_path / "community_alert_south-lhonak.md").exists()
    assert not (tmp_path / "community_alerts_index.md").exists()
    assert run.alerts == []


def test_draft_community_alerts_before_any_assessment_returns_error(tmp_path: Path):
    run = WatchRun(output_dir=str(tmp_path))
    orchestrator = build_orchestrator(run, callback_handler=None)
    result = _tool_text(orchestrator.tool.draft_community_alerts())
    assert "Error" in result
    assert "assess_site_risk" in result


def _run_with_assessed_gepang_gath(tmp_path: Path, *, mm: float, quake_count: int, history_file: str | None = None):
    run = WatchRun(output_dir=str(tmp_path), **({"history_file": history_file} if history_file else {}))
    orchestrator = build_orchestrator(run, callback_handler=None)
    run.conditions_by_site["gepang-gath"] = CurrentConditions(
        site_id="gepang-gath",
        as_of="2026-08-29T00:00:00Z",
        max_daily_precipitation_mm=mm,
        nearby_seismic_events=[
            SeismicEvent(time="2026-08-26T00:00:00Z", magnitude=4.0, distance_km=50.0, place="near X")
            for _ in range(quake_count)
        ],
        weather_source_note="test",
        seismic_source_note="test",
    )
    run.briefs = [
        SiteRiskBrief(
            site_id="gepang-gath", site_name="Gepang Gath Lake", priority_level=PriorityLevel.ELEVATED,
            rationale="fake rationale", recommended_action="fake action",
        )
    ]
    return run, orchestrator


def test_record_run_history_and_detect_trends_before_assessment_returns_error(tmp_path: Path):
    run = WatchRun(output_dir=str(tmp_path), history_file=str(tmp_path / "history.json"))
    orchestrator = build_orchestrator(run, callback_handler=None)
    result = _tool_text(orchestrator.tool.record_run_history_and_detect_trends())
    assert "Error" in result
    assert "assess_site_risk" in result
    assert not (tmp_path / "history.json").exists()
    assert not (tmp_path / "trend_report.md").exists()


def test_record_run_history_fresh_history_is_insufficient_history_not_an_error(tmp_path: Path):
    history_path = tmp_path / "history.json"
    run, orchestrator = _run_with_assessed_gepang_gath(tmp_path, mm=50.0, quake_count=1, history_file=str(history_path))

    result = _tool_text(orchestrator.tool.record_run_history_and_detect_trends())
    assert "Error" not in result
    assert "Recorded 1 site(s)" in result
    assert "0 of 1 site(s) show a rising trend" in result

    assert history_path.exists()
    assert (tmp_path / "trend_report.md").exists()
    trend_md = (tmp_path / "trend_report.md").read_text()
    assert "insufficient_history".upper().replace("_", " ") in trend_md.upper()
    assert "not a forecast" in trend_md.lower()

    assert len(run.trends) == 1
    assert run.trends[0].trend.value == "insufficient_history"
    assert len(run.history.entries) == 1


def test_record_run_history_happy_path_detects_rising_trend_from_synthetic_history(tmp_path: Path):
    history_path = tmp_path / "history.json"
    # Two prior runs of climbing rainfall and seismic counts, written directly
    # to disk to simulate a multi-week deployment history.
    save_history(
        str(history_path),
        RunHistory(
            entries=[
                HistoryEntry(
                    site_id="gepang-gath", run_at="2026-08-01T00:00:00Z", max_daily_precipitation_mm=10.0,
                    nearby_seismic_events=0, priority_level=PriorityLevel.ROUTINE,
                ),
                HistoryEntry(
                    site_id="gepang-gath", run_at="2026-08-08T00:00:00Z", max_daily_precipitation_mm=30.0,
                    nearby_seismic_events=1, priority_level=PriorityLevel.ROUTINE,
                ),
            ]
        ),
    )
    run, orchestrator = _run_with_assessed_gepang_gath(tmp_path, mm=80.0, quake_count=3, history_file=str(history_path))

    result = _tool_text(orchestrator.tool.record_run_history_and_detect_trends())
    assert "Recorded 1 site(s)" in result
    assert "1 of 1 site(s) show a rising trend" in result

    assert len(run.trends) == 1
    assert run.trends[0].trend.value == "rising"
    assert run.trends[0].site_name == "Gepang Gath Lake"
    # The two prior runs plus this one were persisted back to disk.
    assert len(run.history.entries) == 3
    reloaded = RunHistory.model_validate_json(history_path.read_text())
    assert len(reloaded.entries) == 3

    trend_md = (tmp_path / "trend_report.md").read_text()
    assert "RISING" in trend_md
    assert "Gepang Gath Lake" in trend_md

    # And the watchlist report, drafted after, surfaces the same rising
    # trend for a site that isn't yet at priority level this week.
    monkeypatch_report = WatchlistReport(briefs=run.briefs, overall_summary="0 site(s) at priority level.")
    from glacierwatch.rendering import render_watchlist_report_md

    report_md = render_watchlist_report_md(monkeypatch_report, run.trends)
    assert "Trend early-warning" in report_md
    assert "Gepang Gath Lake" in report_md
