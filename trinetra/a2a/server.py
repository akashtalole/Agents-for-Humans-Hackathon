"""Exposing Trinetra to third-party agents over A2A.

The agent card published here is a contract, and the honest parts of it
matter more than the capable parts. Anything that reads this card is
deciding what to hand Trinetra and what to do with what comes back, so the
skill descriptions say plainly that Trinetra returns decision support and
never executes anything - no gate closes, no unit is dispatched, and no
answer from here authorises an action. A peer that treats a Trinetra reply
as an instruction has misread it, and the card is where that is stated.

The declared skills are the same services the CLI and REST API expose. There
is deliberately no A2A skill for the incident-command flow: reconciling live
hazards against a finite responder pool is a decision made inside one
authority's control room, with a named human accountable for it, and it is
not a thing to answer for an anonymous caller over a network.
"""
from __future__ import annotations

from a2a.types import AgentSkill

from trinetra.config import create_agent
from trinetra.orchestrator import TrinetraSession, build_orchestrator

AGENT_NAME = "Trinetra"

AGENT_DESCRIPTION = (
    "Decision-support agents for the Nashik-Trimbakeshwar Kumbh Mela 2027, covering pilgrim "
    "guidance in nine Indian languages, safety/SOS triage, crowd-simulation foresight, Godavari "
    "compound flood risk, and rumour triage. Trinetra ADVISES; it never executes an action and "
    "never authorises one. Every figure it returns is either computed from its own bundled, cited "
    "site data or explicitly labelled as an illustrative planning estimate - it is not an official "
    "NTKMA or NMC system and does not speak for either."
)

SKILLS = [
    AgentSkill(
        id="pilgrim_guidance",
        name="Pilgrim guidance",
        description=(
            "Answer a pilgrim's routing, ghat-status or logistics question in Hindi, Marathi, "
            "English, Gujarati, Bhojpuri, Tamil, Telugu, Kannada or Bengali, grounded only in "
            "Trinetra's bundled site data. Flags and escalates a described emergency."
        ),
        tags=["pilgrim", "multilingual", "wayfinding", "kumbh"],
        examples=[
            "Ramkund par kitni bheed hai abhi?",
            "How do I reach Kushavarta Ghat from Panchavati?",
        ],
    ),
    AgentSkill(
        id="safety_triage",
        name="Safety and SOS triage",
        description=(
            "Classify a reported incident (lost person, medical, crowd pressure, harassment), "
            "return a 60-second action for the reporter and the responder type it should route "
            "to. Returns a recommendation for a human to act on - it does not dispatch anyone."
        ),
        tags=["safety", "sos", "emergency", "triage"],
        examples=["An elderly man has collapsed near Ramkund and is not breathing well."],
    ),
    AgentSkill(
        id="crowd_foresight",
        name="Crowd simulation foresight",
        description=(
            "Run a deterministic crowd digital-twin for a described scenario and return per-ghat "
            "peak occupancy, bottleneck routes and risk levels, with an interpretation. Calibrated "
            "against the 2003 Nashik and 2025 Prayagraj crowd-crush incidents."
        ),
        tags=["simulation", "planning", "crowd-safety", "digital-twin"],
        examples=["Simulate 500,000 pilgrims at Ramkund and Kushavarta over three hours."],
    ),
    AgentSkill(
        id="flood_risk",
        name="Godavari compound flood risk",
        description=(
            "Given a Gangapur Dam discharge and current ghat occupancy, compute whether each "
            "flood-exposed ghat can be cleared before the water arrives, accounting for the "
            "crowd's mobility mix. Lead times and egress rates are illustrative planning "
            "estimates, not official figures."
        ),
        tags=["flood", "godavari", "evacuation", "compound-risk"],
        examples=["Gangapur is releasing 22,000 cusecs and Ramkund holds 8,000 people."],
    ),
    AgentSkill(
        id="rumour_triage",
        name="Rumour triage",
        description=(
            "Assess the crush risk of a rumour circulating in a crowd and draft a bilingual "
            "counter-message. The draft is scanned by a deterministic guardrail and is returned "
            "NOT approved for broadcast - a human must verify the facts before any of it is said "
            "aloud."
        ),
        tags=["rumour", "misinformation", "crowd-safety", "communication"],
        examples=["People are saying there has been a stampede at Ramkund."],
    ),
]


def build_a2a_agent(session: TrinetraSession | None = None):
    """The Trinetra router, named and described so it can publish a card."""
    session = session or TrinetraSession()
    agent = build_orchestrator(session)
    agent.name = AGENT_NAME
    agent.description = AGENT_DESCRIPTION
    return agent


def build_a2a_server(host: str = "127.0.0.1", port: int = 9100, http_url: str | None = None,
                     session: TrinetraSession | None = None):
    """An A2AServer publishing Trinetra's card and skills.

    Imported lazily so the rest of the package - and the whole test suite -
    does not require the a2a extra to be installed.
    """
    from strands.multiagent.a2a import A2AServer

    return A2AServer(
        build_a2a_agent(session),
        host=host,
        port=port,
        http_url=http_url,
        skills=SKILLS,
        version="0.1.0",
    )
