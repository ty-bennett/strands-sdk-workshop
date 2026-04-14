# Written by Ty Bennett
# Locally run agent with Google Calendar integration.
# Reads existing calendar events and schedules study blocks only in free slots.
# Requires credentials.json from your Google Cloud project in the same directory.

from strands_tools import http_request
from strands.models import BedrockModel
from strands import Agent, tool
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from botocore.exceptions import ClientError
import boto3
import csv
import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()


# Calendar read scope — matches your existing project's scopes
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CALENDARS = [
    item.strip()
    for item in os.getenv(
        "GOOGLE_CALENDARS",
        "primary,tybennett924@gmail.com,school schedule",
    ).split(",")
    if item.strip()
]


def _resolve_path(path: str) -> Path:
    file_path = Path(path).expanduser()
    if not file_path.is_absolute():
        file_path = BASE_DIR / file_path
    return file_path


def _resolve_output_path(path: str) -> Path:
    output_path = Path(path).expanduser()
    if output_path.is_absolute():
        return output_path
    return BASE_DIR / output_path


def _escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


# ---------------------------------------------------------------------------
# Google Calendar helpers
# ---------------------------------------------------------------------------

def _get_calendar_service():
    """
    Authenticate with Google Calendar using credentials.json.
    Saves token.json after first login so subsequent runs are automatic.
    """
    creds = None
    token_path = _resolve_path("token.json")
    credentials_path = _resolve_path("credentials.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with token_path.open("w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _resolve_calendar_ids(service, requested_calendars: list[str]) -> tuple[list[str], list[str]]:
    calendar_entries = []
    page_token = None

    while True:
        response = service.calendarList().list(pageToken=page_token).execute()
        calendar_entries.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    ids_by_key = {}
    for entry in calendar_entries:
        calendar_id = entry.get("id", "").strip()
        summary = entry.get("summary", "").strip()
        if calendar_id:
            ids_by_key[calendar_id.lower()] = calendar_id
        if summary:
            ids_by_key[summary.lower()] = calendar_id

    resolved = []
    unresolved = []
    seen = set()

    for calendar_name in requested_calendars:
        key = calendar_name.strip().lower()
        resolved_id = "primary" if key == "primary" else ids_by_key.get(key)
        if not resolved_id:
            unresolved.append(calendar_name)
            continue
        if resolved_id not in seen:
            resolved.append(resolved_id)
            seen.add(resolved_id)

    return resolved, unresolved


def _parse_event_datetime(value: str) -> datetime:
    if "T" in value:
        iso_value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(iso_value).astimezone().replace(tzinfo=None)

    day = date.fromisoformat(value)
    return datetime(day.year, day.month, day.day, 0, 0)


def _get_busy_slots(start_dt: datetime, end_dt: datetime) -> tuple[list[tuple[datetime, datetime]], list[str], list[str], list[str]]:
    """
    Fetch all calendar events between start_dt and end_dt from both the default
    calendar (tybennett924@gmail.com) and the 'school schedule' calendar.
    Returns a combined list of (event_start, event_end) tuples in local time.
    """
    service = _get_calendar_service()
    calendar_ids, unresolved = _resolve_calendar_ids(service, DEFAULT_CALENDARS)
    if not calendar_ids:
        raise RuntimeError(
            "No readable Google calendars were resolved. "
            f"Configured calendars: {', '.join(DEFAULT_CALENDARS)}"
        )

    busy = []
    checked = []
    errors = []

    for cal_id in calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=start_dt.astimezone(timezone.utc).isoformat(),
                timeMax=end_dt.astimezone(timezone.utc).isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            checked.append(cal_id)
        except Exception as exc:
            errors.append(f"{cal_id}: {exc}")
            continue

        for event in events_result.get("items", []):
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))

            # Parse and convert to naive local datetime for comparison
            if "T" in start:
                ev_start = _parse_event_datetime(start)
                ev_end = _parse_event_datetime(end)
            else:
                # Google Calendar all-day event end dates are exclusive.
                ev_start = _parse_event_datetime(start)
                ev_end = _parse_event_datetime(end)

            busy.append((ev_start, ev_end))

    return busy, checked, unresolved, errors


