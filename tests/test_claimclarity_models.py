from claimclarity.models import (
    AppealPackage,
    Classification,
    ClaimLineItem,
    ClaimRecord,
    DenialFindings,
    LineItemFinding,
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
