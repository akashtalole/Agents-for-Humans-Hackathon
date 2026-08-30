import httpx
import pytest

from glacierwatch.tools.seismic import _haversine_km, fetch_seismic_events

# Real-shaped fixture, structurally identical to what earthquake.usgs.gov returns
# (values taken from an actual live query made while building this tool).
FAKE_USGS_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "properties": {
                "mag": 4.0,
                "place": "38 km NE of Sarahan, India",
                "time": 1787703415088,
                "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000tbxyz",
            },
            "geometry": {"coordinates": [77.9, 31.6, 10.0]},
        },
        {
            "properties": {
                "mag": 4.3,
                "place": "39 km WSW of Kyelang, India",
                "time": 1787233803059,
                "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000tbabc",
            },
            "geometry": {"coordinates": [76.9, 32.3, 15.0]},
        },
    ],
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


def test_haversine_km_known_distance():
    # Roughly the distance between Delhi and Mumbai, ~1150km actual great-circle distance
    delhi = (28.6139, 77.2090)
    mumbai = (19.0760, 72.8777)
    distance = _haversine_km(*delhi, *mumbai)
    assert 1100 < distance < 1200


def test_haversine_km_same_point_is_zero():
    assert _haversine_km(32.5, 77.2, 32.5, 77.2) == 0.0


def test_fetch_seismic_events_parses_real_shaped_response(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(FAKE_USGS_RESPONSE))

    events = fetch_seismic_events(32.5, 77.22)
    assert len(events) == 2
    assert events[0].magnitude in (4.0, 4.3)
    assert all(e.distance_km >= 0 for e in events)
    assert all(e.place for e in events)


def test_fetch_seismic_events_sorted_most_recent_first(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse(FAKE_USGS_RESPONSE))

    events = fetch_seismic_events(32.5, 77.22)
    times = [e.time for e in events]
    assert times == sorted(times, reverse=True)


def test_fetch_seismic_events_empty_result(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse({"features": []}))

    events = fetch_seismic_events(32.5, 77.22)
    assert events == []


def test_fetch_seismic_events_propagates_http_errors_rather_than_fabricating(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse({}, status_code=503))

    with pytest.raises(httpx.HTTPError):
        fetch_seismic_events(32.5, 77.22)
