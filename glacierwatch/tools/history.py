"""Persistent run-history load/append/save, plus the trend classification
that history makes possible - all pure code, no LLM, same discipline as the
rest of this project's structured data flowing through deterministic
functions rather than a model's own retelling.

Same shape as tools/watchlist.py: plain functions, not `@tool`-decorated,
because the orchestrator needs the full structured RunHistory/HistoryEntry
objects, not a text summary it would have to re-parse.

Without this, GlacierWatch's weekly triage is a single-snapshot judgment -
it decides this week's priority level from this week's conditions alone,
with no memory of prior weeks. A site whose recent-day rainfall and nearby
seismic activity have been climbing for three straight weekly runs is a
meaningfully different situation from a site with the same absolute
readings today but a flat or declining trend, even when neither has yet
crossed the "priority" threshold this week - and that trajectory is
invisible without this file.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from glacierwatch.models import HistoryEntry, RunHistory, SiteTrend, TrendClassification

# This run plus its 3 most recent predecessors - "2-4 prior snapshots" per
# the feature's design goal, capped so a long-running deployment's history
# file doesn't make every classification drag in years of stale data.
_WINDOW_SIZE = 4
_MIN_PRIOR_RUNS = 2


def load_history(path: str) -> RunHistory:
    """Load prior run history from `path`.

    A missing file is not an error - it just means this is the first run,
    so an empty RunHistory is returned. A malformed or empty file (corrupted
    JSON, or JSON that doesn't match RunHistory's shape) is also not fatal:
    a bad history file must never take down the rest of the pipeline, so
    this returns a fresh empty RunHistory rather than raising. Either way
    the caller gets a usable RunHistory back and this run's data still gets
    recorded going forward.
    """
    file_path = Path(path)
    if not file_path.exists():
        return RunHistory()

    raw = file_path.read_text(encoding="utf-8")
    if not raw.strip():
        return RunHistory()

    try:
        return RunHistory.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError):
        return RunHistory()


def append_entries(history: RunHistory, new_entries: list[HistoryEntry]) -> RunHistory:
    """Return a new RunHistory with `new_entries` appended. Pure - doesn't
    touch disk; call save_history separately to persist the result."""
    return RunHistory(entries=[*history.entries, *new_entries])


def save_history(path: str, history: RunHistory) -> None:
    """Write `history` to `path` as JSON, creating parent directories as
    needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(history.model_dump_json(indent=2), encoding="utf-8")


def classify_trend(entries: list[HistoryEntry]) -> tuple[TrendClassification, str]:
    """Classify a trend from `entries`, ordered oldest-to-newest, where the
    last entry is this run's data and every entry before it is a past run
    for the same site.

    This is deliberately simple, not statistics - an honest, explainable
    rule over a handful of numbers, not a sophisticated model:

    - Compute the run-over-run delta between each consecutive pair of
      entries, separately for max_daily_precipitation_mm and for
      nearby_seismic_events.
    - RISING: every consecutive delta on BOTH signals is >= 0 (neither
      signal ever dropped run over run), AND at least one delta on either
      signal is strictly > 0 (something actually increased somewhere in the
      window - two identical flat runs are FLAT, not RISING).
    - FALLING: the mirror image - every consecutive delta on both signals is
      <= 0, with at least one strictly < 0.
    - FLAT: anything else. This includes genuinely unchanged readings and
      mixed signals (e.g. rainfall climbing while seismic activity falls).
      FLAT is the conservative default on purpose: an early-warning tracker
      that calls noisy, contradictory data "rising" would be worse than
      useless for triage.
    """
    precip_deltas = [
        b.max_daily_precipitation_mm - a.max_daily_precipitation_mm for a, b in zip(entries, entries[1:])
    ]
    seismic_deltas = [b.nearby_seismic_events - a.nearby_seismic_events for a, b in zip(entries, entries[1:])]

    precip_summary = (
        f"max daily precipitation {entries[0].max_daily_precipitation_mm:.1f}mm -> "
        f"{entries[-1].max_daily_precipitation_mm:.1f}mm"
    )
    seismic_summary = f"nearby seismic events {entries[0].nearby_seismic_events} -> {entries[-1].nearby_seismic_events}"
    summary = f"{precip_summary}, {seismic_summary} over {len(entries)} recorded run(s)."

    all_non_decreasing = all(d >= 0 for d in precip_deltas) and all(d >= 0 for d in seismic_deltas)
    all_non_increasing = all(d <= 0 for d in precip_deltas) and all(d <= 0 for d in seismic_deltas)
    any_increase = any(d > 0 for d in precip_deltas) or any(d > 0 for d in seismic_deltas)
    any_decrease = any(d < 0 for d in precip_deltas) or any(d < 0 for d in seismic_deltas)

    if all_non_decreasing and any_increase:
        return TrendClassification.RISING, f"Rising: {summary}"
    if all_non_increasing and any_decrease:
        return TrendClassification.FALLING, f"Falling: {summary}"
    return TrendClassification.FLAT, f"Flat or mixed, no consistent direction: {summary}"


def compute_site_trends(
    current_entries: list[HistoryEntry],
    prior_history: RunHistory,
    site_names: dict[str, str],
) -> list[SiteTrend]:
    """Classify a trend for every site in `current_entries` (this run's
    freshly recorded signals) against `prior_history` (all past runs, not
    yet including this run - call this before append_entries). `site_names`
    maps site_id -> a human-readable name for the resulting report.

    A site needs at least 2 prior runs recorded plus this run (3 total)
    before a trend is classified; fewer than that is honestly reported as
    insufficient_history rather than guessed at.
    """
    trends = []
    for entry in current_entries:
        prior_for_site = sorted(
            (e for e in prior_history.entries if e.site_id == entry.site_id),
            key=lambda e: e.run_at,
        )
        window = prior_for_site[-(_WINDOW_SIZE - 1):] + [entry]
        site_name = site_names.get(entry.site_id, entry.site_id)

        if len(prior_for_site) < _MIN_PRIOR_RUNS:
            trends.append(
                SiteTrend(
                    site_id=entry.site_id,
                    site_name=site_name,
                    trend=TrendClassification.INSUFFICIENT_HISTORY,
                    runs_considered=len(window),
                    explanation=(
                        f"Only {len(prior_for_site)} prior run(s) recorded for this site - at least "
                        f"{_MIN_PRIOR_RUNS} prior runs plus this one are needed before a trend can be classified."
                    ),
                )
            )
            continue

        trend, explanation = classify_trend(window)
        trends.append(
            SiteTrend(
                site_id=entry.site_id,
                site_name=site_name,
                trend=trend,
                runs_considered=len(window),
                explanation=explanation,
            )
        )
    return trends
