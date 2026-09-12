"""Anukaran Netra (अनुकरण नेत्र, "simulation eye") - decides the
qualitative shape of one telemetry-seeding run for KumbhDigiTwin's
ThingsBoard tenant.

Deliberately the narrowest possible LLM role in this whole feature: this
agent picks a ScenarioDirective (a handful of bounded numbers plus a short
narrative) ONCE per run. It never sees or produces an actual telemetry
value - tools/thingsboard_seed.py's deterministic, seeded code turns the
directive into every number actually pushed to ThingsBoard. If this agent
hallucinated a ghat name or an out-of-range multiplier, Pydantic validation
catches the shape problem and the caller (see cli.py's seed-thingsboard
command) validates surge_asset_names against the known-ghats list before
anything is pushed - an invented ghat name here fails loudly, it does not
silently no-op or write to the wrong entity.
"""
from __future__ import annotations

from strands import Agent

from trinetra.config import create_agent
from trinetra.models import ScenarioDirective
from trinetra.tools.thingsboard_seed import KNOWN_GHAT_ASSET_NAMES

SYSTEM_PROMPT = """\
You direct one synthetic-telemetry seeding run for a Kumbh Mela crowd/river \
digital twin. You do not choose any number that gets written anywhere - you \
choose a qualitative scenario, expressed as bounded structured parameters, \
and pure deterministic code turns your choice into an actual reproducible \
curve.

Rules:
- surge_asset_names must be drawn ONLY from the ghat names you are given in \
the prompt. Never invent a ghat name, and never include a name you were not \
given verbatim.
- baseline_multiplier around 1.0 is an ordinary day; use higher values \
(up to the allowed maximum) only when the request describes an actual \
crowded/peak period (a Shahi Snan, an Amrit Snan, a festival day).
- flood_intensity stays 0 unless the request specifically describes rising \
water, monsoon conditions, or a dam release - do not add flood risk to a \
pure crowd scenario.
- cycle_minutes should roughly match how long the described period would \
realistically last - a short localized surge might be 30-60 minutes; a full \
bathing-day buildup might be 180-360.
- narrative is for a human operator watching this run: one or two sentences \
in plain language, grounded in what you were actually asked to simulate - \
never invented statistics, never a claim that this is real sensor data.
"""


def build_scenario_director() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def decide_scenario(request: str) -> ScenarioDirective:
    agent = build_scenario_director()
    prompt = (
        f"KNOWN GHATS (the only valid values for surge_asset_names): "
        f"{list(KNOWN_GHAT_ASSET_NAMES)}\n\n"
        f"OPERATOR'S REQUEST: {request}\n\n"
        "Produce the scenario directive now."
    )
    result = agent(prompt, structured_output_model=ScenarioDirective)
    directive = result.structured_output
    # Belt-and-braces: strip anything that slipped past the prompt's own
    # instruction not to invent a ghat name, rather than trusting the model
    # alone - see this module's docstring.
    known = set(KNOWN_GHAT_ASSET_NAMES)
    directive.surge_asset_names = [n for n in directive.surge_asset_names if n in known]
    return directive
