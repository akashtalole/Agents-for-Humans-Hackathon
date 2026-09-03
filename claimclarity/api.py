"""FastAPI backend for the ClaimClarity web UI.

Serves the same underlying pipeline (`claimclarity.pipeline.run_claim_case`)
as the CLI and the Streamlit demo (`app_claimclarity.py`), behind a small
JSON/SSE API consumed by the React frontend in `webapp/claimclarity/`.

Architectural note on the background-job callback (see the class docstring
comparison in CLAIMCLARITY.md's "Web UI" section for the full story): the
Streamlit demo works around a real bug where Strands always runs the agent
(and therefore every `callback_handler` invocation) on its own background
thread, which never carries Streamlit's `ScriptRunContext` - touching `st.*`
from that thread raises `NoSessionContext` (see
`docs/claimclarity/screenshots/NOTES.md`; fixed in `app_claimclarity.py` by
re-attaching the context on every callback). This API sidesteps that whole
class of bug by construction: the callback here only ever pushes plain dicts
onto a thread-safe `queue.Queue` - it never touches a framework/session
object of any kind - and the SSE endpoint drains that queue from whichever
thread/task is serving the request. There is no framework context to lose.

No authentication. See CLAIMCLARITY.md's "Web UI" section and this project's
"Honest limitations" for why that's an explicit, called-out gap rather than
an oversight - this handles denial notices and (optionally) medical record
excerpts, so treat any real deployment of this API as needing an auth layer
added in front of it before it touches real patient data. The one mitigation
built in: job ids are `uuid4`, so a job cannot be guessed or enumerated -
this is "unguessable IDs," not "access control."

Human-in-the-loop approval gate: a successful run never lands on "completed"
directly - it lands on "awaiting_approval", because the orchestrator always
drafts appeal_package.md, and a human always has to review it (plus the
independent critic's review and the guardrail findings, both already
computed) before it counts as ready to send. POST .../approve moves it to
"completed" (optionally overwriting appeal_package.md with a human-edited
version first); POST .../reject moves it to "rejected" with a stored reason.
Nothing here submits anything anywhere - both endpoints only change job
bookkeeping and, for approve, the on-disk draft file.

Conversational follow-up: POST/GET .../chat lets the frontend ask grounded
follow-up questions about one job. Grounded strictly - the chat agent gets a
fresh, tool-less Strands Agent whose only knowledge is the concatenation of
that job's own generated .md files, never the open internet or the model's
own training data about insurance law. It is built and called fresh per
question (no conversation history is fed back into the model - each answer
is grounded only in the case files, not in prior chat turns) and run off the
event loop via the shared executor, same reasoning as the SSE queue read
below: nothing here should block `asyncio`'s single thread.
"""
from __future__ import annotations

import asyncio
import json
import queue
import shutil
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from claimclarity.config import create_agent, model_status
from claimclarity.pipeline import ClaimCaseResult, run_claim_case
from claimclarity.tools.documents import save_text_file

EXAMPLES_DIR = Path(__file__).parent.parent / "examples" / "claimclarity"
EXAMPLE_DOCUMENTS = [
    EXAMPLES_DIR / "denial_notice.md",
    EXAMPLES_DIR / "plan_summary_of_benefits.md",
    EXAMPLES_DIR / "medical_record_excerpt.md",
]

# Fixed, ordered file manifest - mirrors app_claimclarity.py's tab order
# exactly. Each entry's "download" (an .ics reminder) is only surfaced by
# GET /api/runs/{job_id} when that file actually exists on disk.
FILE_MANIFEST = [
    {
        "name": "decisions_needed.md",
        "label": "Decisions Needed",
        "download": {"name": "appeal_deadline.ics", "label": "Appeal deadline reminder (.ics)"},
    },
    {"name": "claim_summary.md", "label": "Claim Summary"},
    {"name": "denial_findings.md", "label": "Denial Findings"},
    {"name": "appeal_package.md", "label": "Appeal Package"},
    {
        "name": "escalation_package.md",
        "label": "External Review & Escalation",
        "download": {
            "name": "external_review_deadline.ics",
            "label": "External review deadline reminder (.ics)",
        },
    },
]

