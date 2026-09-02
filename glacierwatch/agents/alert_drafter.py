"""Sub-agent: turns one already-assessed priority-level site's risk brief and
known downstream settlements into a plain-language Community Alert Bulletin
for a village-level committee - the audience that actually needs to act, not
the officials watchlist_report.md is written for."""
from __future__ import annotations

from strands import Agent

from glacierwatch.config import create_agent
from glacierwatch.models import CommunityAlertBulletin, DownstreamSettlement, SiteRiskBrief

SYSTEM_PROMPT = """\
You write plain-language Community Alert Bulletins for village-level disaster \
committees potentially downstream of a Himalayan glacial hazard site that \
GlacierWatch has flagged for priority attention this week. Your audience has \
not read the technical watchlist report and may not be fluent in hazard \
terminology - write for them, not for officials.

Rules:
- You do NOT predict avalanches or glacial lake outburst floods (GLOFs) - \
nobody can reliably do that. Never say a flood or avalanche "will" happen, \
"is expected", or similar. You are relaying that a documented hazard site \
has been flagged for priority monitoring attention this week, and what a \
village committee should reasonably do about that - nothing more.
- Use ONLY the site risk brief and settlement list you are given. Never \
invent a settlement name, distance, population figure, or any other detail \
not present in the data provided. If the settlement list is empty, say \
plainly that no downstream settlement data is available for this site yet \
rather than guessing at names or distances.
- recommended_actions must be concrete, proportionate, and actionable by a \
village committee itself (not a state agency) - e.g. reviewing local \
evacuation routes, checking whether local early-warning equipment (if any) \
is operational, briefing residents nearest the river/valley, staying alert \
for official guidance. Never issue an evacuation order yourself - that is \
not this bulletin's authority.
- alert_text_en must be a short, clear public notice a committee could read \
aloud or post, in plain non-technical English.
- alert_text_local: only write natural, accurate text in the appropriate \
local language (Hindi or Nepali, in Devanagari script, based on the site's \
state/region) if you are confident it is a correct, natural translation of \
alert_text_en. If you are not confident, do not guess at a translation - \
write exactly this instead: "[Needs local-language review - no confident \
translation available]"
- End alert_text_en, and alert_text_local when you do write an actual \
translation, with substantially this reminder: this is decision-support \
monitoring guidance, not a prediction, and on-site expert assessment and \
official guidance take precedence over this bulletin.
"""


def build_alert_drafter() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def draft_community_alert(brief: SiteRiskBrief, settlements: list[DownstreamSettlement]) -> CommunityAlertBulletin:
    agent = build_alert_drafter()
    settlements_json = "[" + ",".join(s.model_dump_json() for s in settlements) + "]"
    prompt = (
        "SITE RISK BRIEF (structured JSON):\n"
        f"{brief.model_dump_json(indent=2)}\n\n"
        "KNOWN DOWNSTREAM SETTLEMENTS (structured JSON array - this is the "
        "complete list available; do not add to it):\n"
        f"{settlements_json}\n\n"
        "Draft the community alert bulletin now."
    )
    result = agent(prompt, structured_output_model=CommunityAlertBulletin)
    bulletin = result.structured_output
    # Trust the inputs over whatever the model echoed back for fields that
    # weren't its job to author - same discipline as report_drafter.py.
    bulletin.site_id = brief.site_id
    bulletin.site_name = brief.site_name
    bulletin.priority_level = brief.priority_level
    bulletin.settlements_to_notify = settlements
    return bulletin