def _overlaps(slot_start: datetime, slot_end: datetime,
              busy: list[tuple[datetime, datetime]]) -> bool:
    """Return True if the proposed slot overlaps any existing event."""
    for ev_start, ev_end in busy:
        if slot_start < ev_end and slot_end > ev_start:
            return True
    return False


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

def load_system_prompt(filepath: str = "system_prompt.txt") -> str:
    """Load system prompt from file."""
    prompt_path = _resolve_path(filepath)
    try:
        with prompt_path.open("r") as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"System prompt file not found: {prompt_path}. "
            "This file is required for agent operation."
        )


def calculate_priority_score(days_remaining: int, estimated_hours: float,
                             days_until_due_weight: float = 2.0,
                             effort_weight: float = 1.0) -> float:
    """Lower score = higher priority (more urgent)."""
    return (days_until_due_weight * days_remaining) + (effort_weight * estimated_hours)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_gmail_calendar_events(filepath: str, start_hour: int = 9, end_hour: int = 21,
                              max_block_hours: float = 2.0,
                              output_file: str = "study_schedule.ics") -> str:
    """
    Reads the Google Calendar of the specified user and then returns the times in which the user is busy.
    By doing so, you can see when the user is free to study or complete assignments. Assignment prioroty
    should be prioritized based on the priority score descending.
    """
    window_start = datetime.now()
    window_end = window_start + timedelta(days=14)

    try:
        busy_slots, checked, unresolved, errors = _get_busy_slots(window_start, window_end)
    except Exception as exc:
        return f"Could not read Google Calendar: {exc}"

    lines = [
        f"Checked Google Calendar from {window_start.strftime('%Y-%m-%d %I:%M %p')} "
        f"to {window_end.strftime('%Y-%m-%d %I:%M %p')}.",
        f"Resolved calendars: {', '.join(checked) if checked else '(none)'}",
    ]

    if unresolved:
        lines.append(f"Unresolved calendar names: {', '.join(unresolved)}")
    if errors:
        lines.append(f"Calendar read errors: {' | '.join(errors)}")

    lines.append(f"Busy events found: {len(busy_slots)}")
    for start_dt, end_dt in busy_slots[:25]:
        lines.append(
            f"  {start_dt.strftime('%a %b %d %I:%M %p')} - "
            f"{end_dt.strftime('%I:%M %p')}"
        )

    return "\n".join(lines)


