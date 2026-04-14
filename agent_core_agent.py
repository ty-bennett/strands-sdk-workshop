# Written by Ty Bennett
# Fully hosted on AWS via Bedrock Agent Core.
# Deploy with: agentcore deploy

# Only stdlib and bedrock_agentcore are imported at module level.
# boto3, strands, and all heavy dependencies are deferred to first invocation
# so the server starts well within Agent Core's 30-second cold start window.

import csv
import io
import json
import os
import shlex
import uuid
from datetime import date, datetime, timedelta, timezone

from bedrock_agentcore import BedrockAgentCoreApp


# ---------------------------------------------------------------------------
# S3 helpers — boto3 imported lazily inside each function
# ---------------------------------------------------------------------------

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
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

def _parse_s3_uri(s3_uri: str) -> tuple[str, str]:
    path = s3_uri.replace("s3://", "")
    bucket, key = path.split("/", 1)
    return bucket, key


def _read_s3_text(s3_uri: str) -> str:
    import boto3
    bucket, key = _parse_s3_uri(s3_uri)
    return boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")


def _write_s3_text(content: str, s3_uri: str, content_type: str = "text/plain") -> None:
    import boto3
    bucket, key = _parse_s3_uri(s3_uri)
    boto3.client("s3").put_object(
        Bucket=bucket, Key=key,
        Body=content.encode("utf-8"), ContentType=content_type
    )


def _open_csv(filepath: str):
    if filepath.startswith("s3://"):
        return io.StringIO(_read_s3_text(filepath))
    return open(filepath, newline="")


def _generate_presigned_url(s3_uri: str, expiry_seconds: int = 86400) -> str:
    import boto3
    bucket, key = _parse_s3_uri(s3_uri)
    return boto3.client("s3").generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiry_seconds
    )


def _normalize_output_s3_uri(output_file: str) -> str:
    candidate = (output_file or "").strip()
    if not candidate:
        candidate = "study_schedule.ics"
    if candidate.startswith("s3://"):
        return candidate
    if not candidate.endswith(".ics"):
        candidate = f"{candidate}.ics"
    return f"{DEFAULT_S3_ICS_PREFIX.rstrip('/')}/{os.path.basename(candidate)}"


def _escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", r"\,")
        .replace(";", r"\;")
    )


def _read_text_source(source: str) -> str:
    if source.startswith("s3://"):
        return _read_s3_text(source)
    with open(source, "r") as f:
        return f.read()


def _write_text_source(content: str, destination: str, content_type: str = "text/plain") -> None:
    if destination.startswith("s3://"):
        _write_s3_text(content, destination, content_type=content_type)
        return
    with open(destination, "w") as f:
        f.write(content)


def _get_calendar_service():
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = None
    token_json = os.getenv("GOOGLE_CALENDAR_TOKEN_JSON")
    token_source = os.getenv("GOOGLE_CALENDAR_TOKEN_URI")
    credentials_json = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_JSON")
    credentials_source = os.getenv("GOOGLE_CALENDAR_CREDENTIALS_URI")
    allow_local_oauth = os.getenv("ENABLE_LOCAL_GOOGLE_OAUTH") == "1"

    if token_json:
        creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    elif token_source:
        creds = Credentials.from_authorized_user_info(
            json.loads(_read_text_source(token_source)), SCOPES
        )
    elif os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        if token_source:
            _write_text_source(creds.to_json(), token_source, content_type="application/json")
        elif os.path.exists("token.json"):
            _write_text_source(creds.to_json(), "token.json", content_type="application/json")

    if not creds or not creds.valid:
        if credentials_json:
            client_config = json.loads(credentials_json)
        elif credentials_source:
            client_config = json.loads(_read_text_source(credentials_source))
        elif os.path.exists("credentials.json"):
            client_config = json.loads(_read_text_source("credentials.json"))
        else:
            raise RuntimeError(
                "Google Calendar credentials are not configured. "
                "Set GOOGLE_CALENDAR_TOKEN_JSON or GOOGLE_CALENDAR_TOKEN_URI, "
                "and GOOGLE_CALENDAR_CREDENTIALS_JSON or GOOGLE_CALENDAR_CREDENTIALS_URI."
            )

        if not allow_local_oauth:
            raise RuntimeError(
                "Google Calendar token is missing or unusable for cloud execution. "
                "Provide GOOGLE_CALENDAR_TOKEN_JSON or GOOGLE_CALENDAR_TOKEN_URI with a refreshable token."
            )

        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        creds = flow.run_local_server(port=0)
        if token_source:
            _write_text_source(creds.to_json(), token_source, content_type="application/json")
        else:
            _write_text_source(creds.to_json(), "token.json", content_type="application/json")

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
            busy.append((_parse_event_datetime(start), _parse_event_datetime(end)))

    return busy, checked, unresolved, errors


