"""Sub-agent: an independent second opinion on one site's priority level.

Unlike `alert_reviewer.py` (which critiques a drafted community alert
against the brief it came from), this agent re-derives a priority
classification from scratch - the same documented site and the same
current conditions `risk_assessor.py` used, but with no knowledge of what
that first assessment concluded. Because understating risk here is worse
than overstating it, `compare_site_risk` below always adopts the MORE
CAUTIOUS of the two independent ratings, never silently trusting the first
assessor alone - see orchestrator.py's `cross_verify_site_risk`.
"""
from __future__ import annotations

from strands import Agent

from glacierwatch.config import create_agent
from glacierwatch.models import CurrentConditions, PriorityLevel, RiskCrossCheckItem, SiteRiskBrief, WatchSite

AUDITOR_SYSTEM_PROMPT = """\
You are a second, independent hazard-monitoring triage analyst - a \
skeptical, adversarial check on a first analyst's work, not a replacement \
for it. You are given the same documented site's published risk profile \
and the same current conditions a first analyst already assessed, but you \
have NOT seen their conclusions and must reach your own from scratch.

You do NOT predict avalanches or glacial lake outburst floods - nobody can \
reliably do that. Your job is narrower: given the facts provided, decide \
whether the site deserves priority attention, elevated awareness, or \
routine monitoring this week, and say exactly why.

Rules:
- Assume the first analyst may have been too lenient. Actively look for \
reasons a site's baseline risk or current conditions might justify a higher \
priority level than an easier first read would suggest.
- Use ONLY the static_risk_factors and current conditions actually \
provided. Never invent additional facts.
- "historical_case_study" sites should be classified "routine" with a \
rationale that plainly says this is a historical reference, not an active \
monitoring target.
- For "active_watch" sites: classify "priority" only when a genuine active \
trigger is present (heavy_rainfall_flag true, and/or a notable nearby \
seismic event). Classify "elevated" when documented baseline risk is high \
but no active trigger is present. Classify "routine" only when neither \
applies.
- Never use the words "predict", "will occur", "will fail", or similar - \
this tool prioritizes attention, it does not forecast events.
"""

_PRIORITY_ORDER = {PriorityLevel.ROUTINE: 0, PriorityLevel.ELEVATED: 1, PriorityLevel.PRIORITY: 2}


def build_risk_auditor() -> Agent:
    return create_agent(system_prompt=AUDITOR_SYSTEM_PROMPT)


def audit_site(site: WatchSite, conditions: CurrentConditions) -> SiteRiskBrief:
    agent = build_risk_auditor()
    prompt = (
        "DOCUMENTED SITE (structured JSON):\n"
        f"{site.model_dump_json(indent=2)}\n\n"
        "CURRENT CONDITIONS (structured JSON):\n"
        f"{conditions.model_dump_json(indent=2)}\n\n"
        "Produce your own independent site risk brief now."
    )
    result = agent(prompt, structured_output_model=SiteRiskBrief)
    return result.structured_output


def compare_site_risk(first: SiteRiskBrief, second: SiteRiskBrief) -> RiskCrossCheckItem:
    """Plain-code diff, no LLM: both briefs carry the same site_id and a
    priority_level from the same three-value ordered enum, so comparing and
    adopting the more cautious rating is exact, not a semantic-matching
    problem."""
    agrees = first.priority_level == second.priority_level
    if agrees:
        adopted = first.priority_level
        note = "Both independent assessments agree."
    else:
        more_cautious = max(first.priority_level, second.priority_level, key=lambda p: _PRIORITY_ORDER[p])
        adopted = more_cautious
        if more_cautious == first.priority_level:
            note = (
                "The two assessments disagreed; the independent auditor rated this site LOWER, so the "
                "original (more cautious) rating was kept."
            )
        else:
            note = (
                "The two assessments disagreed; the independent auditor rated this site HIGHER, so that "
                "more cautious rating was adopted instead of the first assessment."
            )

    return RiskCrossCheckItem(
        site_id=first.site_id,
        site_name=first.site_name,
        first_priority=first.priority_level.value,
        second_priority=second.priority_level.value,
        adopted_priority=adopted.value,
        agrees=agrees,
        note=note,
    )
