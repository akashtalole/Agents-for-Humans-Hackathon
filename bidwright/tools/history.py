"""Persistent cross-bid history load/append/save, plus the recurrence
detection that history makes possible - all pure code, no LLM, same
discipline as the rest of this project's structured data flowing through
deterministic functions rather than a model's own retelling.

Same shape as glacierwatch/tools/history.py: plain functions, not
`@tool`-decorated, because the orchestrator needs the full structured
BidHistory/BidHistoryEntry objects, not a text summary it would have to
re-parse.

Without this, every BidWright run is a single-snapshot judgment - the
compliance report for one RFP has no way to know that "insufficient bonding
capacity" was also the blocking gap on the last three bids this company
lost. Nobody notices a recurring, fixable pattern across bids because
nothing persists across runs to notice it with.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from bidwright.models import BidHistory, BidHistoryEntry, RecurringGapInsight

# "The last N runs" - a small, fixed lookback so an old, long-since-fixed
# gap from years ago doesn't keep surfacing as "recurring" forever, and so a
# long-running deployment's history file doesn't make every scan drag in a
# company's entire bidding history.
DEFAULT_WINDOW_SIZE = 5
_MIN_OCCURRENCES = 2


def load_history(path: str) -> BidHistory:
    """Load prior bid history from `path`.

    A missing file is not an error - it just means this is the first run,
    so an empty BidHistory is returned. A malformed or empty file (corrupted
    JSON, or JSON that doesn't match BidHistory's shape) is also not fatal:
    a bad history file must never take down the rest of the pipeline, so
    this returns a fresh empty BidHistory rather than raising. Either way
    the caller gets a usable BidHistory back and this run's data still gets
    recorded going forward.
    """
    file_path = Path(path)
    if not file_path.exists():
        return BidHistory()

    raw = file_path.read_text(encoding="utf-8")
    if not raw.strip():
        return BidHistory()

    try:
        return BidHistory.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError):
        return BidHistory()


def append_entry(history: BidHistory, entry: BidHistoryEntry) -> BidHistory:
    """Return a new BidHistory with `entry` appended. Pure - doesn't touch
    disk; call save_history separately to persist the result."""
    return BidHistory(entries=[*history.entries, entry])


def save_history(path: str, history: BidHistory) -> None:
    """Write `history` to `path` as JSON, creating parent directories as
    needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(history.model_dump_json(indent=2), encoding="utf-8")


def detect_recurring_gaps(
    history: BidHistory, window_size: int = DEFAULT_WINDOW_SIZE
) -> list[RecurringGapInsight]:
    """Scan the most recent `window_size` runs in `history` (entries are
    stored oldest-first, so this is the tail of the list) for gap
    requirement descriptions that appear in at least 2 of those runs.

    Call this AFTER appending the current run's entry, so a gap that only
    ever appeared once before now correctly surfaces as "2 of N" the moment
    it recurs, rather than reporting "1 of N" a step behind.

    Matching is exact string equality on the gap requirement description -
    a known, honest limitation, not an oversight. "Insufficient bonding
    capacity" and "bonding capacity too low" describe the same real-world
    problem but will NOT match each other without a normalization step this
    function doesn't attempt (e.g. lowercasing plus a synonym/embedding
    pass). A simple, predictable rule that's honest about what it misses
    beats a fuzzy matcher whose behavior no one could reliably predict -
    if this limitation turns out to matter in practice, that normalization
    step belongs here, isolated from everything else in this module.

    Results are sorted by occurrence count, most-recurring first.
    """
    recent = history.entries[-window_size:]

    occurrences_by_requirement: dict[str, list[BidHistoryEntry]] = {}
    for entry in recent:
        for gap in entry.gaps:
            occurrences_by_requirement.setdefault(gap.requirement, []).append(entry)

    insights = []
    for requirement, occurring_entries in occurrences_by_requirement.items():
        if len(occurring_entries) < _MIN_OCCURRENCES:
            continue
        first_entry = occurring_entries[0]
        most_recent_entry = occurring_entries[-1]
        most_recent_gap = next(
            g for g in most_recent_entry.gaps if g.requirement == requirement
        )
        insights.append(
            RecurringGapInsight(
                requirement=requirement,
                severity=most_recent_gap.severity,
                occurrences=len(occurring_entries),
                runs_considered=len(recent),
                first_seen_rfp=f"{first_entry.project_title} ({first_entry.issuing_organization})",
                most_recent_rfp=f"{most_recent_entry.project_title} ({most_recent_entry.issuing_organization})",
            )
        )

    insights.sort(key=lambda i: i.occurrences, reverse=True)
    return insights
