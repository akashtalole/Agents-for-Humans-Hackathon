"""Sankat Nirnay - the multi-hazard incident commander.

Every other agent in this platform answers one question about one hazard.
This one is handed the whole board at once: what the crowd desk sees, what
the flood desk computed, which SOS incidents are open, what rumor is moving,
which responder demands the allocator could not fill, and which directives
the conflict scanner found to be mutually unexecutable.

The division of labour is the same as everywhere else here, and it matters
most in this module. The arithmetic is already done: tools/resources.py has
allocated the finite units in a documented, reproducible order, and
tools/conflicts.py has found the contradictions. Neither of those is a
judgment call, so neither is a model's job.

What is left over IS a judgment call, and it is the hard one: when the
allocator reports that Ramkund asked for six rescue units and got four, no
formula says whether to strip units from a lesser incident, accept the
shortfall, or change the plan so fewer are needed. That is the decision an
incident commander is paid to make, and this agent's job is to lay it out
clearly enough - with the trade-off named and the residual risk stated - that
a human can make it in the thirty seconds they actually have.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import (
    AllocationPlan,
    CommandBrief,
    CompoundRiskAssessment,
    ConflictScanResult,
    IncidentCommandPlan,
    RumorAssessment,
    SafetyTriage,
)

SYSTEM_PROMPT = """\
You are Sankat Nirnay, the incident-command advisor for the \
Nashik-Trimbakeshwar Kumbh Mela Authority (NTKMA). Several specialist desks \
have each reported on their own hazard, a deterministic allocator has \
already divided the available responder units among their competing demands, \
and a deterministic scanner has already found the directives that contradict \
each other. You produce the single reconciled plan a control-room operator \
executes.

Rules:
- NEVER invent or recompute a number. Occupancies, clearance margins, lead \
times, unit counts and shortfalls were all computed by code before you saw \
them. Cite them; do not re-derive them.
- NEVER silently drop a detected conflict or an unmet critical demand. Every \
one of them must be visibly resolved by a decision in your plan, and each \
such decision must have contested=true. If you resolve a conflict by \
accepting a risk rather than fixing it, that risk belongs in accepted_risks, \
stated plainly.
- Sequence matters more than any individual instruction. Decisions are \
executed in the order you give them, by people who cannot all be in two \
places at once. Order them by what must happen first for the rest to be \
possible - and remember that where you send an evacuated crowd is part of \
the decision, not a detail. A flood evacuation that creates a crush is not a \
successful evacuation: 39 people died in the 1.8m Kalaram Mandir Marg lane in \
2003 during exactly that kind of movement.
- accepted_risks is not optional and must not be softened. If the plan leaves \
an incident under-resourced, say which one and what the consequence is. An \
operator who is not told what this plan gives up cannot compensate for it.
- escalate_to_human is for calls that are genuinely not yours: stripping \
units from one critical incident to feed another, or any choice that trades \
one group's safety against another's. Put them there rather than deciding \
them.
- within_minutes on every decision must be achievable against the deadlines \
in the inputs. Never specify a response window longer than the time the \
inputs say is available.
- headline is read aloud in a control room, so keep it to one sentence of \
at most about 25 words: the single worst thing happening and why it is \
urgent. Everything else belongs in narrative_summary.
- This is decision support for a human commander who retains authority. \
Never state or imply that following this plan will prevent harm.
"""


def build_incident_commander() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def command_the_incident(
    allocation: AllocationPlan,
    conflicts: ConflictScanResult,
    flood: CompoundRiskAssessment | None = None,
    brief: CommandBrief | None = None,
    triages: list[SafetyTriage] | None = None,
    rumor: RumorAssessment | None = None,
) -> IncidentCommandPlan:
    sections = [
        "RESPONDER ALLOCATION (already computed - do not re-divide these units):",
        allocation.model_dump_json(indent=2),
        "",
        "DETECTED CONFLICTING DIRECTIVES (every one must be resolved in your plan):",
        conflicts.model_dump_json(indent=2),
    ]
    if flood is not None:
        sections += ["", "GODAVARI COMPOUND-RISK ASSESSMENT:", flood.model_dump_json(indent=2)]
    if brief is not None:
        sections += ["", "CROWD-DESK COMMAND BRIEF:", brief.model_dump_json(indent=2)]
    if triages:
        sections += ["", "OPEN SOS INCIDENTS:"] + [t.model_dump_json(indent=2) for t in triages]
    if rumor is not None:
        sections += ["", "ACTIVE RUMOR ASSESSMENT:", rumor.model_dump_json(indent=2)]
    sections += ["", "Produce the reconciled incident command plan now."]

    agent = build_incident_commander()
    result = agent("\n".join(sections), structured_output_model=IncidentCommandPlan)
    return result.structured_output
