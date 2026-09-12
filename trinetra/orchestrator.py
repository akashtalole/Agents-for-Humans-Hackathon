"""The Trinetra orchestrator: one conversational entry point in front of
all three pillars (Yatri Netra / pilgrim, Prashasan Netra / administration,
Bhavishya Netra / foresight simulator).

Unlike bidwright/claimclarity/glacierwatch's orchestrators, which each run
one linear "read documents -> produce one report" pipeline, Trinetra is a
multi-service platform - a pilgrim's question, an SOS report, an NTKMA
operator's crowd-signal check, and a "simulate Mauni Amavasya day" request
are four genuinely different requests that don't belong in one pipeline.
So this orchestrator follows the same "agents as tools" shape as the other
three projects, but each tool is a complete service in its own right, and
the top-level agent's only job is figuring out which one a free-text
request actually needs - never answering the substance itself. Every tool
still returns/writes the same validated, deterministically-rendered
output the direct API (orchestrator.py's own module-level functions, used
by the CLI/tests without going through the top-level agent at all) would
produce - the top-level agent is a convenience router, not a second
source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from strands import Agent, tool

from trinetra.agents.command_advisor import advise_on_crowd_signals
from trinetra.agents.foresight_advisor import advise_on_simulation
from trinetra.agents.hydrology_advisor import advise_on_compound_risk
from trinetra.agents.incident_commander import command_the_incident
from trinetra.agents.live_monitor import monitor_ghat
from trinetra.agents.pilgrim_assistant import answer_pilgrim_query
from trinetra.agents.red_team import critique_plan
from trinetra.agents.rumor_analyst import assess_rumor
from trinetra.agents.safety_triage import triage_sos_report
from trinetra.config import create_agent
from trinetra.models import (
    AllocationPlan,
    CommandBrief,
    CompoundRiskAssessment,
    ConflictScanResult,
    CrowdSignal,
    DamRelease,
    Ghat,
    HydrologyAdvisory,
    IncidentCommandPlan,
    IndianLanguage,
    MobilityProfile,
    MonitoringBrief,
    NetworkMode,
    NTKMAAdvisory,
    PilgrimGuidance,
    PilgrimQuery,
    PlanCritique,
    Route,
    RumorAssessment,
    RumorGuardrailResult,
    RumorReport,
    SafetyTriage,
    SimulationReport,
    SimulationScenario,
    SOSReport,
)
from trinetra.tools.calibration import run_all_calibration_cases
from trinetra.tools.calibration import CalibrationResult
from trinetra.tools.conflicts import scan_for_conflicts
from trinetra.tools.crowd_signals import signals_from_simulation
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


@dataclass
class TrinetraSession:
    """Shared, loaded-once state for one orchestrator session - the
    bundled site geography, plus whatever the session has produced so far
    (kept so a CLI/API layer can inspect what happened without re-deriving
    it from the top-level agent's free-text reply)."""

    ghats: dict[str, Ghat] = field(default_factory=dict)
    routes: list[Route] = field(default_factory=list)
    last_guidance: PilgrimGuidance | None = None
    last_triage: SafetyTriage | None = None
    last_command_brief: CommandBrief | None = None
    last_simulation: SimulationReport | None = None
    last_advisory: NTKMAAdvisory | None = None
    last_compound_risk: CompoundRiskAssessment | None = None
    last_hydrology_advisory: HydrologyAdvisory | None = None
    last_rumor_assessment: RumorAssessment | None = None
    last_rumor_guardrail: RumorGuardrailResult | None = None
    last_allocation: AllocationPlan | None = None
    last_conflicts: ConflictScanResult | None = None
    last_command_plan: IncidentCommandPlan | None = None
    last_critique: PlanCritique | None = None
    last_monitoring_brief: MonitoringBrief | None = None

    def __post_init__(self) -> None:
        if not self.ghats:
            self.ghats, self.routes = load_sites()


# --- direct API: no top-level agent involved, used by CLI/tests/API layer ---


def ask_pilgrim(session: TrinetraSession, text: str, language: IndianLanguage = IndianLanguage.HINDI,
                 network_mode: NetworkMode = NetworkMode.APP_ONLINE) -> PilgrimGuidance:
    query = PilgrimQuery(text=text, language=language, network_mode=network_mode)
    guidance = answer_pilgrim_query(query, session.ghats, session.routes)
    session.last_guidance = guidance
    return guidance


def report_sos(session: TrinetraSession, report: SOSReport) -> SafetyTriage:
    triage = triage_sos_report(report)
    session.last_triage = triage
    return triage


def get_command_brief(session: TrinetraSession, signals: list[CrowdSignal]) -> CommandBrief:
    brief = advise_on_crowd_signals(signals, session.ghats)
    session.last_command_brief = brief
    return brief


def run_simulation(session: TrinetraSession, scenario: SimulationScenario) -> tuple[SimulationReport, NTKMAAdvisory]:
    report = simulate_scenario(scenario, session.ghats, session.routes)
    advisory = advise_on_simulation(report)
    session.last_simulation = report
    session.last_advisory = advisory
    return report, advisory


def run_calibration(session: TrinetraSession) -> list[CalibrationResult]:
    return run_all_calibration_cases()


def monitor_live(session: TrinetraSession, ghat_id: str, question: str | None = None) -> MonitoringBrief:
    """Runs Kshetra Netra's live-monitoring pass for one ghat. Unlike every
    other function in this module, this one agent decides for itself which
    tools to call (live ThingsBoard signals, a lookahead simulation, a
    calibration sanity check) rather than being handed pre-assembled data -
    see agents/live_monitor.py's module docstring."""
    brief = monitor_ghat(ghat_id, question=question)
    session.last_monitoring_brief = brief
    return brief


def assess_flood_risk(
    session: TrinetraSession,
    discharge_cusecs: int,
    occupancy_by_ghat: dict[str, int],
    mobility_mix: dict[MobilityProfile, float] | None = None,
    fetch_rainfall: bool = True,
) -> tuple[CompoundRiskAssessment, HydrologyAdvisory]:
    """Godavari compound risk: a Gangapur Dam release against who is
    currently standing on the flood-exposed ghats. The assessment is pure
    deterministic code; only the advisory comes from a model."""
    rainfall_mm: float | None = None
    rainfall_note = "Live rainfall lookup skipped for this assessment."
    if fetch_rainfall:
        rainfall_mm, rainfall_note = fetch_recent_rainfall_mm()

    assessment = assess_compound_risk(
        DamRelease(discharge_cusecs=discharge_cusecs),
        session.ghats,
        occupancy_by_ghat,
        mobility_mix=mobility_mix,
        recent_rainfall_mm=rainfall_mm,
        rainfall_note=rainfall_note,
    )
    advisory = advise_on_compound_risk(assessment)
    session.last_compound_risk = assessment
    session.last_hydrology_advisory = advisory
    return assessment, advisory


def triage_rumor(session: TrinetraSession, report: RumorReport) -> tuple[RumorAssessment, RumorGuardrailResult]:
    """Assess a rumor's crush potential and draft a counter-message, then
    scan that draft deterministically before any human sees it as
    broadcast-ready - see tools/rumor_guardrail.py for why the scan is not
    optional."""
    assessment = assess_rumor(report)
    guardrail = scan_counter_message(assessment.counter_message)
    session.last_rumor_assessment = assessment
    session.last_rumor_guardrail = guardrail
    return assessment, guardrail




def command_incident(
    session: TrinetraSession,
    signals: list[CrowdSignal] | None = None,
    flood_discharge_cusecs: int | None = None,
    flood_occupancy: dict[str, int] | None = None,
    sos_reports: list[SOSReport] | None = None,
    rumor: RumorReport | None = None,
    mobility_mix: dict[MobilityProfile, float] | None = None,
    fetch_rainfall: bool = True,
    run_red_team: bool = True,
) -> tuple[IncidentCommandPlan, AllocationPlan, ConflictScanResult, PlanCritique | None]:
    """Sankat Nirnay: run every live hazard through its own desk, then
    reconcile them against a finite responder pool.

    The order here is the architecture. Each desk runs independently and
    without knowledge of the others - that independence is deliberate, and it
    is why the flood desk's numbers cannot be argued down by a crowd-pressure
    case. The cost of that independence is that no desk can see whether the
    union of their advice is executable, so the two deterministic passes
    (allocate, then scan for conflicts) run over their combined output before
    any model is asked to command anything.
    """
    demands = []
    brief = None
    flood = None
    triages: list[SafetyTriage] = []
    rumor_assessment = None

    if signals:
        brief = get_command_brief(session, signals)
        demands += demands_from_command_brief(brief)

    if flood_discharge_cusecs is not None and flood_occupancy:
        flood, _ = assess_flood_risk(
            session,
            flood_discharge_cusecs,
            flood_occupancy,
            mobility_mix=mobility_mix,
            fetch_rainfall=fetch_rainfall,
        )
        demands += demands_from_flood(flood, session.last_hydrology_advisory)

    if sos_reports:
        paired = [(r, report_sos(session, r)) for r in sos_reports]
        triages = [t for _, t in paired]
        demands += demands_from_sos(paired)

    if rumor is not None:
        rumor_assessment, _ = triage_rumor(session, rumor)
        demands += demands_from_rumor(rumor_assessment, rumor.location)

    allocation = allocate(default_resource_pool(), demands)
    conflicts = scan_for_conflicts(
        session.ghats,
        session.routes,
        flood=flood,
        brief=brief,
        signals=signals,
        allocation=allocation,
    )

    plan = command_the_incident(
        allocation=allocation,
        conflicts=conflicts,
        flood=flood,
        brief=brief,
        triages=triages,
        rumor=rumor_assessment,
    )
    critique = critique_plan(plan, allocation, conflicts) if run_red_team else None

    session.last_allocation = allocation
    session.last_conflicts = conflicts
    session.last_command_plan = plan
    session.last_critique = critique
    return plan, allocation, conflicts, critique

# --- top-level conversational router (agents as tools) ---

ROUTER_PROMPT = """\
You are the Trinetra router - the single conversational entry point for the \
Nashik-Trimbakeshwar Kumbh Mela 2027 platform. You never answer a pilgrim \
question, safety report, admin request, or simulation request yourself - \
you ALWAYS call exactly one of your tools, which does the actual work with \
its own specialized agent. Your only job is picking the right tool:

- pilgrim_help: a pilgrim asking about routes, ghats, crowd status, or any \
Kumbh-logistics question.
- report_emergency: anything describing a lost person, medical emergency, \
crowd-crush danger, lost item, or harassment - even if phrased as a question.
- simulate_scenario: a request to model/simulate/stress-test a crowd \
scenario (e.g. "what happens on Mauni Amavasya", "simulate a surge at \
Ramkund").
- run_calibration_check: a request to validate the simulator against real \
historical incidents.
- flood_risk_check: anything about the Godavari rising, Gangapur Dam \
discharge/release, or whether a ghat can be cleared before water arrives.
- rumor_check: a report that something is being SAID or spread among the \
crowd - a rumour of a stampede, a closure, a collapse - as distinct from a \
report that it actually happened (that is report_emergency).
- command_incident_tool: use this when SEVERAL hazards are live at once, or \
when the request is about priorities, competing demands, or who to send \
where first. It is the only tool that reconciles the other desks against a \
finite number of responder units; the single-hazard tools above each assume \
they can have whatever they ask for.
- live_monitor_tool: a request to check the CURRENT/live situation at a \
specific ghat right now (e.g. "what's happening at Ramkund", "is it getting \
crowded", "check live sensors") - as distinct from simulate_scenario, which \
models a hypothetical scenario rather than checking live telemetry. This \
tool has its own sub-agent that decides which live signals to check.

After calling the right tool, give a brief final reply pointing to the \
generated report/response - never restate its specifics from memory, since \
the tool's structured output is the source of truth, not your paraphrase of it.
"""


def build_orchestrator(session: TrinetraSession) -> Agent:
    @tool
    def pilgrim_help(question: str, language: str = "hindi") -> str:
        """Answer a pilgrim's logistics/safety/crowd-status question about the Kumbh Mela."""
        lang = IndianLanguage(language) if language in IndianLanguage._value2member_map_ else IndianLanguage.HINDI
        guidance = ask_pilgrim(session, question, language=lang)
        return guidance.model_dump_json(indent=2)

    @tool
    def report_emergency(description: str, location: str, incident_type: str = "other") -> str:
        """Triage a safety/emergency report from a pilgrim or operator."""
        from trinetra.models import IncidentType

        itype = IncidentType(incident_type) if incident_type in IncidentType._value2member_map_ else IncidentType.OTHER
        triage = report_sos(session, SOSReport(incident_type=itype, reporter_description=description, location=location))
        return triage.model_dump_json(indent=2)

    @tool
    def simulate_scenario_tool(scenario_name: str, description: str, total_pilgrims: int,
                                duration_minutes: int, peak_inflow_multiplier: float,
                                active_ghat_ids: list[str]) -> str:
        """Run Bhavishya Netra's crowd simulation for a described scenario and get NTKMA recommendations."""
        scenario = SimulationScenario(
            name=scenario_name, description=description, total_pilgrims=total_pilgrims,
            duration_minutes=duration_minutes, peak_inflow_multiplier=peak_inflow_multiplier,
            active_ghat_ids=active_ghat_ids,
        )
        report, advisory = run_simulation(session, scenario)
        return f"{report.model_dump_json(indent=2)}\n\nADVISORY:\n{advisory.model_dump_json(indent=2)}"

    @tool
    def run_calibration_check() -> str:
        """Validate the simulator against real historical Kumbh crowd-crush incidents."""
        results = run_calibration(session)
        return "\n".join(f"{r.case_name}: {r.simulated_peak_risk.value} (correct={r.correctly_flagged})" for r in results)

    @tool
    def flood_risk_check(discharge_cusecs: int, occupancy_by_ghat: dict[str, int]) -> str:
        """Assess a Gangapur Dam release against who is currently on the flood-exposed Godavari ghats."""
        assessment, advisory = assess_flood_risk(session, discharge_cusecs, occupancy_by_ghat)
        return f"{assessment.model_dump_json(indent=2)}\n\nADVISORY:\n{advisory.model_dump_json(indent=2)}"

    @tool
    def rumor_check(text: str, location: str, spreading_fast: bool = False) -> str:
        """Assess a rumour circulating in the crowd and draft a guardrail-scanned counter-message."""
        assessment, guardrail = triage_rumor(
            session, RumorReport(text=text, location=location, spreading_fast=spreading_fast)
        )
        return f"{assessment.model_dump_json(indent=2)}\n\nGUARDRAIL:\n{guardrail.model_dump_json(indent=2)}"

    @tool
    def command_incident_tool(
        discharge_cusecs: int | None = None,
        flood_occupancy: dict[str, int] | None = None,
        rumor_text: str | None = None,
        rumor_location: str | None = None,
    ) -> str:
        """Reconcile every live hazard against the finite responder pool and produce one command plan."""
        rumor = (
            RumorReport(text=rumor_text, location=rumor_location or "unspecified")
            if rumor_text
            else None
        )
        plan, allocation, conflicts, critique = command_incident(
            session,
            flood_discharge_cusecs=discharge_cusecs,
            flood_occupancy=flood_occupancy,
            rumor=rumor,
        )
        parts = [
            plan.model_dump_json(indent=2),
            f"ALLOCATION:\n{allocation.model_dump_json(indent=2)}",
            f"CONFLICTS:\n{conflicts.model_dump_json(indent=2)}",
        ]
        if critique is not None:
            parts.append(f"RED TEAM:\n{critique.model_dump_json(indent=2)}")
        return "\n\n".join(parts)

    @tool
    def live_monitor_tool(ghat_id: str, question: str | None = None) -> str:
        """Run Kshetra Netra's live-monitoring pass for one ghat - checks live
        ThingsBoard telemetry and Trinetra's own deterministic models, and
        decides for itself what needs the operator's attention right now."""
        return monitor_live(session, ghat_id, question=question).model_dump_json(indent=2)

    return create_agent(
        system_prompt=ROUTER_PROMPT,
        tools=[
            pilgrim_help,
            report_emergency,
            simulate_scenario_tool,
            run_calibration_check,
            flood_risk_check,
            rumor_check,
            command_incident_tool,
            live_monitor_tool,
        ],
    )
