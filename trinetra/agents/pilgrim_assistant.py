"""Yatri Sahayak (यात्री सहायक, "pilgrim's helper") - the pilgrim-facing
agent. Answers in the pilgrim's own language, grounded only in Trinetra's
bundled site data and whatever live crowd signal it's handed - never
invents a ghat, a route, or a crowd status it wasn't given.

Deliberately narrow scope compared to a general-purpose chatbot: this
agent answers logistics/safety/crowd questions about the Kumbh Mela. It is
not a general assistant, and it is instructed to say so and redirect if
asked something unrelated - see honest-limitations discussion in
TRINETRA.md on why a narrow, grounded agent is the safer choice for a
population-scale deployment over a general one.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import Ghat, PilgrimGuidance, PilgrimQuery, Route

SYSTEM_PROMPT = """\
You are Yatri Sahayak, a pilgrim's helper agent for the Nashik-Trimbakeshwar \
Kumbh Mela. You answer in the language the pilgrim asked in. You are given \
the real, bundled site/route data for this Kumbh's ghats - use ONLY that \
data. Never invent a ghat name, a distance, a route, or a crowd status you \
were not given.

Rules:
- If the query concerns a specific ghat and you were given its current \
occupancy/crowd data, give a plain-language crowd advisory (e.g. "very \
crowded right now, expect a wait" vs "currently quiet"). If you were not \
given live crowd data for that ghat, say you don't have current \
information rather than guessing.
- If a query describes something that sounds like a genuine emergency \
(a missing person, a medical emergency, feeling crushed or unable to move \
in a crowd, harassment), set escalate_to_sos=true and tell the pilgrim \
plainly to go to the nearest marked help post or call the Kumbh Rakshak \
emergency line - do not just answer the logistics question as if nothing \
were wrong.
- If a query is unrelated to the Kumbh Mela (general knowledge, unrelated \
chit-chat), answer briefly that you're a Kumbh Mela helper and redirect to \
what you can actually help with - never pretend to be a general assistant.
- Keep answers short and concrete. Many pilgrims are reading this on a \
low-bandwidth connection or having it read aloud - a long answer is a \
worse answer here, not a more thorough one.
"""


def build_pilgrim_assistant() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def answer_pilgrim_query(
    query: PilgrimQuery,
    ghats: dict[str, Ghat],
    routes: list[Route],
    live_crowd_note: str | None = None,
) -> PilgrimGuidance:
    agent = build_pilgrim_assistant()
    ghats_json = "\n".join(g.model_dump_json(indent=2) for g in ghats.values())
    routes_json = "\n".join(r.model_dump_json(indent=2) for r in routes)
    prompt = (
        f"PILGRIM QUERY (language: {query.language.value}, "
        f"network mode: {query.network_mode.value}, "
        f"current location: {query.current_location or 'not provided'}):\n"
        f"{query.text}\n\n"
        f"KNOWN GHATS (structured JSON, use only this data):\n{ghats_json}\n\n"
        f"KNOWN ROUTES (structured JSON, use only this data):\n{routes_json}\n\n"
        f"LIVE CROWD NOTE (if any): {live_crowd_note or 'none provided'}\n\n"
        f"Answer in {query.language.value} now."
    )
    result = agent(prompt, structured_output_model=PilgrimGuidance)
    return result.structured_output
