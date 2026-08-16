from pathlib import Path

from claimclarity.tools.calendar import create_appeal_deadline_reminder


def test_create_appeal_deadline_reminder_iso_date(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_appeal_deadline_reminder(
        path=str(ics_path),
        title="File appeal: Heartland Mutual claim CLM-2026-0619884",
        deadline_iso="2026-12-28",
        description="Submit via member.heartlandmutual.example/appeals",
    )
    assert "saved" in message.lower()
    content = ics_path.read_text()
    assert "BEGIN:VCALENDAR" in content
    assert "SUMMARY:File appeal: Heartland Mutual claim CLM-2026-0619884" in content
    assert "DTSTART:20261228T000000" in content


def test_create_appeal_deadline_reminder_unparsable_text(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_appeal_deadline_reminder(
        path=str(ics_path), title="File appeal", deadline_iso="sometime, probably"
    )
    assert "could not parse" in message.lower()
    assert not ics_path.exists()


def test_create_appeal_deadline_reminder_empty_text(tmp_path: Path):
    ics_path = tmp_path / "deadline.ics"
    message = create_appeal_deadline_reminder(path=str(ics_path), title="File appeal", deadline_iso="")
    assert "no appeal deadline" in message.lower()
    assert not ics_path.exists()
