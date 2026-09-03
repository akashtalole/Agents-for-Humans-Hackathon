"""Sub-agent: a skeptical second pass over one already-drafted Community Alert
Bulletin, comparing it against the SiteRiskBrief it was drafted from
(glacierwatch/agents/alert_drafter.py). This is a critic, not a rubber
stamp - but also not a prose-style editor: it flags only concrete,
checkable problems, and the single most important one is whether the
bulletin contains any language that sounds like a prediction of when or
whether the hazard will occur, since that's this project's one
non-negotiable rule (see the DISCLAIMER constant in
glacierwatch/rendering.py)."""
from __future__ import annotations

from strands import Agent

from glacierwatch.config import create_agent
from glacierwatch.models import CommunityAlertBulletin, ReviewResult, SiteRiskBrief

SYSTEM_PROMPT = """\
You are a skeptical reviewer checking one Community Alert Bulletin against \
the SiteRiskBrief it was drafted from, before it can reach a village-level \
disaster committee. You are the last check before this bulletin could reach \
the public - be genuinely skeptical, not a rubber stamp.

Flag ONLY concrete, checkable problems. Do not nitpick prose style, tone, or \
wording choices that don't change the substance.

Check specifically for:
1. Priority level mismatch: does the bulletin's stated priority_level and \
the urgency of its language actually match the brief's priority_level? A \
bulletin that reads more (or less) alarming than the brief's actual \
priority_level warrants is a real problem.
2. Invented specifics: does the bulletin state a settlement name, distance, \
population figure, trigger, or timeline that is NOT present in the \
SiteRiskBrief or the settlement data the bulletin itself lists in \
settlements_to_notify? Anything invented beyond what was actually provided \
is a real problem, no matter how plausible it sounds.
3. Prediction language - THE MOST IMPORTANT CHECK. Does the bulletin \
contain ANY language, anywhere (situation_summary, recommended_actions, \
alert_text_en, alert_text_local), that sounds like a prediction or \
forecast of when or whether an avalanche or glacial lake outburst flood \
will occur, or a claim of certainty about safety? This includes subtler \
phrasing, not just obvious words like "will occur" - an implied timeline \
("within days"), a false-certainty safety claim, or language that reads as \
"this will happen" even if hedged elsewhere. GlacierWatch's non-negotiable \
rule is that it never predicts if, when, or where a hazard will occur - \
treat this check with exactly that seriousness. If you find nothing else \
wrong but find prediction language, that alone means approved=False.

Set approved=True only if you find none of the above. issues should be a \
list of specific, concrete problems (empty if approved). summary should be \
one or two sentences stating your overall verdict and why.
"""


def build_alert_reviewer() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def review_alert(alert: CommunityAlertBulletin, brief: SiteRiskBrief) -> ReviewResult:
    agent = build_alert_reviewer()
    prompt = (
        "SITE RISK BRIEF this bulletin was drafted from (structured JSON):\n"
        f"{brief.model_dump_json(indent=2)}\n\n"
        "DRAFTED COMMUNITY ALERT BULLETIN to review (structured JSON):\n"
        f"{alert.model_dump_json(indent=2)}\n\n"
        "Review it now."
    )
    result = agent(prompt, structured_output_model=ReviewResult)
    return result.structured_output
