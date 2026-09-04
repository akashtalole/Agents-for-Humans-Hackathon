"""Offline tests for the deterministic half of the guardrail check
(bidwright/tools/guardrail.py:scan_overclaim_patterns). No LLM, no network -
this function must behave predictably regardless of model behavior."""
from __future__ import annotations

from bidwright.tools.guardrail import scan_overclaim_patterns


def test_overclaim_flagged_when_blocking_gaps_present():
    text = "This company is fully compliant with all requirements."
    findings = scan_overclaim_patterns(text, has_blocking_gaps=True)
    assert any(f.rule == "overstated_compliance_claim" for f in findings)


def test_overclaim_not_flagged_without_blocking_gaps():
    text = "This company is fully compliant with all requirements."
    findings = scan_overclaim_patterns(text, has_blocking_gaps=False)
    assert not any(f.rule == "overstated_compliance_claim" for f in findings)


def test_guaranteed_outcome_flagged_regardless_of_blocking_gaps():
    text = "We are guaranteed to win this contract."
    findings_with_gaps = scan_overclaim_patterns(text, has_blocking_gaps=True)
    findings_without_gaps = scan_overclaim_patterns(text, has_blocking_gaps=False)
    assert any(f.rule == "guaranteed_outcome_claim" for f in findings_with_gaps)
    assert any(f.rule == "guaranteed_outcome_claim" for f in findings_without_gaps)


def test_clean_hedge_worded_text_has_zero_findings():
    text = (
        "We believe our qualifications align well with this project's needs, and we "
        "look forward to discussing our approach further."
    )
    assert scan_overclaim_patterns(text, has_blocking_gaps=True) == []
    assert scan_overclaim_patterns(text, has_blocking_gaps=False) == []


def test_multiple_overclaim_phrases_each_produce_a_finding():
    text = "We are fully compliant and also meets all requirements of this RFP."
    findings = scan_overclaim_patterns(text, has_blocking_gaps=True)
    rules = [f.rule for f in findings]
    assert rules.count("overstated_compliance_claim") == 2


def test_excerpt_is_the_matched_phrase():
    text = "Our firm has no compliance gaps whatsoever."
    findings = scan_overclaim_patterns(text, has_blocking_gaps=True)
    assert len(findings) == 1
    assert findings[0].excerpt.lower() == "no compliance gaps"
