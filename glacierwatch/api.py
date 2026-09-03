"""FastAPI backend for GlacierWatch's web UI.

Same trust hierarchy as app_glacierwatch.py (the Streamlit demo) and the
same architectural discipline as the rest of this repo: this module never
generates the "headline" output itself - it only runs the pipeline
(glacierwatch/pipeline.py:run_watchlist) and serves back the deterministic,
code-rendered files it writes (glacierwatch/rendering.py). The orchestrator's
own free-text summary_text is exposed too, but only ever as an explicitly
"(unverified)" field - the frontend is expected to label it the same way the
Streamlit demo does, never as the primary result.

Background jobs run on a plain ThreadPoolExecutor, and the only thing the
Strands callback_handler touches is a thread-safe queue.Queue - never a
framework request/session object. This sidesteps the exact class of bug
already found and fixed in app_glacierwatch.py (NoSessionContext: Strands
runs callback_handler on its own executor thread, and Streamlit's session
context is a thread-local attribute that thread never has). A plain
queue.Queue has no such thread affinity, so there is nothing here to fix.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from glacierwatch.config import create_agent, model_status
from glacierwatch.pipeline import run_watchlist
from glacierwatch.rendering import DISCLAIMER

app = FastAPI(title="GlacierWatch API")

# --- in-memory job store ---------------------------------------------------
#
# Deliberately in-memory, per-process - see the "Honest limitations" note in
# GLACIERWATCH.md's Web UI section and deploy/ecs-express/glacierwatch/README.md:
# this is why the ECS Express deployment is pinned to a single task
# (minTaskCount=1, maxTaskCount=1). A second concurrently-running task would
# not share job state with this one.

_executor = ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _run_job(job_id: str, output_dir: str) -> None:
    events: queue.Queue = _jobs[job_id]["events"]
    seen: list[str] = []

    def callback(**kwargs):
        tool_use = kwargs.get("current_tool_use") or {}
        name = tool_use.get("name")
        if name and (not seen or seen[-1] != name):
            seen.append(name)
            events.put({"tool": name})

    try:
        result = run_watchlist(output_dir=output_dir, callback_handler=callback)
        with _lock:
            # Community alert bulletins (community_alert_<site_id>.md) are the
            # only externally-facing artifact this pipeline produces - the rest
            # (watchlist_report.md, trend_report.md, inspection_schedule.md)
            # are internal, official-facing documents that don't need a human
            # approval gate. Most weeks have zero priority sites, so most runs
            # go straight to "completed" - see GLACIERWATCH.md's Web UI section.
            _jobs[job_id]["status"] = "awaiting_approval" if result.run.alerts else "completed"
            _jobs[job_id]["result"] = result
    except Exception as e:  # noqa: BLE001 - report any failure honestly to the client
        with _lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(e)
    finally:
        events.put({"done": True})


# --- response models ---------------------------------------------------

class StatusResponse(BaseModel):
    status_text: str
    ready: bool
    disclaimer: str


class CreateRunResponse(BaseModel):
    job_id: str


class SiteOut(BaseModel):
    id: str
    name: str
    status: str


class FileOut(BaseModel):
    name: str
    label: str


class StatusBadge(BaseModel):
    level: str
    message: str


class AlertForApprovalOut(BaseModel):
    site_id: str
    site_name: str
    text: str


class ReviewOut(BaseModel):
    approved: bool
    issues: list[str]


class GuardrailFindingOut(BaseModel):
    rule: str
    excerpt: str
    explanation: str


class GuardrailOut(BaseModel):
    passed: bool
    findings: list[GuardrailFindingOut]


class RunStatusResponse(BaseModel):
    job_id: str
    status: str
    error: str | None = None
    status_badge: StatusBadge | None = None
    sites: list[SiteOut] | None = None
    files: list[FileOut] | None = None
    summary_text: str | None = None
    # Meaningful only when this run drafted at least one community alert
    # bulletin (most runs have zero - see GLACIERWATCH.md) - the human
    # approval gate for that batch of alerts. None when there's nothing to
    # approve, including for runs still "running".
    alerts_for_approval: list[AlertForApprovalOut] | None = None
    reviews: dict[str, ReviewOut] | None = None
    guardrails: dict[str, GuardrailOut] | None = None
    reject_reason: str | None = None


class ApproveBody(BaseModel):
    edited_alerts: dict[str, str] | None = None


class RejectBody(BaseModel):
    reason: str | None = None


class ChatBody(BaseModel):
    message: str


class ChatReply(BaseModel):
    reply: str


class ChatMessageOut(BaseModel):
    role: str
    content: str


class ChatHistoryResponse(BaseModel):
    messages: list[ChatMessageOut]


# --- routes ---------------------------------------------------------------

@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    status_text = model_status()
    return StatusResponse(
        status_text=status_text,
        ready=not status_text.startswith("No credentials"),
        disclaimer=DISCLAIMER,
    )


@app.post("/api/runs", response_model=CreateRunResponse)
def create_run() -> CreateRunResponse:
    job_id = str(uuid.uuid4())
    output_dir = Path.cwd() / ".glacierwatch_runs" / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    _jobs[job_id] = {
        "status": "running",
        "output_dir": str(output_dir),
        "events": queue.Queue(),
        "result": None,
        "error": None,
        "reject_reason": None,
        "chat_history": [],
    }
    _executor.submit(_run_job, job_id, str(output_dir))
    return CreateRunResponse(job_id=job_id)


def _get_job(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job


def _compute_status_badge(run, status: str, reject_reason: str | None = None) -> StatusBadge:
    """Mirrors app_glacierwatch.py's status-badge logic, extended with the
    two new post-run statuses the web UI's approval gate introduces."""
    if status == "awaiting_approval":
        return StatusBadge(
            level="warning",
            message=f"{len(run.alerts)} community alert(s) awaiting your approval before they can be sent.",
        )
    if status == "rejected":
        return StatusBadge(level="error", message="Rejected — alerts not approved for distribution.")
    if run.report is None:
        return StatusBadge(level="warning", message="Run did not complete.")
    priority_sites = [b for b in run.briefs if b.priority_level.value == "priority"]
    if priority_sites:
        return StatusBadge(
            level="error",
            message=f"{len(priority_sites)} site(s) at PRIORITY level this week — see below.",
        )
    return StatusBadge(level="success", message="No sites at priority level this week.")


