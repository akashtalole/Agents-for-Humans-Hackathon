"""Offline tests for the ThingsBoard REST client and Trinetra's live-signal
mapping layer. All HTTP is monkeypatched - same convention as
tests/test_glacierwatch_weather.py's Open-Meteo mocking - so this suite
needs no network access and no ThingsBoard credentials.
"""
from __future__ import annotations

import pytest

from trinetra.models import RiverStage
from trinetra.tools import live_signals as ls
from trinetra.tools import thingsboard as tb


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json


def _config(**overrides):
    defaults = dict(base_url="https://demo.thingsboard.io", username="u", password="p")
    defaults.update(overrides)
    return tb.ThingsBoardConfig(**defaults)


# --- ThingsBoardConfig ------------------------------------------------------


def test_config_not_configured_without_any_credential():
    assert not tb.ThingsBoardConfig(base_url="https://x").configured


def test_config_configured_with_username_password():
    assert _config().configured


def test_config_configured_with_api_key_alone():
    assert tb.ThingsBoardConfig(base_url="https://x", api_key="k").configured


# --- login -------------------------------------------------------------------


def test_login_returns_token_on_success(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"token": "tok123"}))
    assert tb.login(_config()) == "tok123"


def test_login_raises_honest_error_on_bad_credentials(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({}, status_code=401))
    with pytest.raises(tb.ThingsBoardError, match="401"):
        tb.login(_config())


def test_login_raises_without_any_credential_configured():
    with pytest.raises(tb.ThingsBoardError, match="no THINGSBOARD_USERNAME"):
        tb.login(tb.ThingsBoardConfig(base_url="https://x"))


def test_login_skipped_entirely_for_api_key_auth():
    """No HTTP call at all when api_key is set - see _auth_headers."""
    assert tb.login(tb.ThingsBoardConfig(base_url="https://x", api_key="k")) is None


# --- telemetry / attributes ---------------------------------------------------


def test_get_latest_telemetry_parses_numeric_and_string_values(monkeypatch):
    monkeypatch.setattr(
        "httpx.get",
        lambda *a, **k: _FakeResponse(
            {
                "densityPaxPerSqm": [{"ts": 1700000000000, "value": "4.9"}],
                "losGrade": [{"ts": 1700000000000, "value": "E"}],
                "empty_key": [],
            }
        ),
    )
    result = tb.get_latest_telemetry(_config(), "tok", "ASSET", "asset-1", ["densityPaxPerSqm", "losGrade"])
    assert result["densityPaxPerSqm"][0] == 4.9
    assert result["losGrade"][0] == "E"
    assert "empty_key" not in result


def test_get_server_attributes_parses_numeric_values(monkeypatch):
    monkeypatch.setattr(
        "httpx.get",
        lambda *a, **k: _FakeResponse([{"key": "safeCapacity", "value": 36511}, {"key": "note", "value": "x"}]),
    )
    result = tb.get_server_attributes(_config(), "tok", "ASSET", "asset-1", ["safeCapacity", "note"])
    assert result["safeCapacity"] == 36511.0
    assert result["note"] == "x"


def test_get_raises_on_non_200(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse({}, status_code=500))
    with pytest.raises(tb.ThingsBoardError, match="500"):
        tb.get_server_attributes(_config(), "tok", "ASSET", "x", ["k"])


# --- find_entity_id: exact match, not textSearch's substring match ----------


def test_find_entity_id_exact_match_not_substring(monkeypatch):
    """A textSearch-style substring match would let 'Ramkund' find 'Ramkund
    and near by Ghats' - the wrong asset. This must not happen."""
    monkeypatch.setattr(
        "httpx.get",
        lambda *a, **k: _FakeResponse(
            {"data": [{"name": "Ramkund and near by Ghats", "id": {"id": "asset-1"}}], "hasNext": False}
        ),
    )
    assert tb.find_entity_id(_config(), "tok", "ASSET", "Ramkund") is None
    assert tb.find_entity_id(_config(), "tok", "ASSET", "Ramkund and near by Ghats") == "asset-1"


def test_find_entity_id_pages_until_found(monkeypatch):
    pages = [
        {"data": [{"name": "A", "id": {"id": "a"}}], "hasNext": True},
        {"data": [{"name": "B", "id": {"id": "b"}}], "hasNext": False},
    ]
    calls = {"n": 0}

    def fake_get(*a, **k):
        page = pages[calls["n"]]
        calls["n"] += 1
        return _FakeResponse(page)

    monkeypatch.setattr("httpx.get", fake_get)
    assert tb.find_entity_id(_config(), "tok", "ASSET", "B") == "b"
    assert calls["n"] == 2


# --- live_signals.py: mapping and honest gaps --------------------------------


def test_unmapped_ghat_raises_instead_of_guessing():
    with pytest.raises(ls.LiveSignalUnavailable, match="no known ThingsBoard asset"):
        ls.fetch_ghat_live_reading("kalaram_marg", config=_config())
    with pytest.raises(ls.LiveSignalUnavailable, match="no known ThingsBoard asset"):
        ls.fetch_river_gauge_reading("kushavarta", config=_config())


def test_unconfigured_thingsboard_raises_honest_message():
    with pytest.raises(ls.LiveSignalUnavailable, match="not configured"):
        ls.fetch_ghat_live_reading("ramkund", config=tb.ThingsBoardConfig(base_url="https://x"))


