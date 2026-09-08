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
    CompoundRiskAssessment,
    HydrologyAdvisory,
    NTKMAAdvisory,
    PilgrimGuidance,
    RumorAssessment,
    RumorGuardrailResult,
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


def render_compound_risk_md(
    assessment: CompoundRiskAssessment, advisory: HydrologyAdvisory | None = None
) -> str:
    """The Godavari compound-risk report. Every number here comes straight
    from the deterministic assessment - the advisory, if present, only adds
    interpretation around them."""
    lines = [
        "# Godavari Compound Risk — dam release into a crowded riverfront",
        "",
        DISCLAIMER,
        "",
        f"**Overall risk: {assessment.overall_risk.value.upper()}**",
        "",
        f"- Gangapur Dam discharge: **{assessment.discharge_cusecs:,} cusecs**",
        f"- Godavari stage: **{assessment.river_stage.value.upper()}**",
        f"- Estimated flood lead time to the Panchavati/Ramkund riverfront: **{assessment.lead_time_minutes} minutes**",
    ]
    if assessment.recent_rainfall_mm is not None:
        lines.append(f"- Recent peak daily rainfall (live): **{assessment.recent_rainfall_mm} mm** — {assessment.rainfall_note}")
    else:
        lines.append(f"- Rainfall: _{assessment.rainfall_note}_")
    lines.append("")

    if advisory:
        lines += [f"## {advisory.headline}", "", advisory.narrative_summary, ""]
        if advisory.ghats_to_clear_first:
            lines += ["**Clear in this order:** " + " → ".join(advisory.ghats_to_clear_first), ""]

    lines += ["## Can each ghat be cleared before the water arrives?", ""]
    if not assessment.ghat_feasibility:
        lines.append("_No flood-exposed ghat currently has reported occupancy._")
    for f in assessment.ghat_feasibility:
        verdict = "✅ clears with margin" if f.feasible else ("❌ CANNOT CLEAR IN TIME" if f.margin_minutes < 0 else "⚠️ margin too thin")
        lines.append(f"### {f.ghat_name} — {f.risk.value.upper()} · {verdict}")
        lines.append(f"- Occupancy: {f.occupancy:,} people")
        lines.append(f"- Mobility-adjusted egress: {f.effective_egress_per_min:.0f} people/min")
        lines.append(f"- Time to clear: **{f.clearance_minutes:.0f} min** vs **{f.lead_time_minutes} min** of lead time")
        lines.append(f"- Margin: **{f.margin_minutes:+.0f} min**")
        lines.append("")

    if assessment.findings:
        lines += ["## Findings", "", _bullets(assessment.findings), ""]

    if advisory and advisory.recommended_actions:
        lines += ["## Recommended actions", ""]
        for rec in advisory.recommended_actions:
            lines.append(
                f"- **{rec.target_name}** ({rec.current_risk.value}): {rec.action.value} "
                f"— {rec.rationale} (respond within {rec.urgency_minutes} min)"
            )
        lines.append("")

    return "\n".join(lines)


def render_rumor_assessment_md(
    assessment: RumorAssessment, guardrail: RumorGuardrailResult | None = None
) -> str:
    lines = [
        "# Rumor Assessment — Kumbh Rakshak rumor desk",
        "",
        f"**Crush risk: {assessment.crush_risk.value.upper()}** · category: {assessment.category}",
        "",
        f"**Why it's dangerous:** {assessment.why_dangerous}",
        "",
        "## ⚠️ Verify BEFORE broadcasting anything",
        "",
        _bullets(assessment.verify_before_broadcast),
        "",
        "## Draft counter-message (NOT yet approved for broadcast)",
        "",
        f"> {assessment.counter_message}",
        "",
        f"> {assessment.counter_message_local}",
        "",
        f"**Suggested channels:** {', '.join(assessment.recommended_channels)}",
        "",
    ]
    if guardrail:
        mark = "✅ passed" if guardrail.passed else "❌ BLOCKED"
        lines += [f"## Guardrail scan — {mark}", "", guardrail.summary, ""]
        for finding in guardrail.findings:
            lines.append(f"- **{finding.rule}** — “{finding.excerpt}” — {finding.explanation}")
        if guardrail.findings:
            lines.append("")
    lines.append(
        "_Trinetra never broadcasts. A human official verifies the points above and issues the message._"
    )
    return "\n".join(lines)


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
