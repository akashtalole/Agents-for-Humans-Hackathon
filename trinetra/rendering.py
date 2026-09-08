"""Deterministic Markdown rendering for Trinetra's structured outputs.

Never calls a model - same discipline as bidwright/rendering.py,
claimclarity/rendering.py, and glacierwatch/rendering.py: the files a
pilgrim, NTKMA/NMC operator, or judge actually reads reflect the validated
structured data exactly, never an LLM's retelling of it.
"""
from __future__ import annotations

from trinetra.models import (
    CalibrationResult,
    CommandBrief,
    NTKMAAdvisory,
    PilgrimGuidance,
    SafetyTriage,
    SimulationReport,
)

DISCLAIMER = (
    "**Trinetra is decision support, not an autonomous authority.** Every recommendation "
    "below is generated for a human NTKMA/NMC operator, pilgrim, or responder to act on - "
    "nothing here auto-executes a gate closure, route diversion, or dispatch. Crowd-simulation "
    "figures are Trinetra's own illustrative planning estimates unless explicitly cited to a "
    "published NTKMA figure - see each report's own sourcing notes."
)


def _bullets(items: list[str]) -> str:
    if not items:
        return "_None._"
    return "\n".join(f"- {item}" for item in items)


def render_simulation_report_md(report: SimulationReport, advisory: NTKMAAdvisory | None = None) -> str:
    lines = [
        f"# Bhavishya Netra Simulation Report — {report.scenario_name}",
        "",
        DISCLAIMER,
        "",
        f"**Overall risk: {report.overall_risk.value.upper()}**",
        "",
    ]

    if advisory:
        lines += ["## Advisory summary", "", advisory.narrative_summary, ""]
        lines += ["## Top concerns", "", _bullets(advisory.top_concerns), ""]

    lines += ["## Per-ghat results", ""]
    for g in report.ghat_results:
        lines.append(f"### {g.ghat_name} — {g.risk_level.value.upper()}")
        lines.append(
            f"- Peak occupancy: {g.peak_occupancy} people "
            f"({g.peak_occupancy_pct_of_safe_capacity}% of safe capacity), at minute {g.peak_tick_minute}"
        )
        if g.bottleneck_routes:
            lines.append(f"- Bottleneck route(s): {', '.join(g.bottleneck_routes)}")
        lines.append("")

    if report.incidents_triggered:
        lines += ["## Incidents the simulation flagged", "", _bullets(report.incidents_triggered), ""]

    if advisory and advisory.recommended_capacity_changes:
        lines += ["## Recommended interventions", ""]
        for rec in advisory.recommended_capacity_changes:
            lines.append(
                f"- **{rec.target_name}** ({rec.current_risk.value}): {rec.action.value} "
                f"— {rec.rationale} (respond within {rec.urgency_minutes} min)"
            )
        lines.append("")

    return "\n".join(lines)


def render_calibration_md(results: list[CalibrationResult]) -> str:
    lines = [
        "# Bhavishya Netra Calibration Against Real Historical Incidents",
        "",
        "Each case below is a real, documented Kumbh crowd-crush disaster. Trinetra's "
        "simulator replays the documented conditions; if it does not come back CRITICAL, "
        "the simulator's thresholds are not trustworthy enough to use for real planning.",
        "",
    ]
    all_correct = all(r.correctly_flagged for r in results)
    lines.append(f"**Result: {'✅ all cases correctly flagged' if all_correct else '⚠️ one or more cases NOT flagged'}**")
    lines.append("")
    for r in results:
        mark = "✅" if r.correctly_flagged else "❌"
        lines.append(f"## {mark} {r.case_name}")
        lines.append(f"- Real-world deaths: {r.real_world_deaths}")
        lines.append(f"- Simulated peak risk: {r.simulated_peak_risk.value.upper()}")
        lines.append(f"- {r.note}")
        lines.append("")
    return "\n".join(lines)


def render_command_brief_md(brief: CommandBrief) -> str:
    lines = [
        "# Prashasan Command Brief",
        "",
        DISCLAIMER,
        "",
        f"**Overall status: {brief.overall_status.value.upper()}**",
        "",
        brief.summary,
        "",
        "## Recommendations",
        "",
    ]
    if not brief.recommendations:
        lines.append("_No interventions recommended at this time._")
    for rec in brief.recommendations:
        lines.append(
            f"- **{rec.target_name}** ({rec.current_risk.value}): {rec.action.value} "
            f"— {rec.rationale} (respond within {rec.urgency_minutes} min)"
        )
    return "\n".join(lines)


def render_safety_triage_md(triage: SafetyTriage) -> str:
    return (
        f"# Kumbh Rakshak Safety Triage\n\n"
        f"**Severity: {triage.severity.value.upper()}**\n\n"
        f"**Do now:** {triage.immediate_action}\n\n"
        f"**Routed to:** {triage.dispatch_target}\n\n"
        f"**Rationale:** {triage.rationale}\n"
    )


def render_pilgrim_guidance_md(guidance: PilgrimGuidance) -> str:
    lines = [guidance.answer, ""]
    if guidance.suggested_route:
        lines.append(f"**Suggested route:** {guidance.suggested_route}")
    if guidance.ghat_crowd_advisory:
        lines.append(f"**Crowd status:** {guidance.ghat_crowd_advisory}")
    if guidance.safety_note:
        lines.append(f"**Safety note:** {guidance.safety_note}")
    if guidance.escalate_to_sos:
        lines.append("\n⚠️ **This looked like it might be an emergency - routed for SOS follow-up.**")
    return "\n".join(lines)
