"""Deterministic Markdown rendering for BidWright's structured outputs.

These functions never call a model — they exist so the files BidWright writes
to disk (and the "what needs your attention" summary) are guaranteed to
reflect the structured data exactly, rather than depending on an LLM to
faithfully restate its own output.
"""
from __future__ import annotations

from bidwright.models import (
    AmendmentImpact,
    ComplianceReport,
    ProposalDraft,
    RFPRequirements,
    TeamingPlan,
)


def _bullets(items: list[str]) -> str:
    if not items:
        return "_None stated._"
    return "\n".join(f"- {item}" for item in items)


def render_requirements_md(req: RFPRequirements) -> str:
    checklist_lines = "\n".join(
        f"- [ ] {item.item}"
        + (" (optional)" if not item.required else "")
        + (f" — {item.notes}" if item.notes else "")
        for item in req.checklist
    ) or "_No checklist items extracted._"

    return f"""# RFP Requirements: {req.project_title}

**Issuing organization:** {req.issuing_organization}
**Submission deadline:** {req.submission_deadline or "_not stated_"}
**Submission method:** {req.submission_method or "_not stated_"}

## Scope summary
{req.key_scope_summary or "_not stated_"}

## Eligibility criteria
{_bullets(req.eligibility_criteria)}

## Required certifications
{_bullets(req.required_certifications)}

## Required licenses
{_bullets(req.required_licenses)}

## Insurance requirements
{_bullets(req.insurance_requirements)}

## Evaluation criteria
{_bullets(req.evaluation_criteria)}

## Submission format rules
{_bullets(req.submission_format_rules)}

## Submission checklist
{checklist_lines}
"""


def render_compliance_md(report: ComplianceReport) -> str:
    status_label = "✅ READY TO SUBMIT" if report.overall_status == "ready" else "⚠️ GAPS FOUND"

    def gap_block(gap) -> str:
        return (
            f"### [{gap.severity.value.upper()}] {gap.requirement}\n"
            f"- **Status:** {gap.status}\n"
            f"- **Detail:** {gap.detail}\n"
            + (f"- **Recommendation:** {gap.recommendation}\n" if gap.recommendation else "")
        )

    gaps_md = "\n".join(gap_block(g) for g in report.gaps) or "_No gaps found._"

    return f"""# Compliance Report

**Overall status:** {status_label}

## Requirements met
{_bullets(report.met_requirements)}

## Gaps and items needing review
{gaps_md}
"""


def render_proposal_md(proposal: ProposalDraft) -> str:
    open_questions = _bullets(proposal.open_questions)
    return f"""# Proposal Draft

## Cover Letter
{proposal.cover_letter}

## Executive Summary
{proposal.executive_summary}

## Technical Approach
{proposal.technical_approach}

## Qualifications & Past Performance
{proposal.qualifications_past_performance}

## Compliance Matrix Notes
{proposal.compliance_matrix_notes}

## Pricing Notes
{proposal.pricing_notes}

## Open Questions For You
{open_questions}
"""


def render_amendment_impact_md(impact: AmendmentImpact) -> str:
    def modified_block(mod) -> str:
        return (
            f"### {mod.item}\n"
            f"- **Was:** {mod.previous}\n"
            f"- **Now:** {mod.updated}\n"
            + (f"- **Notes:** {mod.notes}\n" if mod.notes else "")
        )

    def checklist_block(items) -> str:
        return "\n".join(
            f"- {item.item}" + (" (optional)" if not item.required else "") + (f" — {item.notes}" if item.notes else "")
            for item in items
        ) or "_None._"

    modified_md = "\n".join(modified_block(m) for m in impact.modified_requirements) or "_None._"

    return f"""# Amendment Impact Analysis

**Urgency:** {impact.urgency.value.upper()}
**Deadline changed:** {"Yes — new deadline: " + impact.new_deadline if impact.deadline_changed and impact.new_deadline else ("Yes" if impact.deadline_changed else "No")}

## Summary
{impact.summary}

## New requirements added by this amendment
{checklist_block(impact.new_requirements)}

## Requirements removed or waived by this amendment
{checklist_block(impact.removed_requirements)}

## Requirements modified by this amendment
{modified_md}

## Impact on prior compliance work
{impact.compliance_impact or "_No prior compliance report to reconsider, or nothing affected._"}

## Proposal sections that need revision
{_bullets(impact.proposal_sections_requiring_revision)}

## Recommendation
{impact.recommendation}
"""


