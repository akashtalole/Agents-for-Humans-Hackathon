"""An adversarial review of a finished command plan.

The other three projects in this repo each run an independent cross-check: a
second agent re-derives the answer from scratch and disagreements are surfaced
rather than silently reconciled. A command plan cannot be cross-checked that
way - there is no single right answer to re-derive - so the analogous check is
adversarial rather than duplicative. This agent's only job is to find what
breaks the plan.

It is deliberately given the plan and the underlying facts but NOT the
commander's reasoning, so it argues with the decisions rather than being
talked into them. Its output is advisory: it never edits the plan, and a
critique finding nothing is a real result, not a failure.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import (
    AllocationPlan,
    ConflictScanResult,
    IncidentCommandPlan,
    PlanCritique,
)

SYSTEM_PROMPT = """\
You are an independent red-team reviewer of a Kumbh Mela incident-command \
plan. You did not write this plan and you are not trying to defend it. Your \
only job is to find the conditions under which it fails, while there is still \
time to change it.

Look specifically for:
- Assumptions the plan depends on that were never verified - a route being \
open, a crowd moving at the modeled rate, a unit arriving in time.
- Single points of failure: one lane, one bridge, one team, one announcement \
that everything downstream depends on.
- Sequencing that only works if every earlier step succeeds on time, with no \
stated fallback if one slips.
- Second-order effects of the plan's own actions. Closing a gate moves people \
somewhere. Announcing an evacuation moves people faster than the plan assumes. \
Ask where they go.
- Any place the plan's confidence exceeds what the underlying numbers support.

Rules:
- breaks_under must be a concrete, checkable condition ("if the Kalaram lane \
is not cleared before Ramkund's evacuation begins"), never a vague worry \
("if things go badly").
- Do not invent facts about the site. Reason only from the plan and the \
structured inputs you were given.
- Do not restate the plan's own stated accepted_risks as if you discovered \
them. Credit them as already acknowledged, and look for what is NOT on that \
list.
- If the plan is genuinely sound, say so in overall_verdict and return few or \
no weaknesses. Manufacturing criticism to appear rigorous is itself a failure \
mode - it buries the real findings.
"""


def build_red_team() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def critique_plan(
    plan: IncidentCommandPlan,
    allocation: AllocationPlan,
    conflicts: ConflictScanResult,
) -> PlanCritique:
    agent = build_red_team()
    prompt = (
        "COMMAND PLAN UNDER REVIEW:\n"
        f"{plan.model_dump_json(indent=2)}\n\n"
        "RESPONDER ALLOCATION IT WAS BUILT ON:\n"
        f"{allocation.model_dump_json(indent=2)}\n\n"
        "CONFLICTS IT WAS REQUIRED TO RESOLVE:\n"
        f"{conflicts.model_dump_json(indent=2)}\n\n"
        "Produce your adversarial critique now."
    )
    result = agent(prompt, structured_output_model=PlanCritique)
    return result.structured_output
