from bidwright.models import (
    ChecklistItem,
    ComplianceGap,
    ComplianceReport,
    ProposalDraft,
    RFPRequirements,
    Severity,
)


def test_rfp_requirements_round_trip():
    req = RFPRequirements(
        project_title="Grounds Maintenance",
        issuing_organization="City of Rivertown",
        submission_deadline="2026-09-30T17:00",
        required_certifications=["Pesticide Applicator Certification"],
        checklist=[ChecklistItem(item="Sign cover letter")],
    )
    restored = RFPRequirements.model_validate_json(req.model_dump_json())
    assert restored == req
    assert restored.checklist[0].required is True


def test_compliance_report_severity_enum():
    gap = ComplianceGap(
        requirement="General liability minimum $2,000,000",
        status="gap",
        severity=Severity.BLOCKING,
        detail="Company carries $1,000,000 per occurrence.",
        recommendation="Increase coverage before the deadline.",
    )
    report = ComplianceReport(overall_status="gaps_found", gaps=[gap], met_requirements=["Business license"])
    assert report.gaps[0].severity == Severity.BLOCKING
    assert report.gaps[0].severity.value == "blocking"


def test_proposal_draft_defaults():
    draft = ProposalDraft(
        cover_letter="...",
        executive_summary="...",
        technical_approach="...",
        qualifications_past_performance="...",
        compliance_matrix_notes="...",
        pricing_notes="...",
    )
    assert draft.open_questions == []
