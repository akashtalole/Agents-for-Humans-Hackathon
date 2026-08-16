from claimclarity.models import (
    AppealPackage,
    Classification,
    ClaimLineItem,
    ClaimRecord,
    DenialFindings,
    LineItemFinding,
)
from claimclarity.rendering import (
    render_appeal_md,
    render_claim_summary_md,
    render_decision_summary_md,
    render_findings_md,
)

CLAIM = ClaimRecord(
    patient_name="Maria Chen",
    insurer_name="Heartland Mutual Health Plan",
    claim_number="CLM-2026-0619884",
    appeal_deadline="2026-12-28",
    line_items=[
        ClaimLineItem(
            procedure_code="97110",
            procedure_description="Therapeutic exercise",
            diagnosis_code_billed="M54.5",
            billed_amount="$270.00",
            denial_reason_text="Missing/incomplete/invalid diagnosis or condition",
            carc_code="CO-16",
            rarc_code="M76",
        ),
        ClaimLineItem(
            procedure_code="97124",
            procedure_description="Massage therapy",
            diagnosis_code_billed="M54.5",
            billed_amount="$75.00",
            denial_reason_text="Non-covered charge(s)",
            carc_code="CO-96",
        ),
    ],
)


def test_render_claim_summary_md_includes_line_items():
    md = render_claim_summary_md(CLAIM)
    assert "Maria Chen" in md
    assert "97110" in md
    assert "CO-16" in md
    assert "M76" in md
    assert "97124" in md


def test_render_findings_md_marks_worth_appealing():
    findings = DenialFindings(
        overall_recommendation="Appeal line 1, skip line 2.",
        findings=[
            LineItemFinding(
                procedure_code="97110",
                classification=Classification.BILLING_ERROR,
                evidence="M54.5 is a non-billable category header.",
                corrected_diagnosis_code="M54.51",
                recommendation="Appeal with corrected code M54.51.",
                worth_appealing=True,
            ),
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="Plan explicitly excludes massage therapy.",
                recommendation="Do not appeal.",
                worth_appealing=False,
            ),
        ],
    )
    md = render_findings_md(findings)
    assert "Worth appealing" in md
    assert "Not worth appealing" in md
    assert "M54.51" in md


def test_render_appeal_md_handles_empty_letter():
    package = AppealPackage(non_appeal_explanation="Nothing here is worth appealing.")
    md = render_appeal_md(package)
    assert "No line items were found worth appealing" in md
    assert "Nothing here is worth appealing." in md


def test_render_decision_summary_with_mixed_findings():
    findings = DenialFindings(
        overall_recommendation="Appeal line 1, skip line 2.",
        findings=[
            LineItemFinding(
                procedure_code="97110",
                classification=Classification.BILLING_ERROR,
                evidence="...",
                recommendation="Appeal with corrected code M54.51.",
                worth_appealing=True,
            ),
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="...",
                recommendation="Do not appeal - plan exclusion.",
                worth_appealing=False,
            ),
        ],
    )
    md = render_decision_summary_md(CLAIM, findings)
    assert "1 item(s) look worth appealing" in md
    assert "Do not appeal - plan exclusion." in md


def test_render_decision_summary_before_analysis():
    md = render_decision_summary_md(None, None)
    assert "not been analyzed" in md.lower()
