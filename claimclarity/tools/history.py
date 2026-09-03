"""Persistent cross-run insurer-accountability history load/append/save,
plus the recurrence detection it makes possible - all pure code, no LLM,
same discipline as glacierwatch/tools/history.py: structured data flowing
through deterministic functions rather than a model's own retelling.

Plain functions, not `@tool`-decorated, because the orchestrator needs the
full structured ClaimHistory/InsurerPatternInsight objects, not a text
summary it would have to re-parse.

Without this, ClaimClarity evaluates every denial in isolation. The same
patient (or household) often gets multiple denials from the same insurer
over time, and if the *same denial reason* keeps recurring - a specific
CPT/procedure repeatedly denied as "not medically necessary," or the same
documentation excuse reused across otherwise unrelated claims - that is a
materially stronger fact pattern for an appeal or a state DOI complaint than
any single denial looked at alone. This file is what lets ClaimClarity
notice that, across runs, without ever sending the underlying data anywhere:
it lives in the same local JSON file, on the same machine, as every other
file ClaimClarity already writes.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from claimclarity.models import (
    ClaimHistory,
    ClaimHistoryEntry,
    ClaimLineItem,
    ClaimRecord,
    DeniedItemSummary,
    DenialFindings,
    InsurerPatternInsight,
    LineItemFinding,
)

# A pattern needs to recur across at least this many *separate* recorded
# cases before it's reported - one denial is just a denial, not a pattern.
_MIN_OCCURRENCES = 2


def load_history(path: str) -> ClaimHistory:
    """Load prior case history from `path`.

    A missing file is not an error - it just means this is the first case
    ever recorded, so an empty ClaimHistory is returned. A malformed or
    empty file (corrupted JSON, or JSON that doesn't match ClaimHistory's
    shape) is also not fatal: a bad history file must never take down the
    rest of the pipeline, so this returns a fresh empty ClaimHistory rather
    than raising. Either way the caller gets a usable ClaimHistory back and
    this case's data still gets recorded going forward.
    """
    file_path = Path(path)
    if not file_path.exists():
        return ClaimHistory()

    raw = file_path.read_text(encoding="utf-8")
    if not raw.strip():
        return ClaimHistory()

    try:
        return ClaimHistory.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError):
        return ClaimHistory()


def _denial_reason_category(line_item: ClaimLineItem, finding: LineItemFinding | None) -> str:
    """The recurrence-matching key for one denied line item: the EOB's own
    CARC code if it stated one (standardized across insurers, so the
    strongest signal available), else the EOB's own literal denial reason
    text, else - if neither was stated - the investigation's classification.
    Always exact/near-exact string comparison; see detect_insurer_patterns'
    docstring for the honest limitation this implies."""
    if line_item.carc_code.strip():
        return line_item.carc_code.strip().upper()
    if line_item.denial_reason_text.strip():
        return line_item.denial_reason_text.strip()
    if finding is not None:
        return finding.classification.value
    return "unspecified"


def build_case_entry(claim: ClaimRecord, findings: DenialFindings, recorded_at: str) -> ClaimHistoryEntry:
    """Build this case's compact history entry from the full ClaimRecord and
    DenialFindings. Deliberately narrow - no patient name, member ID,
    diagnosis code, billed amount, or clinical notes - so the persisted
    history stays limited to what recurrence matching actually needs, not a
    second copy of the patient's medical record."""
    findings_by_code = {f.procedure_code: f for f in findings.findings}
    denied_items = [
        DeniedItemSummary(
            procedure_code=line_item.procedure_code,
            procedure_description=line_item.procedure_description,
            denial_reason_category=_denial_reason_category(line_item, findings_by_code.get(line_item.procedure_code)),
            worth_appealing=(
                findings_by_code[line_item.procedure_code].worth_appealing
                if line_item.procedure_code in findings_by_code
                else False
            ),
        )
        for line_item in claim.line_items
    ]
    return ClaimHistoryEntry(
        insurer_name=claim.insurer_name,
        recorded_at=recorded_at,
        claim_number=claim.claim_number,
        denied_items=denied_items,
    )


def append_entry(history: ClaimHistory, new_entry: ClaimHistoryEntry) -> ClaimHistory:
    """Return a new ClaimHistory with `new_entry` appended. Pure - doesn't
    touch disk; call save_history separately to persist the result."""
    return ClaimHistory(entries=[*history.entries, new_entry])


def save_history(path: str, history: ClaimHistory) -> None:
    """Write `history` to `path` as JSON, creating parent directories as
    needed."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(history.model_dump_json(indent=2), encoding="utf-8")


def detect_insurer_patterns(history: ClaimHistory) -> list[InsurerPatternInsight]:
    """Scan `history` for denial-reason patterns from the same insurer that
    recur across 2+ *separate* recorded cases, by plain code - never an LLM
    judgment call.

    Grouping key is (insurer name, denial reason category), both compared
    case-insensitively after stripping whitespace. A case that denies the
    same procedure twice on the same basis only counts once toward a
    pattern's occurrence count - the point is a pattern *across claims over
    time*, not a claim padded with duplicate line items.

    Known limitation, documented honestly rather than hidden: this is
    exact/near-exact string matching, not semantic matching. "Not medically
    necessary" and "medical necessity not established" would be treated as
    two different denial reasons even though a person reading both would
    recognize them as the same excuse worded differently. Recurrence found
    here is real; recurrence NOT found here is not proof there isn't one -
    it just means the wording didn't line up closely enough to match.
    """
    entries_by_group: dict[tuple[str, str], list[ClaimHistoryEntry]] = {}
    representative_item: dict[tuple[str, str], DeniedItemSummary] = {}

    for entry in history.entries:
        insurer_key = entry.insurer_name.strip().lower()
        if not insurer_key:
            continue
        reasons_seen_this_entry: set[str] = set()
        for item in entry.denied_items:
            reason_key = item.denial_reason_category.strip().lower()
            if not reason_key or reason_key in reasons_seen_this_entry:
                continue
            reasons_seen_this_entry.add(reason_key)
            group_key = (insurer_key, reason_key)
            entries_by_group.setdefault(group_key, []).append(entry)
            representative_item[group_key] = item

    insights = []
    for group_key, matching_entries in entries_by_group.items():
        if len(matching_entries) < _MIN_OCCURRENCES:
            continue
        # history.entries is append-only in chronological order, so this is
        # already oldest-to-newest.
        rep_item = representative_item[group_key]
        insights.append(
            InsurerPatternInsight(
                insurer_name=matching_entries[-1].insurer_name,
                denial_reason_category=rep_item.denial_reason_category,
                procedure_description=rep_item.procedure_description,
                occurrence_count=len(matching_entries),
                dates=[entry.recorded_at for entry in matching_entries],
                claim_numbers=[entry.claim_number for entry in matching_entries if entry.claim_number],
            )
        )

    return sorted(insights, key=lambda i: (-i.occurrence_count, i.insurer_name, i.denial_reason_category))
