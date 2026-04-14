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

from dotenv import load_dotenv
load_dotenv()


# Calendar read scope — matches your existing project's scopes
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


# ---------------------------------------------------------------------------
# Google Calendar helpers
# ---------------------------------------------------------------------------

def _get_calendar_service():
    """
    Authenticate with Google Calendar using credentials.json.
    Saves token.json after first login so subsequent runs are automatic.
    """
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _get_busy_slots(start_dt: datetime, end_dt: datetime) -> list[tuple[datetime, datetime]]:
    """
    Fetch all calendar events between start_dt and end_dt from both the default
    calendar (tybennett924@gmail.com) and the 'school schedule' calendar.
    Returns a combined list of (event_start, event_end) tuples in local time.
    """
    service = _get_calendar_service()

    calendar_ids = ["tybennett924@gmail.com", "school schedule"]
    busy = []

    for cal_id in calendar_ids:
        try:
            events_result = service.events().list(
                calendarId=cal_id,
                timeMin=start_dt.astimezone(timezone.utc).isoformat(),
                timeMax=end_dt.astimezone(timezone.utc).isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
        except Exception:
            # Skip calendars that can't be read (e.g. wrong ID or no access)
            continue

        for event in events_result.get("items", []):
            start = event["start"].get("dateTime", event["start"].get("date"))
            end = event["end"].get("dateTime", event["end"].get("date"))

            # Parse and convert to naive local datetime for comparison
            if "T" in start:
                ev_start = datetime.fromisoformat(start).replace(tzinfo=None)
                ev_end = datetime.fromisoformat(end).replace(tzinfo=None)
            else:
                # All-day event — block the whole day
                d = date.fromisoformat(start)
                ev_start = datetime(d.year, d.month, d.day, 0, 0)
                ev_end = datetime(d.year, d.month, d.day, 23, 59)

            busy.append((ev_start, ev_end))

    return busy


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
    try:
        with open(filepath, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"System prompt file not found: {
                                filepath}. This file is required for agent operation.")


def calculate_priority_score(days_remaining: int, estimated_hours: float,
                             days_until_due_weight: float = 2.0,
                             effort_weight: float = 1.0) -> float:
    """Lower score = higher priority (more urgent)."""
    return (days_until_due_weight * days_remaining) + (effort_weight * estimated_hours)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

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
        f = open(filepath, newline="")
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

        lines = [f"Today: {today.strftime('%a %b %d')}  |  Week ends: {
            week_end.strftime('%a %b %d')}\n"]
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
    try:
        f = open(filepath, newline="")
    except FileNotFoundError:
        return f"Assignment file not found: {filepath}"

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
            busy_slots = _get_busy_slots(window_start, window_end)
            calendar_status = f"Checked Google Calendar — {
                len(busy_slots)} existing event(s) found."
        except Exception as e:
            busy_slots = []
            calendar_status = f"Could not read Google Calendar ({
                e}). Scheduling without conflict checks."

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
                f"DTSTART:{ev['start'].strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{ev['end'].strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{ev['summary']}",
                f"DESCRIPTION:{ev['description']}",
                "STATUS:CONFIRMED",
                "END:VEVENT",
            ]
        ics_lines.append("END:VCALENDAR")

        with open(output_file, "w") as out:
            out.write("\r\n".join(ics_lines))

        summary = [calendar_status, f"Scheduled {
            len(events)} study block(s) — saved to {output_file}\n"]
        for ev in events:
            duration_mins = int((ev["end"] - ev["start"]).seconds / 60)
            summary.append(
                f"  {ev['start'].strftime('%a %b %d %I:%M %p')} – "
                f"{ev['end'].strftime('%I:%M %p')} ({duration_mins}min)  {
                    ev['summary']}"
            )
        summary.append(
            f"\nTo import: Google Calendar → Settings → Import → select {output_file}")
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
            tools=[load_assignments, schedule_study_blocks, http_request],
        )
    return _agent


if __name__ == "__main__":
    _get_agent()("""Give me my daily briefing and schedule study blocks around my existing calendar events.
        My assignments file is 'assignments.csv'.""")
