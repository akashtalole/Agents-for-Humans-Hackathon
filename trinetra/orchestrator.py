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
from trinetra.agents.pilgrim_assistant import answer_pilgrim_query
from trinetra.agents.safety_triage import triage_sos_report
from trinetra.config import create_agent
from trinetra.models import (
    CommandBrief,
    CrowdSignal,
    Ghat,
    IndianLanguage,
    NetworkMode,
    NTKMAAdvisory,
    PilgrimGuidance,
    PilgrimQuery,
    Route,
    SafetyTriage,
    SimulationReport,
    SimulationScenario,
    SOSReport,
)
from trinetra.tools.calibration import run_all_calibration_cases
from trinetra.tools.calibration import CalibrationResult
from trinetra.tools.crowd_signals import signals_from_simulation
from trinetra.tools.geography import load_sites
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

    return create_agent(
        system_prompt=ROUTER_PROMPT,
        tools=[pilgrim_help, report_emergency, simulate_scenario_tool, run_calibration_check],
    )
