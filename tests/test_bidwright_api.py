"""Offline tests for the BidWright FastAPI web API (bidwright/api.py).

Mocks `run_bid_job` (monkeypatched in `bidwright.api`, same pattern as
`tests/test_bidwright_orchestrator_wiring.py` mocks sub-agent functions) so
these run with no API key and no network - same offline-test discipline as
the rest of this repo.
"""
from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import bidwright.api as api_module
from bidwright.models import ChecklistItem, ComplianceGap, ComplianceReport, RFPRequirements, Severity
from bidwright.orchestrator import BidJob
from bidwright.pipeline import BidJobResult


@pytest.fixture(autouse=True)
def _reset_jobs():
    """Each test gets a clean job registry."""
    api_module._jobs.clear()
    yield
    api_module._jobs.clear()


@pytest.fixture
def client():
    return TestClient(api_module.app)


def _fake_requirements() -> RFPRequirements:
    return RFPRequirements(
        project_title="Test Project",
        issuing_organization="City of Test",
        submission_deadline="2026-09-30T17:00",
        checklist=[ChecklistItem(item="Sign cover letter")],
    )


def _fake_compliance_with_blocking_gap() -> ComplianceReport:
    return ComplianceReport(
        overall_status="gaps_found",
        met_requirements=["Business license"],
        gaps=[
            ComplianceGap(
                requirement="General liability minimum $2,000,000",
                status="gap",
                severity=Severity.BLOCKING,
                detail="Company carries $1,000,000 per occurrence.",
                recommendation="Increase coverage before the deadline.",
            )
        ],
    )


def _fake_compliance_ready() -> ComplianceReport:
    return ComplianceReport(overall_status="ready", met_requirements=["Everything"], gaps=[])


def _make_run_bid_job(compliance_factory, output_files: dict[str, str] | None = None):
    """Build a fake run_bid_job() that mimics the real pipeline's side effect
    of writing files to output_dir and returning a BidJobResult, without
    running any agent or touching the network."""

    def _fake_run_bid_job(
        rfp_path, profile_path, output_dir, amendment_path=None, history_file="bidwright_history.json", callback_handler=None
    ):
        if callback_handler is not None:
            callback_handler(current_tool_use={"name": "load_rfp_and_profile"})
            callback_handler(current_tool_use={"name": "load_rfp_and_profile"})  # dedup check
            callback_handler(current_tool_use={"name": "extract_rfp_requirements"})

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        job = BidJob(rfp_path=rfp_path, profile_path=profile_path, output_dir=output_dir)
        job.requirements = _fake_requirements()
        job.compliance = compliance_factory()

        files = output_files or {
            "decisions_needed.md": "# Decisions Needed\nReady to submit.",
            "requirements.md": "# Requirements",
            "compliance_report.md": "# Compliance Report",
            "proposal_draft.md": "# Proposal Draft",
        }
        for name, content in files.items():
            (out / name).write_text(content)

        return BidJobResult(job=job, summary_text="Orchestrator's own free-text summary.")

    return _fake_run_bid_job