_MEDIA_TYPES = {".md": "text/markdown", ".ics": "text/calendar"}

CHAT_SYSTEM_PROMPT = """\
You answer questions about this specific ClaimClarity insurance denial case \
using ONLY the documents provided below. If the answer isn't in them, say so \
honestly instead of guessing - and note once, if relevant, that this isn't \
legal or medical advice. Answer in 2-4 sentences unless more detail is \
clearly needed.
"""

_CHAT_CONTEXT_CHAR_LIMIT = 40_000
# Drop order when the concatenated .md files would exceed the cap - least
# essential first. appeal_review.md and appeal_guardrail.md are internal QA
# artifacts (a second opinion ON the appeal, not case facts), so they go
# before the primary case files; appeal_package.md, decisions_needed.md, and
# denial_findings.md are the last things dropped, in that order.
_CHAT_CONTEXT_DROP_ORDER = [
    "appeal_review.md",
    "appeal_guardrail.md",
    "insurer_pattern_report.md",
    "physician_evidence_request.md",
    "escalation_package.md",
    "claim_summary.md",
    "appeal_package.md",
    "decisions_needed.md",
    "denial_findings.md",
]

app = FastAPI(title="ClaimClarity API")

_executor = ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


class StatusResponse(BaseModel):
    status_text: str
    ready: bool


class RunCreatedResponse(BaseModel):
    job_id: str


class ApproveRequest(BaseModel):
    edited_text: Optional[str] = None


class RejectRequest(BaseModel):
    reason: Optional[str] = None


class ChatRequest(BaseModel):
    message: str


@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    status_text = model_status()
    return StatusResponse(status_text=status_text, ready=not status_text.startswith("No credentials"))


def _new_job_entry() -> dict[str, Any]:
    return {
        "status": "running",
        "error": None,
        "result": None,
        "events": queue.Queue(),
        "output_dir": None,
        "reject_reason": None,
        "chat_history": [],
    }


def _run_job(job_id: str, documents_paths: list[str], output_dir: str) -> None:
    events: queue.Queue = _jobs[job_id]["events"]
    seen: list[Optional[str]] = []

    def callback(**kwargs: Any) -> None:
        tool_use = kwargs.get("current_tool_use") or {}
        name = tool_use.get("name")
        if name and (not seen or seen[-1] != name):
            seen.append(name)
            events.put({"tool": name})

    try:
        result = run_claim_case(
            documents_paths=documents_paths,
            output_dir=output_dir,
            callback_handler=callback,
        )
        with _lock:
            # Never "completed" straight off a successful run - the
            # orchestrator always drafts appeal_package.md, and a human
            # always has to approve (or reject) it before it's done. See
            # POST .../approve and .../reject below.
            _jobs[job_id]["status"] = "awaiting_approval"
            _jobs[job_id]["result"] = result
    except Exception as exc:  # noqa: BLE001 - reported to the client, not swallowed
        with _lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)
    finally:
        events.put({"done": True})


@app.post("/api/runs", response_model=RunCreatedResponse)
async def create_run(
    use_example: str = Form("false"),
    documents: list[UploadFile] = File(default_factory=list),
) -> RunCreatedResponse:
    use_example_bool = use_example.strip().lower() == "true"
    workdir = Path(tempfile.mkdtemp(prefix="claimclarity_api_"))

    if use_example_bool:
        documents_paths = [str(p) for p in EXAMPLE_DOCUMENTS]
    elif documents:
        documents_paths = []
        for upload in documents:
            filename = Path(upload.filename or "document").name
            if not filename:
                continue
            dest = workdir / filename
            data = await upload.read()
            dest.write_bytes(data)
            documents_paths.append(str(dest))
    else:
        documents_paths = []

    if not documents_paths:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail="Please upload at least the denial notice/EOB, or use the example.",
        )

    job_id = str(uuid.uuid4())
    output_dir = workdir / "output"
    with _lock:
        entry = _new_job_entry()
        entry["output_dir"] = output_dir
        _jobs[job_id] = entry

    _executor.submit(_run_job, job_id, documents_paths, str(output_dir))
    return RunCreatedResponse(job_id=job_id)


