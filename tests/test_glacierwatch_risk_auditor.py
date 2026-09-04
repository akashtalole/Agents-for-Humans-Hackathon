"""Unit tests for glacierwatch/agents/risk_auditor.py's compare_site_risk -
a plain-code diff (matching by site_id, comparing priority_level and
adopting the MORE CAUTIOUS of the two), no LLM involved, so this is fully
offline and deterministic. See tests/test_glacierwatch_orchestrator_wiring.py
for the orchestrator-level wiring (escalating run.briefs) that sits on top
of this.
"""
from __future__ import annotations

from glacierwatch.agents.risk_auditor import compare_site_risk
from glacierwatch.models import PriorityLevel, SiteRiskBrief


def _brief(priority: PriorityLevel) -> SiteRiskBrief:
    return SiteRiskBrief(
        site_id="gepang-gath",
        site_name="Gepang Gath Lake",
        priority_level=priority,
        rationale="test rationale",
        active_triggers=[],
        recommended_action="test action",
    )


def test_compare_site_risk_agreement():
    result = compare_site_risk(_brief(PriorityLevel.ELEVATED), _brief(PriorityLevel.ELEVATED))
    assert result.agrees is True
    assert result.adopted_priority == "elevated"
    assert "agree" in result.note.lower()


def test_compare_site_risk_adopts_higher_when_auditor_more_cautious():
    first = _brief(PriorityLevel.ROUTINE)
    second = _brief(PriorityLevel.PRIORITY)
    result = compare_site_risk(first, second)
    assert result.agrees is False
    assert result.first_priority == "routine"
    assert result.second_priority == "priority"
    # The more cautious (higher) rating always wins, regardless of which
    # side found it - understating risk here is worse than overstating it.
    assert result.adopted_priority == "priority"
    assert "higher" in result.note.lower()


def test_compare_site_risk_keeps_original_when_first_was_more_cautious():
    first = _brief(PriorityLevel.PRIORITY)
    second = _brief(PriorityLevel.ROUTINE)
    result = compare_site_risk(first, second)
    assert result.agrees is False
    # The auditor rated it LOWER; the original (higher, more cautious)
    # rating is kept, never silently downgraded.
    assert result.adopted_priority == "priority"
    assert "lower" in result.note.lower()
