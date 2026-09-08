"""FastAPI web API for Trinetra.

Same discipline as bidwright/api.py, claimclarity/api.py, and
glacierwatch/api.py: a second front end onto the exact same direct-API
functions in trinetra/orchestrator.py the CLI uses - no pipeline logic
duplicated for deployment. The callback pattern for streaming Bhavishya
Netra's live simulation state follows bidwright/api.py's architectural
note exactly: the tick callback only pushes a plain dict onto a
thread-safe queue.Queue (no framework/session object involved at all),
and the SSE endpoint drains that queue from the asyncio event loop via
run_in_executor.

Trust hierarchy: the deterministic SimulationReport (and its rendered
Markdown) is the authoritative result of a simulation; the LLM advisor's
narrative is additive context, never a replacement for the numbers - the
frontend must not present the advisory's narrative_summary as more
authoritative than the report's own per-ghat figures.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from trinetra.agents.command_advisor import advise_on_crowd_signals
from trinetra.agents.foresight_advisor import advise_on_simulation
from trinetra.agents.hydrology_advisor import advise_on_compound_risk
from trinetra.agents.pilgrim_assistant import answer_pilgrim_query
from trinetra.agents.rumor_analyst import assess_rumor
from trinetra.agents.safety_triage import triage_sos_report
from trinetra.config import model_status
from trinetra.models import (
    CrowdSignal,
    DamRelease,
    IncidentType,
    IndianLanguage,
    MobilityProfile,
    NetworkMode,
    PilgrimQuery,
    RumorReport,
    SimulationScenario,
    SOSReport,
)
from trinetra.tools.calibration import run_all_calibration_cases
from trinetra.tools.crowd_signals import manual_signal
from trinetra.tools.geography import load_sites
from trinetra.tools.hydrology import assess_compound_risk
from trinetra.tools.rainfall import fetch_recent_rainfall_mm
from trinetra.tools.rumor_guardrail import scan_counter_message
from trinetra.tools.simulator import simulate_scenario

app = FastAPI(title="Trinetra API")

_executor = ThreadPoolExecutor(max_workers=6)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

_GHATS, _ROUTES = load_sites()

# Paces the SSE tick stream so a simulation animates visibly instead of
# arriving all at once - purely a presentation choice for the digital twin
# view, has zero effect on the simulation's actual (identical) result.
_TICK_ANIMATION_DELAY_SECONDS = 0.035


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    status_text = model_status()
    return {"status_text": status_text, "ready": not status_text.startswith("No credentials")}


@app.get("/api/sites")
def get_sites() -> dict[str, Any]:
    return {
        "ghats": [g.model_dump(mode="json") for g in _GHATS.values()],
        "routes": [r.model_dump(mode="json") for r in _ROUTES],
    }


# --- Yatri Netra: pilgrim assistant ----------------------------------------


@app.post("/api/pilgrim/ask")
async def pilgrim_ask(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required.")
    language = IndianLanguage(body.get("language", "hindi"))
    network_mode = NetworkMode(body.get("network_mode", "app_online"))
    query = PilgrimQuery(text=text, language=language, network_mode=network_mode)

    loop = asyncio.get_event_loop()
    guidance = await loop.run_in_executor(_executor, lambda: answer_pilgrim_query(query, _GHATS, _ROUTES))
    return guidance.model_dump(mode="json")


# --- Kumbh Rakshak: safety / SOS --------------------------------------------


@app.post("/api/sos")
async def report_sos(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    description = (body.get("description") or "").strip()
    location = (body.get("location") or "").strip()
    if not description or not location:
        raise HTTPException(status_code=400, detail="description and location are required.")

    report = SOSReport(
        incident_type=IncidentType(body.get("incident_type", "other")),
        reporter_description=description,
        location=location,
        involves_children_or_elderly=bool(body.get("involves_children_or_elderly", False)),
    )
    loop = asyncio.get_event_loop()
    triage = await loop.run_in_executor(_executor, lambda: triage_sos_report(report))
    return triage.model_dump(mode="json")


# --- Prashasan Netra: administration command --------------------------------


@app.post("/api/admin/brief")
async def admin_brief(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Accepts a list of {ghat_id, estimated_occupancy, inflow_rate_per_min,
    outflow_rate_per_min} readings - synthetic/manually-specified in this
    build, see trinetra/tools/crowd_signals.py's honest docstring."""
    raw_signals = body.get("signals", [])
    if not raw_signals:
        raise HTTPException(status_code=400, detail="At least one signal is required.")

    signals: list[CrowdSignal] = []
    for s in raw_signals:
        ghat = _GHATS.get(s["ghat_id"])
        if ghat is None:
            raise HTTPException(status_code=400, detail=f"Unknown ghat_id: {s['ghat_id']}")
        signals.append(
            manual_signal(
                ghat,
                estimated_occupancy=int(s["estimated_occupancy"]),
                inflow_rate_per_min=int(s.get("inflow_rate_per_min", 0)),
                outflow_rate_per_min=int(s.get("outflow_rate_per_min", 0)),
            )
        )

    loop = asyncio.get_event_loop()
    brief = await loop.run_in_executor(_executor, lambda: advise_on_crowd_signals(signals, _GHATS))
    return brief.model_dump(mode="json")