def _status_badge(status: str, result: Optional[ClaimCaseResult]) -> Optional[dict[str, str]]:
    # "awaiting_approval" and "rejected" get a fixed badge about the approval
    # gate itself, regardless of what the findings say - a human reviewing
    # this job needs to know first whether it's actionable at all. Only once
    # a job is actually "completed" (i.e. approved) does the badge fall back
    # to describing what the (now-final) appeal actually says.
    if status == "awaiting_approval":
        return {"level": "warning", "message": "Awaiting your approval before this appeal is sent."}
    if status == "rejected":
        return {"level": "error", "message": "Rejected — not approved for sending."}
    if result is None:
        return None
    case = result.case
    if case.findings is None:
        return {"level": "warning", "message": "Run did not complete denial investigation."}
    worth_appealing = [f for f in case.findings.findings if f.worth_appealing]
    if worth_appealing:
        return {
            "level": "success",
            "message": f"{len(worth_appealing)} item(s) look worth appealing — a draft letter is ready for review.",
        }
    return {"level": "info", "message": "Nothing here looks worth appealing — see the explanation for why."}


def _files_payload(output_dir: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for entry in FILE_MANIFEST:
        if not (output_dir / entry["name"]).exists():
            continue
        item: dict[str, Any] = {"name": entry["name"], "label": entry["label"]}
        download = entry.get("download")
        if download and (output_dir / download["name"]).exists():
            item["download"] = download
        files.append(item)
    return files


def _get_job(job_id: str) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id.")
    return job


def _draft_text(output_dir: Path) -> Optional[str]:
    appeal_path = output_dir / "appeal_package.md"
    if not appeal_path.is_file():
        return None
    return appeal_path.read_text(encoding="utf-8")


@app.get("/api/runs/{job_id}")
def get_run(job_id: str) -> JSONResponse:
    job = _get_job(job_id)
    status = job["status"]
    payload: dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "error": job.get("error"),
        "status_badge": None,
        "files": None,
        "summary_text": None,
        "draft_text": None,
        "review": None,
        "guardrail": None,
        "reject_reason": job.get("reject_reason"),
    }
    # Every non-"running" status (awaiting_approval, completed, rejected,
    # failed) gets a status badge - only "failed" has no result to build the
    # rest of the payload from.
    if status != "running":
        result: Optional[ClaimCaseResult] = job.get("result")
        payload["status_badge"] = _status_badge(status, result)
        if result is not None:
            payload["files"] = _files_payload(job["output_dir"])
            payload["summary_text"] = result.summary_text
            payload["draft_text"] = _draft_text(job["output_dir"])
            case = result.case
            if case.review is not None:
                payload["review"] = case.review.model_dump()
            if case.guardrail is not None:
                payload["guardrail"] = case.guardrail.model_dump()
    return JSONResponse(payload)


@app.post("/api/runs/{job_id}/approve")
def approve_run(job_id: str, body: ApproveRequest = ApproveRequest()) -> JSONResponse:
    job = _get_job(job_id)
    with _lock:
        if job["status"] != "awaiting_approval":
            raise HTTPException(
                status_code=400,
                detail=f"Job is '{job['status']}', not awaiting approval.",
            )
        if body.edited_text is not None and body.edited_text.strip():
            save_text_file(str(job["output_dir"] / "appeal_package.md"), body.edited_text)
        job["status"] = "completed"
    return get_run(job_id)


