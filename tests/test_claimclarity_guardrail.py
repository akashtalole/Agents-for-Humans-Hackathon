"""Offline tests for the deterministic guardrail scan
(claimclarity/tools/guardrail.py:scan_guaranteed_outcome_claims) - no LLM, no
network, runs against plain strings.
"""
from __future__ import annotations

from claimclarity.tools.guardrail import scan_guaranteed_outcome_claims


def test_guarantee_phrase_is_flagged():
    findings = scan_guaranteed_outcome_claims("We guarantee this appeal will be approved.")
    assert len(findings) >= 1
    assert all(f.rule == "guaranteed_outcome_claim" for f in findings)


def test_ordinary_confident_advocacy_language_is_not_flagged():
    findings = scan_guaranteed_outcome_claims(
        "This claim has a strong basis for appeal given the coding error identified in the investigation."
    )
    assert findings == []


def test_you_will_win_is_flagged():
    findings = scan_guaranteed_outcome_claims("You will win this case.")
    assert len(findings) == 1
    assert findings[0].rule == "guaranteed_outcome_claim"
    assert "will win" in findings[0].excerpt.lower()


def test_empty_text_returns_no_findings():
    assert scan_guaranteed_outcome_claims("") == []


def test_case_insensitive_and_multiple_matches():
    findings = scan_guaranteed_outcome_claims("WE GUARANTEE success. 100% covered, we promise.")
    rules_found = {f.rule for f in findings}
    assert rules_found == {"guaranteed_outcome_claim"}
    assert len(findings) == 3  # "guarantee", "100% covered", "we promise"