# --- Bhavishya Netra: crowd digital-twin simulator --------------------------


def _new_sim_job() -> dict[str, Any]:
    return {"status": "running", "error": None, "report": None, "advisory": None, "events": queue.Queue()}


def _run_simulation_job(job_id: str, scenario: SimulationScenario) -> None:
    entry = _jobs[job_id]
    events: queue.Queue = entry["events"]

    def on_tick(minute: int, snapshot: dict[str, dict[str, float]]) -> None:
        events.put({"type": "tick", "minute": minute, "ghats": snapshot})
        time.sleep(_TICK_ANIMATION_DELAY_SECONDS)

    try:
        report = simulate_scenario(scenario, _GHATS, _ROUTES, on_tick=on_tick)
        events.put({"type": "report", "report": report.model_dump(mode="json")})
        advisory = advise_on_simulation(report)
        with _lock:
            entry["status"] = "completed"
            entry["report"] = report
            entry["advisory"] = advisory
        events.put({"type": "advisory", "advisory": advisory.model_dump(mode="json")})
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as job status
        with _lock:
            entry["status"] = "failed"
            entry["error"] = str(exc)
        events.put({"type": "error", "message": str(exc)})
    finally:
        events.put({"type": "done"})


@app.post("/api/simulations")
def create_simulation(body: dict[str, Any] = Body(...)) -> dict[str, str]:
    try:
        scenario = SimulationScenario(
            name=body.get("name", "Ad-hoc scenario"),
            description=body.get("description", ""),
            total_pilgrims=int(body["total_pilgrims"]),
            duration_minutes=int(body["duration_minutes"]),
            peak_inflow_multiplier=float(body.get("peak_inflow_multiplier", 1.0)),
            active_ghat_ids=list(body["active_ghat_ids"]),
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid scenario: {exc}") from exc

    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = _new_sim_job()
    _executor.submit(_run_simulation_job, job_id, scenario)
    return {"job_id": job_id}


def _get_sim_job(job_id: str) -> dict[str, Any]:
    with _lock:
        entry = _jobs.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return entry


@app.get("/api/simulations/{job_id}")
def get_simulation(job_id: str) -> dict[str, Any]:
    entry = _get_sim_job(job_id)
    return {
        "status": entry["status"],
        "error": entry["error"],
        "report": entry["report"].model_dump(mode="json") if entry["report"] else None,
        "advisory": entry["advisory"].model_dump(mode="json") if entry["advisory"] else None,
    }


@app.get("/api/simulations/{job_id}/events")
async def simulation_events(job_id: str):
    entry = _get_sim_job(job_id)
    events: queue.Queue = entry["events"]

    async def event_stream():
        loop = asyncio.get_event_loop()
        while True:
            item = await loop.run_in_executor(None, events.get)
            yield f"data: {json.dumps(item)}\n\n"
            if item.get("type") == "done":
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Godavari compound flood risk -------------------------------------------


def _run_flood_assessment(discharge_cusecs: int, occupancy: dict[str, int], elderly_share: float, fetch_rainfall: bool):
    """Blocking work (a live rainfall fetch plus one model call) - always run
    via the executor, never directly on the asyncio event loop."""
    rainfall_mm: float | None = None
    rainfall_note = "Live rainfall lookup skipped for this assessment."
    if fetch_rainfall:
        rainfall_mm, rainfall_note = fetch_recent_rainfall_mm()

    elderly = max(0.0, min(1.0, elderly_share))
    mobility_mix = {
        MobilityProfile.ELDERLY_OR_MOBILITY_LIMITED: elderly,
        MobilityProfile.STANDARD: 1.0 - elderly,
    }
    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=discharge_cusecs),
        _GHATS,
        occupancy,
        mobility_mix=mobility_mix,
        recent_rainfall_mm=rainfall_mm,
        rainfall_note=rainfall_note,
    )
    advisory = advise_on_compound_risk(assessment)
    return assessment, advisory


