"""The orchestrator agent: the single entry point a disaster management
official or village committee talks to.

Same "agents as tools" shape as bidwright/orchestrator.py and
claimclarity/orchestrator.py: a shared WatchRun holds state, each pipeline
stage is a tool, and the trusted output is generated deterministically from
validated data rather than the orchestrator's own retelling of it.

One thing built in from the start here, learned the hard way while building
the other two projects in this repo: the risk_assessor and report_drafter
sub-agents are always handed the FULL structured data for what they're
judging (not a terse tool-result summary), and the orchestrator's own
final reply is instructed to defer to the deterministic report file rather
than reconstruct specifics from memory - see ORCHESTRATOR_PROMPT below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
from strands import Agent, tool

from glacierwatch.agents.report_drafter import draft_watchlist_report
from glacierwatch.agents.risk_assessor import assess_site
from glacierwatch.config import create_agent
from glacierwatch.models import CurrentConditions, SiteRiskBrief, WatchlistReport, WatchSite
from glacierwatch.rendering import render_conditions_md, render_site_profile_md, render_watchlist_report_md
from glacierwatch.tools.documents import save_text_file
from glacierwatch.tools.seismic import fetch_seismic_events
from glacierwatch.tools.seismic import source_note as seismic_source_note
from glacierwatch.tools.watchlist import load_all_sites
from glacierwatch.tools.weather import EXTREMELY_HEAVY_MM, fetch_precipitation
from glacierwatch.tools.weather import source_note as weather_source_note

ORCHESTRATOR_PROMPT = """\
You are GlacierWatch, an assistant that helps disaster management officials \
and village-level committees in the Indian Himalaya decide where to focus \
limited monitoring and inspection attention this week.

You are NOT a prediction system and must never claim to be one. You combine \
published, cited hazard assessments with live weather and seismic data to \
prioritize attention - nothing more.

For every run, always execute the full pipeline in this order:
1. load_watchlist
2. For every active_watch site returned: fetch_current_conditions(site_id)
3. For every site (active_watch AND historical_case_study): assess_site_risk(site_id)
4. draft_watchlist_report

Then write a final answer for a busy official who has 30 seconds. Your tool \
results only give you counts and filenames, not the actual rationale text \
for each site - so do NOT try to recall or restate specific rationale, \
trigger details, or recommendations from memory. You do not reliably have \
them, and guessing produces confident-sounding fabrications. Instead, your \
final answer must include, in this order:
- One-line bottom line: how many sites need priority attention this week \
(state the count only, e.g. "1 of 4 sites at priority level").
- A direct pointer to watchlist_report.md as the place to read exactly \
which sites and why - do not enumerate them yourself.
- One sentence restating that this is decision support, not a prediction, \
and that on-site expert assessment is still required for any operational \
decision.

