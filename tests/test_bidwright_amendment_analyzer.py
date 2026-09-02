"""Wiring tests for BidWright's amendment/addendum impact analysis, following
the same offline `agent.tool.<name>(...)` direct-call pattern as
tests/test_bidwright_orchestrator_wiring.py - no API key or network access
required.
"""
from __future__ import annotations

from pathlib import Path

import bidwright.orchestrator as orchestrator_module
from bidwright.models import (
    AmendmentImpact,
    ChecklistItem,
    ComplianceGap,
    ComplianceReport,
    ModifiedRequirement,
    RFPRequirements,
    Severity,
)
from bidwright.orchestrator import BidJob, build_orchestrator

RFP_PATH = "examples/sample_rfp.md"
PROFILE_PATH = "examples/company_profile.json"
# No dedicated amendment fixture exists yet - any real file works for this test
# since analyze_amendment itself is monkeypatched and read_document just needs
# something on disk to read.
AMENDMENT_PATH = "examples/sample_rfp.md"


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


def _fake_amendment_impact_blocking() -> AmendmentImpact:
    return AmendmentImpact(
        summary="The deadline moved up one week and a new bonding requirement was added.",
        urgency=Severity.BLOCKING,
        deadline_changed=True,
        new_deadline="2026-09-23T17:00",
        new_requirements=[ChecklistItem(item="Submit a $50,000 performance bond")],
        removed_requirements=[],
        modified_requirements=[
            ModifiedRequirement(
                item="Insurance minimum",
                previous="$1,000,000 general liability",
                updated="$2,500,000 general liability",
                notes="Raised, not lowered.",
            )
        ],
        compliance_impact="The prior 'General liability minimum $2,000,000' gap is now understated - "
        "the real minimum is $2,500,000.",
        proposal_sections_requiring_revision=["compliance_matrix_notes"],
        recommendation="Confirm bonding capacity and update the insurance gap before the new deadline.",
    )


def _fake_amendment_impact_minor() -> AmendmentImpact:
    return AmendmentImpact(
        summary="A typo in the point of contact's phone number was corrected.",
        urgency=Severity.INFO,
        deadline_changed=False,
        new_deadline=None,
        recommendation="No action needed.",
    )


def _build_job_with_amendment(tmp_path: Path, amendment_path: str | None = AMENDMENT_PATH) -> BidJob:
    return BidJob(
        rfp_path=RFP_PATH,
        profile_path=PROFILE_PATH,
        output_dir=str(tmp_path),
        amendment_path=amendment_path,
    )


def test_analyze_amendment_happy_path_writes_file_and_updates_job(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(
        orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_with_blocking_gap()
    )
    monkeypatch.setattr(
        orchestrator_module,
        "analyze_amendment",
        lambda original_requirements, original_compliance, amendment_text: _fake_amendment_impact_blocking(),
    )

    job = _build_job_with_amendment(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    result = orchestrator.tool.analyze_rfp_amendment()
    text = _tool_text(result)
    assert "Amendment analyzed" in text
    assert "amendment_impact.md" in text

    assert (tmp_path / "amendment_impact.md").exists()
    assert job.amendment_impact is not None
    assert job.amendment_impact.urgency == Severity.BLOCKING
    assert job.amendment_impact.deadline_changed is True

    impact_md = (tmp_path / "amendment_impact.md").read_text()
    assert "$50,000 performance bond" in impact_md
    assert "Insurance minimum" in impact_md

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "AMENDMENT ALERT" in decisions
    assert "BLOCKING" in decisions
    assert "Confirm bonding capacity" in decisions


def test_analyze_amendment_before_extract_requirements_returns_clean_error(tmp_path: Path):
    job = _build_job_with_amendment(tmp_path)
    orchestrator = build_orchestrator(job)
    result = orchestrator.tool.analyze_rfp_amendment()
    text = _tool_text(result)
    assert "Error" in text
    assert "extract_rfp_requirements" in text
    assert job.amendment_impact is None


def test_analyze_amendment_with_no_amendment_path_is_a_clean_noop(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())

    job = _build_job_with_amendment(tmp_path, amendment_path=None)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()

    result = orchestrator.tool.analyze_rfp_amendment()
    text = _tool_text(result)

    assert result["status"] == "success"
    assert "Error" not in text
    assert "nothing to do" in text.lower()
    assert job.amendment_impact is None
    assert not (tmp_path / "amendment_impact.md").exists()


def test_minor_amendment_does_not_add_alert_section_to_decisions_needed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_with_blocking_gap())
    monkeypatch.setattr(
        orchestrator_module,
        "analyze_amendment",
        lambda original_requirements, original_compliance, amendment_text: _fake_amendment_impact_minor(),
    )

    job = _build_job_with_amendment(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()
    orchestrator.tool.analyze_rfp_amendment()

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "AMENDMENT ALERT" not in decisions


def test_analyze_amendment_before_compliance_check_still_works(tmp_path: Path, monkeypatch):
    """Amendments can arrive before compliance has even been checked once -
    the tool should still run using whatever prior compliance exists (None)."""
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(
        orchestrator_module,
        "analyze_amendment",
        lambda original_requirements, original_compliance, amendment_text: _fake_amendment_impact_blocking(),
    )

    job = _build_job_with_amendment(tmp_path)
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()

    result = orchestrator.tool.analyze_rfp_amendment()
    assert "Amendment analyzed" in _tool_text(result)
    assert job.amendment_impact is not None
    # No compliance report exists yet, so decisions_needed.md is not rewritten
    # by this tool - check_company_compliance is what creates it.
    assert not (tmp_path / "decisions_needed.md").exists()
