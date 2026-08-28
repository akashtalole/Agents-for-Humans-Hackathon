from bidwright.models import (
    ChecklistItem,
    ComplianceGap,
    ComplianceReport,
    ProposalDraft,
    RFPRequirements,
    Severity,
)
from bidwright.rendering import (
    render_compliance_md,
    render_decision_summary_md,
    render_proposal_md,
    render_requirements_md,
)

REQUIREMENTS = RFPRequirements(
    project_title="Grounds Maintenance",
    issuing_organization="City of Rivertown",
    submission_deadline="2026-09-30T17:00",
    required_certifications=["Pesticide Applicator Certification"],
    insurance_requirements=["General liability, minimum $2,000,000 per occurrence"],
    checklist=[ChecklistItem(item="Sign cover letter"), ChecklistItem(item="Attach references", notes="min 3")],
)


def test_render_requirements_md_includes_key_fields():
    md = render_requirements_md(REQUIREMENTS)
    assert "Grounds Maintenance" in md
    assert "City of Rivertown" in md
    assert "2026-09-30T17:00" in md
    assert "Pesticide Applicator Certification" in md
    assert "- [ ] Sign cover letter" in md
    assert "min 3" in md


def test_render_compliance_md_ready():
    report = ComplianceReport(overall_status="ready", met_requirements=["Business license"], gaps=[])
    md = render_compliance_md(report)
    assert "READY TO SUBMIT" in md
    assert "Business license" in md


def test_render_compliance_md_gaps_found():
    gap = ComplianceGap(
        requirement="General liability minimum $2,000,000",
        status="gap",
        severity=Severity.BLOCKING,
        detail="Company carries $1,000,000 per occurrence.",
        recommendation="Increase coverage.",
    )
    report = ComplianceReport(overall_status="gaps_found", gaps=[gap])
    md = render_compliance_md(report)
    assert "GAPS FOUND" in md
    assert "[BLOCKING]" in md
    assert "Increase coverage." in md


def test_render_proposal_md():
    draft = ProposalDraft(
        cover_letter="Dear City of Rivertown,",
        executive_summary="We are pleased to submit...",
        technical_approach="Weekly mowing...",
        qualifications_past_performance="7 years in business...",
        compliance_matrix_notes="Insurance: currently below minimum.",
        pricing_notes="Owner must set final pricing.",
        open_questions=["Confirm whether to bid given the insurance gap."],
    )
    md = render_proposal_md(draft)
    assert "Dear City of Rivertown," in md
    assert "Confirm whether to bid" in md


def test_render_decision_summary_no_blocking_gaps():
    report = ComplianceReport(overall_status="ready", met_requirements=["License"], gaps=[])
    md = render_decision_summary_md(REQUIREMENTS, report)
    assert "no blocking gaps" in md.lower()


def test_render_decision_summary_with_blocking_gap():
    gap = ComplianceGap(
        requirement="General liability minimum $2,000,000",
        status="gap",
        severity=Severity.BLOCKING,
        detail="Company carries $1,000,000 per occurrence.",
        recommendation="Increase coverage before the deadline.",
    )
    report = ComplianceReport(overall_status="gaps_found", gaps=[gap])
    md = render_decision_summary_md(REQUIREMENTS, report)
    assert "1 blocking gap" in md
    assert "Increase coverage before the deadline." in md


def test_render_decision_summary_before_analysis():
    md = render_decision_summary_md(None, None)
    assert "not been analyzed" in md.lower()
