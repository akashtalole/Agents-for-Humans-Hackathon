"""Wiring tests for ClaimClarity's orchestrator - same discipline as
tests/test_bidwright_orchestrator_wiring.py: use `agent.tool.<name>(...)`
(Strands' documented direct tool-call interface) to exercise the real
tool-call plumbing without hitting a live model. See that file's docstring
for what this does and doesn't prove.
"""
from __future__ import annotations

from pathlib import Path

import claimclarity.orchestrator as orchestrator_module
from claimclarity.models import (
    AppealPackage,
    Classification,
    ClaimLineItem,
    ClaimRecord,
    DenialFindings,
    EscalationPackage,
    LineItemFinding,
)
from claimclarity.orchestrator import ClaimCase, build_orchestrator

DOCUMENT_PATHS = [
    "examples/claimclarity/denial_notice.md",
    "examples/claimclarity/plan_summary_of_benefits.md",
    "examples/claimclarity/medical_record_excerpt.md",
]


def _tool_text(result) -> str:
    return result["content"][0]["text"]


def _fake_claim() -> ClaimRecord:
    return ClaimRecord(
        patient_name="Maria Chen",
        insurer_name="Heartland Mutual Health Plan",
        claim_number="CLM-2026-0619884",
        appeal_deadline="2026-12-28",
        appeal_submission_method="member.heartlandmutual.example/appeals",
        line_items=[
            ClaimLineItem(procedure_code="97110", diagnosis_code_billed="M54.5", carc_code="CO-16"),
            ClaimLineItem(procedure_code="97124", diagnosis_code_billed="M54.5", carc_code="CO-96"),
        ],
    )


def _fake_mixed_findings() -> DenialFindings:
    return DenialFindings(
        overall_recommendation="Appeal line 97110, skip 97124.",
        findings=[
            LineItemFinding(
                procedure_code="97110",
                classification=Classification.BILLING_ERROR,
                evidence="M54.5 is a non-billable category header per lookup_icd10_code.",
                corrected_diagnosis_code="M54.51",
                recommendation="Appeal with corrected code M54.51.",
                worth_appealing=True,
            ),
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="Plan explicitly excludes massage therapy regardless of necessity.",
                recommendation="Do not appeal - genuine plan exclusion.",
                worth_appealing=False,
            ),
        ],
    )


def _fake_appeal() -> AppealPackage:
    return AppealPackage(
        appeal_letter="Dear Heartland Mutual Appeals Department, ...",
        non_appeal_explanation="Massage therapy is excluded under your plan regardless of documentation.",
        open_questions=["Confirm you still want to appeal given the 97124 exclusion."],
    )


def _fake_escalation() -> EscalationPackage:
    return EscalationPackage(
        eligible_for_external_review=True,
        external_review_deadline="2027-04-28",
        external_review_request_letter="Dear Heartland Mutual External Review Coordinator, ...",
        state_doi_complaint_letter=None,
        regulatory_basis=["General ACA external review framework (45 CFR 147.136)."],
        escalation_checklist=["Gather your internal appeal denial letter.", "Submit the external review request."],
        rationale="97110 was denied for a mechanical coding reason and is still worth escalating if the internal appeal doesn't fix it.",
    )


def test_full_pipeline_wiring_writes_all_expected_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())
    monkeypatch.setattr(orchestrator_module, "investigate_denial", lambda claim: _fake_mixed_findings())
    monkeypatch.setattr(orchestrator_module, "draft_appeal", lambda claim, findings: _fake_appeal())
    monkeypatch.setattr(
        orchestrator_module, "prepare_escalation", lambda claim, findings, appeal, doi_info: _fake_escalation()
    )

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)

    assert "Loaded 3 document(s)" in _tool_text(orchestrator.tool.load_claim_documents())
    assert "CLM-2026-0619884" in _tool_text(orchestrator.tool.extract_claim_details())
    assert "saved" in _tool_text(orchestrator.tool.create_appeal_deadline_reminder_tool()).lower()
    assert "1 of 2" in _tool_text(orchestrator.tool.investigate_denial_tool())
    assert "appeal_package.md" in _tool_text(orchestrator.tool.draft_appeal_package())
    escalation_result = _tool_text(orchestrator.tool.prepare_external_review_escalation())
    assert "escalation_package.md" in escalation_result
    assert "recommended" in escalation_result

    for filename in (
        "claim_summary.md",
        "denial_findings.md",
        "decisions_needed.md",
        "appeal_package.md",
        "appeal_deadline.ics",
        "escalation_package.md",
        "external_review_deadline.ics",
    ):
        assert (tmp_path / filename).exists(), f"{filename} was not written"

    assert case.claim.claim_number == "CLM-2026-0619884"
    assert len(case.findings.findings) == 2
    assert case.appeal.appeal_letter.startswith("Dear Heartland Mutual")
    assert case.escalation.eligible_for_external_review is True

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "1 item(s) look worth appealing" in decisions
    assert "Do not appeal - genuine plan exclusion." in decisions
    assert "escalation_package.md" in decisions

    escalation_md = (tmp_path / "escalation_package.md").read_text()
    assert "External Review Request Letter" in escalation_md
    assert "Dear Heartland Mutual External Review Coordinator" in escalation_md
    assert "Not drafted" in escalation_md  # no DOI complaint basis in the fake findings


