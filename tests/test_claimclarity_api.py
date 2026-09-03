"""Offline tests for the ClaimClarity FastAPI backend (claimclarity/api.py).

`run_claim_case` is monkeypatched (same discipline as
tests/test_claimclarity_orchestrator_wiring.py mocking sub-agent functions)
so these run with no API key and no network. Background jobs run on a
ThreadPoolExecutor inside the app; tests poll GET /api/runs/{job_id} for the
"completed"/"failed" status rather than sleeping a fixed amount.
"""
from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import claimclarity.api as api_module
from claimclarity.models import Classification, DenialFindings, LineItemFinding
from claimclarity.orchestrator import ClaimCase
from claimclarity.pipeline import ClaimCaseResult


@pytest.fixture()
def client():
    return TestClient(api_module.app)


def _wait_for_completion(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/runs/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


def _fake_run_claim_case_worth_appealing(documents_paths, output_dir, history_file="claimclarity_history.json", callback_handler=None):
    if callback_handler:
        callback_handler(current_tool_use={"name": "load_claim_documents"})
        callback_handler(current_tool_use={"name": "load_claim_documents"})  # dedup check
        callback_handler(current_tool_use={"name": "investigate_denial"})

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decisions_needed.md").write_text("# Decisions Needed\n\nAppeal line 97110.")
    (out / "claim_summary.md").write_text("# Claim Summary")
    (out / "denial_findings.md").write_text("# Denial Findings")
    (out / "appeal_package.md").write_text("# Appeal Package")
    (out / "appeal_deadline.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n")
    # escalation_package.md and external_review_deadline.ics deliberately
    # omitted, to exercise the "only include files that exist" branch.

    case = ClaimCase(documents_paths=documents_paths, output_dir=output_dir, history_file=history_file)
    case.findings = DenialFindings(
        overall_recommendation="Appeal 97110.",
        findings=[
            LineItemFinding(
                procedure_code="97110",
                classification=Classification.BILLING_ERROR,
                evidence="M54.5 is non-billable per lookup_icd10_code.",
                corrected_diagnosis_code="M54.51",
                worth_appealing=True,
                recommendation="Billing code fix.",
            )
        ],
    )
    return ClaimCaseResult(case=case, summary_text="The orchestrator's own free-text summary.")


def _fake_run_claim_case_nothing_worth_appealing(documents_paths, output_dir, history_file="claimclarity_history.json", callback_handler=None):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "decisions_needed.md").write_text("# Decisions Needed\n\nNothing worth appealing.")

    case = ClaimCase(documents_paths=documents_paths, output_dir=output_dir, history_file=history_file)
    case.findings = DenialFindings(
        overall_recommendation="Do not appeal.",
        findings=[
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="Plan exclusion.",
                worth_appealing=False,
                recommendation="Not worth appealing.",
            )
        ],
    )
    return ClaimCaseResult(case=case, summary_text="Nothing to appeal here.")


def _fake_run_claim_case_incomplete(documents_paths, output_dir, history_file="claimclarity_history.json", callback_handler=None):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    case = ClaimCase(documents_paths=documents_paths, output_dir=output_dir, history_file=history_file)
    # findings stays None
    return ClaimCaseResult(case=case, summary_text="Investigation did not complete.")


def _fake_run_claim_case_raises(documents_paths, output_dir, history_file="claimclarity_history.json", callback_handler=None):
    raise RuntimeError("boom: simulated pipeline failure")


def test_status_endpoint_shape(client, monkeypatch):
    monkeypatch.setattr(api_module, "model_status", lambda: "Anthropic API direct (claude-sonnet-4-5-20250929)")
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status_text": "Anthropic API direct (claude-sonnet-4-5-20250929)", "ready": True}


def test_status_endpoint_not_ready_when_no_credentials(client, monkeypatch):
    monkeypatch.setattr(api_module, "model_status", lambda: "No credentials found (set ANTHROPIC_API_KEY or configure AWS credentials)")
    resp = client.get("/api/status")
    body = resp.json()
    assert body["ready"] is False


def test_create_run_with_no_documents_returns_400(client):
    resp = client.post("/api/runs", data={"use_example": "false"})
    assert resp.status_code == 400


