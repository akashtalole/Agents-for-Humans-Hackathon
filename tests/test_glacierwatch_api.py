"""Offline tests for glacierwatch/api.py using FastAPI's TestClient.

Same discipline as test_glacierwatch_orchestrator_wiring.py: mock
run_watchlist (monkeypatched in glacierwatch.api, the module that imported
it) so these run with no API key and no network. Each test uses a fresh
TestClient/job store state via monkeypatching glacierwatch.api._jobs.
"""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

import glacierwatch.api as api_module
from glacierwatch.models import (
    CommunityAlertBulletin,
    GuardrailFinding,
    GuardrailResult,
    PriorityLevel,
    ReviewResult,
    SiteRiskBrief,
    WatchlistReport,
    WatchSite,
)
from glacierwatch.orchestrator import WatchRun
from glacierwatch.pipeline import WatchRunResult
from glacierwatch.rendering import DISCLAIMER, render_community_alert_md


@pytest.fixture(autouse=True)
def _clean_job_store():
    """Each test gets an isolated, empty job store."""
    api_module._jobs.clear()
    yield
    api_module._jobs.clear()


@pytest.fixture()
def client():
    return TestClient(api_module.app)


def _fake_site(site_id: str, name: str, status: str = "active_watch") -> WatchSite:
    return WatchSite(
        id=site_id,
        name=name,
        also_known_as=[],
        state="Himachal Pradesh",
        district="Lahaul-Spiti",
        river_basin="Chandra",
        latitude=32.5,
        longitude=77.1,
        elevation_m=4200,
        status=status,
        static_risk_classification="high",
        static_risk_factors=["fake factor"],
        downstream_exposure="fake exposure",
        sources=["fake source"],
    )


def _fake_run_watchlist_factory(*, priority_count: int, complete: bool = True):
    """Builds a fake run_watchlist() that mimics the real WatchRunResult
    shape without touching any network or model."""

    def _fake_run_watchlist(output_dir, history_file="glacierwatch_history.json", max_field_stops=5, callback_handler=None):
        # Exercise the callback the same way the real pipeline would, so the
        # SSE plumbing (a plain queue.Queue, never a framework object) is
        # covered too.
        if callback_handler:
            callback_handler(current_tool_use={"name": "load_watchlist"})
            callback_handler(current_tool_use={"name": "load_watchlist"})  # dup, should be deduped by api.py
            callback_handler(current_tool_use={"name": "fetch_current_conditions"})

        run = WatchRun(output_dir=output_dir)
        run.sites = [
            _fake_site("gepang-gath", "Gepang Gath Lake", "active_watch"),
            _fake_site("south-lhonak", "South Lhonak Lake", "historical_case_study"),
        ]
        if not complete:
            run.report = None
            return WatchRunResult(run=run, summary_text="incomplete run")

        briefs = [
            SiteRiskBrief(
                site_id="gepang-gath",
                site_name="Gepang Gath Lake",
                priority_level=PriorityLevel.PRIORITY if priority_count else PriorityLevel.ROUTINE,
                rationale="fake rationale",
                recommended_action="fake action",
            ),
            SiteRiskBrief(
                site_id="south-lhonak",
                site_name="South Lhonak Lake",
                priority_level=PriorityLevel.ROUTINE,
                rationale="fake rationale",
                recommended_action="fake action",
            ),
        ]
        run.briefs = briefs
        run.report = WatchlistReport(briefs=briefs, overall_summary="fake summary")

        from pathlib import Path

        Path(output_dir).mkdir(parents=True, exist_ok=True)
        (Path(output_dir) / "watchlist_report.md").write_text("# fake watchlist report\n")
        (Path(output_dir) / "site_profile_gepang-gath.md").write_text("fake profile A\n")
        (Path(output_dir) / "site_profile_south-lhonak.md").write_text("fake profile B\n")
        (Path(output_dir) / "site_conditions_gepang-gath.md").write_text("fake conditions A\n")

        return WatchRunResult(run=run, summary_text="fake orchestrator summary text")

    return _fake_run_watchlist


