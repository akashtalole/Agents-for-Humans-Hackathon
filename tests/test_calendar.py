from pathlib import Path

from bidwright.tools.calendar import create_deadline_reminder


def test_create_deadline_reminder_iso_date(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_deadline_reminder(
        path=str(ics_path),
        title="Submit proposal: Test Project",
        deadline_iso="2027-09-30T17:00",
        description="Email submission",
    )
    assert "saved" in message.lower()
    content = ics_path.read_text()
    assert "BEGIN:VCALENDAR" in content
    assert "SUMMARY:Submit proposal: Test Project" in content
    assert "DTSTART:20270930T170000" in content
    # 3-day and 1-day reminder events should also be present for a future date
    assert content.count("BEGIN:VEVENT") == 3


def test_create_deadline_reminder_unparsable_text(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_deadline_reminder(
        path=str(ics_path),
        title="Submit proposal",
        deadline_iso="whenever we feel like it, no rush",
    )
    assert "could not parse" in message.lower()
    assert not ics_path.exists()


def test_create_deadline_reminder_empty_text(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_deadline_reminder(path=str(ics_path), title="Submit proposal", deadline_iso="")
    assert "no deadline" in message.lower()
    assert not ics_path.exists()