def test_full_run_lifecycle_worth_appealing(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_worth_appealing)

    resp = client.post("/api/runs", data={"use_example": "true"})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert job_id  # non-empty uuid4 string

    # Immediately after creation the job should be running (or already done -
    # our fake is fast/synchronous-ish, so just assert the shape is sane).
    initial = client.get(f"/api/runs/{job_id}")
    assert initial.status_code == 200
    assert initial.json()["job_id"] == job_id

    body = _wait_for_completion(client, job_id)
    assert body["status"] == "completed"
    assert body["error"] is None
    assert body["status_badge"] == {
        "level": "success",
        "message": "1 item(s) look worth appealing — a draft letter is ready for review.",
    }
    assert body["summary_text"] == "The orchestrator's own free-text summary."

    names = [f["name"] for f in body["files"]]
    assert names == ["decisions_needed.md", "claim_summary.md", "denial_findings.md", "appeal_package.md"]
    # escalation_package.md was never written, so it must not appear.
    assert "escalation_package.md" not in names

    decisions_entry = body["files"][0]
    assert decisions_entry["download"] == {"name": "appeal_deadline.ics", "label": "Appeal deadline reminder (.ics)"}

    # Fetch a generated file's raw content.
    file_resp = client.get(f"/api/runs/{job_id}/files/decisions_needed.md")
    assert file_resp.status_code == 200
    assert "Appeal line 97110" in file_resp.text
    assert file_resp.headers["content-type"].startswith("text/markdown")

    ics_resp = client.get(f"/api/runs/{job_id}/files/appeal_deadline.ics")
    assert ics_resp.status_code == 200
    assert ics_resp.headers["content-type"].startswith("text/calendar")


def test_run_with_uploaded_documents(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_worth_appealing)

    resp = client.post(
        "/api/runs",
        data={"use_example": "false"},
        files={"documents": ("my_denial.md", io.BytesIO(b"# Denial\nSome content"), "text/markdown")},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    body = _wait_for_completion(client, job_id)
    assert body["status"] == "completed"


def test_nothing_worth_appealing_badge(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_nothing_worth_appealing)

    resp = client.post("/api/runs", data={"use_example": "true"})
    job_id = resp.json()["job_id"]
    body = _wait_for_completion(client, job_id)
    assert body["status_badge"] == {
        "level": "info",
        "message": "Nothing here looks worth appealing — see the explanation for why.",
    }


def test_incomplete_investigation_badge(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_incomplete)

    resp = client.post("/api/runs", data={"use_example": "true"})
    job_id = resp.json()["job_id"]
    body = _wait_for_completion(client, job_id)
    assert body["status_badge"] == {
        "level": "warning",
        "message": "Run did not complete denial investigation.",
    }
    assert body["files"] == []


def test_failed_run_reports_error(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_raises)

    resp = client.post("/api/runs", data={"use_example": "true"})
    job_id = resp.json()["job_id"]
    body = _wait_for_completion(client, job_id)
    assert body["status"] == "failed"
    assert "boom: simulated pipeline failure" in body["error"]
    assert body["status_badge"] is None
    assert body["files"] is None
    assert body["summary_text"] is None


def test_unknown_job_id_404(client):
    resp = client.get("/api/runs/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_events_stream_dedupes_and_ends_with_done(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_worth_appealing)

    resp = client.post("/api/runs", data={"use_example": "true"})
    job_id = resp.json()["job_id"]
    _wait_for_completion(client, job_id)

    with client.stream("GET", f"/api/runs/{job_id}/events") as stream:
        lines = [line for line in stream.iter_lines() if line.startswith("data: ")]

    events = [json.loads(line[len("data: "):]) for line in lines]
    tool_events = [e for e in events if "tool" in e]
    # The fake callback fires load_claim_documents twice in a row, which
    # must be deduped to a single event, then investigate_denial once.
    assert tool_events == [{"tool": "load_claim_documents"}, {"tool": "investigate_denial"}]
    assert events[-1] == {"done": True}


def test_file_endpoint_rejects_path_traversal(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_worth_appealing)

    resp = client.post("/api/runs", data={"use_example": "true"})
    job_id = resp.json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/..%2F..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code in (400, 404)

    # Starlette's routing itself rejects an encoded "/" in a single path
    # segment before our handler even runs (404), which is an equally valid
    # way to reject this - either way, no path outside output_dir is served.
    resp = client.get(f"/api/runs/{job_id}/files/nested%2Ffile.md")
    assert resp.status_code in (400, 404)


def test_resolve_job_file_rejects_traversal_directly(tmp_path):
    # A ".." (single path segment) never survives standard URL normalization
    # in a real HTTP client on the way to the server, so it can't be
    # exercised reliably over the wire - test the validation helper itself.
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "decisions_needed.md").write_text("hi")

    assert api_module._resolve_job_file(output_dir, "decisions_needed.md") == (output_dir / "decisions_needed.md").resolve()
    assert api_module._resolve_job_file(output_dir, "..") is None
    assert api_module._resolve_job_file(output_dir, "../secret.txt") is None
    assert api_module._resolve_job_file(output_dir, "sub/dir.md") is None
    assert api_module._resolve_job_file(output_dir, "") is None


def test_file_endpoint_404_for_missing_file(client, monkeypatch):
    monkeypatch.setattr(api_module, "run_claim_case", _fake_run_claim_case_worth_appealing)

    resp = client.post("/api/runs", data={"use_example": "true"})
    job_id = resp.json()["job_id"]
    _wait_for_completion(client, job_id)

    resp = client.get(f"/api/runs/{job_id}/files/does_not_exist.md")
    assert resp.status_code == 404