@app.post("/api/runs/{job_id}/reject")
def reject_run(job_id: str, body: RejectRequest = RejectRequest()) -> JSONResponse:
    job = _get_job(job_id)
    with _lock:
        if job["status"] != "awaiting_approval":
            raise HTTPException(
                status_code=400,
                detail=f"Job is '{job['status']}', not awaiting approval.",
            )
        job["status"] = "rejected"
        job["reject_reason"] = body.reason
    return get_run(job_id)


def _build_chat_context(output_dir: Path) -> str:
    """Concatenate every .md file this job wrote, capped at
    `_CHAT_CONTEXT_CHAR_LIMIT` characters - drop the least essential files
    first (`_CHAT_CONTEXT_DROP_ORDER`) rather than truncating mid-file."""
    contents: dict[str, str] = {}
    for path in sorted(output_dir.glob("*.md")):
        try:
            contents[path.name] = path.read_text(encoding="utf-8")
        except OSError:
            continue

    total = sum(len(text) for text in contents.values())
    for name in _CHAT_CONTEXT_DROP_ORDER:
        if total <= _CHAT_CONTEXT_CHAR_LIMIT:
            break
        dropped = contents.pop(name, None)
        if dropped is not None:
            total -= len(dropped)

    return "\n\n".join(f"--- {name} ---\n{text}" for name, text in sorted(contents.items()))


def _ask_chat_agent(context: str, message: str) -> str:
    agent = create_agent(system_prompt=f"{CHAT_SYSTEM_PROMPT}\n\n{context}")
    result = agent(message)
    return str(result)


@app.post("/api/runs/{job_id}/chat")
async def chat_with_run(job_id: str, body: ChatRequest) -> JSONResponse:
    job = _get_job(job_id)
    status = job["status"]
    if status in ("running", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot chat about a job that is '{status}'.")

    context = _build_chat_context(job["output_dir"])
    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(_executor, _ask_chat_agent, context, body.message)

    with _lock:
        job["chat_history"].append({"role": "user", "content": body.message})
        job["chat_history"].append({"role": "assistant", "content": reply})

    return JSONResponse({"reply": reply})


@app.get("/api/runs/{job_id}/chat")
def get_chat_history(job_id: str) -> JSONResponse:
    job = _get_job(job_id)
    return JSONResponse({"messages": job["chat_history"]})


@app.get("/api/runs/{job_id}/events")
async def run_events(job_id: str):
    job = _get_job(job_id)
    events: queue.Queue = job["events"]

    async def event_stream():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, events.get)
            yield f"data: {json.dumps(item)}\n\n"
            if item.get("done"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _resolve_job_file(output_dir: Path, filename: str) -> Path | None:
    """Resolve `filename` inside `output_dir`, or return None if it's unsafe.

    Rejects any filename containing a path separator (`Path(filename).name
    != filename` catches e.g. "sub/dir.md") and, belt-and-suspenders, any
    filename that resolves outside `output_dir` even without one (e.g. the
    single segment ".."). Extracted as a standalone function so it can be
    unit-tested directly - a `..` path segment never survives standard URL
    normalization in a real HTTP client, so exercising this over the wire
    can't reliably prove the check exists.
    """
    if not filename or Path(filename).name != filename:
        return None
    output_dir_resolved = output_dir.resolve()
    candidate = (output_dir_resolved / filename).resolve()
    try:
        candidate.relative_to(output_dir_resolved)
    except ValueError:
        return None
    return candidate


@app.get("/api/runs/{job_id}/files/{filename}")
def get_run_file(job_id: str, filename: str) -> PlainTextResponse:
    job = _get_job(job_id)
    output_dir: Path = job["output_dir"]
    candidate = _resolve_job_file(output_dir, filename)
    if candidate is None:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    media_type = _MEDIA_TYPES.get(candidate.suffix, "application/octet-stream")
    return PlainTextResponse(candidate.read_bytes().decode("utf-8", errors="replace"), media_type=media_type)


_DIST_DIR = Path(__file__).parent.parent / "webapp" / "claimclarity" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
