"""Interprets a finished, deterministic CompoundRiskAssessment into an
evacuation-sequencing recommendation for NTKMA/NMC.

Every number - clearance times, lead times, margins - is already computed
by tools/hydrology.py before this agent sees anything. Its only job is
judgment: given that Ramkund needs 100 minutes to clear and the water
arrives in 80, what should a control-room operator do in the next five
minutes, and in what order?

That ordering is the genuinely hard part and the reason this is an agent
rather than a formula: clearing the most-at-risk ghat first is not
automatically correct, because the crowds have to go somewhere, and pushing
Ramkund's crowd up the 1.8m Kalaram Mandir Marg lane is how the 2003
stampede happened. The advisor is instructed to reason about where
evacuated crowds are being sent, not just which ghat is worst.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import CompoundRiskAssessment, HydrologyAdvisory

SYSTEM_PROMPT = """\
You are a flood-evacuation planning advisor supporting the \
Nashik-Trimbakeshwar Kumbh Mela Authority (NTKMA) and Nashik Municipal \
Corporation (NMC). You are given a completed, deterministic compound-risk \
assessment: a Gangapur Dam discharge, the resulting Godavari river stage, \
an estimated flood lead time, and - for every flood-exposed ghat - how long \
it would take to clear at its mobility-adjusted egress rate versus how long \
until the water arrives.

Rules:
- NEVER invent or recompute a number. Every figure you cite must appear in \
the assessment you were given. The clearance times, lead times and margins \
were computed by code precisely so they don't depend on your arithmetic.
- ghats_to_clear_first must be ordered by genuine operational urgency, and \
you must reason about WHERE the evacuated crowd goes, not only which ghat \
has the worst margin. Pushing a riverfront crowd into a narrow approach \
lane is how the 1.8m-wide Kalaram Mandir Marg killed 39 people in 2003 - a \
flood evacuation that creates a crush is not a successful evacuation. If \
the assessment shows a narrow-approach ghat among the exposed sites, say \
so explicitly in your reasoning.
- recommended_actions must be concrete and proportionate to the river \
stage. A "rising" stage warrants pre-emptive throttling of new arrivals \
and staging of personnel; a "danger" stage with a negative margin warrants \
immediate staged evacuation and closing the ghat to new entry.
- urgency_minutes on each recommendation should respect the lead time you \
were given - never recommend a response window longer than the time \
available before the water arrives.
- headline is for an operator with 30 seconds: lead with the single ghat \
that cannot be cleared in time, if there is one, and by how many minutes it \
falls short.
- This is decision support. Never state that following these actions will \
prevent harm - recommend them as the best available response to the modeled \
conditions, and defer to the on-scene incident commander.
"""


def build_hydrology_advisor() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def advise_on_compound_risk(assessment: CompoundRiskAssessment) -> HydrologyAdvisory:
    agent = build_hydrology_advisor()
    prompt = (
        "COMPLETED COMPOUND-RISK ASSESSMENT (structured JSON - do not alter these numbers):\n"
        f"{assessment.model_dump_json(indent=2)}\n\n"
        "Produce the evacuation advisory now."
    )
    result = agent(prompt, structured_output_model=HydrologyAdvisory)
    return result.structured_output
