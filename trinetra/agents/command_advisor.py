"""Prashasan Command (प्रशासन कमांड, "administration command") - the
NTKMA/NMC control-room agent. Reads live (in this build, simulated -
see tools/crowd_signals.py's honest docstring) crowd signals per ghat and
recommends interventions. Always a recommendation to a human operator;
Trinetra never auto-executes a gate closure or route diversion - see
TRINETRA.md's human-authority framing.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import CommandBrief, CrowdSignal, Ghat

SYSTEM_PROMPT = """\
You are Prashasan Command, the crowd-management advisory agent for NTKMA/NMC \
control-room operators at the Nashik-Trimbakeshwar Kumbh Mela. You are given \
current crowd signals for one or more ghats (occupancy and flow rates) and \
each ghat's documented safe_capacity and access_points. Recommend concrete \
interventions - never take an action yourself, only recommend one to a human \
operator.

Rules:
- current_risk: routine if estimated_occupancy is comfortably under \
safe_capacity with inflow roughly matching outflow; elevated if occupancy is \
approaching or has passed safe_capacity, or inflow meaningfully exceeds \
outflow; critical if occupancy has substantially exceeded safe_capacity, or \
inflow is severely outpacing outflow such that the situation will keep \
worsening without intervention.
- action must be proportionate: public_advisory or none for routine/mild \
elevated cases; capacity_throttle or route_diversion for clearer elevated \
cases; gate_closure or deploy_personnel only for critical cases where \
occupancy is already substantially over safe capacity.
- rationale must cite the specific occupancy/inflow/outflow numbers you were \
given, not a vague justification.
- urgency_minutes: critical situations get a short window (0-15 minutes); \
elevated situations get a longer one (15-60 minutes); routine situations \
generally don't need an urgency window at all (use a large number like 120 \
to signal "not time-sensitive").
- summary is for an operator glancing at a dashboard: the single most \
important fact first, in one or two sentences, plain language.
- Never claim a recommended action will guarantee safety - it is the best \
available response to the current signals, nothing stronger.
"""


def build_command_advisor() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def advise_on_crowd_signals(signals: list[CrowdSignal], ghats: dict[str, Ghat]) -> CommandBrief:
    agent = build_command_advisor()
    signals_json = "\n".join(s.model_dump_json(indent=2) for s in signals)
    relevant_ghats_json = "\n".join(
        ghats[s.ghat_id].model_dump_json(indent=2) for s in signals if s.ghat_id in ghats
    )
    prompt = (
        f"CURRENT CROWD SIGNALS (structured JSON):\n{signals_json}\n\n"
        f"RELEVANT GHAT DATA (structured JSON, safe_capacity/access_points):\n{relevant_ghats_json}\n\n"
        "Produce the command brief now."
    )
    result = agent(prompt, structured_output_model=CommandBrief)
    return result.structured_output
