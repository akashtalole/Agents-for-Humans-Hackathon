"""Typed data contracts passed between GlacierWatch's agents.

Two distinct kinds of data flow through this pipeline, and the models below
keep them visibly separate:
  - WatchSite: static, published, cited facts about a known glacial hazard
    site (sourced from NRSC/ICIMOD/peer-reviewed reporting - see
    glacierwatch/data/watchlist.json). This never changes at runtime.
  - CurrentConditions: live weather/seismic data pulled from real APIs at
    the moment GlacierWatch runs. This changes every run.
SiteRiskBrief is the only place these two are combined, and only to prioritize
attention - never to assert that an event will or won't happen.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class WatchSite(BaseModel):
    """A documented glacial hazard site from the bundled reference watchlist."""

    id: str
    name: str
    also_known_as: list[str] = Field(default_factory=list)
    state: str
    district: str
    river_basin: str
    latitude: float
    longitude: float
    elevation_m: int
    status: str = Field(description="'active_watch' or 'historical_case_study'")
    static_risk_classification: str
    static_risk_factors: list[str] = Field(default_factory=list)
    downstream_exposure: str = ""
    sources: list[str] = Field(default_factory=list)


class PrecipitationReading(BaseModel):
    date: str
    precipitation_mm: float
    category: str = Field(description="IMD-style rainfall category for this day")


class SeismicEvent(BaseModel):
    time: str
    magnitude: float
    distance_km: float
    place: str
    usgs_url: str = ""


class CurrentConditions(BaseModel):
    """Live data pulled from real APIs for one site, at the moment this ran."""

    site_id: str
    as_of: str = Field(description="ISO timestamp this data was fetched")
    precipitation_recent_days: list[PrecipitationReading] = Field(
        default_factory=list, description="Daily precipitation for the recent observation window, including today so far"
    )
    max_daily_precipitation_mm: float = 0.0
    heavy_rainfall_flag: bool = Field(
        default=False, description="True if any day in the window met/exceeded the extreme-rainfall threshold"
    )
    nearby_seismic_events: list[SeismicEvent] = Field(default_factory=list)
    weather_source_note: str = ""
    seismic_source_note: str = ""


class PriorityLevel(str, Enum):
    ROUTINE = "routine"
    ELEVATED = "elevated"
    PRIORITY = "priority"


class SiteRiskBrief(BaseModel):
    """The judgment step: what a documented site plus this week's real
    conditions add up to. Never a prediction - a prioritization."""

    site_id: str
    site_name: str
    priority_level: PriorityLevel
    rationale: str = Field(
        description="Grounded in only the specific static risk factors and current conditions actually "
        "provided - never invented detail"
    )
    active_triggers: list[str] = Field(
        default_factory=list, description="Specific current conditions driving the priority level, if any"
    )
    recommended_action: str


class WatchlistReport(BaseModel):
    briefs: list[SiteRiskBrief] = Field(default_factory=list)
    overall_summary: str = Field(
        description="One or two sentences: how many sites need priority attention this week, and why"
    )


class DownstreamSettlement(BaseModel):
    """One plausibly-exposed downstream settlement from the bundled,
    illustrative glacierwatch/data/downstream_exposure.json reference data -
    see that file's data_caveat field before treating any of this as
    verified."""

    name: str
    distance_km: float = Field(description="Approximate downstream distance in km - illustrative, not from flood-routing modeling unless the notes say otherwise")
    population_band: str = Field(
        description="A coarse population-exposure band, e.g. 'small hamlet <500' or 'town 5,000-20,000' - "
        "never a false-precision exact figure, and never invented where no source exists"
    )
    notes: str = ""


class HistoryEntry(BaseModel):
    """One site's key numeric signals from one past run, appended to the
    persistent run-history file (glacierwatch/tools/history.py) after every
    run. Deliberately narrow - just the numbers a trend needs, not a full
    CurrentConditions/SiteRiskBrief snapshot - so history stays small and
    easy to reason about."""

    site_id: str
    run_at: str = Field(description="ISO timestamp this run's data was recorded")
    max_daily_precipitation_mm: float
    nearby_seismic_events: int
    priority_level: PriorityLevel


class RunHistory(BaseModel):
    """The full run-history file: every HistoryEntry recorded across all past
    runs, in the order they were appended (oldest first)."""

    entries: list[HistoryEntry] = Field(default_factory=list)


class TrendClassification(str, Enum):
    RISING = "rising"
    FLAT = "flat"
    FALLING = "falling"
    INSUFFICIENT_HISTORY = "insufficient_history"


class SiteTrend(BaseModel):
    """A pure-code trend classification for one site, computed by comparing
    this run's signals against prior runs recorded in the run-history file -
    never an LLM judgment. See glacierwatch/tools/history.py:classify_trend
    for the exact, documented threshold logic. A trend describes already-
    observed conditions across past runs; it is never a prediction."""

    site_id: str
    site_name: str
    trend: TrendClassification
    runs_considered: int = Field(
        description="How many recorded runs (including this one) the classification is based on"
    )
    explanation: str = Field(description="Plain-language statement of the deltas that produced this classification")


class CommunityAlertBulletin(BaseModel):
    """Plain-language output for a village-level committee downstream of a
    priority-level site - distinct audience and register from
    SiteRiskBrief/WatchlistReport, which are written for officials. Never a
    prediction; always the same non-prediction, seek-expert-guidance
    discipline as the rest of this project."""

    site_id: str
    site_name: str
    priority_level: PriorityLevel
    situation_summary: str = Field(
        description="Plain, non-technical explanation of why this site was flagged this week, for a reader "
        "with no hazard-terminology background"
    )
    recommended_actions: list[str] = Field(
        default_factory=list,
        description="Concrete steps a village committee itself can take - never an evacuation order",
    )
    settlements_to_notify: list[DownstreamSettlement] = Field(default_factory=list)
    alert_text_en: str = Field(description="Short public notice in plain English a committee could read aloud or post")
    alert_text_local: str = Field(
        description="Same notice in the appropriate local language (Hindi or Nepali, Devanagari script) if a "
        "confident, natural translation is possible - otherwise a clear '[Needs local-language review]' label, "
        "never a garbled machine translation"
    )


class InspectionStop(BaseModel):
    """One stop on a field team's weekly inspection route, built entirely by
    plain code (glacierwatch/tools/scheduler.py) from this week's already-
    validated SiteRiskBrief and WatchSite data - never an LLM judgment. This
    is the "what does the team actually do Monday morning" translation of a
    priority ranking into a routed, capacity-bounded work list."""

    site_id: str
    site_name: str
    priority_level: PriorityLevel
    why_visit: str = Field(
        description="The site's SiteRiskBrief.rationale, carried over verbatim so a field team lead can see "
        "why this stop is on the route without cross-referencing watchlist_report.md"
    )
    latitude: float
    longitude: float


class InspectionSchedule(BaseModel):
    """A field team's ordered weekly inspection route: which sites (capped by
    field-team capacity), in what visiting order. The stop order is a greedy
    nearest-neighbor route over `stops`' lat/long, not a guaranteed-optimal
    one - see glacierwatch/tools/scheduler.py:build_inspection_schedule for
    the exact algorithm and its documented limitations."""

    stops: list[InspectionStop] = Field(default_factory=list)
    summary: str = Field(
        description="One or two sentences: how many stops were scheduled out of how many candidate sites, "
        "and the field-team capacity limit that was applied"
    )
