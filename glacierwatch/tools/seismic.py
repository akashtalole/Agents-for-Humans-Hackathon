"""Live seismic activity via the USGS earthquake catalog (free, no API key
required, global coverage - not limited to US events).

Relevant here because several documented Himalayan ice/rock-avalanche and
GLOF events have been triggered or accompanied by seismic activity, and the
August 2026 Nepal-Tibet event was itself large enough to register on
seismographs (initially reported by USGS as a M4.4 equivalent). Recent
nearby seismicity is one input to prioritization - not a trigger on its own.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from glacierwatch.models import SeismicEvent
from glacierwatch.tools._http import get_with_retries

USGS_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch_seismic_events(
    latitude: float, longitude: float, radius_km: float = 150.0, days: int = 14, min_magnitude: float = 2.5
) -> list[SeismicEvent]:
    """Fetch recent earthquakes within `radius_km` of a location from the
    USGS earthquake catalog.

    Raises:
        httpx.HTTPError: on network failure or a non-2xx response - callers
            should handle this explicitly rather than silently substituting
            data, per GlacierWatch's rule of never fabricating conditions.
    """
    start_time = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    response = get_with_retries(
        lambda: httpx.get(
            USGS_URL,
            params={
                "format": "geojson",
                "latitude": latitude,
                "longitude": longitude,
                "maxradiuskm": radius_km,
                "starttime": start_time,
                "minmagnitude": min_magnitude,
            },
            timeout=20.0,
        )
    )
    response.raise_for_status()
    data = response.json()

    events = []
    for feature in data.get("features", []):
        props = feature["properties"]
        coords = feature["geometry"]["coordinates"]  # [lon, lat, depth]
        distance_km = _haversine_km(latitude, longitude, coords[1], coords[0])
        event_time = datetime.fromtimestamp(props["time"] / 1000, tz=timezone.utc).isoformat()
        events.append(
            SeismicEvent(
                time=event_time,
                magnitude=props.get("mag") or 0.0,
                distance_km=distance_km,
                place=props.get("place") or "unknown location",
                usgs_url=props.get("url") or "",
            )
        )
    events.sort(key=lambda e: e.time, reverse=True)
    return events


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    r_km = 6371.0
    lat1_r, lon1_r, lat2_r, lon2_r = map(radians, (lat1, lon1, lat2, lon2))
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlon / 2) ** 2
    return 2 * r_km * asin(sqrt(a))


def source_note() -> str:
    return f"USGS Earthquake Catalog (earthquake.usgs.gov), fetched {datetime.now(timezone.utc).isoformat()}"