def _alerts_payload(job: dict[str, Any]) -> dict[str, Any]:
    """The approval-gate fields for a run that has finished (whether
    awaiting_approval, completed, or rejected) - meaningful only when this
    run drafted at least one community alert bulletin. Alert text is always
    read fresh from disk, so it reflects any edit an approve call already
    applied."""
    result = job["result"]
    run = result.run
    output_dir = Path(job["output_dir"])

    if not run.alerts:
        return {"alerts_for_approval": None, "reviews": None, "guardrails": None, "reject_reason": None}

    alerts_for_approval = []
    for alert in run.alerts:
        alert_path = output_dir / f"community_alert_{alert.site_id}.md"
        text = alert_path.read_text() if alert_path.exists() else ""
        alerts_for_approval.append(AlertForApprovalOut(site_id=alert.site_id, site_name=alert.site_name, text=text))

    reviews = {
        site_id: ReviewOut(approved=r.approved, issues=r.issues) for site_id, r in run.reviews.items()
    } or None
    guardrails = {
        site_id: GuardrailOut(
            passed=g.passed,
            findings=[
                GuardrailFindingOut(rule=f.rule, excerpt=f.excerpt, explanation=f.explanation) for f in g.findings
            ],
        )
        for site_id, g in run.guardrails.items()
    } or None

    return {
        "alerts_for_approval": alerts_for_approval,
        "reviews": reviews,
        "guardrails": guardrails,
        "reject_reason": job.get("reject_reason"),
    }