def _wait_for_completion(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/runs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not complete within {timeout}s")


# --- /api/status ------------------------------------------------------


def test_status_ready_when_credentials_present(client, monkeypatch):
    monkeypatch.setattr(api_module, "model_status", lambda: "Anthropic API direct (claude-sonnet-4-5)")
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert "Anthropic" in body["status_text"]


def test_status_not_ready_without_credentials(client, monkeypatch):
    monkeypatch.setattr(api_module, "model_status", lambda: "No credentials found (set ANTHROPIC_API_KEY ...)")
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is False
    assert body["status_text"].startswith("No credentials")


# --- POST /api/runs -----------------------------------------------------


def test_create_run_with_example_returns_job_id(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    resp = client.post("/api/runs", data={"use_example": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert "job_id" in body and body["job_id"]


def test_create_run_without_example_requires_uploads(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    resp = client.post("/api/runs", data={"use_example": "false"})
    assert resp.status_code == 400


def test_create_run_with_uploads(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    resp = client.post(
        "/api/runs",
        data={"use_example": "false"},
        files={
            "rfp": ("my_rfp.md", io.BytesIO(b"# RFP text"), "text/markdown"),
            "profile": ("profile.json", io.BytesIO(b"{}"), "application/json"),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["job_id"]


# --- GET /api/runs/{job_id} status transitions --------------------------


def test_run_status_transitions_to_awaiting_approval(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    body = _wait_for_completion(client, job_id)
    # The orchestrator always drafts proposal_draft.md, so the web UI always
    # routes through a human-in-the-loop approval gate before the run is
    # "completed" - see bidwright/api.py's `_run_job`.
    assert body["status"] == "awaiting_approval"
    assert body["error"] is None
    assert body["status_badge"] == {
        "level": "warning",
        "message": "Awaiting your approval before this proposal is final.",
    }
    assert body["draft_text"] == "# Proposal Draft"
    assert body["summary_text"] == "Orchestrator's own free-text summary."
    names = [f["name"] for f in body["files"]]
    assert names == ["decisions_needed.md", "requirements.md", "compliance_report.md", "proposal_draft.md"]
    # decisions_needed.md carries the .ics download only when the file exists;
    # our fake run_bid_job didn't write one.
    assert "download" not in body["files"][0]


def test_run_status_transitions_to_completed_success_after_approval(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/approve", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["status_badge"] == {
        "level": "success",
        "message": "No blocking gaps found — this bid is ready for final human review.",
    }
    assert body["summary_text"] == "Orchestrator's own free-text summary."
    names = [f["name"] for f in body["files"]]
    assert names == ["decisions_needed.md", "requirements.md", "compliance_report.md", "proposal_draft.md"]
    # decisions_needed.md carries the .ics download only when the file exists;
    # our fake run_bid_job didn't write one.
    assert "download" not in body["files"][0]

    # Confirm the status persists on subsequent GETs, not just in the
    # approve response.
    body2 = client.get(f"/api/runs/{job_id}").json()
    assert body2["status"] == "completed"


def test_run_status_blocking_gap_gives_error_badge(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_with_blocking_gap))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    body = _wait_for_completion(client, job_id)
    assert body["status"] == "awaiting_approval"

    resp = client.post(f"/api/runs/{job_id}/approve", json={})
    body = resp.json()
    assert body["status"] == "completed"
    assert body["status_badge"]["level"] == "error"
    assert "1 blocking gap(s)" in body["status_badge"]["message"]


def test_run_status_none_compliance_gives_warning_badge(client, monkeypatch):
    def _fake_run_bid_job(rfp_path, profile_path, output_dir, amendment_path=None, history_file="bidwright_history.json", callback_handler=None):
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        job = BidJob(rfp_path=rfp_path, profile_path=profile_path, output_dir=output_dir)
        job.compliance = None
        return BidJobResult(job=job, summary_text="Incomplete run.")

    monkeypatch.setattr(api_module, "run_bid_job", _fake_run_bid_job)
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/approve", json={})
    body = resp.json()
    assert body["status"] == "completed"
    assert body["status_badge"] == {
        "level": "warning",
        "message": "Run did not complete compliance checking.",
    }
    assert body["files"] == []


# --- POST /api/runs/{job_id}/approve and /reject ------------------------


def test_approve_with_edited_text_overwrites_draft_and_completes(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/approve", json={"edited_text": "# Edited Proposal\nBetter now."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["draft_text"] == "# Edited Proposal\nBetter now."

    # The edit is persisted to disk, not just echoed back.
    resp2 = client.get(f"/api/runs/{job_id}/files/proposal_draft.md")
    assert resp2.text == "# Edited Proposal\nBetter now."


def test_approve_without_edited_text_keeps_original_draft(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/approve", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["draft_text"] == "# Proposal Draft"


def test_reject_sets_status_and_reason(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/reject", json={"reason": "Pricing section is wrong."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["reject_reason"] == "Pricing section is wrong."
    # The draft stays available for reference even though it's rejected.
    assert body["draft_text"] == "# Proposal Draft"

    # Persists on a fresh GET too.
    body2 = client.get(f"/api/runs/{job_id}").json()
    assert body2["status"] == "rejected"
    assert body2["reject_reason"] == "Pricing section is wrong."


def test_approve_on_already_awaiting_job_twice_second_call_errors(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    first = client.post(f"/api/runs/{job_id}/approve", json={})
    assert first.status_code == 200
    # Job is now "completed" - approving again is not a no-op, it's an error.
    second = client.post(f"/api/runs/{job_id}/approve", json={})
    assert second.status_code == 409


def test_approve_on_running_job_returns_error_not_crash(client, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def _blocking_run_bid_job(rfp_path, profile_path, output_dir, amendment_path=None, history_file="bidwright_history.json", callback_handler=None):
        started.set()
        release.wait(timeout=5)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        job = BidJob(rfp_path=rfp_path, profile_path=profile_path, output_dir=output_dir)
        job.compliance = _fake_compliance_ready()
        return BidJobResult(job=job, summary_text="done")

    monkeypatch.setattr(api_module, "run_bid_job", _blocking_run_bid_job)
    try:
        job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
        assert started.wait(timeout=5)

        approve_resp = client.post(f"/api/runs/{job_id}/approve", json={})
        assert approve_resp.status_code == 409

        reject_resp = client.post(f"/api/runs/{job_id}/reject", json={})
        assert reject_resp.status_code == 409

        # Job is still tracked and eventually finishes cleanly once released.
        assert client.get(f"/api/runs/{job_id}").json()["status"] == "running"
    finally:
        release.set()
        _wait_for_completion(client, job_id)


def test_approve_reject_unknown_job_404(client):
    assert client.post("/api/runs/does-not-exist/approve", json={}).status_code == 404
    assert client.post("/api/runs/does-not-exist/reject", json={}).status_code == 404


# --- /api/runs/{job_id}/chat ---------------------------------------------


def test_chat_on_running_job_returns_400(client, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def _blocking_run_bid_job(rfp_path, profile_path, output_dir, amendment_path=None, history_file="bidwright_history.json", callback_handler=None):
        started.set()
        release.wait(timeout=5)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        job = BidJob(rfp_path=rfp_path, profile_path=profile_path, output_dir=output_dir)
        job.compliance = _fake_compliance_ready()
        return BidJobResult(job=job, summary_text="done")

    monkeypatch.setattr(api_module, "run_bid_job", _blocking_run_bid_job)
    try:
        job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
        assert started.wait(timeout=5)

        resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "hello?"})
        assert resp.status_code == 400
    finally:
        release.set()
        _wait_for_completion(client, job_id)


def test_chat_on_failed_job_returns_400(client, monkeypatch):
    def _raising_run_bid_job(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_module, "run_bid_job", _raising_run_bid_job)
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "hello?"})
    assert resp.status_code == 400


def test_chat_on_completed_job_returns_reply_and_appends_history(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))

    calls: list[tuple[str, str]] = []

    class _FakeAgent:
        def __init__(self, system_prompt: str) -> None:
            self._system_prompt = system_prompt

        def __call__(self, message: str) -> str:
            calls.append((self._system_prompt, message))
            return "The submission deadline is 2026-09-30T17:00."

    def _fake_create_agent(system_prompt: str = "", **kwargs):
        return _FakeAgent(system_prompt)

    monkeypatch.setattr(api_module, "create_agent", _fake_create_agent)

    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)
    client.post(f"/api/runs/{job_id}/approve", json={})

    resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "what's the submission deadline?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "The submission deadline is 2026-09-30T17:00."
    # The chat agent is grounded only in this job's own generated files - the
    # RFP/profile paths never appear in the system prompt.
    assert calls and "what's the submission deadline?" == calls[0][1]
    assert "Proposal Draft" in calls[0][0]

    history = client.get(f"/api/runs/{job_id}/chat").json()["messages"]
    assert history == [
        {"role": "user", "content": "what's the submission deadline?"},
        {"role": "assistant", "content": "The submission deadline is 2026-09-30T17:00."},
    ]


def test_chat_requires_nonempty_message(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)
    client.post(f"/api/runs/{job_id}/approve", json={})

    resp = client.post(f"/api/runs/{job_id}/chat", json={"message": "   "})
    assert resp.status_code == 400


def test_chat_unknown_job_404(client):
    assert client.post("/api/runs/does-not-exist/chat", json={"message": "hi"}).status_code == 404
    assert client.get("/api/runs/does-not-exist/chat").status_code == 404


def test_run_status_failed_job_reports_error(client, monkeypatch):
    def _raising_run_bid_job(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_module, "run_bid_job", _raising_run_bid_job)
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    body = _wait_for_completion(client, job_id)
    assert body["status"] == "failed"
    assert body["error"] == "boom"
    assert body["status_badge"] is None
    assert body["files"] is None


def test_run_status_unknown_job_id_404(client):
    resp = client.get("/api/runs/does-not-exist")
    assert resp.status_code == 404


def test_ics_download_included_when_present(client, monkeypatch):
    files = {
        "decisions_needed.md": "# Decisions Needed",
        "requirements.md": "# Requirements",
        "compliance_report.md": "# Compliance Report",
        "proposal_draft.md": "# Proposal Draft",
        "submission_deadline.ics": "BEGIN:VCALENDAR\nEND:VCALENDAR",
    }
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready, files))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    body = _wait_for_completion(client, job_id)
    decisions = body["files"][0]
    assert decisions["name"] == "decisions_needed.md"
    assert decisions["download"] == {"name": "submission_deadline.ics", "label": "Deadline reminder (.ics)"}


# --- GET /api/runs/{job_id}/events (SSE) ---------------------------------


def test_events_stream_emits_tools_then_done(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    with client.stream("GET", f"/api/runs/{job_id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in resp.iter_lines() if line]

    assert 'data: {"tool": "load_rfp_and_profile"}' in lines
    assert 'data: {"tool": "extract_rfp_requirements"}' in lines
    # consecutive duplicate tool calls are deduped
    assert lines.count('data: {"tool": "load_rfp_and_profile"}') == 1
    assert lines[-1] == 'data: {"done": true}'


# --- GET /api/runs/{job_id}/files/{filename} -----------------------------


def test_get_run_file_returns_content(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/decisions_needed.md")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/markdown")
    assert "Decisions Needed" in resp.text


def test_get_run_file_ics_media_type(client, monkeypatch):
    files = {
        "decisions_needed.md": "# Decisions Needed",
        "submission_deadline.ics": "BEGIN:VCALENDAR\nEND:VCALENDAR",
    }
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready, files))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/submission_deadline.ics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/calendar")


def test_get_run_file_missing_file_404(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/does_not_exist.md")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "filename",
    [
        "../../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
        "subdir/requirements.md",
    ],
)
def test_get_run_file_rejects_path_traversal(client, monkeypatch, filename):
    monkeypatch.setattr(api_module, "run_bid_job", _make_run_bid_job(_fake_compliance_ready))
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/{filename}")
    # Never leak file content from outside the job's own output_dir.
    assert resp.status_code in (400, 404)
    assert "root:" not in resp.text


def test_run_files_include_compliance_cross_check_when_present(client, monkeypatch):
    monkeypatch.setattr(
        api_module,
        "run_bid_job",
        _make_run_bid_job(
            _fake_compliance_ready,
            output_files={
                "decisions_needed.md": "# Decisions Needed\nReady to submit.",
                "requirements.md": "# Requirements",
                "compliance_report.md": "# Compliance Report",
                "compliance_cross_check.md": "# Independent Compliance Cross-Check",
                "proposal_draft.md": "# Proposal Draft",
            },
        ),
    )
    job_id = client.post("/api/runs", data={"use_example": "true"}).json()["job_id"]
    body = _wait_for_completion(client, job_id)
    names = [f["name"] for f in body["files"]]
    assert names == [
        "decisions_needed.md",
        "requirements.md",
        "compliance_report.md",
        "compliance_cross_check.md",
        "proposal_draft.md",
    ]
    assert body["files"][3]["label"] == "Independent Audit"
