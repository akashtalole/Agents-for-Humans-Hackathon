"""Sub-agent: synthesizes the full set of site risk briefs into one
top-level summary sentence for the weekly watchlist report. The briefs
themselves are already validated structured data - this agent only adds the
one-line synthesis a busy official reads first."""
from __future__ import annotations

from strands import Agent

from glacierwatch.config import create_agent
from glacierwatch.models import SiteRiskBrief, WatchlistReport

SYSTEM_PROMPT = """\
You write the one-paragraph top-line summary for a weekly Himalayan glacial \
hazard watchlist read by disaster management officials. You are given the \
full list of already-assessed site risk briefs - do not re-assess or \
second-guess them, and do not add sites or facts that are not in the list \
you were given.

Write overall_summary as 1-2 sentences: how many sites are at "priority" \
level this week and why (name them briefly), and a one-line reminder that \
this is a prioritization aid, not a prediction, so on-site expert \
assessment is still required for any operational decision. Keep the briefs \
list exactly as given - copy it through unchanged; you are only writing the \
summary.
"""


def build_report_drafter() -> Agent:
    return create_agent(system_prompt=SYSTEM_PROMPT)


def draft_watchlist_report(briefs: list[SiteRiskBrief]) -> WatchlistReport:
    agent = build_report_drafter()
    briefs_json = "[" + ",".join(b.model_dump_json() for b in briefs) + "]"
    prompt = f"SITE RISK BRIEFS (structured JSON array):\n{briefs_json}\n\nWrite the overall_summary now."
    result = agent(prompt, structured_output_model=WatchlistReport)
    # Trust the input briefs over whatever the model echoed back - it was
    # only asked to write the summary sentence, not to retranscribe data.
    result.structured_output.briefs = briefs
    return result.structured_output
