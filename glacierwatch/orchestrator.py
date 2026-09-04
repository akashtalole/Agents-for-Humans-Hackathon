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

from glacierwatch.agents.alert_drafter import draft_community_alert
from glacierwatch.agents.alert_reviewer import review_alert
from glacierwatch.agents.report_drafter import draft_watchlist_report
from glacierwatch.agents.risk_assessor import assess_site
from glacierwatch.agents.risk_auditor import audit_site, compare_site_risk
from glacierwatch.config import create_agent
from glacierwatch.models import (
    CommunityAlertBulletin,
    CurrentConditions,
    GuardrailResult,
    HistoryEntry,
    InspectionSchedule,
    PriorityLevel,
    ReviewResult,
    RiskCrossCheckItem,
    RunHistory,
    SiteRiskBrief,
    SiteTrend,
    TrendClassification,
    WatchlistReport,
    WatchSite,
)
from glacierwatch.rendering import (
    DISCLAIMER,
    render_community_alert_md,
    render_community_alerts_index_md,
    render_conditions_md,
    render_guardrail_md,
    render_inspection_schedule_md,
    render_review_md,
    render_risk_cross_check_md,
    render_site_profile_md,
    render_trend_report_md,
    render_watchlist_report_md,
)
from glacierwatch.tools.documents import save_text_file
from glacierwatch.tools.downstream import load_downstream_exposure
from glacierwatch.tools.guardrail import run_guardrail_check
from glacierwatch.tools.history import append_entries, compute_site_trends, load_history, save_history
from glacierwatch.tools.scheduler import build_inspection_schedule
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
3. For every site (active_watch AND historical_case_study): assess_site_risk(site_id), \
then immediately cross_verify_site_risk(site_id) for that same site before moving to the next one
4. record_run_history_and_detect_trends
5. draft_watchlist_report
6. draft_community_alerts
7. review_community_alerts
8. check_alerts_guardrail
9. build_field_inspection_schedule

cross_verify_site_risk gets a second, INDEPENDENT priority-level opinion \
from a separate auditor agent that has not seen assess_site_risk's brief \
for that site - not a revision of that assessment, a genuinely separate \
one. Because understating risk here is worse than overstating it, any \
disagreement is never silently resolved in favor of the first assessment: \
the MORE CAUTIOUS of the two ratings is always adopted, and every \
comparison is written to risk_cross_check.md whether or not the two agree. \
Always call it right after assess_site_risk for each site, even when you \
expect them to agree - the whole point is that you don't actually know \
that until you check.

Step 7 is a skeptical second reviewer that compares every drafted community \
alert bulletin against the SiteRiskBrief it was drafted from, checking for a \
priority-level mismatch, invented specifics not present in the brief or \
settlement data, and - most importantly - any language anywhere in a \
bulletin that sounds like a prediction of when or whether an avalanche or \
glacial lake outburst flood will occur. If zero alerts were drafted this \
run (the common case - most weeks have zero priority sites), this tool \
reports that cleanly and does nothing; call it anyway, right after \
draft_community_alerts, so you don't have to reason about whether it's \
needed. If it finds real issues, revise by calling draft_community_alerts \
again with the feedback in mind, then call review_community_alerts once \
more to confirm the fix - but this revision loop is capped at ONE pass for \
the whole batch, enforced in code, not just by this instruction: calling \
review_community_alerts a second time after a revision already happened \
returns immediately without re-reviewing, so you cannot loop forever \
chasing a perfect review even if you wanted to. Treat "maximum \
review-revision pass already used" as your signal to move on.

