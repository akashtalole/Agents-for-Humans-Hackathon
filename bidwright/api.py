"""FastAPI web API for BidWright.

This is a second front end onto the exact same `run_bid_job()` pipeline the
Streamlit demo (`app_streamlit.py`) and the CLI use — same orchestrator, same
Pydantic-validated sub-agents, same deterministic rendered output files. It
does not change any pipeline behavior; it only adds a way to drive it over
HTTP and stream progress to a browser.

Architectural note vs. the Streamlit demo: `app_streamlit.py`'s
`stream_callback` has to re-attach Streamlit's `ScriptRunContext` on every
callback invocation, because Strands runs the agent (and therefore every
`callback_handler` call) on its own background thread, which never receives
Streamlit's thread-local session context — omitting that re-attachment
raises `NoSessionContext` (see `docs/bidwright/screenshots/NOTES.md` for the
real crash this caused). This API sidesteps that whole class of bug by never
touching a framework/session object from the callback at all: the callback
here only pushes plain dicts onto a thread-safe `queue.Queue`, which requires
no session/context of any kind, then the SSE endpoint drains that queue from
the asyncio event loop via `run_in_executor`. Simpler, and there is no
framework object to forget to re-attach.

Trust hierarchy: exactly like the Streamlit demo, the orchestrator's own
free-text reply (`summary_text`) is exposed to callers but is never treated
as authoritative. The generated files on disk (`decisions_needed.md` most of
all) are the trusted output; `summary_text` is provided for transparency
only, and the frontend must label it "(unverified)".
"""
from __future__ import annotations

import asyncio
import queue
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from bidwright.config import create_agent, model_status
from bidwright.pipeline import BidJobResult, run_bid_job

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

app = FastAPI(title="BidWright API")

_executor = ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# Fixed, ordered list of output files the UI cares about. `download` is an
# extra file offered alongside the tab (only decisions_needed.md has one:
# the .ics deadline reminder). Mirrors app_streamlit.py's tab order exactly.
_FILE_SPECS: list[dict[str, Any]] = [
    {
        "name": "decisions_needed.md",
        "label": "Decisions Needed",
        "download": {"name": "submission_deadline.ics", "label": "Deadline reminder (.ics)"},
    },
    {"name": "requirements.md", "label": "Requirements"},
    {"name": "compliance_report.md", "label": "Compliance Report"},
    {"name": "compliance_cross_check.md", "label": "Independent Audit"},
    {"name": "proposal_draft.md", "label": "Proposal Draft"},
]

_MEDIA_TYPES = {
    ".md": "text/markdown",
    ".ics": "text/calendar",
}


def _new_job_entry() -> dict[str, Any]:
    return {
        "status": "running",
        "error": None,
        "result": None,
        "output_dir": None,
        "events": queue.Queue(),
        "reject_reason": None,
        "chat_history": [],
    }


def _run_job(
    job_id: str,
    rfp_path: str,
    profile_path: str,
    output_dir: str,
    amendment_path: str | None,
) -> None:
    entry = _jobs[job_id]
    events: queue.Queue = entry["events"]
    seen: list[str | None] = []

    def callback(**kwargs: Any) -> None:
        tool_use = kwargs.get("current_tool_use") or {}
        name = tool_use.get("name")
        if name and (not seen or seen[-1] != name):
            seen.append(name)
            events.put({"tool": name})

    try:
        result: BidJobResult = run_bid_job(
            rfp_path=rfp_path,
            profile_path=profile_path,
            output_dir=output_dir,
            amendment_path=amendment_path,
            callback_handler=callback,
        )
        with _lock:
            # The orchestrator always drafts proposal_draft.md, so there is
            # always something for a human to approve before it's final -
            # the web UI's human-in-the-loop gate (CLI/Streamlit are
            # unaffected; they never look at this status field).
            entry["status"] = "awaiting_approval"
            entry["result"] = result
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as job status
        with _lock:
            entry["status"] = "failed"
            entry["error"] = str(exc)
    finally:
        events.put({"done": True})


def _status_badge(status: str, result: BidJobResult | None) -> dict[str, str] | None:
    if status == "awaiting_approval":
        return {"level": "warning", "message": "Awaiting your approval before this proposal is final."}
    if status == "rejected":
        return {"level": "error", "message": "Rejected — not approved for submission."}
    if result is None:
        return None
    job = result.job
    if job.compliance is None:
        return {"level": "warning", "message": "Run did not complete compliance checking."}
    blocking = [g for g in job.compliance.gaps if g.severity.value == "blocking"]
    if blocking:
        return {
            "level": "error",
            "message": f"{len(blocking)} blocking gap(s) found — this bid is NOT ready to submit yet.",
        }
    return {"level": "success", "message": "No blocking gaps found — this bid is ready for final human review."}


