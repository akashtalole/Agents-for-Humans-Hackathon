"""Live precipitation data via Open-Meteo (free, no API key required).

Categorization uses India Meteorological Department's standard 24-hour
rainfall categories. The "heavy rainfall" trigger flag is set at IMD's
"extremely heavy rainfall" threshold (>204.4 mm/day) - the same order of
magnitude as the documented trigger in the 2013 Chorabari Lake failure
(>315 mm combined with rapid glacier melt; see glacierwatch/data/watchlist.json),
and the threshold IMD itself uses for its most severe daily-rainfall alerts.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from glacierwatch.models import PrecipitationReading
from glacierwatch.tools._http import get_with_retries

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
EXTREMELY_HEAVY_MM = 204.4


def categorize_rainfall_mm(mm: float) -> str:
    """IMD's standard 24-hour rainfall categories."""
    if mm < 2.5:
        return "no rain / trace"
    if mm <= 15.5:
        return "light"
    if mm <= 64.4:
        return "moderate"
    if mm <= 115.5:
        return "heavy"
    if mm <= 204.4:
        return "very heavy"
    return "extremely heavy"


def fetch_precipitation(latitude: float, longitude: float, past_days: int = 7) -> list[PrecipitationReading]:
    """Fetch the last `past_days` of daily precipitation for a location from
    Open-Meteo and categorize each day using IMD's rainfall scale.

    Raises:
        httpx.HTTPError: on network failure or a non-2xx response - callers
            should handle this explicitly rather than silently substituting
            data, per GlacierWatch's rule of never fabricating conditions.
    """
    response = get_with_retries(
        lambda: httpx.get(
            OPEN_METEO_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "daily": "precipitation_sum",
                "past_days": past_days,
                "forecast_days": 1,
                "timezone": "Asia/Kolkata",
            },
            timeout=20.0,
        )
    )
    response.raise_for_status()
    data = response.json()

    dates = data["daily"]["time"]
    values = data["daily"]["precipitation_sum"]
    return [
        PrecipitationReading(date=date, precipitation_mm=mm or 0.0, category=categorize_rainfall_mm(mm or 0.0))
        for date, mm in zip(dates, values)
    ]


def source_note() -> str:
    return f"Open-Meteo (api.open-meteo.com), fetched {datetime.now(timezone.utc).isoformat()}"
