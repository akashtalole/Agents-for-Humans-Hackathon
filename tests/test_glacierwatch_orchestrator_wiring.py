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
from glacierwatch.models import PriorityLevel, SiteRiskBrief, WatchlistReport
from glacierwatch.orchestrator import WatchRun, build_orchestrator

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