def _build_run_status_response(job_id: str, job: dict[str, Any]) -> RunStatusResponse:
    status = job["status"]

    if status == "running":
        return RunStatusResponse(job_id=job_id, status=status)

    if status == "failed":
        return RunStatusResponse(job_id=job_id, status=status, error=job.get("error"))

    # awaiting_approval, completed, or rejected - a run that finished.
    result = job["result"]
    run = result.run
    output_dir = Path(job["output_dir"])

    sites = [SiteOut(id=s.id, name=s.name, status=s.status) for s in run.sites]

    files = []
    for name, label in [("watchlist_report.md", "Weekly Watchlist")]:
        if (output_dir / name).exists():
            files.append(FileOut(name=name, label=label))

    return RunStatusResponse(
        job_id=job_id,
        status=status,
        status_badge=_compute_status_badge(run, status),
        sites=sites,
        files=files,
        summary_text=result.summary_text,
        **_alerts_payload(job),
    )


@app.get("/api/runs/{job_id}", response_model=RunStatusResponse)
def get_run(job_id: str) -> RunStatusResponse:
    job = _get_job(job_id)
    return _build_run_status_response(job_id, job)


@app.post("/api/runs/{job_id}/approve", response_model=RunStatusResponse)
def approve_run(job_id: str, body: ApproveBody) -> RunStatusResponse:
    """Approve this run's whole batch of community alert bulletins at once -
    there is no per-site approval, since a run's alerts are reviewed and
    guarded together (see review_community_alerts/check_alerts_guardrail in
    glacierwatch/orchestrator.py). `edited_alerts` overwrites only the sites
    named in it with the given text; any alert not mentioned keeps its
    current drafted text unchanged."""
    job = _get_job(job_id)
    with _lock:
        if job["status"] != "awaiting_approval":
            raise HTTPException(status_code=400, detail=f"Job is not awaiting approval (status: {job['status']}).")

        run = job["result"].run
        known_site_ids = {a.site_id for a in run.alerts}
        output_dir = Path(job["output_dir"])
        edited = body.edited_alerts or {}
        unknown = set(edited) - known_site_ids
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown site_id(s) in edited_alerts: {sorted(unknown)}")

        for site_id, text in edited.items():
            (output_dir / f"community_alert_{site_id}.md").write_text(text)

        job["status"] = "completed"

    return _build_run_status_response(job_id, job)


@app.post("/api/runs/{job_id}/reject", response_model=RunStatusResponse)
def reject_run(job_id: str, body: RejectBody) -> RunStatusResponse:
    """Reject this run's whole batch of community alert bulletins at once -
    same batch-not-per-site discipline as approve. The underlying
    community_alert_<site_id>.md files are left untouched on disk (an
    official can still inspect what was rejected and why); only the job's
    status changes, so nothing here is ever served as approved."""
    job = _get_job(job_id)
    with _lock:
        if job["status"] != "awaiting_approval":
            raise HTTPException(status_code=400, detail=f"Job is not awaiting approval (status: {job['status']}).")
        job["status"] = "rejected"
        job["reject_reason"] = body.reason

    return _build_run_status_response(job_id, job)


