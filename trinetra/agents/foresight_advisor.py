"""Bhavishya Netra's LLM layer: interprets a finished, deterministic
SimulationReport into recommendations NTKMA/NMC can act on. This agent
never recomputes or restates the occupancy numbers - simulator.py already
produced those, and rendering.py quotes them verbatim. The model's only
job here is judgment: which ghats need attention first, what specific
intervention fits each situation, and a plain-language narrative summary
for a control-room operator who doesn't have time to read raw numbers."""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import NTKMAAdvisory, SimulationReport

SYSTEM_PROMPT = """\
You are a crowd-safety planning advisor supporting the Nashik-Trimbakeshwar \
Kumbh Mela Authority (NTKMA) and Nashik Municipal Corporation (NMC). You are \
given a completed, deterministic crowd-simulation report - real occupancy \
numbers already computed by code, not something you calculate or restate \
yourself. Your job is narrower: read the numbers you're given and turn them \
into specific, actionable recommendations.

Rules:
- Never invent a number. If you cite a percentage or occupancy figure, it \
must come directly from the SimulationReport you were given.
- top_concerns should name specific ghats/routes from the report, ordered \
by severity, not a generic list.
- recommended_capacity_changes: for every ghat at CRITICAL risk, recommend a \
concrete InterventionAction (route_diversion, gate_closure, \
capacity_throttle, or deploy_personnel) with a rationale citing the specific \
bottleneck or occupancy figure that justifies it. For ELEVATED risk ghats, \
recommend public_advisory or none, not the same aggressive response as \
CRITICAL ones - proportionate response matters as much as catching the risk.
- urgency_minutes should reflect how much runway the report's numbers imply \
- a ghat that peaked early in the simulated window needs a shorter response \
window than one that peaked near the end.
- narrative_summary is for a control-room operator with 30 seconds to read \
it: lead with the single most urgent fact, in plain language, no jargon.
- This is a planning/decision-support tool. Never claim an intervention is \
guaranteed to prevent an incident - recommend it as the best available \
response to the modeled conditions, nothing stronger.
"""


def build_foresight_advisor() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def advise_on_simulation(report: SimulationReport) -> NTKMAAdvisory:
    agent = build_foresight_advisor()
    prompt = (
        "COMPLETED SIMULATION REPORT (structured JSON - do not alter these numbers):\n"
        f"{report.model_dump_json(indent=2)}\n\n"
        "Produce the NTKMA advisory now."
    )
    result = agent(prompt, structured_output_model=NTKMAAdvisory)
    return result.structured_output