@tool
def load_assignments(filepath: str, days_until_due_weight: float = 2.0,
                     effort_weight: float = 1.0) -> str:
    """
    Reads an assignment CSV file, categorizes assignments by deadline, and returns
    formatted text organized into buckets: overdue, due today, due this week, and
    upcoming. Skips completed assignments and sorts each bucket by priority score.

    Args:
        filepath: Path to CSV file with columns: course, assignment, due_date,
                  type, estimated_hours, status, notes
        days_until_due_weight: Weight for urgency in priority calculation (default 2.0)
        effort_weight: Weight for effort in priority calculation (default 1.0)

    Returns:
        Formatted string with categorized, prioritized assignments and date metadata
    """
    try:
        f = _resolve_path(filepath).open(newline="")
    except FileNotFoundError:
        return f"Assignment file not found: {filepath}"

    try:
        today = date.today()
        week_end = date.fromordinal(today.toordinal() + (6 - today.weekday()))
        buckets = {"overdue": [], "due_today": [],
                   "due_this_week": [], "upcoming": []}

        reader = csv.DictReader(f)
        required_columns = {"course", "assignment", "due_date",
                            "type", "estimated_hours", "status", "notes"}

        if reader.fieldnames is None:
            return "Malformed CSV file: unable to read header row"

        missing_columns = required_columns - set(reader.fieldnames)
        if missing_columns:
            return f"Missing required columns: {', '.join(sorted(missing_columns))}"

        row_number = 1
        for row in reader:
            row_number += 1
            if row.get("status", "").strip().lower() == "complete":
                continue
            try:
                due = datetime.strptime(
                    row["due_date"].strip(), "%Y-%m-%d").date()
            except ValueError:
                return f"Invalid date format in row {row_number}: {row['due_date']}. Expected YYYY-MM-DD"
            except KeyError:
                return f"Invalid date format in row {row_number}: . Expected YYYY-MM-DD"

            hours_str = row.get("estimated_hours", "").strip()
            try:
                hours = float(hours_str)
                hours_display = f"{hours_str}h"
            except ValueError:
                hours = 0.0
                hours_display = "?h"

            days_remaining = (due - today).days
            priority_score = calculate_priority_score(
                days_remaining, hours, days_until_due_weight, effort_weight)

            entry = (
                f"  [{row['course']}] {row['assignment']}"
                f" — due {due.strftime('%a %b %d')}"
                f" ({row['type']}, ~{hours_display}, {row['status']})"
            )
            if row.get("notes", "").strip():
                entry += f"\n    Note: {row['notes'].strip()}"

            if due < today:
                buckets["overdue"].append((priority_score, entry))
            elif due == today:
                buckets["due_today"].append((priority_score, entry))
            elif due <= week_end:
                buckets["due_this_week"].append((priority_score, entry))
            else:
                buckets["upcoming"].append((priority_score, entry))

        for bucket_key in buckets:
            buckets[bucket_key].sort(key=lambda x: x[0])
            buckets[bucket_key] = [entry for _, entry in buckets[bucket_key]]

        lines = [
            f"Today: {today.strftime('%a %b %d')}  |  "
            f"Week ends: {week_end.strftime('%a %b %d')}\n"
        ]
        for key, items in buckets.items():
            bucket_name = key.replace("_", " ").upper()
            lines.append(f"{bucket_name} ({len(items)})")
            lines += items if items else ["  (none)"]
            lines.append("")

        return "\n".join(lines)

    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()


