"""Unit tests for claimclarity/agents/denial_auditor.py's compare_denial_findings
- a plain-code diff (matching by procedure_code, comparing classification),
no LLM involved, so this is fully offline and deterministic. See
tests/test_claimclarity_orchestrator_wiring.py for the orchestrator-level
wiring (escalation to needs_review) that sits on top of this.
"""
from __future__ import annotations

from claimclarity.agents.denial_auditor import compare_denial_findings
from claimclarity.models import Classification, DenialFindings, LineItemFinding


def _finding(code: str, classification: Classification, worth_appealing: bool = True) -> LineItemFinding:
    return LineItemFinding(
        procedure_code=code,
        classification=classification,
        evidence="test evidence",
        recommendation="test recommendation",
        worth_appealing=worth_appealing,
    )


def test_compare_denial_findings_full_agreement():
    first = DenialFindings(
        overall_recommendation="x",
        findings=[
            _finding("97110", Classification.BILLING_ERROR),
            _finding("97124", Classification.VALID_DENIAL, worth_appealing=False),
        ],
    )
    second = DenialFindings(
        overall_recommendation="y",
        findings=[
            _finding("97110", Classification.BILLING_ERROR),
            _finding("97124", Classification.VALID_DENIAL, worth_appealing=False),
        ],
    )
    result = compare_denial_findings(first, second)
    assert result.disagreement_count == 0
    assert len(result.items) == 2
    assert all(item.agrees for item in result.items)
    assert "agree" in result.summary.lower()


def test_compare_denial_findings_detects_classification_disagreement():
    first = DenialFindings(
        overall_recommendation="x",
        findings=[_finding("97110", Classification.BILLING_ERROR)],
    )
    second = DenialFindings(
        overall_recommendation="y",
        findings=[_finding("97110", Classification.VALID_DENIAL, worth_appealing=False)],
    )
    result = compare_denial_findings(first, second)
    assert result.disagreement_count == 1
    assert result.items[0].agrees is False
    assert result.items[0].first_classification == "billing_error"
    assert result.items[0].second_classification == "valid_denial"


def test_compare_denial_findings_handles_code_missing_from_auditor():
    first = DenialFindings(
        overall_recommendation="x",
        findings=[_finding("97110", Classification.BILLING_ERROR)],
    )
    second = DenialFindings(overall_recommendation="y", findings=[])
    result = compare_denial_findings(first, second)
    assert result.disagreement_count == 1
    assert result.items[0].second_classification == "not assessed by auditor"
    assert result.items[0].agrees is False
