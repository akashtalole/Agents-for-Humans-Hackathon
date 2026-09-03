"""Offline unit tests for BidWright's persistent cross-bid history and
recurrence detection (bidwright/tools/history.py) - pure code, no LLM, no
network access required. Mirrors tests/test_glacierwatch_history.py.
"""
from __future__ import annotations

from pathlib import Path

from bidwright.models import BidHistory, BidHistoryEntry, BidHistoryGap, Severity
from bidwright.tools.history import append_entry, detect_recurring_gaps, load_history, save_history


def _entry(
    project_title="Landscaping Contract",
    org="City of Test",
    run_at="2026-01-01T00:00:00Z",
    status="gaps_found",
    gaps=None,
):
    return BidHistoryEntry(
        project_title=project_title,
        issuing_organization=org,
        run_at=run_at,
        overall_status=status,
        gaps=gaps if gaps is not None else [],
    )


def _gap(requirement="Insufficient bonding capacity", severity=Severity.BLOCKING):
    return BidHistoryGap(requirement=requirement, severity=severity)


# --- load/append/save round trip ---------------------------------------


def test_load_history_missing_file_starts_fresh(tmp_path: Path):
    history = load_history(str(tmp_path / "does_not_exist.json"))
    assert history == BidHistory()
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


def test_append_entry_is_pure_and_preserves_order():
    history = BidHistory(entries=[_entry(run_at="2026-01-01T00:00:00Z")])
    updated = append_entry(history, _entry(run_at="2026-02-01T00:00:00Z"))

    assert len(updated.entries) == 2
    assert [e.run_at for e in updated.entries] == ["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"]
    # Pure - the original history is untouched.
    assert len(history.entries) == 1


def test_save_and_load_history_round_trips(tmp_path: Path):
    path = tmp_path / "nested" / "history.json"
    history = BidHistory(
        entries=[
            _entry(run_at="2026-01-01T00:00:00Z", gaps=[_gap()]),
            _entry(run_at="2026-02-01T00:00:00Z", status="ready", gaps=[]),
        ]
    )
    save_history(str(path), history)
    assert path.exists()

    reloaded = load_history(str(path))
    assert reloaded == history


# --- recurrence detection -------------------------------------------------


def test_detect_recurring_gaps_empty_history_reports_nothing():
    assert detect_recurring_gaps(BidHistory()) == []


def test_detect_recurring_gaps_single_run_is_not_recurring():
    history = BidHistory(entries=[_entry(gaps=[_gap()])])
    assert detect_recurring_gaps(history) == []


def test_detect_recurring_gaps_finds_a_gap_seen_twice():
    history = BidHistory(
        entries=[
            _entry(
                project_title="Landscaping RFP #1",
                org="City of Test",
                run_at="2026-01-01T00:00:00Z",
                gaps=[_gap("Insufficient bonding capacity", Severity.BLOCKING)],
            ),
            _entry(
                project_title="Landscaping RFP #2",
                org="County of Test",
                run_at="2026-02-01T00:00:00Z",
                gaps=[_gap("Insufficient bonding capacity", Severity.BLOCKING)],
            ),
        ]
    )

    insights = detect_recurring_gaps(history)
    assert len(insights) == 1
    insight = insights[0]
    assert insight.requirement == "Insufficient bonding capacity"
    assert insight.severity == Severity.BLOCKING
    assert insight.occurrences == 2
    assert insight.runs_considered == 2
    assert insight.first_seen_rfp == "Landscaping RFP #1 (City of Test)"
    assert insight.most_recent_rfp == "Landscaping RFP #2 (County of Test)"


def test_detect_recurring_gaps_ignores_a_gap_seen_only_once():
    history = BidHistory(
        entries=[
            _entry(run_at="2026-01-01T00:00:00Z", gaps=[_gap("Insufficient bonding capacity")]),
            _entry(run_at="2026-02-01T00:00:00Z", gaps=[_gap("Missing OSHA 30 certification")]),
        ]
    )
    assert detect_recurring_gaps(history) == []


def test_detect_recurring_gaps_uses_most_recent_severity():
    history = BidHistory(
        entries=[
            _entry(run_at="2026-01-01T00:00:00Z", gaps=[_gap("Missing OSHA 30 certification", Severity.WARNING)]),
            _entry(run_at="2026-02-01T00:00:00Z", gaps=[_gap("Missing OSHA 30 certification", Severity.BLOCKING)]),
        ]
    )
    insights = detect_recurring_gaps(history)
    assert insights[0].severity == Severity.BLOCKING


def test_detect_recurring_gaps_sorted_by_occurrence_count_descending():
    history = BidHistory(
        entries=[
            _entry(run_at="2026-01-01T00:00:00Z", gaps=[_gap("A"), _gap("B")]),
            _entry(run_at="2026-02-01T00:00:00Z", gaps=[_gap("A")]),
            _entry(run_at="2026-03-01T00:00:00Z", gaps=[_gap("A"), _gap("B")]),
        ]
    )
    insights = detect_recurring_gaps(history)
    assert [i.requirement for i in insights] == ["A", "B"]
    assert insights[0].occurrences == 3
    assert insights[1].occurrences == 2


def test_detect_recurring_gaps_is_exact_match_not_semantic():
    # Documented, known limitation: "insufficient bonding capacity" and
    # "bonding capacity too low" describe the same real gap but are two
    # distinct strings, so they don't count as recurrence of each other.
    history = BidHistory(
        entries=[
            _entry(run_at="2026-01-01T00:00:00Z", gaps=[_gap("Insufficient bonding capacity")]),
            _entry(run_at="2026-02-01T00:00:00Z", gaps=[_gap("Bonding capacity too low")]),
        ]
    )
    assert detect_recurring_gaps(history) == []


def test_detect_recurring_gaps_windows_to_recent_runs_only():
    # Six runs sharing the same gap, but a window_size of 3 should only
    # consider the last 3.
    history = BidHistory(
        entries=[
            _entry(run_at=f"2026-0{i}-01T00:00:00Z", gaps=[_gap("Insufficient bonding capacity")])
            for i in range(1, 5)
        ]
    )
    insights = detect_recurring_gaps(history, window_size=3)
    assert insights[0].occurrences == 3
    assert insights[0].runs_considered == 3


def test_detect_recurring_gaps_non_recurring_history_reports_nothing():
    history = BidHistory(
        entries=[
            _entry(run_at="2026-01-01T00:00:00Z", status="ready", gaps=[]),
            _entry(run_at="2026-02-01T00:00:00Z", status="ready", gaps=[]),
        ]
    )
    assert detect_recurring_gaps(history) == []
