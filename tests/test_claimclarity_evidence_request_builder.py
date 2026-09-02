"""Wiring tests for the Physician Evidence Request Builder - same discipline
as tests/test_claimclarity_orchestrator_wiring.py: use `agent.tool.<name>(...)`
to exercise the real tool-call plumbing without hitting a live model.
"""
from __future__ import annotations

from pathlib import Path

import claimclarity.orchestrator as orchestrator_module
from claimclarity.models import (
    Classification,
    ClaimLineItem,
    ClaimRecord,
    DenialFindings,
    EvidenceRequestItem,
    LineItemFinding,
    PhysicianEvidenceRequest,
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
        line_items=[
            ClaimLineItem(procedure_code="72148", diagnosis_code_billed="M54.5", carc_code="CO-50"),
            ClaimLineItem(procedure_code="97124", diagnosis_code_billed="M54.5", carc_code="CO-96"),
        ],
    )


def _fake_medical_necessity_findings() -> DenialFindings:
    """One item genuinely denied for lack of medical necessity documentation
    (worth appealing, and physician evidence could fix it), one item that's a
    pure plan exclusion (physician evidence can't fix that)."""
    return DenialFindings(
        overall_recommendation="Appeal the imaging denial with the right documentation; skip the massage denial.",
        findings=[
            LineItemFinding(
                procedure_code="72148",
                classification=Classification.DOCUMENTATION_GAP,
                evidence="Denied as 'not medically necessary' - lumbar MRI without documented conservative "
                "treatment first per plan medical necessity criteria.",
                recommendation="Appeal once conservative-treatment documentation is obtained.",
                worth_appealing=True,
            ),
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="Plan explicitly excludes massage therapy regardless of documentation.",
                recommendation="Do not appeal - genuine plan exclusion.",
                worth_appealing=False,
            ),
        ],
    )


def _fake_billing_and_exclusion_findings() -> DenialFindings:
    """Neither item turns on medical necessity: one's a mechanical coding fix,
    the other's a flat plan exclusion. No physician evidence request should be
    generated for either."""
    return DenialFindings(
        overall_recommendation="Appeal line 1 with the corrected code; skip line 2.",
        findings=[
            LineItemFinding(
                procedure_code="72148",
                classification=Classification.BILLING_ERROR,
                evidence="M54.5 is a non-billable category header per lookup_icd10_code.",
                corrected_diagnosis_code="M54.51",
                recommendation="Appeal with corrected code M54.51.",
                worth_appealing=True,
            ),
            LineItemFinding(
                procedure_code="97124",
                classification=Classification.VALID_DENIAL,
                evidence="Plan explicitly excludes massage therapy regardless of documentation.",
                recommendation="Do not appeal - genuine plan exclusion.",
                worth_appealing=False,
            ),
        ],
    )


def _fake_evidence_request() -> PhysicianEvidenceRequest:
    return PhysicianEvidenceRequest(
        items=[
            EvidenceRequestItem(
                procedure_code="72148",
                evidence_needed="Documented failure of at least 6 weeks of conservative physical therapy prior "
                "to imaging.",
                why_insurer_requires_it="General standard-of-care reasoning: imaging is typically only medically "
                "necessary after conservative treatment fails, since the plan's own terms don't state a specific "
                "criterion here.",
                physician_office_justification="Pull PT visit notes and dates from the chart showing the 6-week "
                "course and its outcome.",
            )
        ],
        cover_letter_to_physician="Dear Dr. Office, please send documentation of Maria Chen's physical therapy "
        "history before her 2026-12-28 appeal deadline...",
        patient_followup_checklist=[
            "Confirm the office received this request.",
            "Follow up if you haven't heard back within 5 business days.",
        ],
        rationale="The imaging denial turns on missing conservative-treatment documentation, which your doctor's "
        "office can supply.",
    )


def _fake_empty_evidence_request() -> PhysicianEvidenceRequest:
    return PhysicianEvidenceRequest(
        items=[],
        cover_letter_to_physician="",
        patient_followup_checklist=[],
        rationale="Neither denial here turns on missing physician documentation - one is a coding fix, the "
        "other a flat plan exclusion, so no physician evidence request is needed.",
    )


def test_evidence_request_happy_path_writes_nonempty_items(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())
    monkeypatch.setattr(
        orchestrator_module, "investigate_denial", lambda claim: _fake_medical_necessity_findings()
    )
    monkeypatch.setattr(
        orchestrator_module,
        "build_physician_evidence_request",
        lambda claim, findings: _fake_evidence_request(),
    )

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    orchestrator.tool.investigate_denial_tool()
    result = orchestrator.tool.build_physician_evidence_request_tool()

    assert "physician_evidence_request.md" in _tool_text(result)
    assert "1 line item(s)" in _tool_text(result)

    assert (tmp_path / "physician_evidence_request.md").exists()
    content = (tmp_path / "physician_evidence_request.md").read_text()
    assert "72148" in content
    assert "conservative physical therapy" in content
    assert "Dear Dr. Office" in content

    assert case.physician_evidence_request is not None
    assert len(case.physician_evidence_request.items) == 1

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "physician_evidence_request.md" in decisions
    assert "Before you appeal" in decisions


def test_no_qualifying_findings_is_graceful_not_fabricated(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())
    monkeypatch.setattr(
        orchestrator_module, "investigate_denial", lambda claim: _fake_billing_and_exclusion_findings()
    )
    monkeypatch.setattr(
        orchestrator_module,
        "build_physician_evidence_request",
        lambda claim, findings: _fake_empty_evidence_request(),
    )

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    orchestrator.tool.investigate_denial_tool()
    result = orchestrator.tool.build_physician_evidence_request_tool()

    assert "physician_evidence_request.md" in _tool_text(result)
    assert "none needed" in _tool_text(result).lower()

    assert (tmp_path / "physician_evidence_request.md").exists()
    content = (tmp_path / "physician_evidence_request.md").read_text()
    assert "No denied line item here turns on missing physician documentation" in content
    assert "coding fix" in content

    assert case.physician_evidence_request is not None
    assert case.physician_evidence_request.items == []
    assert case.physician_evidence_request.cover_letter_to_physician == ""

    decisions = (tmp_path / "decisions_needed.md").read_text()
    assert "No denied item here needs extra documentation" in decisions


def test_evidence_request_before_investigate_returns_error_not_exception(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(orchestrator_module, "analyze_claim", lambda text: _fake_claim())

    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    orchestrator.tool.load_claim_documents()
    orchestrator.tool.extract_claim_details()
    result = orchestrator.tool.build_physician_evidence_request_tool()

    assert "Error" in _tool_text(result)
    assert "investigate_denial_tool" in _tool_text(result)
    assert case.physician_evidence_request is None
    assert not (tmp_path / "physician_evidence_request.md").exists()


def test_evidence_request_before_extract_returns_error(tmp_path: Path):
    case = ClaimCase(documents_paths=DOCUMENT_PATHS, output_dir=str(tmp_path))
    orchestrator = build_orchestrator(case)
    result = orchestrator.tool.build_physician_evidence_request_tool()
    assert "Error" in _tool_text(result)
