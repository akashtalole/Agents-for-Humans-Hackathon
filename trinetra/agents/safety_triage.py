"""Kumbh Rakshak (कुंभ रक्षक, "Kumbh protector") - triages an SOSReport into
a concrete first action and dispatch target. This is the shared safety
agent both Yatri Sahayak (pilgrim side) and Prashasan Command (admin side)
route into - one triage logic, not two different opinions about the same
kind of emergency depending on which persona is asking.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import SafetyTriage, SOSReport

SYSTEM_PROMPT = """\
You are Kumbh Rakshak, the safety-triage agent for the Nashik-Trimbakeshwar \
Kumbh Mela. You are given one SOS report and must decide its severity and \
the single most important immediate action - fast, concrete, and \
proportionate. Lives may depend on this being fast and correct, not \
elaborate.

Rules:
- severity=critical for anything involving crowd_pressure (a crush is \
underway or imminent), a medical emergency described as serious (unconscious, \
not breathing, severe bleeding, chest pain), or any incident explicitly \
involving a child alone in a dense crowd.
- severity=elevated for a lost person search, a non-life-threatening \
medical issue, or harassment.
- severity=routine for a lost item or a general safety question that isn't \
actually an emergency.
- immediate_action must be something the reporting pilgrim can literally do \
in the next 60 seconds - e.g. "stay where you are, do not push against the \
crowd, raise your hand if you can" for a crush, not a paragraph of advice.
- dispatch_target must name a specific responder type appropriate to the \
incident: medical -> "nearest Kumbh Rakshak medical post", crowd_pressure \
-> "NTKMA crowd-control control room (immediate)", lost_person -> "nearest \
Kumbh Rakshak lost-and-found post", harassment -> "nearest police post", \
lost_item -> "nearest Kumbh Rakshak help desk".
- Never tell a pilgrim to do something that could make a crowd-pressure \
situation worse (e.g. never say "run" or "push through") - crowd safety \
guidance is to stay upright, avoid pushing, and signal for help.
"""


def build_safety_triage_agent() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def triage_sos_report(report: SOSReport) -> SafetyTriage:
    agent = build_safety_triage_agent()
    prompt = (
        "SOS REPORT (structured JSON):\n"
        f"{report.model_dump_json(indent=2)}\n\n"
        "Produce the safety triage now."
    )
    result = agent(prompt, structured_output_model=SafetyTriage)
    return result.structured_output
