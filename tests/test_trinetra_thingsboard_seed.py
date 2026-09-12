"""Offline tests for Anukaran Netra's synthetic telemetry generator
(tools/thingsboard_seed.py). All HTTP is monkeypatched - same convention as
the rest of tests/test_trinetra_thingsboard*.py.
"""
from __future__ import annotations

import pytest

from trinetra.models import ScenarioDirective
from trinetra.tools import thingsboard as tb
from trinetra.tools import thingsboard_seed as seed


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json


def _config():
    return tb.ThingsBoardConfig(base_url="https://demo.thingsboard.io", username="u", password="p")


def _directive(**overrides):
    defaults = dict(narrative="test", baseline_multiplier=1.0, cycle_minutes=60)
    defaults.update(overrides)
    return ScenarioDirective(**defaults)


# --- pure tick math ----------------------------------------------------------


def test_crowd_shape_monotonic_zero_to_one():
    """Monotonic build-up ending at 1.0 exactly at cycle_minutes ("now") -
    not a rise-then-fall hump. See _crowd_shape's own docstring for why:
    run_seeding_cycle backdates its last tick to "now", and a shape that
    fell back toward zero by the end would make the latest pushed value
    read as calm even for a "building toward a peak" scenario."""
    assert seed._crowd_shape(0, 120) == 0.0
    assert seed._crowd_shape(120, 120) == pytest.approx(1.0)
    assert seed._crowd_shape(60, 120) < seed._crowd_shape(120, 120)
    assert 0.0 < seed._crowd_shape(60, 120) < 1.0


def test_compute_pax_count_is_reproducible():
    calib = seed._GhatCalibration(
        asset_name="Ramkund and near by Ghats", asset_id="x", safe_capacity=36511, area_sqm=18255.6,
        warning_level_m=None, danger_level_m=None, river_device_id=None,
    )
    d = _directive(cycle_minutes=120)
    a = seed.compute_pax_count(calib, d, 45)
    b = seed.compute_pax_count(calib, d, 45)
    assert a == b
    assert a > 0


def test_compute_pax_count_surge_ghat_exceeds_baseline():
    calib = seed._GhatCalibration(
        asset_name="Someshwar Ghat", asset_id="y", safe_capacity=32496, area_sqm=16248.0,
        warning_level_m=None, danger_level_m=None, river_device_id=None,
    )
    baseline = _directive(baseline_multiplier=1.0, cycle_minutes=120)
    surged = _directive(baseline_multiplier=1.0, cycle_minutes=120,
                         surge_asset_names=["Someshwar Ghat"], surge_multiplier=1.8)
    assert seed.compute_pax_count(calib, surged, 60) > seed.compute_pax_count(calib, baseline, 60)


def test_compute_pax_count_never_negative():
    calib = seed._GhatCalibration(
        asset_name="X", asset_id="x", safe_capacity=1000, area_sqm=500,
        warning_level_m=None, danger_level_m=None, river_device_id=None,
    )
    d = _directive(baseline_multiplier=0.2, cycle_minutes=60)
    for m in range(0, 61, 5):
        assert seed.compute_pax_count(calib, d, m) >= 0


def test_compute_river_reading_none_without_thresholds():
    calib = seed._GhatCalibration(
        asset_name="X", asset_id="x", safe_capacity=1000, area_sqm=500,
        warning_level_m=None, danger_level_m=None, river_device_id="dev",
    )
    assert seed.compute_river_reading(calib, _directive(), 30) is None


def test_compute_river_reading_approaches_danger_at_full_intensity_at_end_of_cycle():
    calib = seed._GhatCalibration(
        asset_name="X", asset_id="x", safe_capacity=1000, area_sqm=500,
        warning_level_m=4.5, danger_level_m=5.5, river_device_id="dev",
    )
    d = _directive(flood_intensity=1.0, cycle_minutes=60)
    level, trend = seed.compute_river_reading(calib, d, 60)  # end of cycle = "now" = shape 1.0
    assert level == pytest.approx(5.5, abs=0.01)
    assert trend > 0


def test_compute_river_reading_trend_grows_monotonically_toward_now():
    """Same monotonic build-up as crowd - "now" (the last tick) is always
    at least as elevated as any earlier point, never a point already past
    a peak - see _crowd_shape's own docstring for why."""
    calib = seed._GhatCalibration(
        asset_name="X", asset_id="x", safe_capacity=1000, area_sqm=500,
        warning_level_m=4.5, danger_level_m=5.5, river_device_id="dev",
    )
    d = _directive(flood_intensity=0.8, cycle_minutes=60)
    _, trend_early = seed.compute_river_reading(calib, d, 10)
    _, trend_late = seed.compute_river_reading(calib, d, 50)
    assert 0 <= trend_early < trend_late


def test_scenario_directive_bounds_are_enforced():
    with pytest.raises(Exception):
        ScenarioDirective(narrative="x", baseline_multiplier=10.0, cycle_minutes=60)  # over max
    with pytest.raises(Exception):
        ScenarioDirective(narrative="x", baseline_multiplier=1.0, cycle_minutes=5)  # under min


# --- run_seeding_cycle: config/auth failure paths, no live network ----------


def test_run_seeding_cycle_reports_honest_error_when_unconfigured():
    summary = seed.run_seeding_cycle(_directive(), config=tb.ThingsBoardConfig(base_url="https://x"))
    assert summary.ticks_pushed == 0
    assert summary.errors
    assert "not configured" in summary.errors[0]
    assert set(summary.skipped_assets) == set(seed.KNOWN_GHAT_ASSET_NAMES)


def test_run_seeding_cycle_reports_honest_error_on_auth_failure(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({}, status_code=401))
    summary = seed.run_seeding_cycle(_directive(), config=_config())
    assert summary.ticks_pushed == 0
    assert any("authenticate" in e for e in summary.errors)


