from pathlib import Path

from claimclarity.models import (
    Classification,
    ClaimHistory,
    ClaimHistoryEntry,
    ClaimLineItem,
    ClaimRecord,
    DeniedItemSummary,
    DenialFindings,
    LineItemFinding,
)
from claimclarity.tools.history import (
    append_entry,
    build_case_entry,
    detect_insurer_patterns,
    load_history,
    save_history,
)


def _entry(insurer="Heartland Mutual", recorded_at="2026-01-01T00:00:00+00:00", claim_number="", items=None):
    return ClaimHistoryEntry(
        insurer_name=insurer, recorded_at=recorded_at, claim_number=claim_number, denied_items=items or []
    )


def _item(procedure_code="97110", description="Physical therapy", reason="not medically necessary", worth=True):
    return DeniedItemSummary(
        procedure_code=procedure_code,
        procedure_description=description,
        denial_reason_category=reason,
        worth_appealing=worth,
    )


# --- load/append/save round trip ---------------------------------------


def test_load_history_missing_file_starts_fresh(tmp_path: Path):
    history = load_history(str(tmp_path / "does_not_exist.json"))
    assert history == ClaimHistory()
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
    history = ClaimHistory(entries=[_entry(recorded_at="2026-01-01T00:00:00+00:00")])
    new_entry = _entry(recorded_at="2026-02-01T00:00:00+00:00")
    updated = append_entry(history, new_entry)

    assert len(updated.entries) == 2
    assert [e.recorded_at for e in updated.entries] == ["2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"]
    # Pure - the original history is untouched.
    assert len(history.entries) == 1


def test_save_and_load_history_round_trips(tmp_path: Path):
    path = tmp_path / "nested" / "history.json"
    history = ClaimHistory(
        entries=[
            _entry(recorded_at="2026-01-01T00:00:00+00:00", items=[_item()]),
            _entry(recorded_at="2026-02-01T00:00:00+00:00", items=[_item(worth=False)]),
        ]
    )
    save_history(str(path), history)
    assert path.exists()

    reloaded = load_history(str(path))
    assert reloaded == history


# --- build_case_entry ----------------------------------------------------


def test_build_case_entry_uses_carc_code_when_present():
    claim = ClaimRecord(
        insurer_name="Heartland Mutual",
        claim_number="CLM-1",
        line_items=[
            ClaimLineItem(procedure_code="97110", procedure_description="Physical therapy", carc_code="co-16")
        ],
    )
    findings = DenialFindings(
        overall_recommendation="Appeal it.",
        findings=[
            LineItemFinding(
                procedure_code="97110",
                classification=Classification.BILLING_ERROR,
                evidence="Bad code.",
                recommendation="Appeal.",
                worth_appealing=True,
            )
        ],
    )
    entry = build_case_entry(claim, findings, "2026-01-01T00:00:00+00:00")
    assert entry.insurer_name == "Heartland Mutual"
    assert entry.claim_number == "CLM-1"
    assert len(entry.denied_items) == 1
    item = entry.denied_items[0]
    # Normalized to uppercase - the CARC code is the strongest, most
    # standardized signal, so it wins over the free-text denial reason.
    assert item.denial_reason_category == "CO-16"
    assert item.worth_appealing is True


def test_build_case_entry_falls_back_to_denial_reason_text_then_classification():
    claim_with_text = ClaimRecord(
        insurer_name="Heartland Mutual",
        line_items=[ClaimLineItem(procedure_code="97110", denial_reason_text="Not medically necessary")],
    )
    findings = DenialFindings(overall_recommendation="x", findings=[])
    entry = build_case_entry(claim_with_text, findings, "2026-01-01T00:00:00+00:00")
    assert entry.denied_items[0].denial_reason_category == "Not medically necessary"
    # No matching LineItemFinding was found - worth_appealing conservatively
    # defaults to False rather than guessing.
    assert entry.denied_items[0].worth_appealing is False

    claim_with_neither = ClaimRecord(
        insurer_name="Heartland Mutual", line_items=[ClaimLineItem(procedure_code="97110")]
    )
    findings_with_classification = DenialFindings(
        overall_recommendation="x",
        findings=[
            LineItemFinding(
                procedure_code="97110",
                classification=Classification.VALID_DENIAL,
                evidence="Excluded.",
                recommendation="Don't appeal.",
                worth_appealing=False,
            )
        ],
    )
    entry2 = build_case_entry(claim_with_neither, findings_with_classification, "2026-01-01T00:00:00+00:00")
    assert entry2.denied_items[0].denial_reason_category == "valid_denial"


# --- recurrence detection --------------------------------------------------


