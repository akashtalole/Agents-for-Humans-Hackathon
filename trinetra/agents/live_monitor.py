"""Kshetra Netra (क्षेत्र नेत्र, "sector eye") - Trinetra's live-monitoring
agent, backed by github.com/akashtalole/KumbhDigiTwin's ThingsBoard telemetry.

Structurally different from every other agent in this repo, on purpose.
Every other agent (safety_triage, command_advisor, foresight_advisor, ...)
is a single-shot call: the caller assembles the relevant structured data,
hands it to the model in one prompt, and the model extracts/interprets it
into a Pydantic object. That is the right shape when the caller already
knows exactly what the model needs to see.

Kshetra Netra doesn't get that assembled prompt. It is asked something like
"what's the situation at Ramkund right now" and has to *decide what to check*
- live crowd density, live river stage, whether a quick simulation says the
current trend is heading somewhere bad, whether the simulator itself is
still calibrated correctly. It is given real tools for each of those and
runs Strands' own tool-use loop before producing a MonitoringBrief. This is
the one place in Trinetra where "agents as tools" is literally true of the
agent's own internal tool calls, not just of the orchestrator router that
wraps this agent alongside the others.

The discipline does not change just because the loop got more interesting:
every tool below returns a fact (a live reading, a deterministic simulation
result, or an honest "unavailable") - never an opinion - and the model is
never allowed to invent a number a tool didn't return. See MonitoringBrief's
docstring for how checked_signals/data_gaps let a human verify the agent
actually looked before it spoke.
"""
from __future__ import annotations

import json

from strands import Agent, tool

from trinetra.config import create_agent
from trinetra.models import MonitoringBrief, RiskLevel, SimulationScenario
from trinetra.tools.calibration import run_all_calibration_cases
from trinetra.tools.geography import load_sites
from trinetra.tools.live_signals import (
    LiveSignalUnavailable,
    cross_check_ghat_capacity,
    fetch_ghat_live_reading,
    fetch_river_gauge_reading,
    los_grade_to_risk_label,
)
from trinetra.tools.simulator import simulate_scenario

SYSTEM_PROMPT = """\
You are Kshetra Netra, Trinetra's live-monitoring agent for the \
Nashik-Trimbakeshwar Kumbh Mela. You support a control-room operator who \
wants to know the current situation at a ghat and whether anything needs \
their attention right now.

You have tools. USE THEM before answering - never guess or recall a number \
from earlier in the conversation. A monitoring brief that did not actually \
check anything this turn is worse than no brief.

Available checks, and when to use them:
- get_live_ghat_crowd_signal: live density/occupancy from ThingsBoard for \
one ghat. Call this first for any ghat-specific question. If it reports \
unavailable (no sensor mapping, or a live-fetch failure), say so plainly in \
data_gaps - never substitute a plausible-sounding number.
- get_live_river_gauge: live water-level/trend for the same ghat, from a \
separate ThingsBoard device. A rising or danger-stage reading matters even \
if crowd density looks fine, because a flood evacuation decision depends on \
both being read together (see TRINETRA.md's compound-hazard section) - \
check this whenever you check crowd signal for a flood-exposed ghat, not \
only when explicitly asked about the river.
- run_quick_lookahead_simulation: Trinetra's own deterministic simulator, \
run for a short window at a SUSTAINED ARRIVAL RATE you estimate (not the \
live occupancy snapshot - a pax count and an arrival rate are different \
quantities; do not pass one where the other is asked for). Use this to \
check whether a given rate of arrivals is heading toward critical occupancy \
or an approach-lane queue that will not clear, and say what your rate \
estimate is based on."
- check_simulator_is_calibrated: sanity-checks that Trinetra's own \
simulator still reproduces the two documented historical disasters as \
CRITICAL and correctly declines to flag the negative-control cases. Call \
this if you are about to lean heavily on a simulation result and want to \
know whether that result is coming from a trustworthy model.

Rules:
- overall_status must be justified by at least one finding you actually \
produced this turn - never assign a status "in general" without a cited \
observation.
- Every finding's observation must cite the specific number a tool \
returned (density, occupancy_pct, level_m, margin_minutes, etc.), not a \
vague description.
- When two signals disagree (e.g. ThingsBoard's LOS grade says critical but \
occupancy_pct looks moderate, or Trinetra's own safe_capacity and \
ThingsBoard's reported safe_capacity are far apart), report the \
disagreement as its own finding rather than silently picking one number. \
Two independent estimates disagreeing is itself useful information for the \
operator, not something to resolve for them.
- checked_signals must list every tool call you actually made, verbatim by \
tool name and ghat/argument, and data_gaps must list every check you \
wanted to make but could not (unmapped ghat, live-fetch failure, no \
calibration case for this scenario type).
- recommended_action is a recommendation for a human operator to act on. \
You never claim anything was, or will be, auto-executed - not a gate \
closure, not a PA announcement, not a barrier hold. That decision belongs \
to a person, exactly as it does for every other Trinetra agent.
- Never claim a live reading is more certain than it is: a single sensor \
reading is a snapshot, not a trend, unless you also called the lookahead \
simulation or looked at trend_cm_per_hr.
"""


