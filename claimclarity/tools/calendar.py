"""Calendar tooling: turns a deadline into a .ics reminder file so a patient
never misses a filing window - the (often 180-day) internal appeal deadline,
and the (often 4-month/120-day) independent external review deadline that
follows it."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from dateutil import parser as date_parser
from strands import tool

_REMINDER_LEAD_TIMES = (timedelta(days=14), timedelta(days=3))


def _parse_deadline(deadline_text: str, deadline_label: str) -> tuple[datetime | None, str]:
    if not deadline_text or not deadline_text.strip():
        return None, f"No {deadline_label} was stated in the documents; no reminder was created."
    try:
        parsed = date_parser.parse(deadline_text, fuzzy=True)
        return parsed, ""
    except (ValueError, OverflowError):
        return None, (
            f"Could not parse the {deadline_label} text '{deadline_text}' into a date; "
            "no reminder was created. Check the relevant document manually for the exact date."
        )


def _escape_ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _format_ics_datetime(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


def _build_deadline_reminder_ics(
    path: str, title: str, deadline_iso: str, description: str, deadline_label: str, prodid_suffix: str
) -> str:
    deadline, note = _parse_deadline(deadline_iso, deadline_label)
    if deadline is None:
        return note

    events = [(title, deadline, description)]
    for lead in _REMINDER_LEAD_TIMES:
        reminder_time = deadline - lead
        if reminder_time > datetime.now():
            events.append((f"Reminder: {title} due in {lead.days} day(s)", reminder_time, description))

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//ClaimClarity//{prodid_suffix}//EN"]
    dtstamp = _format_ics_datetime(datetime.utcnow()) + "Z"
    for event_title, event_time, event_description in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uuid.uuid4()}@claimclarity",
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

    return f"{deadline_label.capitalize()} reminder saved to {path} for {deadline.isoformat()}."


@tool
def create_appeal_deadline_reminder(path: str, title: str, deadline_iso: str, description: str = "") -> str:
    """Create a .ics calendar file with the appeal filing deadline plus reminder
    events 14 days and 3 days before it.

    Args:
        path: Destination path for the .ics file.
        title: Short event title, e.g. "File appeal: <insurer> claim <number>".
        deadline_iso: The appeal deadline as stated in the denial notice (ISO
            date preferred, but any reasonably formatted date string is accepted).
        description: Optional extra detail, e.g. submission method.

    Returns:
        A confirmation message, or an explanation if the deadline could not be parsed.
    """
    return _build_deadline_reminder_ics(
        path, title, deadline_iso, description, deadline_label="appeal deadline", prodid_suffix="Appeal Deadlines"
    )


@tool
def create_external_review_deadline_reminder(path: str, title: str, deadline_iso: str, description: str = "") -> str:
    """Create a .ics calendar file with the independent external review filing
    deadline plus reminder events 14 days and 3 days before it.

    Args:
        path: Destination path for the .ics file.
        title: Short event title, e.g. "File external review: <insurer> claim <number>".
        deadline_iso: The external review deadline (ISO date preferred, but any
            reasonably formatted date string is accepted). Pass an empty string
            if only a described window (e.g. "within 4 months") is known - no
            reminder can be created without an actual date.
        description: Optional extra detail, e.g. where to submit the request.

    Returns:
        A confirmation message, or an explanation if the deadline could not be parsed.
    """
    return _build_deadline_reminder_ics(
        path,
        title,
        deadline_iso,
        description,
        deadline_label="external review deadline",
        prodid_suffix="External Review Deadlines",
    )
