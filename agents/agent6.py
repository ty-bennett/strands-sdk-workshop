# Written by Ty Bennett
# Cloud-deployed version — reads/writes CSV and ICS via S3 instead of local filesystem.
# AWS credentials come from the execution environment (IAM role, Lambda, EC2, etc.)

import csv
import io
import os
import shlex
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from strands import Agent, tool
from strands.models import BedrockModel
from strands_tools import http_request


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
DEFAULT_S3_ICS_PREFIX = os.getenv(
    "STUDY_SCHEDULE_S3_PREFIX",
    "s3://uofsc-awscc-strands-agent-workshop-assignments/schedules/",
)


# ---------------------------------------------------------------------------
# Local path helpers
# ---------------------------------------------------------------------------

def _resolve_local_path(path: str) -> Path:
    local_path = Path(path).expanduser()
    if local_path.is_absolute():
        return local_path
    if local_path.exists():
        return local_path.resolve()
    local_path = BASE_DIR / local_path
    return local_path


def _escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


def _normalize_output_s3_uri(output_file: str) -> str:
    """
    Accept either a full s3:// URI or a user-provided filename and return
    the final S3 URI for the uploaded ICS file.
    """
    candidate = output_file.strip()
    if not candidate:
        candidate = "study_schedule.ics"
    if candidate.startswith("s3://"):
        return candidate
    if not candidate.endswith(".ics"):
        candidate = f"{candidate}.ics"
    return f"{DEFAULT_S3_ICS_PREFIX.rstrip('/')}/{Path(candidate).name}"


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------

def _parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    """Split 's3://bucket/key' into (bucket, key)."""
    path = s3_uri.replace("s3://", "")
    bucket, key = path.split("/", 1)
    return bucket, key


def _read_s3_text(s3_uri: str) -> str:
    """Download a text object from S3 and return its contents as a string."""
    bucket, key = _parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode("utf-8")


def _write_s3_text(content: str, s3_uri: str, content_type: str = "text/plain") -> None:
    """Upload a text string to S3."""
    bucket, key = _parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket, Key=key, Body=content.encode(
        "utf-8"), ContentType=content_type)


def _generate_s3_download_url(s3_uri: str, expires_in: int = 86400) -> str:
    """Generate a temporary download URL for an S3 object."""
    bucket, key = _parse_s3_uri(s3_uri)
    s3 = boto3.client("s3")
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def _open_csv(filepath: str):
    """
    Return a file-like object for CSV parsing.
    Supports both local paths and s3:// URIs.
    """
    if filepath.startswith("s3://"):
        return io.StringIO(_read_s3_text(filepath))
    return _resolve_local_path(filepath).open(newline="")


# ---------------------------------------------------------------------------
# Google Calendar helpers
# ---------------------------------------------------------------------------

def _get_calendar_service():
    """Authenticate with Google Calendar using local OAuth credentials."""
    creds = None
    token_path = _resolve_local_path("token.json")
    credentials_path = _resolve_local_path("credentials.json")

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path), SCOPES
            )
            creds = flow.run_local_server(port=0)
        with token_path.open("w") as token_file:
            token_file.write(creds.to_json())

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
    """Return busy calendar slots plus diagnostics for the configured calendars."""
    service = _get_calendar_service()
    calendar_ids, unresolved = _resolve_calendar_ids(
        service, DEFAULT_CALENDARS)
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
            busy.append((_parse_event_datetime(start),
                        _parse_event_datetime(end)))

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
    """Load system prompt — supports local path or S3 URI."""
    try:
        if filepath.startswith("s3://"):
            prompt = _read_s3_text(filepath)
        else:
            with _resolve_local_path(filepath).open("r") as f:
                prompt = f.read()
    except (FileNotFoundError, ClientError) as e:
        raise FileNotFoundError(f"System prompt not found: {filepath}") from e
    return (
        prompt
        + "\n\nFor the CALENDAR step in this agent only: before uploading the ICS file, "
        + "ask the user what filename they want in S3 unless they already provided one "
        + "in their message. Accept a simple filename like 'finals-plan.ics' and pass "
        + "that as output_file to schedule_study_blocks. After the tool returns, explicitly "
        + "repeat the exact 'Download link:' line and the exact 'curl download:' line from "
        + "the tool output in your final CALENDAR section so the user can immediately use them."
    )


def invoke_with_retry(model, prompt, max_retries=3):
    """Invoke Bedrock model with exponential backoff retry logic."""
    for attempt in range(max_retries):
        try:
            return model.invoke(prompt)
        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return "Rate limit exceeded. Please wait and try again."
            raise


_model = None
_agent = None


def _get_agent():
    global _model, _agent
    if _agent is None:
        _model = BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0")
        _agent = Agent(
            model=_model,
            system_prompt=load_system_prompt(),
            tools=[get_gmail_calendar_events, load_assignments,
                   schedule_study_blocks, http_request],
        )
    return _agent


