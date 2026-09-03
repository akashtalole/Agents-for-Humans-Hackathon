"""Deterministic Markdown rendering for ClaimClarity's structured outputs.

Never calls a model - the files written to disk (and the "what do I actually
need to decide" summary) always reflect the validated structured data
exactly, the same discipline used in bidwright/rendering.py.
"""
from __future__ import annotations

from claimclarity.models import (
    AppealPackage,
    ClaimRecord,
    DenialFindings,
    EscalationPackage,
    GuardrailResult,
    InsurerPatternInsight,
    PhysicianEvidenceRequest,
    ReviewResult,
)


def _bullets(items: list[str]) -> str:
    if not items:
        return "_None stated._"
    return "\n".join(f"- {item}" for item in items)


def render_claim_summary_md(claim: ClaimRecord) -> str:
    line_items_md = "\n".join(
        f"### {li.procedure_code} — {li.procedure_description or 'unspecified procedure'}\n"
        f"- Diagnosis code billed: {li.diagnosis_code_billed or '_not stated_'}\n"
        f"- Billed amount: {li.billed_amount or '_not stated_'}\n"
        f"- Denial reason: {li.denial_reason_text or '_not stated_'}"
        + (f" ({li.carc_code})" if li.carc_code else "")
        + (f" / remark {li.rarc_code}" if li.rarc_code else "")
        for li in claim.line_items
    ) or "_No denied line items extracted._"

    return f"""# Claim Summary

**Patient:** {claim.patient_name or "_not stated_"}
**Insurer:** {claim.insurer_name or "_not stated_"}
**Provider:** {claim.provider_name or "_not stated_"}
**Claim number:** {claim.claim_number or "_not stated_"}
**Date of service:** {claim.date_of_service or "_not stated_"}
**Notice date:** {claim.notice_date or "_not stated_"}
**Appeal deadline:** {claim.appeal_deadline or "_not stated_"}
**Where to file:** {claim.appeal_submission_method or "_not stated_"}

## Clinical notes summary
{claim.clinical_notes_summary or "_not stated_"}

## Relevant plan terms
{_bullets(claim.relevant_plan_terms)}

## Denied line items
{line_items_md}
"""


def render_findings_md(findings: DenialFindings) -> str:
    def finding_block(f) -> str:
        verdict = "✅ Worth appealing" if f.worth_appealing else "⛔ Not worth appealing"
        block = (
            f"### {f.procedure_code} — [{f.classification.value.upper()}] {verdict}\n"
            f"- **Evidence:** {f.evidence}\n"
        )
        if f.corrected_diagnosis_code:
            block += f"- **Corrected diagnosis code:** {f.corrected_diagnosis_code}\n"
        block += f"- **Recommendation:** {f.recommendation}\n"
        return block

    findings_md = "\n".join(finding_block(f) for f in findings.findings) or "_No findings._"

    return f"""# Denial Findings

## Overall recommendation
{findings.overall_recommendation}

## Line-by-line findings
{findings_md}
"""


def render_appeal_md(package: AppealPackage) -> str:
    return f"""# Appeal Package

## Appeal Letter
{package.appeal_letter or "_No line items were found worth appealing - see the explanation below instead._"}

## Why the rest isn't worth appealing
{package.non_appeal_explanation or "_Not applicable - every line item was worth appealing._"}

## Open Questions For You
{_bullets(package.open_questions)}
"""


def render_review_md(review: ReviewResult) -> str:
    verdict = "✅ Approved — no concrete issues found." if review.approved else "⚠️ Not approved — issues found."
    return f"""# Appeal Package Review

## Verdict
{verdict}

{review.summary}

## Issues
{_bullets(review.issues)}
"""


def render_guardrail_md(result: GuardrailResult) -> str:
    verdict = "✅ Passed — no guardrail violations found." if result.passed else "⛔ Failed — guardrail violation(s) found."

    def finding_block(f) -> str:
        return f"### {f.rule}\n" f'- **Excerpt:** "{f.excerpt}"\n' f"- **Why this is flagged:** {f.explanation}\n"

    findings_md = "\n".join(finding_block(f) for f in result.findings) or "_None._"

    return f"""# Appeal Guardrail Check

## Verdict
{verdict}

## Findings
{findings_md}
"""


def render_escalation_md(package: EscalationPackage) -> str:
    return f"""# External Review & Regulatory Escalation

**This is not legal advice.** It explains options that exist under the ACA \
and most state insurance codes, so you know they're there — a licensed \
patient advocate or attorney should review anything high-stakes before you \
rely on it.

## Bottom line
{"You have grounds to request an independent External Review." if package.eligible_for_external_review else "External review was not recommended for this claim."}

**External review deadline:** {package.external_review_deadline or "_not applicable / not determinable — see rationale below._"}

## Why
{package.rationale}

## Regulatory basis
{_bullets(package.regulatory_basis)}

## External Review Request Letter
{package.external_review_request_letter or "_Not drafted — external review wasn't found to apply to this claim._"}

## State Department of Insurance Complaint Letter
{package.state_doi_complaint_letter or "_Not drafted — the findings didn't show a process failure to report. A "
"DOI complaint isn't the right tool for a genuinely valid denial._"}

## Checklist
{_bullets(package.escalation_checklist)}
"""