def _wait_for_completion(client: TestClient, job_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/runs/{job_id}")
        if resp.json()["status"] != "running":
            return resp
        time.sleep(0.02)
    raise AssertionError("job did not complete in time")


def test_status_endpoint_shape(client, monkeypatch):
    monkeypatch.setattr(api_module, "model_status", lambda: "Anthropic API direct (claude-sonnet-4-5)")
    resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status_text"] == "Anthropic API direct (claude-sonnet-4-5)"
    assert data["ready"] is True
    assert data["disclaimer"] == DISCLAIMER


def test_status_endpoint_not_ready_when_no_credentials(client, monkeypatch):
    monkeypatch.setattr(api_module, "model_status", lambda: "No credentials found (set ANTHROPIC_API_KEY or configure AWS credentials)")
    resp = client.get("/api/status")
    data = resp.json()
    assert data["ready"] is False


def test_create_run_returns_job_id(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    resp = client.post("/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert len(data["job_id"]) > 0


def test_get_unknown_job_returns_404(client):
    resp = client.get("/api/runs/does-not-exist")
    assert resp.status_code == 404


def test_run_lifecycle_success_no_priority_sites(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]

    resp = _wait_for_completion(client, job_id)
    data = resp.json()
    assert data["status"] == "completed"
    assert data["error"] is None
    assert data["status_badge"] == {"level": "success", "message": "No sites at priority level this week."}
    assert data["sites"] == [
        {"id": "gepang-gath", "name": "Gepang Gath Lake", "status": "active_watch"},
        {"id": "south-lhonak", "name": "South Lhonak Lake", "status": "historical_case_study"},
    ]
    assert data["files"] == [{"name": "watchlist_report.md", "label": "Weekly Watchlist"}]
    assert data["summary_text"] == "fake orchestrator summary text"


def test_run_lifecycle_priority_sites_error_badge(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=1))
    job_id = client.post("/api/runs").json()["job_id"]

    resp = _wait_for_completion(client, job_id)
    data = resp.json()
    assert data["status_badge"]["level"] == "error"
    assert "1 site(s) at PRIORITY level" in data["status_badge"]["message"]


def test_run_did_not_complete_warning_badge(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0, complete=False))
    job_id = client.post("/api/runs").json()["job_id"]

    resp = _wait_for_completion(client, job_id)
    data = resp.json()
    assert data["status"] == "completed"
    assert data["status_badge"] == {"level": "warning", "message": "Run did not complete."}
    assert data["files"] == []


def test_run_failure_reports_error(client, monkeypatch):
    def _raise(output_dir, history_file="glacierwatch_history.json", max_field_stops=5, callback_handler=None):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(api_module, "run_watchlist", _raise)
    job_id = client.post("/api/runs").json()["job_id"]

    resp = _wait_for_completion(client, job_id)
    data = resp.json()
    assert data["status"] == "failed"
    assert "simulated pipeline failure" in data["error"]
    assert data["status_badge"] is None
    assert data["sites"] is None


def test_events_stream_dedupes_and_ends_with_done(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]

    with client.stream("GET", f"/api/runs/{job_id}/events") as resp:
        assert resp.status_code == 200
        lines = [line for line in resp.iter_lines() if line]

    import json as _json

    events = [_json.loads(line[len("data: "):]) for line in lines]
    tool_events = [e for e in events if "tool" in e]
    # The fake callback fires load_watchlist twice consecutively, which
    # api.py's dedupe logic must collapse into a single event.
    assert tool_events == [{"tool": "load_watchlist"}, {"tool": "fetch_current_conditions"}]
    assert events[-1] == {"done": True}


def test_events_stream_unknown_job_404(client):
    resp = client.get("/api/runs/does-not-exist/events")
    assert resp.status_code == 404


def test_get_file_returns_content(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/watchlist_report.md")
    assert resp.status_code == 200
    assert "fake watchlist report" in resp.text
    assert resp.headers["content-type"].startswith("text/markdown")

    resp2 = client.get(f"/api/runs/{job_id}/files/site_profile_gepang-gath.md")
    assert resp2.status_code == 200
    assert "fake profile A" in resp2.text


def test_get_file_not_generated_returns_404(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    # south-lhonak is historical_case_study - conditions were never fetched.
    resp = client.get(f"/api/runs/{job_id}/files/site_conditions_south-lhonak.md")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "bad_filename",
    [
        "../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "subdir/watchlist_report.md",
        # Encoded so the test client's own URL normalization doesn't strip
        # it before the request even reaches the server - a bare ".." in
        # the test string gets collapsed by httpx's URL handling itself,
        # which would test the client library rather than glacierwatch/api.py.
        "%2e%2e",
    ],
)
def test_get_file_rejects_path_traversal(client, monkeypatch, bad_filename):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/{bad_filename}")
    assert resp.status_code in (400, 404)
    # Explicitly never a 200 with real file content leaking out.
    assert resp.status_code != 200


def test_get_file_unknown_job_404(client):
    resp = client.get("/api/runs/does-not-exist/files/watchlist_report.md")
    assert resp.status_code == 404


# --- Feature 3: human-in-the-loop approval gate -----------------------------

def _fake_alert(site_id: str = "gepang-gath", site_name: str = "Gepang Gath Lake") -> CommunityAlertBulletin:
    return CommunityAlertBulletin(
        site_id=site_id,
        site_name=site_name,
        priority_level=PriorityLevel.PRIORITY,
        situation_summary="fake situation summary",
        recommended_actions=["Review local evacuation routes."],
        settlements_to_notify=[],
        alert_text_en="fake alert text",
        alert_text_local="[Needs local-language review - no confident translation available]",
    )


def _fake_run_watchlist_with_alert(output_dir, history_file="glacierwatch_history.json", max_field_stops=5, callback_handler=None):
    """Mimics run_watchlist() for a run with exactly one priority site and
    one drafted (and reviewed/guardrailed) community alert bulletin."""
    from pathlib import Path

    run = WatchRun(output_dir=output_dir)
    run.sites = [_fake_site("gepang-gath", "Gepang Gath Lake", "active_watch")]
    brief = SiteRiskBrief(
        site_id="gepang-gath", site_name="Gepang Gath Lake", priority_level=PriorityLevel.PRIORITY,
        rationale="fake rationale", recommended_action="fake action",
    )
    run.briefs = [brief]
    run.report = WatchlistReport(briefs=run.briefs, overall_summary="fake summary")

    alert = _fake_alert()
    run.alerts = [alert]
    run.reviews = {"gepang-gath": ReviewResult(approved=True, issues=[], summary="Looks good.")}
    run.guardrails = {
        "gepang-gath": GuardrailResult(
            passed=False,
            findings=[
                GuardrailFinding(rule="prediction_language", excerpt="will occur", explanation="Test finding.")
            ],
        )
    }

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    (Path(output_dir) / "watchlist_report.md").write_text("# fake watchlist report\n")
    (Path(output_dir) / f"community_alert_{alert.site_id}.md").write_text(render_community_alert_md(alert))

    return WatchRunResult(run=run, summary_text="fake orchestrator summary text")


def test_run_with_alerts_goes_to_awaiting_approval(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_with_alert)
    job_id = client.post("/api/runs").json()["job_id"]

    resp = _wait_for_completion(client, job_id)
    data = resp.json()
    assert data["status"] == "awaiting_approval"
    assert data["status_badge"]["level"] == "warning"
    assert "1 community alert(s)" in data["status_badge"]["message"]

    assert len(data["alerts_for_approval"]) == 1
    alert = data["alerts_for_approval"][0]
    assert alert["site_id"] == "gepang-gath"
    assert alert["site_name"] == "Gepang Gath Lake"
    assert "fake alert text" in alert["text"]

    assert data["reviews"]["gepang-gath"]["approved"] is True
    assert data["guardrails"]["gepang-gath"]["passed"] is False
    assert len(data["guardrails"]["gepang-gath"]["findings"]) == 1
    assert data["guardrails"]["gepang-gath"]["findings"][0]["rule"] == "prediction_language"
    assert data["reject_reason"] is None


def test_run_with_zero_alerts_still_goes_straight_to_completed(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]
    resp = _wait_for_completion(client, job_id)
    data = resp.json()
    assert data["status"] == "completed"
    assert data["alerts_for_approval"] is None
    assert data["reviews"] is None
    assert data["guardrails"] is None


def test_approve_run_with_no_edits_keeps_original_text_and_completes(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_with_alert)
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/approve", json={"edited_alerts": None})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert "fake alert text" in data["alerts_for_approval"][0]["text"]


def test_approve_run_with_edits_overwrites_only_named_site(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_with_alert)
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(
        f"/api/runs/{job_id}/approve",
        json={"edited_alerts": {"gepang-gath": "EDITED ALERT TEXT"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    alert = data["alerts_for_approval"][0]
    assert alert["text"] == "EDITED ALERT TEXT"

    # A second GET reflects the same edited text, read fresh from disk.
    data2 = client.get(f"/api/runs/{job_id}").json()
    assert data2["alerts_for_approval"][0]["text"] == "EDITED ALERT TEXT"


def test_approve_rejects_unknown_site_id(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_with_alert)
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/approve", json={"edited_alerts": {"not-a-real-site": "x"}})
    assert resp.status_code == 400


def test_reject_run_stores_reason_and_sets_status(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_with_alert)
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/reject", json={"reason": "Needs more local review."})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["status_badge"]["level"] == "error"
    assert data["reject_reason"] == "Needs more local review."

    # Original file untouched.
    file_resp = client.get(f"/api/runs/{job_id}/files/community_alert_gepang-gath.md")
    assert "fake alert text" in file_resp.text


def test_approve_on_running_job_errors_cleanly(client, monkeypatch):
    started = threading.Event()
    finish = threading.Event()

    def _slow_run_watchlist(output_dir, history_file="glacierwatch_history.json", max_field_stops=5, callback_handler=None):
        started.set()
        finish.wait(timeout=5.0)
        return _fake_run_watchlist_factory(priority_count=0)(output_dir)

    monkeypatch.setattr(api_module, "run_watchlist", _slow_run_watchlist)
    job_id = client.post("/api/runs").json()["job_id"]
    started.wait(timeout=5.0)

    resp = client.post(f"/api/runs/{job_id}/approve", json={"edited_alerts": None})
    assert resp.status_code == 400
    reject_resp = client.post(f"/api/runs/{job_id}/reject", json={"reason": None})
    assert reject_resp.status_code == 400

    finish.set()
    _wait_for_completion(client, job_id)


def test_approve_on_completed_job_without_alerts_errors(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)
    resp = client.post(f"/api/runs/{job_id}/approve", json={"edited_alerts": None})
    assert resp.status_code == 400


# --- Feature 4: conversational follow-up (grounded chat) -------------------

def test_chat_on_running_job_returns_400(client, monkeypatch):
    started = threading.Event()
    finish = threading.Event()

    def _slow_run_watchlist(output_dir, history_file="glacierwatch_history.json", max_field_stops=5, callback_handler=None):
        started.set()
        finish.wait(timeout=5.0)
        return _fake_run_watchlist_factory(priority_count=0)(output_dir)

    monkeypatch.setattr(api_module, "run_watchlist", _slow_run_watchlist)
    job_id = client.post("/api/runs").json()["job_id"]
    started.wait(timeout=5.0)

    resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "How many sites are tracked?"})
    assert resp.status_code == 400

    finish.set()
    _wait_for_completion(client, job_id)


def test_chat_on_failed_job_returns_400(client, monkeypatch):
    def _raise(output_dir, history_file="glacierwatch_history.json", max_field_stops=5, callback_handler=None):
        raise RuntimeError("simulated pipeline failure")

    monkeypatch.setattr(api_module, "run_watchlist", _raise)
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "How many sites are tracked?"})
    assert resp.status_code == 400


def test_chat_on_completed_job_returns_reply_and_appends_history(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_watchlist", _fake_run_watchlist_factory(priority_count=0))
    job_id = client.post("/api/runs").json()["job_id"]
    _wait_for_completion(client, job_id)

    captured_prompts = {}

    class _FakeAgent:
        def __init__(self, prompt):
            captured_prompts["system_prompt"] = prompt

        def __call__(self, message):
            captured_prompts["message"] = message
            return "There are 2 sites being tracked this week."

    monkeypatch.setattr(api_module, "create_agent", lambda system_prompt: _FakeAgent(system_prompt))

    resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "How many sites are being tracked?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["reply"] == "There are 2 sites being tracked this week."
    assert "fake watchlist report" in captured_prompts["system_prompt"]
    assert "NOT a prediction system" in captured_prompts["system_prompt"]
    assert captured_prompts["message"] == "How many sites are being tracked?"

    history_resp = client.get(f"/api/runs/{job_id}/chat")
    assert history_resp.status_code == 200
    messages = history_resp.json()["messages"]
    assert messages == [
        {"role": "user", "content": "How many sites are being tracked?"},
        {"role": "assistant", "content": "There are 2 sites being tracked this week."},
    ]
