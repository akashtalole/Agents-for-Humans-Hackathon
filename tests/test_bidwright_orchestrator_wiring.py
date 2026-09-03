"""Wiring tests for BidWright's orchestrator: prove the tool-call plumbing
(state transitions, argument passing, file writes, error paths) is correct
using `agent.tool.<name>(...)` - Strands' documented way to invoke a
registered tool directly, bypassing the model entirely.

This does NOT test whether the orchestrator LLM chooses the right tools in
the right order (that needs a real model - see
tests/test_pipeline_integration.py, opt-in with BIDWRIGHT_RUN_INTEGRATION=1).
It tests that IF the tools are called in the documented order, the pipeline
behaves correctly - which is exactly the part that's easy to get subtly wrong
(wrong file path, wrong field passed between steps, a step silently
no-op'ing) and doesn't require any API key or network access to verify.
"""
from __future__ import annotations

from pathlib import Path

import bidwright.orchestrator as orchestrator_module
from bidwright.models import (
    ChecklistItem,
    ComplianceGap,
    ComplianceReport,
    ProposalDraft,
    RFPRequirements,
    Severity,
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


def _fake_compliance_with_blocking_gap() -> ComplianceReport:
    return ComplianceReport(
        overall_status="gaps_found",
        met_requirements=["Business license"],
        gaps=[
            ComplianceGap(
                requirement="General liability minimum $2,000,000",
                status="gap",
                severity=Severity.BLOCKING,
                detail="Company carries $1,000,000 per occurrence.",
                recommendation="Increase coverage before the deadline.",
            )
        ],
    )


def _fake_compliance_ready() -> ComplianceReport:
    return ComplianceReport(overall_status="ready", met_requirements=["Everything"], gaps=[])


def _fake_proposal() -> ProposalDraft:
    return ProposalDraft(
        cover_letter="Dear City of Test,",
        executive_summary="Summary",
        technical_approach="Approach",
        qualifications_past_performance="Quals",
        compliance_matrix_notes="Notes",
        pricing_notes="Pricing",
        open_questions=["Confirm insurance gap decision."],
    )


def test_full_pipeline_wiring_writes_all_expected_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(
        orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_with_blocking_gap()
    )
    monkeypatch.setattr(
        orchestrator_module, "draft_proposal", lambda req, profile, compliance: _fake_proposal()
    )

    job = BidJob(
        rfp_path=RFP_PATH,
        profile_path=PROFILE_PATH,
        output_dir=str(tmp_path),
        history_file=str(tmp_path / "history.json"),
    )
    orchestrator = build_orchestrator(job)

    assert _tool_text(orchestrator.tool.load_rfp_and_profile()).startswith("Loaded RFP")
    assert "Test Project" in _tool_text(orchestrator.tool.extract_rfp_requirements())
    assert "gaps_found" in _tool_text(orchestrator.tool.check_company_compliance())
    assert "bid(s) on record" in _tool_text(orchestrator.tool.record_bid_and_check_portfolio_trends())
    assert "Calendar reminder saved" in _tool_text(orchestrator.tool.create_submission_deadline_reminder())
    assert "proposal_draft.md" in _tool_text(orchestrator.tool.draft_proposal_document())

    for filename in (
        "requirements.md",
        "compliance_report.md",
        "decisions_needed.md",
        "portfolio_insights.md",
        "proposal_draft.md",
        "submission_deadline.ics",
    ):
        assert (tmp_path / filename).exists(), f"{filename} was not written"

    assert job.requirements.project_title == "Test Project"
    assert job.compliance.overall_status == "gaps_found"
    assert job.proposal.cover_letter == "Dear City of Test,"

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "1 blocking gap" in decisions
    assert "Increase coverage before the deadline." in decisions


def test_decisions_needed_says_ready_when_no_blocking_gaps(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_ready())
    monkeypatch.setattr(orchestrator_module, "draft_proposal", lambda req, profile, compliance: _fake_proposal())

    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "no blocking gaps found" in decisions.lower()


def test_extract_before_load_returns_error_not_exception(tmp_path: Path):
    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(job)
    result = orchestrator.tool.extract_rfp_requirements()
    assert result["status"] == "success"
    assert "Error" in _tool_text(result)
    assert "load_rfp_and_profile" in _tool_text(result)


def test_check_compliance_before_extract_returns_error(tmp_path: Path):
    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(job)
    result = orchestrator.tool.check_company_compliance()
    assert "Error" in _tool_text(result)
    assert "extract_rfp_requirements" in _tool_text(result)


def test_draft_proposal_before_compliance_returns_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())

    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    result = orchestrator.tool.draft_proposal_document()
    assert "Error" in _tool_text(result)


def test_deadline_reminder_before_extract_returns_error(tmp_path: Path):
    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(job)
    result = orchestrator.tool.create_submission_deadline_reminder()
    assert "Error" in _tool_text(result)


def test_explicit_none_callback_handler_is_actually_silent(tmp_path: Path):
    """Regression test: Strands' Agent treats an *omitted* callback_handler as
    "use my verbose default printer" but an *explicit* None as "stay silent"
    (null_callback_handler). build_orchestrator must forward None as None, not
    drop the kwarg - otherwise --quiet silently does nothing."""
    from strands.handlers.callback_handler import null_callback_handler

    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    quiet_orchestrator = build_orchestrator(job, callback_handler=None)
    assert quiet_orchestrator.callback_handler is null_callback_handler


def test_custom_callback_handler_is_used(tmp_path: Path):
    events = []

    def handler(**kwargs):
        events.append(kwargs)

    job = BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(job, callback_handler=handler)
    assert orchestrator.callback_handler is handler