def render_physician_evidence_request_md(request: PhysicianEvidenceRequest) -> str:
    def item_block(item) -> str:
        return (
            f"### {item.procedure_code}\n"
            f"- **Evidence needed:** {item.evidence_needed}\n"
            f"- **Why the insurer likely requires it:** {item.why_insurer_requires_it}\n"
            f"- **For your physician's office:** {item.physician_office_justification}\n"
        )

    items_md = "\n".join(item_block(i) for i in request.items) or (
        "_No denied line item here turns on missing physician documentation — see rationale below._"
    )

    return f"""# Physician Evidence Request

**This is not medical advice.** It lists documentation an insurer's medical \
necessity criteria commonly require, so you know what to ask your doctor's \
office for — your physician's own clinical judgment, not this list, \
determines what's actually appropriate for your care.

## Why
{request.rationale}

## Documentation needed, by line item
{items_md}

## Cover Letter To Your Physician's Office
{request.cover_letter_to_physician or "_Not drafted — no line item needs physician evidence for this claim._"}

## Your Follow-Up Checklist
{_bullets(request.patient_followup_checklist)}
"""


def render_insurer_pattern_report_md(insurer_name: str, insights: list[InsurerPatternInsight]) -> str:
    """Always produces a file, even with zero insights - a first-ever case
    for an insurer gets an honest "no pattern yet" message, not an error and
    not a blank page."""
    header = f"""# Insurer Accountability Pattern Report

**Insurer:** {insurer_name or "_not stated_"}
"""

    if not insights:
        return (
            header
            + """
No recurring denial pattern was found for this insurer in your recorded claim history yet. This may be the \
first case ClaimClarity has recorded for this insurer, or none of its recorded denial reasons has repeated \
across cases. That is not a clean bill of health for the insurer - it just means there isn't enough recorded \
history yet to say more. Run ClaimClarity again the next time this insurer denies something, and this report \
will start showing anything that recurs.

## Privacy
This history is stored only in a local JSON file on your own machine - the same place every other file \
ClaimClarity writes already lives - and is never sent anywhere.
"""
        )

    def insight_block(insight: InsurerPatternInsight) -> str:
        title = insight.denial_reason_category
        if insight.procedure_description:
            title += f" — {insight.procedure_description}"
        lines = [
            f"### {title}",
            f"- **Occurrences:** {insight.occurrence_count} separate recorded case(s)",
            f"- **Dates:** {', '.join(insight.dates) or '_not stated_'}",
        ]
        if insight.claim_numbers:
            lines.append(f"- **Claim number(s):** {', '.join(insight.claim_numbers)}")
        return "\n".join(lines)

    blocks = "\n\n".join(insight_block(i) for i in insights)

    return (
        header
        + f"""
**{len(insights)} recurring denial pattern(s) found** across your recorded claim history with this insurer. A \
denial reason repeating across separate claims is a materially stronger fact pattern for an appeal or a state \
Department of Insurance complaint than any single denial looked at alone — courts and regulators increasingly \
scrutinize insurers with a pattern of improper denials.

{blocks}

## Known limitation
This is exact/near-exact string matching on insurer name and denial reason (the claim's own stated CARC code \
or denial reason text, or the investigation's classification if neither was stated) — not deep semantic \
matching. Two denials a person would recognize as "the same excuse" worded differently on the EOB will not be \
matched here. Treat this as a starting point to verify yourself, not a complete accounting.

## Privacy
This history is stored only in a local JSON file on your own machine - the same place every other file \
ClaimClarity writes already lives - and is never sent anywhere.
"""
    )


def render_decision_summary_md(
    claim: ClaimRecord | None,
    findings: DenialFindings | None,
    escalation: EscalationPackage | None = None,
    physician_evidence_request: PhysicianEvidenceRequest | None = None,
) -> str:
    """The one file a patient should actually read. Generated by plain code so
    the "only tell me what I need to decide" promise doesn't depend on the
    orchestrator LLM remembering to keep it."""
    if claim is None:
        return "# Decisions Needed\n\nThe claim has not been analyzed yet.\n"

    lines = ["# Decisions Needed", ""]
    lines.append(f"**Claim:** {claim.claim_number or 'unknown'} — {claim.insurer_name or 'unknown insurer'}")
    lines.append(f"**Appeal deadline:** {claim.appeal_deadline or 'not stated in the denial notice'}")
    lines.append("")

    if findings is None:
        lines.append("Denial investigation has not run yet.")
        return "\n".join(lines)

    worth_appealing = [f for f in findings.findings if f.worth_appealing]
    not_worth_appealing = [f for f in findings.findings if not f.worth_appealing]

    if worth_appealing:
        lines.append(
            f"**Bottom line: {len(worth_appealing)} item(s) look worth appealing.** "
            "An appeal letter has been drafted for you to review and send."
        )
        lines.append("")
        for f in worth_appealing:
            lines.append(f"- **{f.procedure_code}** ({f.classification.value}) — {f.recommendation}")
    else:
        lines.append("**Bottom line: nothing here looks worth appealing.**")

    if not_worth_appealing:
        lines.append("")
        lines.append(f"Also flagged, but not worth fighting ({len(not_worth_appealing)} item(s)):")
        for f in not_worth_appealing:
            lines.append(f"- {f.procedure_code} — {f.recommendation}")

    if physician_evidence_request is not None:
        lines.append("")
        if physician_evidence_request.items:
            lines.append(
                f"**Before you appeal:** your doctor's office may need to send specific documentation for "
                f"{len(physician_evidence_request.items)} item(s) — see physician_evidence_request.md."
            )
        else:
            lines.append(
                "No denied item here needs extra documentation from your doctor's office — see "
                "physician_evidence_request.md for why."
            )

    if escalation is not None:
        lines.append("")
        if escalation.eligible_for_external_review:
            lines.append(
                "**If the internal appeal doesn't fully resolve this:** you may have the right to an "
                "independent External Review, and possibly a state Department of Insurance complaint — "
                "see escalation_package.md."
            )
        else:
            lines.append("External review wasn't recommended for this claim — see escalation_package.md for why.")

    return "\n".join(lines) + "\n"
