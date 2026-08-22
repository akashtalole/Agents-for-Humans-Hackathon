"""Edge-case robustness tests for BidWright's tools - things that would be
embarrassing to hit for the first time live during a demo."""
from __future__ import annotations

from pathlib import Path

from bidwright.tools.calendar import create_deadline_reminder
from bidwright.tools.documents import read_document, save_text_file


def test_read_document_unicode_content(tmp_path: Path):
    file_path = tmp_path / "unicode.md"
    file_path.write_text("Café — naïve résumé 你好 🎉", encoding="utf-8")
    assert read_document(str(file_path)) == "Café — naïve résumé 你好 🎉"


def test_read_document_empty_file(tmp_path: Path):
    file_path = tmp_path / "empty.txt"
    file_path.write_text("")
    assert read_document(str(file_path)) == ""


def test_read_document_no_extension_treated_as_text(tmp_path: Path):
    file_path = tmp_path / "README"
    file_path.write_text("plain text, no extension")
    assert read_document(str(file_path)) == "plain text, no extension"


def test_read_document_uppercase_extension(tmp_path: Path):
    file_path = tmp_path / "sample.TXT"
    file_path.write_text("still readable")
    assert read_document(str(file_path)) == "still readable"


def test_save_text_file_overwrites_existing(tmp_path: Path):
    file_path = tmp_path / "out.md"
    save_text_file(str(file_path), "first version")
    save_text_file(str(file_path), "second version")
    assert file_path.read_text() == "second version"


def test_save_text_file_empty_content(tmp_path: Path):
    file_path = tmp_path / "empty_out.md"
    message = save_text_file(str(file_path), "")
    assert file_path.read_text() == ""
    assert "0 characters" in message


def test_deadline_reminder_date_only_no_time(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_deadline_reminder(
        path=str(ics_path), title="Submit proposal", deadline_iso="September 30, 2027"
    )
    assert "saved" in message.lower()
    content = ics_path.read_text()
    assert "DTSTART:20270930T000000" in content


def test_deadline_reminder_past_date_creates_only_the_main_event(tmp_path: Path):
    """A deadline in the past shouldn't get 3-day/1-day reminders scheduled
    even further in the past - it should still record the main event without
    crashing."""
    ics_path = tmp_path / "deadline.ics"
    message = create_deadline_reminder(
        path=str(ics_path), title="Submit proposal", deadline_iso="2001-01-01T09:00"
    )
    assert "saved" in message.lower()
    content = ics_path.read_text()
    assert content.count("BEGIN:VEVENT") == 1


def test_deadline_reminder_deadline_very_soon_skips_reminders_already_passed(tmp_path: Path):
    """A deadline less than a day away should still produce the main event
    without a negative-lead-time reminder."""
    from datetime import datetime, timedelta

    near_deadline = (datetime.now() + timedelta(hours=2)).isoformat()
    ics_path = tmp_path / "deadline.ics"
    create_deadline_reminder(path=str(ics_path), title="Submit proposal", deadline_iso=near_deadline)
    content = ics_path.read_text()
    assert content.count("BEGIN:VEVENT") == 1


def test_deadline_reminder_special_characters_are_escaped(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    create_deadline_reminder(
        path=str(ics_path),
        title="Submit; proposal, for Acme, Inc.",
        deadline_iso="2027-01-15T09:00",
        description="Line one\nLine two",
    )
    content = ics_path.read_text()
    assert "SUMMARY:Submit\\; proposal\\, for Acme\\, Inc." in content
    assert "DESCRIPTION:Line one\\nLine two" in content