def render_teaming_plan_md(plan: TeamingPlan) -> str:
    def recommendation_block(rec) -> str:
        return f"""### [{rec.gap.severity.value.upper()}] {rec.gap.requirement}

**Capability needed:** {rec.capability_needed}

**Where to look:**
{rec.partner_search_guidance}

**Draft outreach email:**
```
{rec.outreach_email_draft}
```

**Teaming risk to verify:** {rec.teaming_risk_note}
"""

    recommendations_md = (
        "\n".join(recommendation_block(r) for r in plan.recommendations)
        or "_No compliance gaps in this run were plausibly fillable through teaming._"
    )

    return f"""# Teaming Partner Gap-Fill Plan

## Summary
{plan.summary}

## Recommendations
{recommendations_md}
"""


def _amendment_needs_attention(impact: AmendmentImpact) -> bool:
    return (
        impact.deadline_changed
        or impact.urgency.value != "info"
        or bool(impact.new_requirements)
        or bool(impact.removed_requirements)
        or bool(impact.modified_requirements)
        or bool(impact.proposal_sections_requiring_revision)
        or bool(impact.compliance_impact)
    )


def render_decision_summary_md(
    requirements: RFPRequirements | None,
    compliance: ComplianceReport | None,
    amendment_impact: AmendmentImpact | None = None,
) -> str:
    """The one file a busy human should actually read: what needs a decision,
    and nothing else. This is generated by plain code, not the LLM, so the
    "only ping me for real decisions" promise is guaranteed, not hoped for."""
    if requirements is None:
        return "# Decisions Needed\n\nRFP has not been analyzed yet.\n"

    lines = ["# Decisions Needed", ""]
    lines.append(f"**Project:** {requirements.project_title}")
    lines.append(f"**Deadline:** {requirements.submission_deadline or 'not stated in RFP'}")
    lines.append("")

    if compliance is None:
        lines.append("Compliance has not been checked yet.")
        return "\n".join(lines)

    blocking = [g for g in compliance.gaps if g.severity.value == "blocking"]
    warnings = [g for g in compliance.gaps if g.severity.value == "warning"]

    if not blocking:
        lines.append("**Status: no blocking gaps found — this bid is ready for your final review.**")
    else:
        lines.append(
            f"**Status: {len(blocking)} blocking gap(s) must be resolved before this bid can be submitted.**"
        )
        lines.append("")
        for gap in blocking:
            lines.append(f"- **{gap.requirement}** — {gap.detail}")
            if gap.recommendation:
                lines.append(f"  - Recommendation: {gap.recommendation}")

    if warnings:
        lines.append("")
        lines.append(f"Also worth a look ({len(warnings)} non-blocking item(s)):")
        for gap in warnings:
            lines.append(f"- {gap.requirement} — {gap.detail}")

    if amendment_impact is not None and _amendment_needs_attention(amendment_impact):
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"## ⚠️ AMENDMENT ALERT — [{amendment_impact.urgency.value.upper()}]")
        lines.append("")
        lines.append("An amendment was issued for this RFP after the original analysis above. "
                      "See `amendment_impact.md` for the full diff.")
        lines.append("")
        lines.append(amendment_impact.summary)
        if amendment_impact.deadline_changed:
            lines.append("")
            lines.append(f"**Deadline changed to: {amendment_impact.new_deadline or 'see amendment_impact.md'}**")
        if amendment_impact.compliance_impact:
            lines.append("")
            lines.append(f"**Impact on prior compliance work:** {amendment_impact.compliance_impact}")
        if amendment_impact.proposal_sections_requiring_revision:
            lines.append("")
            lines.append(
                "**Proposal sections needing revision:** "
                + ", ".join(amendment_impact.proposal_sections_requiring_revision)
            )
        lines.append("")
        lines.append(f"**Recommendation:** {amendment_impact.recommendation}")

    return "\n".join(lines) + "\n"
