"""Wiring tests for BidWright's Teaming Partner Gap-Fill Advisor, following
the same offline `agent.tool.<name>(...)` direct-call pattern as
tests/test_bidwright_orchestrator_wiring.py - no API key or network access
required.
"""
from __future__ import annotations

from pathlib import Path

import bidwright.orchestrator as orchestrator_module
from bidwright.models import (
    ChecklistItem,
    ComplianceGap,
    ComplianceReport,
    RFPRequirements,
    Severity,
    TeamingPlan,
    TeamingRecommendation,
)
from bidwright.orchestrator import BidJob, build_orchestrator

RFP_PATH = "examples/sample_rfp.md"
PROFILE_PATH = "examples/company_profile.json"


def _tool_text(result) -> str:
    return result["content"][0]["text"]


def _fake_requirements() -> RFPRequirements:
    return RFPRequirements(
        project_title="Test Project",
        issuing_organization="City of Test",
        submission_deadline="2026-09-30T17:00",
        checklist=[ChecklistItem(item="Sign cover letter")],
    )


def _blocking_gap() -> ComplianceGap:
    return ComplianceGap(
        requirement="Past performance in NAICS 561730 (Landscaping Services)",
        status="gap",
        severity=Severity.BLOCKING,
        detail="Company profile shows no past performance in this NAICS code.",
        recommendation="Team with a subcontractor who has direct past performance in this "
        "NAICS code, since this cannot be manufactured before the deadline.",
    )


def _fake_compliance_with_blocking_gap() -> ComplianceReport:
    return ComplianceReport(
        overall_status="gaps_found",
        met_requirements=["Business license"],
        gaps=[_blocking_gap()],
    )


def _fake_compliance_ready() -> ComplianceReport:
    return ComplianceReport(overall_status="ready", met_requirements=["Everything"], gaps=[])


def _fake_teaming_plan() -> TeamingPlan:
    return TeamingPlan(
        recommendations=[
            TeamingRecommendation(
                gap=_blocking_gap(),
                capability_needed="Direct past performance in NAICS 561730",
                partner_search_guidance="Search SAM.gov's Subcontracting Network (SubNet) and "
                "the local PTAC/APEX Accelerator for landscaping firms with NAICS 561730 past "
                "performance in this region.",
                outreach_email_draft="Subject: Teaming opportunity on an upcoming landscaping "
                "RFP\n\nDear [Partner Company],\n\nWe are preparing a bid...",
                teaming_risk_note="Verify the RFP's actual subcontracting limit before "
                "committing - it was not stated in the extracted requirements.",
            )
        ],
        summary="One gap could be closed by teaming with a subcontractor who has direct past "
        "performance in this NAICS code; reach out to a candidate this week.",
    )


def _build_job(tmp_path: Path) -> BidJob:
    return BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))


def test_teaming_plan_happy_path_writes_file_and_updates_job(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(
        orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_with_blocking_gap()
    )
    monkeypatch.setattr(
        orchestrator_module,
        "draft_teaming_plan",
        lambda requirements, compliance, profile_text: _fake_teaming_plan(),
    )

    job = _build_job(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    result = orchestrator.tool.draft_teaming_plan_tool()
    text = _tool_text(result)
    assert "teaming_plan.md" in text
    assert "1 gap" in text

    assert (tmp_path / "teaming_plan.md").exists()
    assert job.teaming_plan is not None
    assert len(job.teaming_plan.recommendations) == 1

    plan_md = (tmp_path / "teaming_plan.md").read_text()
    assert "NAICS 561730" in plan_md
    assert "SAM.gov" in plan_md
    assert "Subject: Teaming opportunity" in plan_md
    assert "Verify the RFP's actual subcontracting limit" in plan_md


def test_teaming_plan_before_compliance_check_returns_clean_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())

    job = _build_job(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()

    result = orchestrator.tool.draft_teaming_plan_tool()
    text = _tool_text(result)
    assert "Error" in text
    assert "check_company_compliance" in text
    assert job.teaming_plan is None
    assert not (tmp_path / "teaming_plan.md").exists()


def test_teaming_plan_with_zero_gaps_is_a_clean_noop_that_still_writes_a_file(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_ready())

    called = False

    def _should_not_be_called(requirements, compliance, profile_text):
        nonlocal called
        called = True
        raise AssertionError("draft_teaming_plan should not be called when there are no gaps")

    monkeypatch.setattr(orchestrator_module, "draft_teaming_plan", _should_not_be_called)

    job = _build_job(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    result = orchestrator.tool.draft_teaming_plan_tool()
    text = _tool_text(result)

    assert result["status"] == "success"
    assert "Error" not in text
    assert not called

    assert (tmp_path / "teaming_plan.md").exists()
    plan_md = (tmp_path / "teaming_plan.md").read_text()
    assert "no compliance gaps" in plan_md.lower()
    assert job.teaming_plan is not None
    assert job.teaming_plan.recommendations == []


def test_proposal_open_questions_points_to_teaming_plan_when_recommendations_exist(
    tmp_path: Path, monkeypatch
):
    from bidwright.models import ProposalDraft

    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(
        orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_with_blocking_gap()
    )
    monkeypatch.setattr(
        orchestrator_module,
        "draft_teaming_plan",
        lambda requirements, compliance, profile_text: _fake_teaming_plan(),
    )
    monkeypatch.setattr(
        orchestrator_module,
        "draft_proposal",
        lambda req, profile, compliance: ProposalDraft(
            cover_letter="Dear City of Test,",
            executive_summary="Summary",
            technical_approach="Approach",
            qualifications_past_performance="Quals",
            compliance_matrix_notes="Notes",
            pricing_notes="Pricing",
            open_questions=["Confirm the NAICS gap decision."],
        ),
    )

    job = _build_job(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()
    orchestrator.tool.draft_teaming_plan_tool()
    orchestrator.tool.draft_proposal_document()

    assert any("teaming_plan.md" in q for q in job.proposal.open_questions)
    proposal_md = (tmp_path / "proposal_draft.md").read_text()
    assert "teaming_plan.md" in proposal_md
