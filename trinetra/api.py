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
import hmac
import json
import logging
import os
import queue
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Body, FastAPI, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from trinetra.agents.command_advisor import advise_on_crowd_signals
from trinetra.agents.foresight_advisor import advise_on_simulation
from trinetra.agents.hydrology_advisor import advise_on_compound_risk
from trinetra.agents.incident_commander import command_the_incident
from trinetra.agents.live_monitor import monitor_ghat
from trinetra.tools.live_signals import ghat_id_from_thingsboard_asset_name, write_back_monitoring_result
from trinetra.agents.pilgrim_assistant import answer_pilgrim_query
from trinetra.agents.red_team import critique_plan
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
from trinetra.tools.conflicts import scan_for_conflicts
from trinetra.tools.crowd_signals import manual_signal
from trinetra.tools.geography import load_sites
from trinetra.tools.hydrology import assess_compound_risk
from trinetra.tools.rainfall import fetch_recent_rainfall_mm
from trinetra.tools.resources import (
    allocate,
    default_resource_pool,
    demands_from_command_brief,
    demands_from_flood,
    demands_from_rumor,
    demands_from_sos,
)
from trinetra.tools.rumor_guardrail import scan_counter_message
from trinetra.tools.simulator import simulate_scenario

app = FastAPI(title="Trinetra API")

_executor = ThreadPoolExecutor(max_workers=6)
_logger = logging.getLogger("trinetra.webhooks")
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


# --- Kshetra Netra: live monitoring (real tool-calling agent) --------------


