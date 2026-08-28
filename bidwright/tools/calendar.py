"""Calendar tooling: turns an extracted submission deadline into a .ics reminder
file so a human never has to hold the date in their head."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as date_parser
from strands import tool

_REMINDER_LEAD_TIMES = (timedelta(days=3), timedelta(days=1))


def _parse_deadline(deadline_text: str) -> tuple[datetime | None, str]:
    """Best-effort parse of a human-written deadline string.

    Returns (parsed_datetime_or_None, note). `note` explains a fallback when
    parsing fails, so the caller can surface it to a human instead of silently
    guessing.
    """
    if not deadline_text or not deadline_text.strip():
        return None, "No deadline was stated in the RFP; no reminder was created."
    try:
        parsed = date_parser.parse(deadline_text, fuzzy=True)
        return parsed, ""
    except (ValueError, OverflowError):
        return None, (
            f"Could not parse the deadline text '{deadline_text}' into a date; "
            "no reminder was created. Check the RFP manually for the exact date."
        )


def _escape_ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _format_ics_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


@tool
def create_deadline_reminder(path: str, title: str, deadline_iso: str, description: str = "") -> str:
    """Create a .ics calendar file with the submission deadline plus reminder
    events 3 days and 1 day before it, so the deadline can be imported into any
    calendar app.

    Args:
        path: Destination path for the .ics file.
        title: Short event title, e.g. "Submit proposal: <project name>".
        deadline_iso: The deadline as stated in the RFP (ISO date/datetime preferred,
            but any reasonably formatted date string is accepted).
        description: Optional extra detail, e.g. submission method.

    Returns:
        A confirmation message, or an explanation if the deadline could not be parsed.
    """
    deadline, note = _parse_deadline(deadline_iso)
    if deadline is None:
        return note

    events = [(title, deadline, description)]
    for lead in _REMINDER_LEAD_TIMES:
        reminder_time = deadline - lead
        if reminder_time > datetime.now():
            events.append((f"Reminder: {title} due in {lead.days} day(s)", reminder_time, description))

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BidWright//RFP Deadlines//EN"]
    dtstamp = _format_ics_datetime(datetime.utcnow()) + "Z"
    for event_title, event_time, event_description in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@bidwright",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{_format_ics_datetime(event_time)}",
            f"SUMMARY:{_escape_ics_text(event_title)}",
        ]
        if event_description:
            lines.append(f"DESCRIPTION:{_escape_ics_text(event_description)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

    return f"Calendar reminder saved to {path} for deadline {deadline.isoformat()}."
