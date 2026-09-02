import httpx
import pytest

from glacierwatch.tools.weather import EXTREMELY_HEAVY_MM, categorize_rainfall_mm, fetch_precipitation

# Real-shaped fixture, structurally identical to what api.open-meteo.com returns.
FAKE_OPEN_METEO_RESPONSE = {
    "latitude": 32.51,
    "longitude": 77.19,
    "daily": {
        "time": ["2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29", "2026-08-30"],
        "precipitation_sum": [0.2, 0.3, 0.0, 0.0, 0.0, 1.1],
    },
}


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json_data


def test_categorize_rainfall_mm_matches_imd_scale():
    assert categorize_rainfall_mm(0.0) == "no rain / trace"
    assert categorize_rainfall_mm(10.0) == "light"
    assert categorize_rainfall_mm(40.0) == "moderate"
    assert categorize_rainfall_mm(90.0) == "heavy"
    assert categorize_rainfall_mm(150.0) == "very heavy"
    assert categorize_rainfall_mm(250.0) == "extremely heavy"


def test_categorize_rainfall_mm_boundary_values():
    assert categorize_rainfall_mm(2.4) == "no rain / trace"
    assert categorize_rainfall_mm(2.5) == "light"
    assert categorize_rainfall_mm(204.4) == "very heavy"
    assert categorize_rainfall_mm(204.5) == "extremely heavy"
    assert EXTREMELY_HEAVY_MM == 204.4


def test_fetch_precipitation_parses_real_shaped_response(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(FAKE_OPEN_METEO_RESPONSE))

    readings = fetch_precipitation(32.5, 77.2)
    assert len(readings) == 6
    assert readings[-1].date == "2026-08-30"
    assert readings[-1].precipitation_mm == 1.1
    assert readings[-1].category == "no rain / trace"
    assert readings[1].precipitation_mm == 0.3
    assert readings[1].category == "no rain / trace"


def test_fetch_precipitation_treats_null_precipitation_as_zero(monkeypatch):
    response_with_null = {
        "daily": {"time": ["2026-08-30"], "precipitation_sum": [None]},
    }
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(response_with_null))

    readings = fetch_precipitation(32.5, 77.2)
    assert readings[0].precipitation_mm == 0.0
    assert readings[0].category == "no rain / trace"


def test_fetch_precipitation_propagates_http_errors_rather_than_fabricating(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse({}, status_code=500))

    with pytest.raises(httpx.HTTPError):
        fetch_precipitation(32.5, 77.2)