@app.post("/api/monitor")
async def monitor(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Unlike every other endpoint above, this one calls an agent that
    decides for itself which tools to run (live ThingsBoard telemetry, a
    lookahead simulation, a calibration check) - see
    agents/live_monitor.py's module docstring. It costs a model call and can
    take noticeably longer than the deterministic endpoints above."""
    ghat_id = (body.get("ghat_id") or "").strip()
    if not ghat_id:
        raise HTTPException(status_code=400, detail="ghat_id is required.")
    if ghat_id not in _GHATS:
        raise HTTPException(status_code=404, detail=f"Unknown ghat_id '{ghat_id}'.")
    question = body.get("question")
    loop = asyncio.get_event_loop()
    brief = await loop.run_in_executor(_executor, lambda: monitor_ghat(ghat_id, question=question))
    return {"brief": brief.model_dump(mode="json")}


def _run_alarm_triggered_monitoring(ghat_id: str, alarm_type: str, severity: str) -> None:
    """Runs in the background, after the webhook has already responded 202.
    Exceptions here are logged, never raised into nothing - a background
    task with an uncaught exception fails silently and invisibly otherwise,
    which is exactly the failure mode a safety-relevant integration cannot
    have."""
    try:
        brief = monitor_ghat(
            ghat_id,
            question=(
                f"A ThingsBoard alarm just fired here: '{alarm_type}' (severity {severity}). "
                "Check what's actually happening and whether it's still current."
            ),
        )
        _logger.info(
            "alarm-triggered monitoring for %s (%s/%s): overall_status=%s",
            ghat_id, alarm_type, severity, brief.overall_status.value,
        )
        write_back_monitoring_result(ghat_id, brief)
    except Exception:
        _logger.exception("alarm-triggered monitoring failed for ghat_id=%s alarm_type=%s", ghat_id, alarm_type)


@app.post("/api/webhooks/thingsboard-alarm")
async def thingsboard_alarm_webhook(
    response: Response,
    background_tasks: BackgroundTasks,
    body: dict[str, Any] = Body(...),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    """Inbound trigger: a ThingsBoard alarm rule (already configured on
    KumbhDigiTwin's tenant, e.g. CrowdDensityCritical, RiverLevelDanger,
    PanicActivated) calls this instead of Trinetra polling for one. See
    TRINETRA.md's Kshetra Netra section for the ThingsBoard-side rule-chain
    configuration this expects, and for why this points at Trinetra's own
    ECS-hosted backend rather than Bedrock AgentCore directly - AgentCore's
    InvokeAgentRuntime needs an AWS-SigV4-signed request, which a
    ThingsBoard REST Call node cannot produce on its own.

    Auth is a shared secret in the X-Webhook-Secret header, deliberately not
    in the JSON body - a body is more likely to end up in a log line
    somewhere between ThingsBoard and here than a header most middleboxes
    treat as opaque.

    Expected body: {"originator_name": "<ThingsBoard entity name>",
    "alarm_type": "...", "severity": "..."}. Responds immediately (202) and
    runs the actual monitoring in the background - a control-room alarm rule
    must not block on a ~10-30s model call.
    """
    secret = os.environ.get("TRINETRA_WEBHOOK_SECRET")
    if not secret:
        # Fail closed: an unconfigured secret means this endpoint accepts
        # nothing, not everything. Same posture as ThingsBoard itself being
        # "not configured" elsewhere in this repo.
        raise HTTPException(status_code=503, detail="Webhook is not configured (TRINETRA_WEBHOOK_SECRET unset).")
    if not x_webhook_secret or not hmac.compare_digest(x_webhook_secret, secret):
        raise HTTPException(status_code=401, detail="Missing or incorrect X-Webhook-Secret header.")

    originator_name = (body.get("originator_name") or "").strip()
    alarm_type = (body.get("alarm_type") or "unknown").strip()
    severity = (body.get("severity") or "unknown").strip()
    if not originator_name:
        raise HTTPException(status_code=400, detail="originator_name is required.")

    ghat_id = ghat_id_from_thingsboard_asset_name(originator_name)
    if ghat_id is None:
        # Not an error: KumbhDigiTwin raises alarms on many entity types
        # (SanitationBlock, ParkingZone, ...) Trinetra has no ghat for.
        return {"accepted": False, "reason": f"'{originator_name}' has no mapped Trinetra ghat - ignored."}

    background_tasks.add_task(_run_alarm_triggered_monitoring, ghat_id, alarm_type, severity)
    response.status_code = 202
    return {"accepted": True, "ghat_id": ghat_id, "note": "Monitoring in background; result will be written back to ThingsBoard."}


# --- Sankat Nirnay: multi-hazard incident command ----------------------------


def _run_incident_command(
    signals: list[CrowdSignal],
    discharge: int | None,
    flood_occupancy: dict[str, int],
    elderly_share: float,
    sos_reports: list[SOSReport],
    rumor: RumorReport | None,
    run_red_team: bool,
):
    """Every desk runs independently, then the two deterministic passes
    (allocate, then scan for conflicts) run over their combined output before
    the commander agent is asked to judge anything."""
    demands = []
    brief = None
    flood = None
    triages: list[SafetyTriage] = []
    rumor_assessment = None

    if signals:
        brief = advise_on_crowd_signals(signals, _GHATS)
        demands += demands_from_command_brief(brief)

    if discharge is not None and flood_occupancy:
        flood, flood_advisory = _run_flood_assessment(discharge, flood_occupancy, elderly_share, True)
        demands += demands_from_flood(flood, flood_advisory)

    if sos_reports:
        paired = [(r, triage_sos_report(r)) for r in sos_reports]
        triages = [t for _, t in paired]
        demands += demands_from_sos(paired)

    if rumor is not None:
        rumor_assessment = assess_rumor(rumor)
        demands += demands_from_rumor(rumor_assessment, rumor.location)

    allocation = allocate(default_resource_pool(), demands)
    conflicts = scan_for_conflicts(
        _GHATS, _ROUTES, flood=flood, brief=brief, signals=signals, allocation=allocation
    )
    plan = command_the_incident(
        allocation=allocation, conflicts=conflicts, flood=flood, brief=brief,
        triages=triages, rumor=rumor_assessment,
    )
    critique = critique_plan(plan, allocation, conflicts) if run_red_team else None
    return plan, allocation, conflicts, critique


@app.post("/api/command")
async def incident_command(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Reconcile every live hazard against a finite responder pool.

    Unlike the single-hazard endpoints, this one assumes the desks are
    competing: it is the only place that can report that two individually
    correct recommendations cannot both be executed.
    """
    raw_occupancy = body.get("occupancy") or {}
    occupancy: dict[str, int] = {}
    for ghat_id, count in raw_occupancy.items():
        if ghat_id not in _GHATS:
            raise HTTPException(status_code=400, detail=f"Unknown ghat_id: {ghat_id}")
        occupancy[ghat_id] = int(count)

    discharge = body.get("discharge_cusecs")
    discharge = int(discharge) if discharge is not None else None

    raw_sos = body.get("sos") or []
    sos_reports = []
    for entry in raw_sos:
        description = (entry.get("description") or "").strip()
        location = (entry.get("location") or "").strip()
        if not description or not location:
            raise HTTPException(status_code=400, detail="Each sos entry needs a description and a location")
        sos_reports.append(SOSReport(
            incident_type=IncidentType.OTHER, reporter_description=description, location=location,
            involves_children_or_elderly=bool(entry.get("involves_children_or_elderly", False)),
        ))

    rumor = None
    raw_rumor = body.get("rumor")
    if raw_rumor:
        text = (raw_rumor.get("text") or "").strip()
        location = (raw_rumor.get("location") or "").strip()
        if not text or not location:
            raise HTTPException(status_code=400, detail="A rumor needs both text and a location")
        rumor = RumorReport(text=text, location=location,
                            spreading_fast=bool(raw_rumor.get("spreading_fast", False)))

    if not occupancy and discharge is None and not sos_reports and rumor is None:
        raise HTTPException(
            status_code=400,
            detail="Nothing to command: provide at least one of occupancy, discharge_cusecs, sos, or rumor",
        )

    signals = [manual_signal(_GHATS[gid], count, 0, 0) for gid, count in occupancy.items()]
    elderly_share = float(body.get("elderly_share", 0.4))
    run_red_team = bool(body.get("run_red_team", True))

    loop = asyncio.get_event_loop()
    plan, allocation, conflicts, critique = await loop.run_in_executor(
        _executor,
        lambda: _run_incident_command(
            signals, discharge, occupancy, elderly_share, sos_reports, rumor, run_red_team
        ),
    )
    return {
        "plan": plan.model_dump(mode="json"),
        "allocation": allocation.model_dump(mode="json"),
        "conflicts": conflicts.model_dump(mode="json"),
        "critique": critique.model_dump(mode="json") if critique else None,
    }


# --- A2A: third-party agent interoperability ---------------------------------


@app.get("/api/a2a/peers")
async def a2a_peers() -> dict[str, Any]:
    """The allowlist of third-party agents Trinetra may call."""
    from trinetra.a2a.registry import load_peers

    return {"peers": [p.model_dump(mode="json") for p in load_peers().values()]}


@app.post("/api/a2a/consult")
async def a2a_consult(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Ask registered peers a question.

    Note what this endpoint does NOT accept: a URL. Peers are addressed by
    their registered id only, so no caller can talk Trinetra into calling an
    arbitrary agent by passing one in.
    """
    from trinetra.a2a.client import consult_peers
    from trinetra.a2a.registry import is_allowed, peers_for_capability

    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    peer_ids = body.get("peer_ids")
    if peer_ids is not None:
        unknown = [pid for pid in peer_ids if not is_allowed(pid)]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Not registered A2A peers: {', '.join(unknown)}. See GET /api/a2a/peers.",
            )

    capability = (body.get("capability") or "").strip()
    if capability:
        matched = [p.peer_id for p in peers_for_capability(capability)]
        if not matched:
            raise HTTPException(
                status_code=400, detail=f"No registered peer declares a capability matching '{capability}'"
            )
        peer_ids = matched

    timeout = float(body.get("timeout", 20.0))
    loop = asyncio.get_event_loop()
    consultation = await loop.run_in_executor(
        _executor, lambda: consult_peers(question, peer_ids=peer_ids, timeout=timeout)
    )
    return consultation.model_dump(mode="json")


# Mounted LAST so /api/* routes always take priority over the SPA catch-all.
_DIST_DIR = Path(__file__).resolve().parent.parent / "webapp" / "trinetra" / "dist"
if _DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DIST_DIR), html=True), name="static")