def build_live_monitor() -> Agent:
    ghats, _routes = load_sites()

    @tool
    def get_live_ghat_crowd_signal(ghat_id: str) -> str:
        """Live crowd density/occupancy for one ghat from ThingsBoard
        (github.com/akashtalole/KumbhDigiTwin), cross-checked against
        Trinetra's own bundled safe_capacity for the same ghat."""
        try:
            reading = fetch_ghat_live_reading(ghat_id)
        except LiveSignalUnavailable as exc:
            return json.dumps({"available": False, "ghat_id": ghat_id, "reason": str(exc)})
        result = {"available": True, "reading": json.loads(reading.model_dump_json())}
        result["los_based_risk"] = los_grade_to_risk_label(reading.los_grade)
        ghat = ghats.get(ghat_id)
        if ghat is not None:
            result["cross_check"] = json.loads(
                cross_check_ghat_capacity(ghat, reading).model_dump_json()
            )
        return json.dumps(result)

    @tool
    def get_live_river_gauge(ghat_id: str) -> str:
        """Live water-level/trend for one ghat's river gauge from
        ThingsBoard. Independent of Trinetra's own hand-entered
        DamRelease/RiverStage - see RiverGaugeReading's docstring for why
        these are cross-checked, not merged."""
        try:
            reading = fetch_river_gauge_reading(ghat_id)
        except LiveSignalUnavailable as exc:
            return json.dumps({"available": False, "ghat_id": ghat_id, "reason": str(exc)})
        return json.dumps({"available": True, "reading": json.loads(reading.model_dump_json())})

    @tool
    def run_quick_lookahead_simulation(
        ghat_id: str, sustained_inflow_per_min: int, duration_minutes: int = 60, peak_inflow_multiplier: float = 1.3
    ) -> str:
        """Runs Trinetra's deterministic crowd simulator for a short
        look-ahead window, to see whether a given sustained arrival rate is
        heading toward critical occupancy or an unclearable approach-lane
        queue at this ghat. Pure code - the result is reproducible, not the
        model's opinion.

        sustained_inflow_per_min is arrivals per minute, NOT a live
        occupancy snapshot - ThingsBoard's paxCount/densityPaxPerSqm measure
        who is AT the ghat right now, not the rate at which people are
        ARRIVING, and this repo does not convert one into the other by
        guessing. Estimate it from context (e.g. a crowd signal that has
        been rising steadily, or an operator's own knowledge of a gate's
        throughput) and say in your reasoning what the estimate is based on.
        duration_minutes*sustained_inflow_per_min becomes the scenario's
        total_pilgrims for a single-ghat run, so the simulator's average
        inflow over the window matches the rate given, elevated by
        peak_inflow_multiplier during the window's middle third - see
        simulator.py's own docstring for that weighting."""
        ghat = ghats.get(ghat_id)
        if ghat is None:
            return json.dumps({"available": False, "reason": f"'{ghat_id}' is not a known ghat"})
        scenario = SimulationScenario(
            name=f"Kshetra Netra lookahead: {ghat_id}",
            description="Short-window lookahead at a given sustained arrival rate.",
            total_pilgrims=max(sustained_inflow_per_min, 1) * max(duration_minutes, 1),
            duration_minutes=duration_minutes,
            peak_inflow_multiplier=peak_inflow_multiplier,
            active_ghat_ids=[ghat_id],
        )
        report = simulate_scenario(scenario, ghats, _routes)
        result = report.ghat_results[0]
        return json.dumps(
            {
                "available": True,
                "overall_risk": report.overall_risk.value,
                "peak_occupancy_pct_of_safe_capacity": result.peak_occupancy_pct_of_safe_capacity,
                "peak_queue_outside": result.peak_queue_outside,
                "queue_still_growing_at_end": result.queue_still_growing_at_end,
                "incidents": report.incidents_triggered,
            }
        )

    @tool
    def check_simulator_is_calibrated() -> str:
        """Runs Trinetra's calibration suite (2 historical disasters + 3
        negative controls) right now. Use this before leaning heavily on a
        simulation result if you want to confirm the model backing it is
        still trustworthy."""
        results = run_all_calibration_cases()
        all_correct = all(r.correctly_flagged for r in results)
        return json.dumps(
            {
                "all_correct": all_correct,
                "cases": [
                    {"case_id": r.case_id, "correctly_flagged": r.correctly_flagged, "note": r.note}
                    for r in results
                ],
            }
        )

    return create_agent(
        system_prompt=SYSTEM_PROMPT,
        tools=[
            get_live_ghat_crowd_signal,
            get_live_river_gauge,
            run_quick_lookahead_simulation,
            check_simulator_is_calibrated,
        ],
    )


def monitor_ghat(ghat_id: str, question: str | None = None) -> MonitoringBrief:
    """Runs one live-monitoring pass for a ghat. question, if given, is a
    free-text nudge (e.g. "focus on flood risk") appended to the prompt -
    the agent still decides for itself which tools to call."""
    agent = build_live_monitor()
    prompt = (
        f"Monitor the current situation at ghat_id='{ghat_id}'. "
        "Check live crowd and river signals, and run a lookahead simulation "
        "if the live signals suggest the situation may be worsening.\n"
    )
    if question:
        prompt += f"\nOperator's specific question: {question}\n"
    result = agent(prompt, structured_output_model=MonitoringBrief)
    return result.structured_output