def _files_payload(output_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for spec in _FILE_SPECS:
        if not (output_dir / spec["name"]).exists():
            continue
        entry: dict[str, Any] = {"name": spec["name"], "label": spec["label"]}
        download = spec.get("download")
        if download and (output_dir / download["name"]).exists():
            entry["download"] = download
        files.append(entry)
    return files


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    status_text = model_status()
    return {"status_text": status_text, "ready": not status_text.startswith("No credentials")}


@app.post("/api/runs")
async def create_run(
    use_example: str = Form("false"),
    rfp: UploadFile | None = File(None),
    profile: UploadFile | None = File(None),
    amendment: UploadFile | None = File(None),
) -> dict[str, str]:
    use_example_bool = use_example.strip().lower() == "true"
    job_id = str(uuid.uuid4())
    workdir = Path(tempfile.mkdtemp(prefix=f"bidwright_api_{job_id}_"))

    if use_example_bool:
        rfp_path = str(EXAMPLES_DIR / "sample_rfp.md")
        profile_path = str(EXAMPLES_DIR / "company_profile.json")
    else:
        if rfp is None or profile is None:
            shutil.rmtree(workdir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail="Both 'rfp' and 'profile' files are required when use_example is not true.",
            )
        rfp_dest = workdir / (rfp.filename or "rfp_upload")
        rfp_dest.write_bytes(await rfp.read())
        rfp_path = str(rfp_dest)

        profile_dest = workdir / (profile.filename or "profile_upload")
        profile_dest.write_bytes(await profile.read())
        profile_path = str(profile_dest)

    amendment_path: str | None = None
    if amendment is not None and amendment.filename:
        amendment_dest = workdir / amendment.filename
        amendment_dest.write_bytes(await amendment.read())
        amendment_path = str(amendment_dest)

    output_dir = workdir / "output"

    with _lock:
        _jobs[job_id] = _new_job_entry()
        _jobs[job_id]["output_dir"] = output_dir

    _executor.submit(_run_job, job_id, rfp_path, profile_path, str(output_dir), amendment_path)

    return {"job_id": job_id}


def _get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        entry = _jobs.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return entry


def _draft_text(output_dir: Path) -> str | None:
    draft_path = output_dir / "proposal_draft.md"
    return draft_path.read_text() if draft_path.is_file() else None


def _review_payload(result: BidJobResult | None) -> dict[str, Any] | None:
    if result is None or result.job.review is None:
        return None
    review = result.job.review
    return {"approved": review.approved, "issues": list(review.issues)}


def _guardrail_payload(result: BidJobResult | None) -> dict[str, Any] | None:
    if result is None or result.job.guardrail is None:
        return None
    guardrail = result.job.guardrail
    return {
        "passed": guardrail.passed,
        "findings": [
            {"rule": f.rule, "excerpt": f.excerpt, "explanation": f.explanation}
            for f in guardrail.findings
        ],
    }


def _run_payload(job_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    status = entry["status"]
    result: BidJobResult | None = entry["result"]

    payload: dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "error": entry["error"],
        "status_badge": None,
        "files": None,
        "summary_text": None,
        "draft_text": None,
        "review": None,
        "guardrail": None,
        "reject_reason": entry.get("reject_reason"),
    }
    if status != "running":
        payload["status_badge"] = _status_badge(status, result)
        payload["draft_text"] = _draft_text(Path(entry["output_dir"]))
        payload["review"] = _review_payload(result)
        payload["guardrail"] = _guardrail_payload(result)
        if result is not None:
            payload["files"] = _files_payload(Path(entry["output_dir"]))
            payload["summary_text"] = result.summary_text
    return payload


@app.get("/api/runs/{job_id}")
def get_run(job_id: str) -> dict[str, Any]:
    entry = _get_job(job_id)
    return _run_payload(job_id, entry)


@app.post("/api/runs/{job_id}/approve")
def approve_run(job_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    entry = _get_job(job_id)
    with _lock:
        if entry["status"] != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"Job is '{entry['status']}', not 'awaiting_approval' - nothing to approve.",
            )
        edited_text = body.get("edited_text")
        if edited_text:
            (Path(entry["output_dir"]) / "proposal_draft.md").write_text(edited_text)
        entry["status"] = "completed"
    return _run_payload(job_id, entry)


@app.post("/api/runs/{job_id}/reject")
def reject_run(job_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    entry = _get_job(job_id)
    with _lock:
        if entry["status"] != "awaiting_approval":
            raise HTTPException(
                status_code=409,
                detail=f"Job is '{entry['status']}', not 'awaiting_approval' - nothing to reject.",
            )
        entry["status"] = "rejected"
        entry["reject_reason"] = body.get("reason")
    return _run_payload(job_id, entry)


# Chat is grounded ONLY in this job's own generated .md files, capped at
# ~40,000 characters of context so a run with a large RFP/profile can't blow
# past the model's context window - if it would exceed the cap, the least-
# important files (the reviewer/guardrail notes) are dropped first, keeping
# the core proposal/decision files.
_CHAT_CONTEXT_CHAR_LIMIT = 40_000
_CHAT_LOW_PRIORITY_FILES = ["proposal_guardrail.md", "proposal_review.md"]

_CHAT_SYSTEM_PROMPT = (
    "You answer questions about this specific BidWright RFP bid using ONLY the "
    "documents provided below. If the answer isn't in them, say so honestly "
    "instead of guessing. Answer in 2-4 sentences unless more detail is "
    "clearly needed."
)


def _chat_context(output_dir: Path) -> str:
    md_files = {p.name: p.read_text() for p in sorted(output_dir.glob("*.md"))}
    total = sum(len(text) for text in md_files.values())
    # Drop the least-important files first (in _CHAT_LOW_PRIORITY_FILES order)
    # until the total fits, rather than truncating individual files, since a
    # half-truncated compliance report is worse than an absent one.
    for name in _CHAT_LOW_PRIORITY_FILES:
        if total <= _CHAT_CONTEXT_CHAR_LIMIT:
            break
        if name in md_files:
            total -= len(md_files.pop(name))
    parts = [f"## {name}\n\n{text}" for name, text in md_files.items()]
    context = "\n\n".join(parts)
    if len(context) > _CHAT_CONTEXT_CHAR_LIMIT:
        context = context[:_CHAT_CONTEXT_CHAR_LIMIT] + "\n\n_[truncated]_"
    return context


def _run_chat_turn(output_dir: Path, message: str) -> str:
    """Blocking Strands call - always run via the executor, never directly
    on the asyncio event loop."""
    context = _chat_context(output_dir)
    agent = create_agent(system_prompt=f"{_CHAT_SYSTEM_PROMPT}\n\n{context}")
    result = agent(message)
    return str(result)


@app.post("/api/runs/{job_id}/chat")
async def chat_with_run(job_id: str, body: dict[str, Any] = Body(...)) -> dict[str, str]:
    entry = _get_job(job_id)
    if entry["status"] in ("running", "failed"):
        raise HTTPException(
            status_code=400,
            detail=f"Job is '{entry['status']}' - nothing to chat about yet.",
        )
    message = (body.get("message") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required.")

    output_dir = Path(entry["output_dir"])
    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(_executor, _run_chat_turn, output_dir, message)

    with _lock:
        entry["chat_history"].append({"role": "user", "content": message})
        entry["chat_history"].append({"role": "assistant", "content": reply})

    return {"reply": reply}


@app.get("/api/runs/{job_id}/chat")
def get_chat_history(job_id: str) -> dict[str, Any]:
    entry = _get_job(job_id)
    return {"messages": list(entry["chat_history"])}


@app.get("/api/runs/{job_id}/events")
async def run_events(job_id: str):
    entry = _get_job(job_id)
    events: queue.Queue = entry["events"]

    async def event_stream():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, events.get)
            yield f"data: {_to_json(item)}\n\n"
            if item.get("done"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _to_json(item: dict[str, Any]) -> str:
    import json

    return json.dumps(item)


@app.get("/api/runs/{job_id}/files/{filename}")
def get_run_file(job_id: str, filename: str) -> Response:
    entry = _get_job(job_id)
    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    output_dir = Path(entry["output_dir"]).resolve()
    file_path = (output_dir / filename).resolve()
    if output_dir not in file_path.parents and file_path != output_dir:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = _MEDIA_TYPES.get(file_path.suffix, "application/octet-stream")
    if media_type == "text/markdown":
        return PlainTextResponse(file_path.read_text(), media_type=media_type)
    return Response(content=file_path.read_bytes(), media_type=media_type)


# Mounted LAST so /api/* routes always take priority over the SPA catch-all.
_DIST_DIR = Path(__file__).resolve().parent.parent / "webapp" / "bidwright" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
