"""Wiring tests for BidWright's Portfolio Insights (cross-bid history +
recurring gap detection), following the same offline
`agent.tool.<name>(...)` direct-call pattern as
tests/test_bidwright_orchestrator_wiring.py - no API key or network access
required.
"""
from __future__ import annotations

from pathlib import Path

import bidwright.orchestrator as orchestrator_module
from bidwright.models import (
    BidHistory,
    BidHistoryEntry,
    BidHistoryGap,
    ChecklistItem,
    ComplianceGap,
    ComplianceReport,
    RFPRequirements,
    Severity,
)
from bidwright.orchestrator import BidJob, build_orchestrator
from bidwright.tools.history import save_history

RFP_PATH = "examples/sample_rfp.md"
PROFILE_PATH = "examples/company_profile.json"


def _tool_text(result) -> str:
    return result["content"][0]["text"]


def _fake_requirements(title="Test Project", org="City of Test") -> RFPRequirements:
    return RFPRequirements(
        project_title=title,
        issuing_organization=org,
        submission_deadline="2026-09-30T17:00",
        checklist=[ChecklistItem(item="Sign cover letter")],
    )


def _fake_compliance_with_blocking_gap(requirement="Insufficient bonding capacity") -> ComplianceReport:
    return ComplianceReport(
        overall_status="gaps_found",
        met_requirements=["Business license"],
        gaps=[
            ComplianceGap(
                requirement=requirement,
                status="gap",
                severity=Severity.BLOCKING,
                detail="Company profile shows no evidence of this.",
                recommendation="Address before the deadline.",
            )
        ],
    )


def _fake_compliance_ready() -> ComplianceReport:
    return ComplianceReport(overall_status="ready", met_requirements=["Everything"], gaps=[])


def _build_job(tmp_path: Path, history_file: str | None = None) -> BidJob:
    kwargs = {"history_file": history_file} if history_file else {}
    return BidJob(rfp_path=RFP_PATH, profile_path=PROFILE_PATH, output_dir=str(tmp_path), **kwargs)


def test_record_before_compliance_check_returns_clean_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    history_path = tmp_path / "history.json"

    job = _build_job(tmp_path, history_file=str(history_path))
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()

    result = orchestrator.tool.record_bid_and_check_portfolio_trends()
    text = _tool_text(result)
    assert "Error" in text
    assert "check_company_compliance" in text
    assert not history_path.exists()
    assert not (tmp_path / "portfolio_insights.md").exists()
    assert job.history.entries == []


def test_first_ever_run_is_a_graceful_not_enough_history_message(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(
        orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_with_blocking_gap()
    )
    history_path = tmp_path / "history.json"

    job = _build_job(tmp_path, history_file=str(history_path))
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    result = orchestrator.tool.record_bid_and_check_portfolio_trends()
    text = _tool_text(result)
    assert "Error" not in text
    assert "1 bid(s) on record" in text
    assert "0 recurring gap(s)" in text

    assert history_path.exists()
    assert job.portfolio_insights == []
    assert len(job.history.entries) == 1

    insights_md = (tmp_path / "portfolio_insights.md").read_text()
    assert "not enough bid history" in insights_md.lower()
    # No fabricated recurrence table on a first-ever run.
    assert "Insufficient bonding capacity" not in insights_md


def test_recurring_gap_detected_from_synthetic_history(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        orchestrator_module, "analyze_rfp", lambda text: _fake_requirements(title="Landscaping RFP #3", org="Third City")
    )
    monkeypatch.setattr(
        orchestrator_module,
        "check_compliance",
        lambda req, profile: _fake_compliance_with_blocking_gap("Insufficient bonding capacity"),
    )
    history_path = tmp_path / "history.json"
    save_history(
        str(history_path),
        BidHistory(
            entries=[
                BidHistoryEntry(
                    project_title="Landscaping RFP #1",
                    issuing_organization="First City",
                    run_at="2026-01-01T00:00:00Z",
                    overall_status="gaps_found",
                    gaps=[BidHistoryGap(requirement="Insufficient bonding capacity", severity=Severity.BLOCKING)],
                ),
                BidHistoryEntry(
                    project_title="Landscaping RFP #2",
                    issuing_organization="Second City",
                    run_at="2026-02-01T00:00:00Z",
                    overall_status="ready",
                    gaps=[],
                ),
            ]
        ),
    )

    job = _build_job(tmp_path, history_file=str(history_path))
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    result = orchestrator.tool.record_bid_and_check_portfolio_trends()
    text = _tool_text(result)
    assert "3 bid(s) on record" in text
    assert "1 recurring gap(s)" in text

    assert len(job.portfolio_insights) == 1
    insight = job.portfolio_insights[0]
    assert insight.requirement == "Insufficient bonding capacity"
    assert insight.occurrences == 2
    assert insight.first_seen_rfp == "Landscaping RFP #1 (First City)"
    assert insight.most_recent_rfp == "Landscaping RFP #3 (Third City)"

    insights_md = (tmp_path / "portfolio_insights.md").read_text()
    assert "Insufficient bonding capacity" in insights_md
    assert "2 of last" in insights_md

    # This run's outcome was persisted back to disk alongside the two priors.
    reloaded = BidHistory.model_validate_json(history_path.read_text())
    assert len(reloaded.entries) == 3


def test_no_recurrence_reports_cleanly_with_prior_history(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_rfp", lambda text: _fake_requirements())
    monkeypatch.setattr(orchestrator_module, "check_compliance", lambda req, profile: _fake_compliance_ready())
    history_path = tmp_path / "history.json"
    save_history(
        str(history_path),
        BidHistory(
            entries=[
                BidHistoryEntry(
                    project_title="Landscaping RFP #1",
                    issuing_organization="First City",
                    run_at="2026-01-01T00:00:00Z",
                    overall_status="ready",
                    gaps=[],
                )
            ]
        ),
    )

    job = _build_job(tmp_path, history_file=str(history_path))
    orchestrator = build_orchestrator(job)
    orchestrator.tool.load_rfp_and_profile()
    orchestrator.tool.extract_rfp_requirements()
    orchestrator.tool.check_company_compliance()

    result = orchestrator.tool.record_bid_and_check_portfolio_trends()
    text = _tool_text(result)
    assert "2 bid(s) on record" in text
    assert "0 recurring gap(s)" in text
    assert job.portfolio_insights == []

    insights_md = (tmp_path / "portfolio_insights.md").read_text()
    assert "nothing recurring" in insights_md.lower()
