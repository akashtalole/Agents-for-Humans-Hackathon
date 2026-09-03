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

from glacierwatch.config import model_status
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
            _jobs[job_id]["status"] = "completed"
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


class RunStatusResponse(BaseModel):
    job_id: str
    status: str
    error: str | None = None
    status_badge: StatusBadge | None = None
    sites: list[SiteOut] | None = None
    files: list[FileOut] | None = None
    summary_text: str | None = None


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
    }
    _executor.submit(_run_job, job_id, str(output_dir))
    return CreateRunResponse(job_id=job_id)


def _get_job(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return job


def _compute_status_badge(run) -> StatusBadge:
    """Mirrors app_glacierwatch.py's status-badge logic exactly."""
    if run.report is None:
        return StatusBadge(level="warning", message="Run did not complete.")
    priority_sites = [b for b in run.briefs if b.priority_level.value == "priority"]
    if priority_sites:
        return StatusBadge(
            level="error",
            message=f"{len(priority_sites)} site(s) at PRIORITY level this week — see below.",
        )
    return StatusBadge(level="success", message="No sites at priority level this week.")


@app.get("/api/runs/{job_id}", response_model=RunStatusResponse)
def get_run(job_id: str) -> RunStatusResponse:
    job = _get_job(job_id)
    status = job["status"]

    if status == "running":
        return RunStatusResponse(job_id=job_id, status=status)

    if status == "failed":
        return RunStatusResponse(job_id=job_id, status=status, error=job.get("error"))

    # completed
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
        status_badge=_compute_status_badge(run),
        sites=sites,
        files=files,
        summary_text=result.summary_text,
    )


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


# Mount the built frontend LAST, so /api/* routes above always take priority
# over the SPA catch-all. If the frontend hasn't been built (e.g. running
# `pytest` alone, with no `npm run build`), skip this - / should still work
# without crashing the API.
_dist_dir = Path("webapp/glacierwatch/dist")
if _dist_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist_dir), html=True), name="static")