def test_extract_before_load_returns_error_not_exception(tmp_path: Path):
    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    result = orchestrator.tool.extract_claim_details()
    assert result["status"] == "success"
    assert "Error" in _tool_text(result)
    assert "load_claim_documents" in _tool_text(result)


def test_deadline_reminder_before_extract_returns_error(tmp_path: Path):
    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    result = orchestrator.tool.create_appeal_deadline_reminder_tool()
    assert "Error" in _tool_text(result)


def test_investigate_before_extract_returns_error(tmp_path: Path):
    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    result = orchestrator.tool.investigate_denial_tool()
    assert "Error" in _tool_text(result)


def test_draft_appeal_before_investigate_returns_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    result = orchestrator.tool.draft_appeal_package()
    assert "Error" in _tool_text(result)


def test_escalation_before_draft_appeal_returns_error_not_exception(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())
    monkeypatch.setattr(orchestrator_module, "investigate_denial", lambda claim: _fake_mixed_findings())

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    orchestrator.tool.investigate_denial_tool()
    result = orchestrator.tool.prepare_external_review_escalation()
    assert "Error" in _tool_text(result)
    assert "draft_appeal_package" in _tool_text(result)
    assert not (tmp_path / "escalation_package.md").exists()


def test_escalation_falls_back_to_default_doi_when_state_not_extracted(tmp_path: Path, monkeypatch):
    """ClaimRecord.state is often blank (the analyzer can't always tell the
    patient's state from the documents) - the escalation step must still run
    cleanly against the federal DEFAULT entry rather than crashing."""
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())
    monkeypatch.setattr(orchestrator_module, "investigate_denial", lambda claim: _fake_mixed_findings())
    monkeypatch.setattr(orchestrator_module, "draft_appeal", lambda claim, findings: _fake_appeal())

    seen_doi_info = {}

    def fake_prepare_escalation(claim, findings, appeal, doi_info):
        seen_doi_info["value"] = doi_info
        return _fake_escalation()

    monkeypatch.setattr(orchestrator_module, "prepare_escalation", fake_prepare_escalation)

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    assert case.claim is None
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    assert case.claim.state == ""  # _fake_claim() never sets it
    orchestrator.tool.investigate_denial_tool()
    orchestrator.tool.draft_appeal_package()
    result = orchestrator.tool.prepare_external_review_escalation()

    assert "escalation_package.md" in _tool_text(result)
    assert seen_doi_info["value"].state_code == "DEFAULT"
    assert (tmp_path / "escalation_package.md").exists()
    assert (tmp_path / "external_review_deadline.ics").exists()


def test_decisions_needed_when_nothing_worth_appealing(tmp_path: Path, monkeypatch):
    all_denied = DenialFindings(
        overall_recommendation="Neither item is worth appealing.",
        findings=[
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="Plan exclusion.",
                recommendation="Do not appeal.",
                worth_appealing=False,
            )
        ],
    )
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())
    monkeypatch.setattr(orchestrator_module, "investigate_denial", lambda claim: all_denied)

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    orchestrator.tool.investigate_denial_tool()

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "nothing here looks worth appealing" in decisions.lower()


def test_explicit_none_callback_handler_is_actually_silent(tmp_path: Path):
    """Regression test: Strands' Agent treats an *omitted* callback_handler as
    "use my verbose default printer" but an *explicit* None as "stay silent"
    (null_callback_handler). build_orchestrator must forward None as None, not
    drop the kwarg - otherwise --quiet silently does nothing."""
    from strands.handlers.callback_handler import null_callback_handler

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    quiet_orchestrator = build_orchestrator(case, callback_handler=None)
    assert quiet_orchestrator.callback_handler is null_callback_handler


def test_custom_callback_handler_is_used(tmp_path: Path):
    events = []

    def handler(**kwargs):
        events.append(kwargs)

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case, callback_handler=handler)
    assert orchestrator.callback_handler is handler