Never skip a step. If a tool reports an error because a previous step \
wasn't run, run the missing step and retry.
"""


@dataclass
class WatchRun:
    """Working state for one GlacierWatch run, shared across every tool call."""

    output_dir: str
    sites: list[WatchSite] = field(default_factory=list)
    conditions_by_site: dict[str, CurrentConditions] = field(default_factory=dict)
    briefs: list[SiteRiskBrief] = field(default_factory=list)
    report: WatchlistReport | None = None
    activity_log: list[str] = field(default_factory=list)


def build_orchestrator(run: WatchRun, callback_handler=None) -> Agent:
    out_dir = Path(run.output_dir)

    def _find_site(site_id: str) -> WatchSite | None:
        return next((s for s in run.sites if s.id == site_id), None)

    @tool
    def load_watchlist() -> str:
        """Load the bundled reference watchlist of documented Himalayan
        glacial hazard sites. Always call this first."""
        run.sites = load_all_sites()
        active = [s for s in run.sites if s.status == "active_watch"]
        historical = [s for s in run.sites if s.status != "active_watch"]
        for site in run.sites:
            save_text_file(str(out_dir / f"site_profile_{site.id}.md"), render_site_profile_md(site))
        msg = (
            f"Loaded {len(run.sites)} site(s): {len(active)} active_watch "
            f"({', '.join(s.id for s in active)}), {len(historical)} historical_case_study "
            f"({', '.join(s.id for s in historical)})."
        )
        run.activity_log.append(msg)
        return msg

    @tool
    def fetch_current_conditions(site_id: str) -> str:
        """Fetch live precipitation and nearby seismic activity for one
        active_watch site from real, public data sources (Open-Meteo,
        USGS). Only meaningful for active_watch sites - historical case
        study sites don't need live conditions. Must be called after
        load_watchlist."""
        site = _find_site(site_id)
        if site is None:
            return f"Error: unknown site_id '{site_id}'. Call load_watchlist first."

        try:
            precip = fetch_precipitation(site.latitude, site.longitude)
            quakes = fetch_seismic_events(site.latitude, site.longitude)
        except httpx.HTTPError as exc:
            return f"Error: could not fetch live conditions for {site.name}: {exc}"

        max_mm = max((r.precipitation_mm for r in precip), default=0.0)
        conditions = CurrentConditions(
            site_id=site.id,
            as_of=datetime.now(timezone.utc).isoformat(),
            precipitation_recent_days=precip,
            max_daily_precipitation_mm=max_mm,
            heavy_rainfall_flag=max_mm >= EXTREMELY_HEAVY_MM,
            nearby_seismic_events=quakes,
            weather_source_note=weather_source_note(),
            seismic_source_note=seismic_source_note(),
        )
        run.conditions_by_site[site.id] = conditions
        save_text_file(str(out_dir / f"site_conditions_{site.id}.md"), render_conditions_md(conditions))

        msg = (
            f"Fetched conditions for {site.name}: max recent-day rainfall {max_mm:.1f}mm "
            f"({'extremely heavy - flagged' if conditions.heavy_rainfall_flag else 'below extreme threshold'}), "
            f"{len(quakes)} nearby seismic event(s) in the last 14 days."
        )
        run.activity_log.append(msg)
        return msg

    @tool
    def assess_site_risk(site_id: str) -> str:
        """Assess one site's priority level by combining its documented risk
        profile with its current conditions (if fetched). Must be called
        after load_watchlist; for active_watch sites, call
        fetch_current_conditions first for a grounded assessment."""
        site = _find_site(site_id)
        if site is None:
            return f"Error: unknown site_id '{site_id}'. Call load_watchlist first."

        conditions = run.conditions_by_site.get(
            site.id,
            CurrentConditions(
                site_id=site.id,
                as_of=datetime.now(timezone.utc).isoformat(),
                weather_source_note="not fetched (historical case study site)",
                seismic_source_note="not fetched (historical case study site)",
            ),
        )
        brief = assess_site(site, conditions)
        run.briefs = [b for b in run.briefs if b.site_id != site.id] + [brief]
        msg = f"Assessed {site.name}: priority_level={brief.priority_level.value}."
        run.activity_log.append(msg)
        return msg

    @tool
    def draft_watchlist_report_tool() -> str:
        """Synthesize all assessed sites into the final weekly watchlist
        report. Must be called after assess_site_risk has run for every
        site."""
        if not run.briefs:
            return "Error: no sites have been assessed yet. Call assess_site_risk for each site first."
        run.report = draft_watchlist_report(run.briefs)
        save_text_file(str(out_dir / "watchlist_report.md"), render_watchlist_report_md(run.report))
        priority_count = sum(1 for b in run.briefs if b.priority_level.value == "priority")
        msg = (
            f"Watchlist report written to watchlist_report.md. "
            f"{priority_count} of {len(run.briefs)} site(s) at priority level."
        )
        run.activity_log.append(msg)
        return msg

    agent_kwargs = dict(
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[load_watchlist, fetch_current_conditions, assess_site_risk, draft_watchlist_report_tool],
    )
    # Always pass callback_handler explicitly, even when it's None - see
    # bidwright/orchestrator.py's comment on this same line for why.
    agent_kwargs["callback_handler"] = callback_handler
    return create_agent(**agent_kwargs)
