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
