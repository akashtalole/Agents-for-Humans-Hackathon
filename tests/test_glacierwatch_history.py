from pathlib import Path

from glacierwatch.models import HistoryEntry, PriorityLevel, RunHistory, TrendClassification
from glacierwatch.tools.history import append_entries, classify_trend, compute_site_trends, load_history, save_history


def _entry(site_id="gepang-gath", run_at="2026-08-01T00:00:00Z", mm=10.0, quakes=0, priority=PriorityLevel.ROUTINE):
    return HistoryEntry(
        site_id=site_id, run_at=run_at, max_daily_precipitation_mm=mm, nearby_seismic_events=quakes,
        priority_level=priority,
    )


# --- load/append/save round trip ---------------------------------------


def test_load_history_missing_file_starts_fresh(tmp_path: Path):
    history = load_history(str(tmp_path / "does_not_exist.json"))
    assert history == RunHistory()
    assert history.entries == []


def test_load_history_empty_file_starts_fresh(tmp_path: Path):
    path = tmp_path / "empty.json"
    path.write_text("", encoding="utf-8")
    history = load_history(str(path))
    assert history.entries == []


def test_load_history_malformed_json_fails_gracefully(tmp_path: Path):
    path = tmp_path / "malformed.json"
    path.write_text("{not valid json at all", encoding="utf-8")
    history = load_history(str(path))
    assert history.entries == []


def test_load_history_valid_json_wrong_shape_fails_gracefully(tmp_path: Path):
    path = tmp_path / "wrong_shape.json"
    path.write_text('{"entries": [{"totally": "wrong"}]}', encoding="utf-8")
    history = load_history(str(path))
    assert history.entries == []


def test_append_entries_is_pure_and_preserves_order():
    history = RunHistory(entries=[_entry(run_at="2026-08-01T00:00:00Z")])
    new = [_entry(run_at="2026-08-08T00:00:00Z")]
    updated = append_entries(history, new)

    assert len(updated.entries) == 2
    assert [e.run_at for e in updated.entries] == ["2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z"]
    # Pure - the original history is untouched.
    assert len(history.entries) == 1


def test_save_and_load_history_round_trips(tmp_path: Path):
    path = tmp_path / "nested" / "history.json"
    history = RunHistory(
        entries=[
            _entry(run_at="2026-08-01T00:00:00Z", mm=12.0, quakes=1),
            _entry(run_at="2026-08-08T00:00:00Z", mm=45.0, quakes=2, priority=PriorityLevel.ELEVATED),
        ]
    )
    save_history(str(path), history)
    assert path.exists()

    reloaded = load_history(str(path))
    assert reloaded == history


# --- trend classification -----------------------------------------------


def test_classify_trend_insufficient_history_via_compute_site_trends():
    current = [_entry(run_at="2026-08-15T00:00:00Z", mm=50.0, quakes=1)]
    prior_history = RunHistory(entries=[_entry(run_at="2026-08-01T00:00:00Z", mm=10.0, quakes=0)])

    trends = compute_site_trends(current, prior_history, {"gepang-gath": "Gepang Gath Lake"})
    assert len(trends) == 1
    assert trends[0].trend == TrendClassification.INSUFFICIENT_HISTORY
    assert trends[0].site_name == "Gepang Gath Lake"
    assert trends[0].runs_considered == 2


def test_classify_trend_no_prior_runs_is_insufficient_history():
    current = [_entry(run_at="2026-08-15T00:00:00Z")]
    trends = compute_site_trends(current, RunHistory(), {})
    assert trends[0].trend == TrendClassification.INSUFFICIENT_HISTORY
    assert trends[0].runs_considered == 1
    # Falls back to the site_id when no name is supplied.
    assert trends[0].site_name == "gepang-gath"


def test_classify_trend_rising_when_both_signals_climb():
    entries = [
        _entry(run_at="2026-08-01T00:00:00Z", mm=10.0, quakes=0),
        _entry(run_at="2026-08-08T00:00:00Z", mm=25.0, quakes=1),
        _entry(run_at="2026-08-15T00:00:00Z", mm=60.0, quakes=3),
    ]
    trend, explanation = classify_trend(entries)
    assert trend == TrendClassification.RISING
    assert "Rising" in explanation


