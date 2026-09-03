"""Offline tests for the deterministic half of the guardrail check
(glacierwatch/tools/guardrail.py:scan_prediction_language). No LLM, no
network - this function must behave predictably regardless of model
behavior, since it's the last, code-enforced line of defense for
GlacierWatch's one non-negotiable rule: never predict if, when, or where a
hazard will occur."""
from __future__ import annotations

from glacierwatch.tools.guardrail import scan_prediction_language


def test_will_occur_is_flagged_as_prediction_language():
    text = "A glacial lake outburst flood will occur within the next 48 hours."
    findings = scan_prediction_language(text)
    assert len(findings) == 1
    assert findings[0].rule == "prediction_language"
    assert "will occur" in findings[0].excerpt.lower()


def test_hedged_documented_risk_language_has_zero_findings():
    text = (
        "This site is documented at elevated risk based on published hazard "
        "assessments; monitor conditions closely."
    )
    assert scan_prediction_language(text) == []


def test_about_to_breach_is_flagged():
    text = "Residents should evacuate now, the lake is about to breach."
    findings = scan_prediction_language(text)
    assert len(findings) == 1
    assert findings[0].rule == "prediction_language"
    assert "about to breach" in findings[0].excerpt.lower()


def test_case_insensitive_match():
    text = "The dam WILL BREACH imminently."
    findings = scan_prediction_language(text)
    assert any("will breach" in f.excerpt.lower() for f in findings)


def test_multiple_prediction_phrases_each_produce_a_finding():
    text = "Experts expect a flood soon, and the lake is certain to fail catastrophically."
    findings = scan_prediction_language(text)
    rules = [f.rule for f in findings]
    assert rules.count("prediction_language") == 2


def test_explanation_mentions_decision_support_not_prediction():
    text = "This will not occur without warning."
    findings = scan_prediction_language(text)
    assert len(findings) == 1
    assert "decision-support" in findings[0].explanation.lower()
