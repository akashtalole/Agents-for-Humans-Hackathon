"""Deterministic Markdown rendering for Trinetra's structured outputs.

Never calls a model - same discipline as bidwright/rendering.py,
claimclarity/rendering.py, and glacierwatch/rendering.py: the files a
pilgrim, NTKMA/NMC operator, or judge actually reads reflect the validated
structured data exactly, never an LLM's retelling of it.
"""
from __future__ import annotations

from trinetra.models import (
    AllocationPlan,
    CalibrationResult,
    CommandBrief,
    CompoundRiskAssessment,
    ConflictScanResult,
    HydrologyAdvisory,
    IncidentCommandPlan,
    PeerConsultation,
    PlanCritique,
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


def render_incident_command_md(
    plan: IncidentCommandPlan,
    allocation: AllocationPlan,
    conflicts: ConflictScanResult,
    critique: PlanCritique | None = None,
) -> str:
    """The Sankat Nirnay reconciled command picture.

    Ordering here is deliberate and is the whole point of the document: the
    contested decisions, the conflicts and the accepted risks come BEFORE the
    routine sequence. An operator reading under pressure must hit the calls
    that need a human first, not scroll past twelve satisfied demands to find
    the one that isn't."""
    lines = [
        "# Sankat Nirnay — reconciled incident command",
        "",
        DISCLAIMER,
        "",
        f"**Overall risk: {plan.overall_risk.value.upper()}**",
        "",
        f"## {plan.headline}",
        "",
        plan.narrative_summary,
        "",
    ]

    if plan.escalate_to_human:
        lines += [
            "## 🔴 Calls the commander must make personally",
            "",
            _bullets(plan.escalate_to_human),
            "",
        ]

    if conflicts.conflicts:
        lines += ["## Conflicting directives detected", "", f"_{conflicts.summary}_", ""]
        for c in conflicts.conflicts:
            lines.append(
                f"- **[{c.severity.value.upper()}] {c.target_name}** "
                f"({c.kind.value.replace('_', ' ')}, from {' + '.join(c.sources)}): {c.detail}"
            )
        lines.append("")

    if plan.accepted_risks:
        lines += [
            "## Accepted risks — what this plan knowingly gives up",
            "",
            _bullets(plan.accepted_risks),
            "",
        ]

    lines += ["## Execution sequence", ""]
    if not plan.decisions:
        lines.append("_No decisions were produced._")
    for d in sorted(plan.decisions, key=lambda x: x.sequence):
        marker = " ⚠️ **contested**" if d.contested else ""
        responders = ", ".join(r.value for r in d.responder_types) or "—"
        lines.append(f"### {d.sequence}. {d.target_name} — within {d.within_minutes} min{marker}")
        lines.append(f"- **Directive:** {d.directive}")
        lines.append(f"- **Responders:** {responders}")
        lines.append(f"- **Why:** {d.justification}")
        lines.append("")

    lines += ["## Responder allocation", "", f"_{allocation.summary}_", ""]
    lines.append("| Target | Source | Type | Requested | Granted | Severity |")
    lines.append("| --- | --- | --- | ---: | ---: | --- |")
    for a in allocation.allocations:
        granted = f"{a.units_granted}" if a.fully_met else f"**{a.units_granted}**"
        lines.append(
            f"| {a.target_name} | {a.source} | {a.responder_type.value} | "
            f"{a.units_requested} | {granted} | {a.severity.value} |"
        )
    lines.append("")
    remaining = ", ".join(f"{t.value}: {n}" for t, n in sorted(allocation.remaining.items(), key=lambda kv: kv[0].value))
    lines += [f"**Units still uncommitted:** {remaining}", ""]

    if allocation.unmet_critical:
        lines += [
            "### Critical demands that could not be met in full",
            "",
            _bullets(allocation.unmet_critical),
            "",
        ]

    if critique is not None:
        lines += ["## Independent red-team critique", "", f"**Verdict:** {critique.overall_verdict}", ""]
        if critique.single_points_of_failure:
            lines += ["**Single points of failure:**", "", _bullets(critique.single_points_of_failure), ""]
        if critique.weaknesses:
            lines += ["**Weaknesses:**", ""]
            for w in critique.weaknesses:
                lines.append(f"- **[{w.severity.value.upper()}] {w.weakness}**")
                lines.append(f"  - Breaks under: {w.breaks_under}")
                lines.append(f"  - Mitigation: {w.suggested_mitigation}")
            lines.append("")
        else:
            lines += ["_The reviewer found no material weaknesses._", ""]

    return "\n".join(lines)


def render_peer_consultation_md(consultation: PeerConsultation) -> str:
    """What third-party agents said, rendered so provenance is impossible to
    lose.

    Every heading names the operator, not just the agent, because "Central
    Railway says" and "an agent called RailBot says" are different sentences
    to a control room. Withheld replies are shown as withheld with their raw
    text intact rather than dropped - an operator who cannot see what was
    filtered has no way to overrule the filter.
    """
    lines = [
        "# A2A peer consultation",
        "",
        DISCLAIMER,
        "",
        "> **Everything below is a third party's assertion, not a Trinetra finding.** No figure here "
        "enters Trinetra's deterministic risk calculations. If an operator wants to plan on one of "
        "these numbers, they enter it themselves, having decided to believe it.",
        "",
        f"**Question asked:** {consultation.question}",
        "",
        f"_{consultation.summary}_",
        "",
    ]

    if not consultation.responses:
        lines.append("_No registered peer was consulted._")
        return "\n".join(lines)

    for r in consultation.responses:
        if r.error:
            status = "⚠️ unreachable"
        elif not r.usable:
            status = "⛔ withheld by the trust scan"
        else:
            status = "✅ returned an answer"

        lines.append(f"## {r.peer_name} — {status}")
        lines.append(f"- **Operator:** {r.operator}")
        lines.append(f"- **Trust level:** `{r.trust.value}`")
        lines.append(f"- **Asked at:** {r.requested_at.isoformat(timespec='seconds')}Z")
        lines.append("")

        if r.error:
            lines += [f"_{r.error}_", ""]
            continue

        lines += ["> " + line for line in (r.text or "_(empty)_").splitlines()]
        lines.append("")

        if r.scan:
            lines.append(f"**Trust scan:** {r.scan.summary}")
            if r.scan.findings:
                lines.append("")
                for f in r.scan.findings:
                    lines.append(f"- `{f.rule}` — {f.explanation}")
                    lines.append(f"  - triggered on: _{f.excerpt}_")
            lines.append("")

    return "\n".join(lines)