def test_classify_trend_rising_when_one_signal_climbs_and_other_flat():
    # Precipitation climbing while seismic count stays flat at 0 is still a
    # real rise per the documented rule (non-decreasing on both, strict
    # increase on at least one).
    entries = [
        _entry(run_at="2026-08-01T00:00:00Z", mm=10.0, quakes=0),
        _entry(run_at="2026-08-08T00:00:00Z", mm=20.0, quakes=0),
        _entry(run_at="2026-08-15T00:00:00Z", mm=40.0, quakes=0),
    ]
    trend, _ = classify_trend(entries)
    assert trend == TrendClassification.RISING


def test_classify_trend_falling_when_both_signals_decline():
    entries = [
        _entry(run_at="2026-08-01T00:00:00Z", mm=80.0, quakes=4),
        _entry(run_at="2026-08-08T00:00:00Z", mm=40.0, quakes=2),
        _entry(run_at="2026-08-15T00:00:00Z", mm=10.0, quakes=0),
    ]
    trend, explanation = classify_trend(entries)
    assert trend == TrendClassification.FALLING
    assert "Falling" in explanation


def test_classify_trend_flat_when_readings_are_unchanged():
    entries = [
        _entry(run_at="2026-08-01T00:00:00Z", mm=10.0, quakes=1),
        _entry(run_at="2026-08-08T00:00:00Z", mm=10.0, quakes=1),
        _entry(run_at="2026-08-15T00:00:00Z", mm=10.0, quakes=1),
    ]
    trend, _ = classify_trend(entries)
    assert trend == TrendClassification.FLAT


def test_classify_trend_flat_when_signals_are_mixed():
    # Rain climbing while seismic activity falls - conservative default,
    # never called "rising" on contradictory signals.
    entries = [
        _entry(run_at="2026-08-01T00:00:00Z", mm=10.0, quakes=5),
        _entry(run_at="2026-08-08T00:00:00Z", mm=30.0, quakes=2),
        _entry(run_at="2026-08-15T00:00:00Z", mm=60.0, quakes=0),
    ]
    trend, explanation = classify_trend(entries)
    assert trend == TrendClassification.FLAT
    assert "mixed" in explanation.lower()


def test_compute_site_trends_windows_to_last_four_entries():
    # Five prior runs, oldest one has a huge drop that should be excluded
    # from a 4-entry window (this run + 3 most recent predecessors), so the
    # overall classification should still read as rising.
    prior_history = RunHistory(
        entries=[
            _entry(run_at="2026-07-01T00:00:00Z", mm=500.0, quakes=10),
            _entry(run_at="2026-07-08T00:00:00Z", mm=5.0, quakes=0),
            _entry(run_at="2026-07-15T00:00:00Z", mm=10.0, quakes=0),
            _entry(run_at="2026-07-22T00:00:00Z", mm=20.0, quakes=1),
        ]
    )
    current = [_entry(run_at="2026-07-29T00:00:00Z", mm=40.0, quakes=2)]

    trends = compute_site_trends(current, prior_history, {})
    assert trends[0].trend == TrendClassification.RISING
    assert trends[0].runs_considered == 4


def test_compute_site_trends_only_considers_the_given_site():
    prior_history = RunHistory(
        entries=[
            _entry(site_id="other-site", run_at="2026-08-01T00:00:00Z", mm=10.0),
            _entry(site_id="other-site", run_at="2026-08-08T00:00:00Z", mm=20.0),
        ]
    )
    current = [_entry(site_id="gepang-gath", run_at="2026-08-15T00:00:00Z")]

    trends = compute_site_trends(current, prior_history, {})
    assert trends[0].site_id == "gepang-gath"
    assert trends[0].trend == TrendClassification.INSUFFICIENT_HISTORY
