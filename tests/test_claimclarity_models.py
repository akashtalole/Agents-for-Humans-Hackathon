from claimclarity.models import (
    AppealPackage,
    Classification,
    ClaimLineItem,
    ClaimRecord,
    DenialFindings,
    EscalationPackage,
    LineItemFinding,
    StateDOIInfo,
)


def test_claim_record_round_trip():
    claim = ClaimRecord(
        patient_name="Maria Chen",
        insurer_name="Heartland Mutual Health Plan",
        claim_number="CLM-2026-0619884",
        appeal_deadline="2026-12-28",
        line_items=[
            ClaimLineItem(procedure_code="97110", diagnosis_code_billed="M54.5", carc_code="CO-16")
        ],
    )
    restored = ClaimRecord.model_validate_json(claim.model_dump_json())
    assert restored == claim
    assert restored.line_items[0].carc_code == "CO-16"


def test_line_item_finding_classification_enum():
    finding = LineItemFinding(
        procedure_code="97110",
        classification=Classification.BILLING_ERROR,
        evidence="M54.5 is a non-billable category header per lookup_icd10_code.",
        corrected_diagnosis_code="M54.51",
        recommendation="Appeal citing the corrected code.",
        worth_appealing=True,
    )
    assert finding.classification == Classification.BILLING_ERROR
    assert finding.classification.value == "billing_error"


def test_denial_findings_and_appeal_defaults():
    findings = DenialFindings(overall_recommendation="Appeal line 1, skip line 2.")
    assert findings.findings == []

    appeal = AppealPackage(non_appeal_explanation="Plan excludes this service outright.")
    assert appeal.appeal_letter == ""
    assert appeal.open_questions == []


def test_claim_record_state_defaults_blank():
    claim = ClaimRecord(patient_name="Maria Chen")
    assert claim.state == ""


def test_escalation_package_defaults_and_null_doi_letter():
    escalation = EscalationPackage(eligible_for_external_review=False, rationale="No worth-appealing items.")
    assert escalation.external_review_deadline is None
    assert escalation.external_review_request_letter == ""
    assert escalation.state_doi_complaint_letter is None
    assert escalation.regulatory_basis == []
    assert escalation.escalation_checklist == []


def test_state_doi_info_round_trip():
    info = StateDOIInfo(
        state_code="CA",
        state_name="California",
        doi_name="California Department of Insurance",
        doi_complaint_process="File online.",
        external_review_process="Independent Medical Review.",
        external_review_deadline_window="At least 4 months.",
        doi_contact_instruction="Search 'California Department of Insurance complaint'.",
    )
    restored = StateDOIInfo.model_validate_json(info.model_dump_json())
    assert restored == info