@app.post("/api/flood-risk")
async def flood_risk(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Assess a Gangapur Dam release against current ghat occupancy - can
    each flood-exposed ghat be cleared before the water arrives?"""
    try:
        discharge = int(body["discharge_cusecs"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"discharge_cusecs is required and must be an integer: {exc}") from exc

    raw_occupancy = body.get("occupancy") or {}
    if not raw_occupancy:
        raise HTTPException(status_code=400, detail="occupancy is required, e.g. {\"ramkund\": 8000}")

    occupancy: dict[str, int] = {}
    for ghat_id, count in raw_occupancy.items():
        if ghat_id not in _GHATS:
            raise HTTPException(status_code=400, detail=f"Unknown ghat_id: {ghat_id}")
        occupancy[ghat_id] = int(count)

    elderly_share = float(body.get("elderly_share", 0.4))
    fetch_rainfall = bool(body.get("fetch_rainfall", True))

    loop = asyncio.get_event_loop()
    assessment, advisory = await loop.run_in_executor(
        _executor, lambda: _run_flood_assessment(discharge, occupancy, elderly_share, fetch_rainfall)
    )
    return {
        "assessment": assessment.model_dump(mode="json"),
        "advisory": advisory.model_dump(mode="json"),
    }


# --- Kumbh Rakshak rumor desk ------------------------------------------------


def _run_rumor_triage(report: RumorReport):
    assessment = assess_rumor(report)
    guardrail = scan_counter_message(assessment.counter_message)
    return assessment, guardrail


@app.post("/api/rumor")
async def rumor_triage(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    text = (body.get("text") or "").strip()
    location = (body.get("location") or "").strip()
    if not text or not location:
        raise HTTPException(status_code=400, detail="text and location are required.")

    report = RumorReport(
        text=text,
        location=location,
        reported_by=body.get("reported_by", "field staff"),
        spreading_fast=bool(body.get("spreading_fast", False)),
    )
    loop = asyncio.get_event_loop()
    assessment, guardrail = await loop.run_in_executor(_executor, lambda: _run_rumor_triage(report))
    return {
        "assessment": assessment.model_dump(mode="json"),
        "guardrail": guardrail.model_dump(mode="json"),
    }


# --- Bhavishya Netra: calibration against real historical incidents --------


@app.get("/api/calibration")
async def get_calibration() -> dict[str, Any]:
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(_executor, run_all_calibration_cases)
    return {"results": [r.model_dump(mode="json") for r in results]}


# Mounted LAST so /api/* routes always take priority over the SPA catch-all.
_DIST_DIR = Path(__file__).resolve().parent.parent / "webapp" / "trinetra" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