def test_fetch_ghat_live_reading_full_happy_path(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"token": "tok"}))

    def fake_get(url, params=None, headers=None, **kw):
        assert headers["X-Authorization"] == "Bearer tok"
        if url.endswith("/api/tenant/assets"):
            return _FakeResponse(
                {"data": [{"name": "Ramkund and near by Ghats", "id": {"id": "asset-1"}}], "hasNext": False}
            )
        if url.endswith("/values/timeseries"):
            return _FakeResponse(
                {
                    "paxCount": [{"ts": 1700000000000, "value": "9000"}],
                    "densityPaxPerSqm": [{"ts": 1700000000000, "value": "4.9"}],
                    "occupancyPct": [{"ts": 1700000000000, "value": "24.6"}],
                    "losGrade": [{"ts": 1700000000000, "value": "E"}],
                }
            )
        if url.endswith("/values/attributes/SERVER_SCOPE"):
            return _FakeResponse([{"key": "safeCapacity", "value": 36511}, {"key": "areaSqm", "value": 18255.6}])
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("httpx.get", fake_get)
    reading = ls.fetch_ghat_live_reading("ramkund", config=_config())
    assert reading.pax_count == 9000
    assert reading.los_grade == "E"
    assert reading.reported_safe_capacity == 36511
    assert ls.los_grade_to_risk_label(reading.los_grade) == "critical"


def test_fetch_ghat_live_reading_when_asset_not_provisioned(monkeypatch):
    """A mapped ghat_id but a tenant that has not been provisioned yet (or
    points at the wrong instance) - must fail honestly, not fabricate."""
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"token": "tok"}))
    monkeypatch.setattr("httpx.get", lambda *a, **k: _FakeResponse({"data": [], "hasNext": False}))
    with pytest.raises(ls.LiveSignalUnavailable, match="was not found"):
        ls.fetch_ghat_live_reading("ramkund", config=_config())


@pytest.mark.parametrize(
    "level,trend,warning,danger,expected",
    [
        (3.0, 2.0, 4.5, 5.5, RiverStage.NORMAL),
        (4.0, 20.0, 4.5, 5.5, RiverStage.RISING),  # below warning but rising fast
        (4.8, 2.0, 4.5, 5.5, RiverStage.WARNING),
        (5.8, 2.0, 4.5, 5.5, RiverStage.DANGER),
        (5.5, 2.0, 4.5, 5.5, RiverStage.DANGER),  # boundary: >= danger counts as danger
    ],
)
def test_river_gauge_stage_derivation(monkeypatch, level, trend, warning, danger, expected):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"token": "tok"}))

    def fake_get(url, params=None, headers=None, **kw):
        if url.endswith("/api/tenant/devices"):
            return _FakeResponse(
                {"data": [{"name": "Ramkund and near by Ghats :: level", "id": {"id": "dev-1"}}], "hasNext": False}
            )
        if url.endswith("/values/timeseries"):
            return _FakeResponse(
                {"levelM": [{"ts": 1700000000000, "value": str(level)}],
                 "trendCmPerHr": [{"ts": 1700000000000, "value": str(trend)}]}
            )
        if url.endswith("/values/attributes/SERVER_SCOPE"):
            return _FakeResponse([{"key": "warningLevelM", "value": warning}, {"key": "dangerLevelM", "value": danger}])
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("httpx.get", fake_get)
    reading = ls.fetch_river_gauge_reading("ramkund", config=_config())
    assert reading.derived_stage == expected


def test_cross_check_reports_disagreement_without_resolving_it():
    from trinetra.models import Ghat, GhatLiveReading
    from datetime import datetime, timezone

    ghat = Ghat(id="ramkund", name="Ramkund", location="Nashik", safe_capacity=8000,
                access_points=4, narrowest_approach_m=3.5)
    reading = GhatLiveReading(
        ghat_id="ramkund", thingsboard_asset_name="Ramkund and near by Ghats",
        fetched_at=datetime.now(timezone.utc), pax_count=9000, density_pax_per_sqm=4.9,
        occupancy_pct=24.6, los_grade="E", reported_safe_capacity=36511, reported_area_sqm=18255.6,
    )
    xc = ls.cross_check_ghat_capacity(ghat, reading)
    assert xc.trinetra_safe_capacity == 8000
    assert xc.thingsboard_safe_capacity == 36511
    assert xc.capacity_ratio == pytest.approx(4.56, abs=0.01)
    assert xc.agrees_within_20pct is False


def test_cross_check_agrees_when_within_20_percent():
    from trinetra.models import Ghat, GhatLiveReading
    from datetime import datetime, timezone

    ghat = Ghat(id="ramkund", name="Ramkund", location="Nashik", safe_capacity=8000,
                access_points=4, narrowest_approach_m=3.5)
    reading = GhatLiveReading(
        ghat_id="ramkund", thingsboard_asset_name="x", fetched_at=datetime.now(timezone.utc),
        pax_count=100, density_pax_per_sqm=1.0, occupancy_pct=1.0, los_grade="A",
        reported_safe_capacity=8500, reported_area_sqm=1000.0,
    )
    xc = ls.cross_check_ghat_capacity(ghat, reading)
    assert xc.agrees_within_20pct is True


def test_los_grade_to_risk_label_unknown_grade_returns_none():
    assert ls.los_grade_to_risk_label(None) is None
    assert ls.los_grade_to_risk_label("Z") is None
    assert ls.los_grade_to_risk_label("a") == "routine"  # case-insensitive