@tool
def schedule_study_blocks(filepath: str, start_hour: int = 9, end_hour: int = 21,
                          max_block_hours: float = 2.0,
                          output_file: str = "study_schedule.ics") -> str:
    """
    Reads the assignment CSV, fetches existing Google Calendar events to find free
    slots, and schedules study blocks only during open time. Generates an ICS file
    ready to import into Google Calendar or Outlook.

    Args:
        filepath: Path to CSV file with assignment data
        start_hour: Earliest hour to schedule study blocks, 24h format (default 9 = 9am)
        end_hour: Latest hour to end study blocks, 24h format (default 21 = 9pm)
        max_block_hours: Maximum hours per single study session (default 2.0)
        output_file: Output ICS filename (default: study_schedule.ics)

    Returns:
        Summary of scheduled blocks and path to the generated ICS file
    """
    input_path = _resolve_path(filepath)
    output_path = _resolve_output_path(output_file)

    try:
        f = input_path.open(newline="")
    except FileNotFoundError:
        return f"Assignment file not found: {input_path}"

    try:
        today = date.today()
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            return "Malformed CSV file: unable to read header row"

        required = {"course", "assignment",
                    "due_date", "estimated_hours", "status"}
        missing = required - set(reader.fieldnames)
        if missing:
            return f"Missing required columns: {', '.join(sorted(missing))}"

        assignments = []
        for row in reader:
            if row.get("status", "").strip().lower() == "complete":
                continue
            try:
                due = datetime.strptime(
                    row["due_date"].strip(), "%Y-%m-%d").date()
            except ValueError:
                continue
            try:
                hours = float(row.get("estimated_hours", "1").strip() or "1")
            except ValueError:
                hours = 1.0

            days_remaining = (due - today).days
            priority = calculate_priority_score(days_remaining, hours)
            assignments.append({
                "course": row["course"],
                "assignment": row["assignment"],
                "due": due,
                "hours": hours,
                "priority": priority,
            })

        assignments.sort(key=lambda x: x["priority"])

        if not assignments:
            return "No pending assignments found — nothing to schedule."

        # Pull the next 14 days of calendar events to check for conflicts
        window_start = datetime.now()
        window_end = window_start + timedelta(days=14)
        try:
            busy_slots, checked, unresolved, errors = _get_busy_slots(window_start, window_end)
            calendar_status = (
                f"Checked Google Calendar: {len(busy_slots)} existing event(s) found "
                f"across {', '.join(checked) if checked else '(no readable calendars)'}."
            )
            if unresolved:
                calendar_status += f" Unresolved calendars: {', '.join(unresolved)}."
            if errors:
                calendar_status += f" Read errors: {' | '.join(errors)}."
        except Exception as e:
            busy_slots = []
            calendar_status = (
                f"Could not read Google Calendar ({e}). "
                "Scheduling without conflict checks."
            )

        # Find next available slot
        now = datetime.now()
        next_start_hour = max(now.hour + 1, start_hour)
        if next_start_hour >= end_hour:
            tomorrow = today + timedelta(days=1)
            current_slot = datetime(
                tomorrow.year, tomorrow.month, tomorrow.day, start_hour, 0)
        else:
            current_slot = datetime(
                today.year, today.month, today.day, next_start_hour, 0)

        events = []
        for asgn in assignments:
            remaining = asgn["hours"]
            while remaining > 0:
                block = min(remaining, max_block_hours)
                block_end = current_slot + timedelta(hours=block)

                # Push to next day if block overruns end_hour
                if block_end.hour > end_hour or (block_end.hour == end_hour and block_end.minute > 0):
                    next_day = current_slot.date() + timedelta(days=1)
                    current_slot = datetime(
                        next_day.year, next_day.month, next_day.day, start_hour, 0)
                    block_end = current_slot + timedelta(hours=block)

                # Skip slot if it conflicts with an existing calendar event
                if _overlaps(current_slot, block_end, busy_slots):
                    current_slot += timedelta(minutes=30)
                    continue

                events.append({
                    "uid": str(uuid.uuid4()),
                    "summary": f"Study: [{asgn['course']}] {asgn['assignment']}",
                    "description": f"Due: {asgn['due'].strftime('%a %b %d')} | Est. total: {asgn['hours']}h",
                    "start": current_slot,
                    "end": block_end,
                })

                remaining -= block
                current_slot = block_end
                if remaining > 0:
                    current_slot += timedelta(minutes=30)

        ics_lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//Academic Advisor Agent//Study Scheduler//EN",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        ]
        for ev in events:
            ics_lines += [
                "BEGIN:VEVENT",
                f"UID:{ev['uid']}",
                f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                f"DTSTART:{ev['start'].strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{ev['end'].strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{_escape_ics_text(ev['summary'])}",
                f"DESCRIPTION:{_escape_ics_text(ev['description'])}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        ics_lines.append("END:VCALENDAR")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="") as out:
            out.write("\r\n".join(ics_lines))

        summary = [
            calendar_status,
            f"Scheduled {len(events)} study block(s) - saved to {output_path}\n",
        ]
        for ev in events:
            duration_mins = int((ev["end"] - ev["start"]).seconds / 60)
            summary.append(
                f"  {ev['start'].strftime('%a %b %d %I:%M %p')} – "
                f"{ev['end'].strftime('%I:%M %p')} ({duration_mins}min)  {ev['summary']}"
            )
        summary.append(
            f"\nTo import: Google Calendar → Settings → Import → select {output_path}"
        )
        return "\n".join(summary)

    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = Agent(
            model=BedrockModel(model_id="amazon.nova-pro-v1:0"),
            system_prompt=load_system_prompt(),
            tools=[get_gmail_calendar_events, load_assignments, schedule_study_blocks, http_request],
        )
    return _agent


if __name__ == "__main__":
    assignments_path = _resolve_path("assignments.csv")
    configured_calendars = ", ".join(DEFAULT_CALENDARS)
    _get_agent()(
        f"""Read my existing calendar and then give me a daily briefing and schedule study blocks around my existing calendar events.
        My assignments file is '{assignments_path}'. My existing calendar names are '{configured_calendars}'."""
    )