def test_detect_insurer_patterns_finds_real_recurrence():
    history = ClaimHistory(
        entries=[
            _entry(
                insurer="Heartland Mutual",
                recorded_at="2026-01-01T00:00:00+00:00",
                claim_number="CLM-1",
                items=[_item(reason="not medically necessary")],
            ),
            _entry(
                insurer="Heartland Mutual",
                recorded_at="2026-04-01T00:00:00+00:00",
                claim_number="CLM-2",
                items=[_item(reason="not medically necessary")],
            ),
        ]
    )
    insights = detect_insurer_patterns(history)
    assert len(insights) == 1
    insight = insights[0]
    assert insight.insurer_name == "Heartland Mutual"
    assert insight.denial_reason_category == "not medically necessary"
    assert insight.occurrence_count == 2
    assert insight.dates == ["2026-01-01T00:00:00+00:00", "2026-04-01T00:00:00+00:00"]
    assert insight.claim_numbers == ["CLM-1", "CLM-2"]


def test_detect_insurer_patterns_single_case_is_not_a_pattern():
    history = ClaimHistory(
        entries=[_entry(recorded_at="2026-01-01T00:00:00+00:00", items=[_item(reason="not medically necessary")])]
    )
    assert detect_insurer_patterns(history) == []


def test_detect_insurer_patterns_different_insurers_never_cross_contaminate():
    history = ClaimHistory(
        entries=[
            _entry(
                insurer="Heartland Mutual",
                recorded_at="2026-01-01T00:00:00+00:00",
                items=[_item(reason="not medically necessary")],
            ),
            _entry(
                insurer="Coastal Health Plan",
                recorded_at="2026-02-01T00:00:00+00:00",
                items=[_item(reason="not medically necessary")],
            ),
        ]
    )
    # Same denial reason, but two different insurers - not a pattern for
    # either one, and no insight should attribute Coastal's case to
    # Heartland or vice versa.
    assert detect_insurer_patterns(history) == []


def test_detect_insurer_patterns_different_reasons_from_same_insurer_dont_match():
    history = ClaimHistory(
        entries=[
            _entry(recorded_at="2026-01-01T00:00:00+00:00", items=[_item(reason="not medically necessary")]),
            _entry(recorded_at="2026-02-01T00:00:00+00:00", items=[_item(reason="missing prior authorization")]),
        ]
    )
    assert detect_insurer_patterns(history) == []


def test_detect_insurer_patterns_duplicate_reason_within_one_case_counts_once():
    # Two line items in the SAME claim denied on the same basis is not a
    # cross-claim pattern - only a second, separate case should make it one.
    history = ClaimHistory(
        entries=[
            _entry(
                recorded_at="2026-01-01T00:00:00+00:00",
                items=[
                    _item(procedure_code="97110", reason="not medically necessary"),
                    _item(procedure_code="97124", reason="not medically necessary"),
                ],
            )
        ]
    )
    assert detect_insurer_patterns(history) == []


def test_detect_insurer_patterns_is_case_and_whitespace_insensitive():
    history = ClaimHistory(
        entries=[
            _entry(insurer="Heartland Mutual", recorded_at="2026-01-01T00:00:00+00:00", items=[_item(reason=" Not Medically Necessary ")]),
            _entry(insurer="  heartland mutual  ", recorded_at="2026-02-01T00:00:00+00:00", items=[_item(reason="not medically necessary")]),
        ]
    )
    insights = detect_insurer_patterns(history)
    assert len(insights) == 1
    assert insights[0].occurrence_count == 2


def test_detect_insurer_patterns_never_fabricates_dates_or_claim_numbers():
    history = ClaimHistory(
        entries=[
            _entry(recorded_at="2026-01-01T00:00:00+00:00", claim_number="", items=[_item()]),
            _entry(recorded_at="2026-02-01T00:00:00+00:00", claim_number="CLM-2", items=[_item()]),
        ]
    )
    insight = detect_insurer_patterns(history)[0]
    # Only the claim number that was actually recorded shows up - an empty
    # one is omitted rather than represented as a fabricated blank entry.
    assert insight.claim_numbers == ["CLM-2"]
    assert insight.dates == ["2026-01-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"]


def test_detect_insurer_patterns_ignores_entries_with_blank_insurer_name():
    history = ClaimHistory(
        entries=[
            _entry(insurer="", recorded_at="2026-01-01T00:00:00+00:00", items=[_item()]),
            _entry(insurer="", recorded_at="2026-02-01T00:00:00+00:00", items=[_item()]),
        ]
    )
    assert detect_insurer_patterns(history) == []