# ---------------------------------------------------------------------------
# Priority helper
# ---------------------------------------------------------------------------

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
    Reads Google Calendar events for the next 14 days and returns the busy slots.
    """
    window_start = datetime.now()
    window_end = window_start + timedelta(days=14)

    try:
        busy_slots, checked, unresolved, errors = _get_busy_slots(
            window_start, window_end)
    except Exception as exc:
        return f"Could not read Google Calendar: {exc}"

    lines = [
        f"Checked Google Calendar from {
            window_start.strftime('%Y-%m-%d %I:%M %p')} "
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
    Reads an assignment CSV file from a local path or S3 URI, categorizes
    assignments by deadline, and returns formatted text organized into buckets:
    overdue, due today, due this week, and upcoming. Skips completed assignments
    and sorts each bucket by priority score.

    Args:
        filepath: Local path or S3 URI (e.g. s3://bucket/assignments/assignments.csv)
        days_until_due_weight: Weight for urgency in priority calculation (default 2.0)
        effort_weight: Weight for effort in priority calculation (default 1.0)

    Returns:
        Formatted string with categorized, prioritized assignments and date metadata
    """
    try:
        f = _open_csv(filepath)
    except (FileNotFoundError, ClientError):
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
                          output_file: str = "s3://uofsc-awscc-strands-agent-workshop-assignments/schedules/study_schedule.ics") -> str:
    """
    Reads the assignment CSV from a local path or S3 URI, calculates prioritized
    study blocks based on estimated hours and due dates, and writes an ICS calendar
    file to S3. Assignments are scheduled starting from the
    next available slot today, capped at max_block_hours per session with 30-minute
    breaks in between. Completed assignments are skipped.

    Args:
        filepath: Local path or S3 URI to CSV file with assignment data
        start_hour: Earliest hour to schedule study blocks, 24h format (default 9 = 9am)
        end_hour: Latest hour to end study blocks, 24h format (default 21 = 9pm)
        max_block_hours: Maximum hours per single study session (default 2.0)
        output_file: S3 URI or filename for the output ICS file

    Returns:
        Summary of all scheduled blocks and where the ICS file was saved
    """
    output_s3_uri = _normalize_output_s3_uri(output_file)

    try:
        f = _open_csv(filepath)
    except (FileNotFoundError, ClientError):
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

        window_start = datetime.now()
        window_end = window_start + timedelta(days=14)
        try:
            busy_slots, checked, unresolved, errors = _get_busy_slots(
                window_start, window_end)
            calendar_status = (
                f"Checked Google Calendar: {
                    len(busy_slots)} existing event(s) found "
                f"across {
                    ', '.join(checked) if checked else '(no readable calendars)'}."
            )
            if unresolved:
                calendar_status += f" Unresolved calendars: {
                    ', '.join(unresolved)}."
            if errors:
                calendar_status += f" Read errors: {' | '.join(errors)}."
        except Exception as exc:
            busy_slots = []
            calendar_status = (
                f"Could not read Google Calendar ({exc}). "
                "Scheduling without conflict checks."
            )

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

                if block_end.hour > end_hour or (block_end.hour == end_hour and block_end.minute > 0):
                    next_day = current_slot.date() + timedelta(days=1)
                    current_slot = datetime(
                        next_day.year, next_day.month, next_day.day, start_hour, 0)
                    block_end = current_slot + timedelta(hours=block)

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

        now_stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Academic Advisor Agent//Study Scheduler//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:Study Schedule",
        ]
        for ev in events:
            ics_lines += [
                "BEGIN:VEVENT",
                f"UID:{ev['uid']}@study-scheduler",
                f"DTSTAMP:{now_stamp}",
                f"DTSTART:{ev['start'].strftime('%Y%m%dT%H%M%S')}",
                f"DTEND:{ev['end'].strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{_escape_ics_text(ev['summary'])}",
                f"DESCRIPTION:{_escape_ics_text(ev['description'])}",
                "STATUS:CONFIRMED",
                "SEQUENCE:0",
                "END:VEVENT",
            ]
        ics_lines.append("END:VCALENDAR")
        ics_content = "\r\n".join(ics_lines) + "\r\n"

        # Write ICS to S3 only
        download_link = None
        _write_s3_text(ics_content, output_s3_uri,
                       content_type="text/calendar")
        destination = f"uploaded to {output_s3_uri}"
        try:
            download_link = _generate_s3_download_url(output_s3_uri)
        except ClientError as exc:
            download_link = f"Could not generate download link: {exc}"

        summary = [calendar_status, f"Scheduled {
            len(events)} study block(s) — {destination}\n"]
        for ev in events:
            duration_mins = int((ev["end"] - ev["start"]).seconds / 60)
            summary.append(
                f"  {ev['start'].strftime('%a %b %d %I:%M %p')} – "
                f"{ev['end'].strftime('%I:%M %p')} ({duration_mins}min)  {
                    ev['summary']}"
            )
        if download_link:
            summary.append(f"\nDownload link: {download_link}")
            if download_link.startswith("http"):
                suggested_name = Path(_parse_s3_uri(output_s3_uri)[1]).name
                summary.append(
                    "curl download: "
                    f"curl -L {shlex.quote(download_link)
                               } -o {shlex.quote(suggested_name)}"
                )
        summary.append(
            "\nTo add to Google Calendar: Settings → Import → select the ICS file")
        summary.append(
            "To add to Outlook: File → Open & Export → Import/Export → Import an iCalendar file")
        return "\n".join(summary)

    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    assignments_file = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "s3://uofsc-awscc-strands-agent-workshop-assignments/assignments/assignments.csv"
    )
    output_name = sys.argv[2] if len(sys.argv) > 2 else "study_schedule.ics"
    configured_calendars = ", ".join(DEFAULT_CALENDARS)
    _get_agent()(
        f"""Give me my daily briefing and schedule study blocks on my calendar.
        My assignments file is '{assignments_file}'.
        My existing calendar names are '{configured_calendars}'.
        Save the uploaded ICS file as '{output_name}'."""
    )
