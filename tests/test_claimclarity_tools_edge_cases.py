"""Edge-case robustness tests for ClaimClarity's tools."""
from __future__ import annotations

from pathlib import Path

from claimclarity.tools.calendar import create_appeal_deadline_reminder
from claimclarity.tools.documents import read_document
from claimclarity.tools.icd10 import lookup_icd10_code, search_icd10_codes


def test_read_document_unicode_content(tmp_path: Path):
    file_path = tmp_path / "unicode.md"
    file_path.write_text("Café — naïve résumé 你好", encoding="utf-8")
    assert read_document(str(file_path)) == "Café — naïve résumé 你好"


def test_deadline_reminder_past_deadline_creates_only_main_event(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_appeal_deadline_reminder(
        path=str(ics_path), title="File appeal", deadline_iso="2001-01-01"
    )
    assert "saved" in message.lower()
    content = ics_path.read_text()
    assert content.count("BEGIN:VEVENT") == 1


def test_deadline_reminder_special_characters_escaped(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    create_appeal_deadline_reminder(
        path=str(ics_path),
        title="File appeal: claim #123, urgent",
        deadline_iso="2027-01-15",
        description="Submit via portal; see notes",
    )
    content = ics_path.read_text()
    assert "SUMMARY:File appeal: claim #123\\, urgent" in content
    assert "DESCRIPTION:Submit via portal\\; see notes" in content


def test_lookup_icd10_code_empty_string():
    result = lookup_icd10_code("")
    assert "not in ClaimClarity's bundled reference set" in result


def test_lookup_icd10_code_lowercase_input_matches():
    result = lookup_icd10_code("e11.65")
    assert "valid, billable" in result


def test_search_icd10_codes_is_case_insensitive():
    result = search_icd10_codes("LOW BACK PAIN")
    assert "M54.51" in result


def test_search_icd10_codes_empty_query_is_a_documented_edge_case():
    # An empty query is a substring of every description, so this returns the
    # entire bundled reference set rather than erroring. Harmless for a small
    # curated demo list, but pinned down here explicitly rather than being
    # discovered live during a demo.
    result = search_icd10_codes("")
    assert "M54.51" in result and "E11.65" in result


def test_lookup_icd10_code_partial_code_does_not_false_match():
    # "M54" alone is a distinct (non-billable) entry, not a fuzzy match for "M54.5"
    result = lookup_icd10_code("M54")
    assert "NOT billable" in result