@app.get("/api/runs/{job_id}/events")
async def stream_events(job_id: str):
    job = _get_job(job_id)
    events: queue.Queue = job["events"]

    async def event_generator():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, events.get)
            yield f"data: {json.dumps(item)}\n\n"
            if item.get("done"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/runs/{job_id}/files/{filename}")
def get_file(job_id: str, filename: str) -> PlainTextResponse:
    job = _get_job(job_id)

    if Path(filename).name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    output_dir = Path(job["output_dir"]).resolve()
    file_path = (output_dir / filename).resolve()
    try:
        file_path.relative_to(output_dir)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return PlainTextResponse(file_path.read_text(), media_type="text/markdown")


# --- conversational follow-up (grounded chat) ------------------------------
#
# A small, fresh Strands Agent per turn - no tools, no structured output,
# grounded ONLY in this run's own generated .md files (never the model's
# training data or general knowledge). Same non-prediction discipline as
# every other agent in this project: even a direct "will it flood?" question
# gets redirected, never answered as a forecast.

_CHAT_CONTEXT_CHAR_CAP = 40_000

# Per-site alert/review/guardrail files are the first thing dropped if the
# concatenated context is over the cap - they're the most numerous (one set
# per priority site) and the least essential for answering a general
# question about the week's watchlist. watchlist_report.md and
# trend_report.md are the last things dropped, since they're the actual
# headline output this chat should stay grounded in.
_CHAT_DROPPABLE_PREFIXES = ("community_alert_", "alerts_review", "alerts_guardrail")

CHAT_SYSTEM_PROMPT_TEMPLATE = """\
You answer questions about this specific GlacierWatch weekly watchlist run \
using ONLY the documents provided below. You are NOT a prediction system \
and must never speculate about if/when/where a hazard will occur, even if \
asked directly - if asked something like that, explain plainly that this \
tool doesn't and can't answer that, and redirect to what the documented \
risk level and monitoring recommendation actually say. If the answer isn't \
in the documents below, say so honestly instead of guessing.

DOCUMENTS FROM THIS RUN:
{documents}
"""


def _build_chat_context(output_dir: Path, cap: int = _CHAT_CONTEXT_CHAR_CAP) -> str:
    """Concatenate every .md file this run wrote, capped at ~`cap`
    characters. Drops the most numerous, least-essential per-site
    alert/review/guardrail files first if over the cap; watchlist_report.md
    and trend_report.md are dropped last (only if the run somehow still
    doesn't fit)."""
    files = sorted(output_dir.glob("*.md"))
    contents = {f.name: f.read_text() for f in files}
    names = list(contents.keys())

    def _rendered_length(names: list[str]) -> int:
        return sum(len(contents[n]) + len(n) + 10 for n in names)

    while _rendered_length(names) > cap:
        droppable = [n for n in names if n.startswith(_CHAT_DROPPABLE_PREFIXES)]
        if not droppable:
            break
        names.remove(droppable[0])

    text = "\n\n---\n\n".join(f"## {n}\n\n{contents[n]}" for n in names)
    if len(text) > cap:
        text = text[:cap] + "\n\n...[truncated - this run's documents exceeded the context limit]"
    return text


def _run_chat_turn(output_dir: str, message: str) -> str:
    documents = _build_chat_context(Path(output_dir))
    system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(documents=documents)
    agent = create_agent(system_prompt=system_prompt)
    result = agent(message)
    return str(result)


@app.post("/api/runs/{job_id}/chat", response_model=ChatReply)
async def post_chat(job_id: str, body: ChatBody) -> ChatReply:
    job = _get_job(job_id)
    if job["status"] in ("running", "failed"):
        raise HTTPException(
            status_code=400, detail=f"Cannot chat about a run that is {job['status']} - no documents to ground on yet."
        )

    loop = asyncio.get_event_loop()
    reply = await loop.run_in_executor(_executor, _run_chat_turn, job["output_dir"], body.message)

    with _lock:
        job["chat_history"].append({"role": "user", "content": body.message})
        job["chat_history"].append({"role": "assistant", "content": reply})

    return ChatReply(reply=reply)


@app.get("/api/runs/{job_id}/chat", response_model=ChatHistoryResponse)
def get_chat(job_id: str) -> ChatHistoryResponse:
    job = _get_job(job_id)
    return ChatHistoryResponse(messages=[ChatMessageOut(**m) for m in job.get("chat_history", [])])


# Mount the built frontend LAST, so /api/* routes above always take priority
# over the SPA catch-all. If the frontend hasn't been built (e.g. running
# `pytest` alone, with no `npm run build`), skip this - / should still work
# without crashing the API.
_dist_dir = Path("webapp/glacierwatch/dist")
if _dist_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist_dir), html=True), name="static")