def test_run_seeding_cycle_pushes_crowd_and_river_for_a_known_ghat(monkeypatch):
    posted = []
    monkeypatch.setattr("httpx.post", lambda url, json=None, **k: (
        posted.append((url, json)) or _FakeResponse({"token": "tok"} if url.endswith("/api/auth/login") else {}, 200)
    ))

    def fake_get(url, params=None, headers=None, **kw):
        if url.endswith("/api/tenant/assets"):
            return _FakeResponse(
                {"data": [{"name": "Someshwar Ghat", "id": {"id": "asset-1"}}], "hasNext": False}
            )
        if url.endswith("/api/tenant/devices"):
            return _FakeResponse(
                {"data": [{"name": "Someshwar Ghat :: level", "id": {"id": "dev-1"}}], "hasNext": False}
            )
        if url.endswith("/attributes/SERVER_SCOPE") and "asset-1" in url:
            return _FakeResponse([{"key": "safeCapacity", "value": 32496}, {"key": "areaSqm", "value": 16248.0}])
        if url.endswith("/attributes/SERVER_SCOPE") and "dev-1" in url:
            return _FakeResponse([{"key": "warningLevelM", "value": 4.5}, {"key": "dangerLevelM", "value": 5.5}])
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("httpx.get", fake_get)

    # Only exercise one known ghat to keep the fake tenant small.
    monkeypatch.setattr(seed, "KNOWN_GHAT_ASSET_NAMES", ("Someshwar Ghat",))
    monkeypatch.setattr(seed, "GHAT_ASSET_NAMES_WITH_RIVER_GAUGE", frozenset({"Someshwar Ghat"}))

    directive = _directive(cycle_minutes=20)
    summary = seed.run_seeding_cycle(directive, tick_minutes=10, config=_config())

    assert summary.assets_touched == ["Someshwar Ghat"]
    assert summary.river_gauges_touched == ["Someshwar Ghat"]
    assert summary.ticks_pushed > 0
    assert not summary.errors

    telemetry_posts = [p for p in posted if "/timeseries/" in p[0]]
    assert any("asset-1" in url for url, _ in telemetry_posts)
    assert any("dev-1" in url for url, _ in telemetry_posts)
    # Every crowd push must be a real paxCount, never missing/None.
    for url, body in telemetry_posts:
        if "asset-1" in url:
            values = body.get("values", body)
            assert isinstance(values.get("paxCount"), int)


def test_run_seeding_cycle_reports_river_gauge_missing_thresholds_honestly(monkeypatch):
    """Regression test for a real finding on the live demo.thingsboard.io
    tenant: every WaterLevelGauge device exists, but none currently have
    warningLevelM/dangerLevelM attributes set. An earlier version of this
    module silently pushed nothing for the river in that case, with no
    entry anywhere a caller could see - this pins that it is now reported
    once per ghat, not swallowed, and crowd data still gets pushed."""
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"token": "tok"}))

    def fake_get(url, params=None, headers=None, **kw):
        if url.endswith("/api/tenant/assets"):
            return _FakeResponse({"data": [{"name": "Someshwar Ghat", "id": {"id": "asset-1"}}], "hasNext": False})
        if url.endswith("/api/tenant/devices"):
            return _FakeResponse(
                {"data": [{"name": "Someshwar Ghat :: level", "id": {"id": "dev-1"}}], "hasNext": False}
            )
        if url.endswith("/attributes/SERVER_SCOPE") and "asset-1" in url:
            return _FakeResponse([{"key": "safeCapacity", "value": 32496}, {"key": "areaSqm", "value": 16248.0}])
        if url.endswith("/attributes/SERVER_SCOPE") and "dev-1" in url:
            return _FakeResponse([])  # device exists, but no threshold attributes - the real finding
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("httpx.get", fake_get)
    monkeypatch.setattr(seed, "KNOWN_GHAT_ASSET_NAMES", ("Someshwar Ghat",))
    monkeypatch.setattr(seed, "GHAT_ASSET_NAMES_WITH_RIVER_GAUGE", frozenset({"Someshwar Ghat"}))

    directive = _directive(cycle_minutes=20, flood_intensity=0.8)
    summary = seed.run_seeding_cycle(directive, tick_minutes=10, config=_config())

    assert summary.assets_touched == ["Someshwar Ghat"]  # crowd data still pushed
    assert summary.river_gauges_touched == []  # river was not
    assert not summary.errors  # this is a documented gap, not a failure
    assert len(summary.skipped_river_gauges) == 1
    assert "Someshwar Ghat" in summary.skipped_river_gauges[0]
    assert "warningLevelM" in summary.skipped_river_gauges[0]


def test_run_seeding_cycle_skips_ghat_missing_capacity_attributes(monkeypatch):
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"token": "tok"}))

    def fake_get(url, params=None, headers=None, **kw):
        if url.endswith("/api/tenant/assets"):
            return _FakeResponse({"data": [{"name": "Someshwar Ghat", "id": {"id": "asset-1"}}], "hasNext": False})
        if url.endswith("/attributes/SERVER_SCOPE"):
            return _FakeResponse([])  # no safeCapacity/areaSqm attributes at all
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr("httpx.get", fake_get)
    monkeypatch.setattr(seed, "KNOWN_GHAT_ASSET_NAMES", ("Someshwar Ghat",))
    monkeypatch.setattr(seed, "GHAT_ASSET_NAMES_WITH_RIVER_GAUGE", frozenset())

    summary = seed.run_seeding_cycle(_directive(), config=_config())
    assert summary.ticks_pushed == 0
    assert summary.assets_touched == []
    assert any("Someshwar Ghat" in s for s in summary.skipped_assets)