def _overlaps(slot_start: datetime, slot_end: datetime,
              busy: list[tuple[datetime, datetime]]) -> bool:
    for ev_start, ev_end in busy:
        if slot_start < ev_end and slot_end > ev_start:
            return True
    return False


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a sharp academic advisor giving a student their morning briefing.

Structure your response exactly like this:

SITUATION — one blunt sentence on how heavy this week is

TODAY — bullets for what must happen today, in priority order

THIS WEEK — a day-by-day time block plan (Mon through Sun).
  For each day list the tasks and how long to spend on each,
  using the estimated_hours from the CSV to guide the schedule.
  Example: "Tuesday: 2h CSCE 350 HW3, 1h ENGL essay draft"

HEADS UP — anything due next week worth starting now

TIP — one concrete study tip based on what's coming up.
  Use http_request to fetch a URL if a subject-specific tip would genuinely help.

CALENDAR — after the briefing, call schedule_study_blocks with the assignments file.
  If the user did not already specify an output filename, ask one short inline question
  for the S3 filename before uploading. After the tool returns, explicitly repeat the
  exact 'Download link:' line and exact 'curl download:' line from the tool output.
  Tell the user it is ready to import.

Keep it tight. Direct. No filler."""


# ---------------------------------------------------------------------------
# Priority helper
# ---------------------------------------------------------------------------

def calculate_priority_score(days_remaining: int, estimated_hours: float,
                             days_until_due_weight: float = 2.0,
                             effort_weight: float = 1.0) -> float:
    return (days_until_due_weight * days_remaining) + (effort_weight * estimated_hours)


# ---------------------------------------------------------------------------
# Tools — defined as plain functions, @tool applied lazily inside _get_agent()
# ---------------------------------------------------------------------------

def get_gmail_calendar_events(filepath: str, start_hour: int = 9, end_hour: int = 21,
                              max_block_hours: float = 2.0,
                              output_file: str = "study_schedule.ics") -> str:
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
    except Exception:
        return f"Assignment file not found: {filepath}"

    try:
        today = date.today()
        week_end = date.fromordinal(today.toordinal() + (6 - today.weekday()))
        buckets = {"overdue": [], "due_today": [], "due_this_week": [], "upcoming": []}

        reader = csv.DictReader(f)
        required_columns = {"course", "assignment", "due_date", "type", "estimated_hours", "status", "notes"}

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
                due = datetime.strptime(row["due_date"].strip(), "%Y-%m-%d").date()
            except ValueError:
                return f"Invalid date format in row {row_number}: {row['due_date']}. Expected YYYY-MM-DD"
            except KeyError:
                return f"Invalid date format in row {row_number}: missing due_date"

            hours_str = row.get("estimated_hours", "").strip()
            try:
                hours = float(hours_str)
                hours_display = f"{hours_str}h"
            except ValueError:
                hours = 0.0
                hours_display = "?h"

            days_remaining = (due - today).days
            priority_score = calculate_priority_score(days_remaining, hours, days_until_due_weight, effort_weight)

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
            buckets[bucket_key] = [e for _, e in buckets[bucket_key]]

        lines = [f"Today: {today.strftime('%a %b %d')}  |  Week ends: {week_end.strftime('%a %b %d')}\n"]
        for key, items in buckets.items():
            lines.append(f"{key.replace('_', ' ').upper()} ({len(items)})")
            lines += items if items else ["  (none)"]
            lines.append("")

        return "\n".join(lines)

    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()


def schedule_study_blocks(filepath: str, start_hour: int = 9, end_hour: int = 21,
                          max_block_hours: float = 2.0,
                          output_file: str = "s3://uofsc-awscc-strands-agent-workshop-assignments/schedules/study_schedule.ics") -> str:
    """
    Reads the assignment CSV from a local path or S3 URI, calculates prioritized
    study blocks based on estimated hours and due dates, avoids existing Google
    Calendar conflicts when possible, and uploads an ICS calendar file to S3.

    Args:
        filepath: Local path or S3 URI to the CSV file with assignment data
        start_hour: Earliest hour to schedule study blocks, 24h format (default 9 = 9am)
        end_hour: Latest hour to end study blocks, 24h format (default 21 = 9pm)
        max_block_hours: Maximum hours per single study session (default 2.0)
        output_file: S3 URI or filename for the output ICS file

    Returns:
        Summary of scheduled blocks and a presigned S3 download URL for the ICS file
    """
    output_s3_uri = _normalize_output_s3_uri(output_file)

    try:
        f = _open_csv(filepath)
    except Exception:
        return f"Assignment file not found: {filepath}"

    try:
        today = date.today()
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            return "Malformed CSV file: unable to read header row"

        required = {"course", "assignment", "due_date", "estimated_hours", "status"}
        missing = required - set(reader.fieldnames)
        if missing:
            return f"Missing required columns: {', '.join(sorted(missing))}"

        assignments = []
        for row in reader:
            if row.get("status", "").strip().lower() == "complete":
                continue
            try:
                due = datetime.strptime(row["due_date"].strip(), "%Y-%m-%d").date()
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
            busy_slots, checked, unresolved, errors = _get_busy_slots(window_start, window_end)
            calendar_status = (
                f"Checked Google Calendar: {len(busy_slots)} existing event(s) found "
                f"across {', '.join(checked) if checked else '(no readable calendars)'}."
            )
            if unresolved:
                calendar_status += f" Unresolved calendars: {', '.join(unresolved)}."
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
            current_slot = datetime(tomorrow.year, tomorrow.month, tomorrow.day, start_hour, 0)
        else:
            current_slot = datetime(today.year, today.month, today.day, next_start_hour, 0)

        events = []
        for asgn in assignments:
            remaining = asgn["hours"]
            while remaining > 0:
                block = min(remaining, max_block_hours)
                block_end = current_slot + timedelta(hours=block)

                if block_end.hour > end_hour or (block_end.hour == end_hour and block_end.minute > 0):
                    next_day = current_slot.date() + timedelta(days=1)
                    current_slot = datetime(next_day.year, next_day.month, next_day.day, start_hour, 0)
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

        # RFC 5545 requires CRLF line endings and a trailing CRLF
        ics_content = "\r\n".join(ics_lines) + "\r\n"
        _write_s3_text(ics_content, output_s3_uri, content_type="text/calendar")
        download_url = None
        try:
            download_url = _generate_presigned_url(output_s3_uri)
        except Exception as exc:
            download_url = f"Could not generate download link: {exc}"

        summary = [calendar_status, f"Scheduled {len(events)} study block(s) — uploaded to {output_s3_uri}\n"]
        for ev in events:
            duration_mins = int((ev["end"] - ev["start"]).seconds / 60)
            summary.append(
                f"  {ev['start'].strftime('%a %b %d %I:%M %p')} – "
                f"{ev['end'].strftime('%I:%M %p')} ({duration_mins}min)  {ev['summary']}"
            )
        summary.append(f"\nDownload link: {download_url}")
        if download_url.startswith("http"):
            summary.append(
                "curl download: "
                f"curl -L {shlex.quote(download_url)} -o {shlex.quote(os.path.basename(_parse_s3_uri(output_s3_uri)[1]))}"
            )
        summary.append("\nTo add to Google Calendar: Settings → Import → select the ICS file")
        summary.append("To add to Outlook: File → Open & Export → Import/Export → Import an iCalendar file")
        return "\n".join(summary)

    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()


# ---------------------------------------------------------------------------
# Agent Core app
# ---------------------------------------------------------------------------

app = BedrockAgentCoreApp()

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        # All heavy imports deferred here — only runs on first invocation,
        # not during cold start.
        from strands import Agent, tool
        from strands.models import BedrockModel
        from strands_tools import http_request
        _agent = Agent(
            model=BedrockModel(model_id="amazon.nova-pro-v1:0"),
            system_prompt=SYSTEM_PROMPT,
            tools=[tool(get_gmail_calendar_events), tool(load_assignments), tool(schedule_study_blocks), http_request],
        )
    return _agent


def _should_force_schedule(user_message: str, output_file: str, payload: dict) -> bool:
    if "force_schedule" in payload:
        return bool(payload["force_schedule"])
    if output_file:
        return True

    lowered = user_message.lower()
    schedule_keywords = (
        "schedule study",
        "study block",
        "study blocks",
        "calendar",
        ".ics",
    )
    return any(keyword in lowered for keyword in schedule_keywords)


@app.entrypoint
def invoke(payload):
    user_message = payload.get("prompt", "Give me my daily briefing.")
    assignments_file = payload.get(
        "assignments_file",
        "s3://uofsc-awscc-strands-agent-workshop-assignments/assignments/assignments.csv"
    )
    output_file = payload.get("output_file", "")
    full_prompt = (
        f"{user_message}\n"
        f"My assignments file is '{assignments_file}'.\n"
        f"My existing calendar names are '{', '.join(DEFAULT_CALENDARS)}'.\n"
    )
    if output_file:
        full_prompt += f"Save the uploaded ICS file as '{output_file}'."

    result_text = str(_get_agent()(full_prompt))

    if "Download link:" not in result_text and _should_force_schedule(user_message, output_file, payload):
        schedule_text = schedule_study_blocks(
            assignments_file,
            output_file=output_file or "study_schedule.ics",
        )
        if "CALENDAR" in result_text:
            result_text = f"{result_text}\n\n{schedule_text}"
        else:
            result_text = f"{result_text}\n\nCALENDAR\n{schedule_text}"

    return {"result": result_text}


if __name__ == "__main__":
    app.run()
