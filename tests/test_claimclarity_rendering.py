from claimclarity.models import (
    AppealPackage,
    Classification,
    ClaimLineItem,
    ClaimRecord,
    DenialFindings,
    EscalationPackage,
    InsurerPatternInsight,
    LineItemFinding,
)
from claimclarity.rendering import (
    render_appeal_md,
    render_claim_summary_md,
    render_decision_summary_md,
    render_escalation_md,
    render_findings_md,
    render_insurer_pattern_report_md,
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


def test_render_decision_summary_without_escalation_is_unaffected():
    findings = DenialFindings(overall_recommendation="Appeal line 1.")
    md = render_decision_summary_md(CLAIM, findings)
    assert "escalation_package.md" not in md


def test_render_decision_summary_mentions_escalation_when_eligible():
    findings = DenialFindings(overall_recommendation="Appeal line 1.")
    escalation = EscalationPackage(eligible_for_external_review=True, rationale="Still unresolved.")
    md = render_decision_summary_md(CLAIM, findings, escalation)
    assert "escalation_package.md" in md
    assert "External Review" in md


def test_render_escalation_md_eligible_case():
    package = EscalationPackage(
        eligible_for_external_review=True,
        external_review_deadline="2027-04-28",
        external_review_request_letter="Dear External Review Coordinator, ...",
        state_doi_complaint_letter=None,
        regulatory_basis=["General ACA external review framework (45 CFR 147.136)."],
        escalation_checklist=["Gather your internal appeal denial letter."],
        rationale="97110 is still worth escalating if the internal appeal fails.",
    )
    md = render_escalation_md(package)
    assert "grounds to request an independent External Review" in md
    assert "2027-04-28" in md
    assert "Dear External Review Coordinator" in md
    assert "45 CFR 147.136" in md
    assert "Not drafted" in md  # no DOI complaint letter


def test_render_escalation_md_not_eligible_case():
    package = EscalationPackage(
        eligible_for_external_review=False,
        rationale="Every item was a genuine plan exclusion, so there is nothing left to escalate.",
    )
    md = render_escalation_md(package)
    assert "not recommended" in md
    assert "genuine plan exclusion" in md


def test_render_insurer_pattern_report_md_no_prior_history():
    md = render_insurer_pattern_report_md("Heartland Mutual Health Plan", [])
    assert "Heartland Mutual Health Plan" in md
    assert "No recurring denial pattern was found" in md
    assert "never sent anywhere" in md


def test_render_insurer_pattern_report_md_with_recurring_pattern():
    insights = [
        InsurerPatternInsight(
            insurer_name="Heartland Mutual Health Plan",
            denial_reason_category="CO-16",
            procedure_description="Physical therapy",
            occurrence_count=3,
            dates=["2026-01-01T00:00:00+00:00", "2026-04-01T00:00:00+00:00", "2026-07-01T00:00:00+00:00"],
            claim_numbers=["CLM-1", "CLM-2", "CLM-3"],
        )
    ]
    md = render_insurer_pattern_report_md("Heartland Mutual Health Plan", insights)
    assert "1 recurring denial pattern(s) found" in md
    assert "CO-16" in md
    assert "Physical therapy" in md
    assert "3 separate recorded case(s)" in md
    assert "CLM-1, CLM-2, CLM-3" in md
    assert "exact/near-exact string matching" in md
    assert "never sent anywhere" in md