Step 8 runs an enforced guardrail check on the CURRENT community alert \
bulletin text for prediction language specifically - GlacierWatch's one \
non-negotiable rule is that it never claims to predict if, when, or where a \
hazard will occur, and this step is the last, code-enforced line of defense \
for that rule before a human ever sees these bulletins. Always call it \
after review_community_alerts, whether or not that review found issues - \
it is a separate, independent check, not a substitute for the review. It \
also no-ops cleanly when zero alerts were drafted this run.

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
- One line stating how many sites the independent audit disagreed with \
(state the count only, from cross_verify_site_risk's results across all \
sites - never invent which ones) and a pointer to risk_cross_check.md.
- One line stating how many sites show a rising trend across recent runs \
(state the count only, from the record_run_history_and_detect_trends tool \
result, e.g. "1 site shows a rising trend") and a pointer to \
trend_report.md - a rising trend is a real, counted fact, but never claim \
what it portends.
- One line stating how many community alert bulletins were drafted (state \
the count only, from the draft_community_alerts tool result - never invent \
settlement names or details) and a pointer to community_alerts_index.md.
- Only when at least one community alert bulletin was drafted this run: one \
line stating how many review issues and how many guardrail findings were \
found (counts only, from the review_community_alerts and \
check_alerts_guardrail tool results) and a pointer to alerts_review.md and \
alerts_guardrail.md.
- One line stating how many stops were scheduled for the field team's \
inspection route this week (state the count only, from the \
build_field_inspection_schedule tool result) and a pointer to \
inspection_schedule.md - do not enumerate the stops or their order yourself.
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
    history_file: str = "glacierwatch_history.json"
    max_field_stops: int = 5
    sites: list[WatchSite] = field(default_factory=list)
    conditions_by_site: dict[str, CurrentConditions] = field(default_factory=dict)
    briefs: list[SiteRiskBrief] = field(default_factory=list)
    risk_cross_checks: dict[str, RiskCrossCheckItem] = field(default_factory=dict)
    report: WatchlistReport | None = None
    alerts: list[CommunityAlertBulletin] = field(default_factory=list)
    history: RunHistory = field(default_factory=RunHistory)
    trends: list[SiteTrend] = field(default_factory=list)
    inspection_schedule: InspectionSchedule | None = None
    reviews: dict[str, ReviewResult] = field(default_factory=dict)
    review_revision_count: int = 0
    guardrails: dict[str, GuardrailResult] = field(default_factory=dict)
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
    def cross_verify_site_risk(site_id: str) -> str:
        """Get a second, independent priority-level assessment for this
        site from a separate auditor agent that has NOT seen the first
        assessment's brief, then compare the two. Because understating risk
        is worse than overstating it here, whenever the two disagree the
        MORE CAUTIOUS (higher) of the two priority levels is always
        adopted - never the lower one - and every comparison, agreement or
        not, is written to risk_cross_check.md for transparency. Must be
        called right after assess_site_risk for this same site_id."""
        site = _find_site(site_id)
        if site is None:
            return f"Error: unknown site_id '{site_id}'. Call load_watchlist first."
        brief = next((b for b in run.briefs if b.site_id == site_id), None)
        if brief is None:
            return f"Error: call assess_site_risk for site_id '{site_id}' first."

        conditions = run.conditions_by_site.get(
            site.id,
            CurrentConditions(
                site_id=site.id,
                as_of=datetime.now(timezone.utc).isoformat(),
                weather_source_note="not fetched (historical case study site)",
                seismic_source_note="not fetched (historical case study site)",
            ),
        )
        audit_brief = audit_site(site, conditions)
        cross_check_item = compare_site_risk(brief, audit_brief)
        run.risk_cross_checks[site_id] = cross_check_item

        if not cross_check_item.agrees and cross_check_item.adopted_priority != brief.priority_level.value:
            # The independent auditor rated this site HIGHER than the first
            # assessment - adopt its (more cautious) brief in full, not just
            # its priority_level, so the rationale/active_triggers/
            # recommended_action a human reads are consistent with the
            # rating actually being used downstream (draft_watchlist_report,
            # draft_community_alerts).
            run.briefs = [b for b in run.briefs if b.site_id != site_id] + [audit_brief]

        save_text_file(
            str(out_dir / "risk_cross_check.md"), render_risk_cross_check_md(list(run.risk_cross_checks.values()))
        )
        msg = (
            f"Independent audit for {site.name}: first={cross_check_item.first_priority}, "
            f"auditor={cross_check_item.second_priority}, adopted={cross_check_item.adopted_priority}"
            + (
                " (escalated to the auditor's higher rating)."
                if not cross_check_item.agrees and cross_check_item.adopted_priority != cross_check_item.first_priority
                else "."
            )
        )
        run.activity_log.append(msg)
        return msg

    @tool
    def record_run_history_and_detect_trends() -> str:
        """Append this run's key numeric signals (per active_watch site:
        max daily precipitation, nearby seismic event count, priority
        level) to the persistent run-history file, then classify each
        site's trend - rising, flat, falling, or insufficient_history - by
        comparing this run against prior runs recorded there. This is a
        trend of already-observed conditions, computed by plain code, never
        an LLM judgment and never a prediction. Always writes
        trend_report.md, even when nothing is trending or every site has
        insufficient_history - it says so plainly either way. Must be
        called after assess_site_risk has run for every site, before
        draft_watchlist_report so the watchlist report can surface any
        early-warning trend."""
        if not run.briefs:
            return "Error: no sites have been assessed yet. Call assess_site_risk for each site first."

        briefs_by_id = {b.site_id: b for b in run.briefs}
        run_at = datetime.now(timezone.utc).isoformat()
        new_entries = [
            HistoryEntry(
                site_id=site_id,
                run_at=run_at,
                max_daily_precipitation_mm=conditions.max_daily_precipitation_mm,
                nearby_seismic_events=len(conditions.nearby_seismic_events),
                priority_level=briefs_by_id[site_id].priority_level,
            )
            for site_id, conditions in run.conditions_by_site.items()
            if site_id in briefs_by_id
        ]

        prior_history = load_history(run.history_file)
        site_names = {b.site_id: b.site_name for b in run.briefs}
        run.trends = compute_site_trends(new_entries, prior_history, site_names)
        run.history = append_entries(prior_history, new_entries)
        save_history(run.history_file, run.history)
        save_text_file(str(out_dir / "trend_report.md"), render_trend_report_md(run.trends))

        rising = sum(1 for t in run.trends if t.trend == TrendClassification.RISING)
        msg = (
            f"Recorded {len(new_entries)} site(s) to run history ({run.history_file}). "
            f"{rising} of {len(run.trends)} site(s) show a rising trend. See trend_report.md."
        )
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
        save_text_file(
            str(out_dir / "watchlist_report.md"), render_watchlist_report_md(run.report, run.trends)
        )
        priority_count = sum(1 for b in run.briefs if b.priority_level.value == "priority")
        msg = (
            f"Watchlist report written to watchlist_report.md. "
            f"{priority_count} of {len(run.briefs)} site(s) at priority level."
        )
        run.activity_log.append(msg)
        return msg

    @tool
    def draft_community_alerts() -> str:
        """Draft a plain-language Community Alert Bulletin, with downstream
        settlements to notify, for every site assessed at priority level
        this week. Must be called after assess_site_risk has run for every
        site (typically right after draft_watchlist_report). If zero sites
        are at priority level, succeeds with a clear no-op message and
        writes no per-site bulletin files."""
        if not run.briefs:
            return "Error: no sites have been assessed yet. Call assess_site_risk for each site first."

        priority_briefs = [b for b in run.briefs if b.priority_level == PriorityLevel.PRIORITY]
        if not priority_briefs:
            msg = "No priority sites this week - no community alert bulletins drafted."
            run.activity_log.append(msg)
            return msg

        run.alerts = []
        for brief in priority_briefs:
            settlements = load_downstream_exposure(brief.site_id)
            bulletin = draft_community_alert(brief, settlements)
            run.alerts.append(bulletin)
            save_text_file(str(out_dir / f"community_alert_{brief.site_id}.md"), render_community_alert_md(bulletin))
        save_text_file(str(out_dir / "community_alerts_index.md"), render_community_alerts_index_md(run.alerts))

        msg = f"Drafted {len(run.alerts)} community alert bulletin(s). See community_alerts_index.md."
        run.activity_log.append(msg)
        return msg

    @tool
    def review_community_alerts() -> str:
        """Review every drafted community alert bulletin against its site's
        risk brief for accuracy - wrong priority level, invented specifics,
        or (most importantly) any language that sounds like a prediction of
        when/whether the hazard will occur. Call after draft_community_alerts.
        If there are zero alerts this run (no priority sites), this reports
        that cleanly and does nothing - not an error. If it finds real
        issues, revise by calling draft_community_alerts again, then call
        this tool again - but this is capped at ONE revision pass for the
        whole batch; calling it again after a revision already happened
        returns immediately without re-reviewing."""
        if not run.alerts:
            msg = "No community alerts this run - nothing to review."
            run.activity_log.append(msg)
            return msg
        if run.review_revision_count >= 1:
            msg = "Maximum review-revision pass (1) already used; proceeding without a further review."
            run.activity_log.append(msg)
            return msg
        briefs_by_id = {b.site_id: b for b in run.briefs}
        run.reviews = {a.site_id: review_alert(a, briefs_by_id[a.site_id]) for a in run.alerts}
        save_text_file(str(out_dir / "alerts_review.md"), render_review_md(run.reviews))
        any_issues = any(not r.approved for r in run.reviews.values())
        if any_issues:
            run.review_revision_count += 1
            n_issues = sum(len(r.issues) for r in run.reviews.values())
            msg = (
                f"Review found {n_issues} issue(s) across {len(run.reviews)} alert(s) - revise by "
                "calling draft_community_alerts again, then call review_community_alerts once more. "
                "See alerts_review.md."
            )
        else:
            msg = f"Reviewed {len(run.reviews)} alert(s), no issues found. See alerts_review.md."
        run.activity_log.append(msg)
        return msg

    @tool
    def check_alerts_guardrail() -> str:
        """Run GlacierWatch's enforced, non-negotiable guardrail check on the
        CURRENT community_alert_<site_id>.md content for every alert this
        run - a deterministic keyword scan plus a small independent agent
        check for language that sounds like a prediction of when or whether
        an avalanche or glacial lake outburst flood will occur, GlacierWatch's
        single non-negotiable rule. Must be called after
        review_community_alerts, whether or not that review found issues -
        this is a separate, independent safety check, not a substitute for
        the review. If there are zero alerts this run, this reports that
        cleanly and does nothing - not an error."""
        if not run.alerts:
            msg = "No community alerts this run - nothing to guardrail-check."
            run.activity_log.append(msg)
            return msg
        run.guardrails = {}
        for alert in run.alerts:
            alert_path = out_dir / f"community_alert_{alert.site_id}.md"
            alert_text = alert_path.read_text() if alert_path.exists() else render_community_alert_md(alert)
            # Every rendered bulletin includes the fixed DISCLAIMER boilerplate,
            # which itself explicitly names "will occur" in a negated, safe
            # context ("...cannot predict whether, when, or where...will
            # occur"). That's the tool's own safety framing, not generated
            # content to check - strip it before scanning so it can't produce
            # a false positive against the very check that enforces it.
            alert_text = alert_text.replace(DISCLAIMER, "")
            run.guardrails[alert.site_id] = run_guardrail_check(alert_text)
        save_text_file(str(out_dir / "alerts_guardrail.md"), render_guardrail_md(run.guardrails))
        total_findings = sum(len(g.findings) for g in run.guardrails.values())
        msg = (
            f"Guardrail check complete on {len(run.guardrails)} alert(s). {total_findings} finding(s). "
            "See alerts_guardrail.md."
        )
        run.activity_log.append(msg)
        return msg

    @tool
    def build_field_inspection_schedule() -> str:
        """Build this week's field team inspection route: which sites the
        team should physically visit, capped by field-team capacity
        (WatchRun.max_field_stops, default 5), in a sensible driving order -
        the step that turns "these sites are priority" into an actual
        Monday-morning work plan. Pure code, no LLM (a
        geometric/logistics optimization over lat/long and priority level,
        same discipline as record_run_history_and_detect_trends). Only
        active_watch sites are candidates - historical_case_study sites are
        past reference cases, not places to send a field team. Priority and
        elevated sites are always candidates; a routine site showing a
        rising trend (from record_run_history_and_detect_trends, if it has
        already run) is included as a lower-priority bonus candidate,
        capacity allowing. Must be called after assess_site_risk has run for
        every site. Always writes inspection_schedule.md, even when zero
        sites qualify - it says so plainly rather than erroring."""
        if not run.briefs:
            return "Error: no sites have been assessed yet. Call assess_site_risk for each site first."

        active_site_ids = {s.id for s in run.sites if s.status == "active_watch"}
        active_sites = [s for s in run.sites if s.id in active_site_ids]
        active_briefs = [b for b in run.briefs if b.site_id in active_site_ids]
        rising_trend_site_ids = frozenset(
            t.site_id for t in run.trends if t.trend == TrendClassification.RISING
        )

        run.inspection_schedule = build_inspection_schedule(
            sites=active_sites,
            briefs=active_briefs,
            max_stops=run.max_field_stops,
            rising_trend_site_ids=rising_trend_site_ids,
        )
        save_text_file(
            str(out_dir / "inspection_schedule.md"), render_inspection_schedule_md(run.inspection_schedule)
        )

        msg = (
            f"Scheduled {len(run.inspection_schedule.stops)} field inspection stop(s) this week. "
            f"See inspection_schedule.md."
        )
        run.activity_log.append(msg)
        return msg

    agent_kwargs = dict(
        system_prompt=ORCHESTRATOR_PROMPT,
        tools=[
            load_watchlist,
            fetch_current_conditions,
            assess_site_risk,
            cross_verify_site_risk,
            record_run_history_and_detect_trends,
            draft_watchlist_report_tool,
            draft_community_alerts,
            review_community_alerts,
            check_alerts_guardrail,
            build_field_inspection_schedule,
        ],
    )
    # Always pass callback_handler explicitly, even when it's None - see
    # bidwright/orchestrator.py's comment on this same line for why.
    agent_kwargs["callback_handler"] = callback_handler
    return create_agent(**agent_kwargs)
