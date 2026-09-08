"""Live rainfall near Nashik via Open-Meteo (free, no API key required).

Catchment rainfall is what drives a Gangapur Dam release in the first
place - every documented Ramkund flooding event in
trinetra/data/godavari_hydrology.json happened during "incessant rains" /
"catchment rain continues" reporting. So a rising rainfall figure is an
early hint that a release (and therefore a riverfront evacuation decision)
may be coming, hours before the discharge itself is announced.

Same discipline as glacierwatch/tools/weather.py, which calls the same
API: if the fetch fails, this says so honestly and the caller records that
it had no rainfall data - it never substitutes a plausible-looking number.
A fabricated rainfall reading feeding an evacuation decision is exactly
the failure mode this repo refuses everywhere else.
"""
from __future__ import annotations

import httpx

from trinetra.tools._http import get_with_retries

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Panchavati / Ramkund riverfront, Nashik. Used for the rainfall reading
# because that is the stretch of the Godavari the flood-exposed ghats sit
# on; the Gangapur catchment upstream is what actually fills the dam, so a
# real deployment should also pull the catchment's own gauges.
NASHIK_LATITUDE = 19.9975
NASHIK_LONGITUDE = 73.7898


def fetch_recent_rainfall_mm(
    latitude: float = NASHIK_LATITUDE,
    longitude: float = NASHIK_LONGITUDE,
    past_days: int = 3,
) -> tuple[float | None, str]:
    """Returns (max daily rainfall in mm over the recent window, note).

    On success the note explains what the number is. On failure the value
    is None and the note says plainly that live rainfall could not be
    fetched - callers surface that rather than pretending it was dry.
    """
    try:
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
        payload = response.json()
        sums = [v for v in payload.get("daily", {}).get("precipitation_sum", []) if v is not None]
        if not sums:
            return None, "Open-Meteo returned no precipitation values for this location."
        peak = max(float(v) for v in sums)
        return peak, (
            f"Peak daily rainfall over the last {past_days} day(s) near the Panchavati/Ramkund "
            f"riverfront, from Open-Meteo (live)."
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        return None, (
            f"Live rainfall could not be fetched ({type(exc).__name__}) - this assessment is based on the "
            "reported dam discharge alone, with no rainfall context."
        )
