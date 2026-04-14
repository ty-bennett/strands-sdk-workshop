# Written by Ty Bennett
# Fully hosted on AWS via Bedrock Agent Core.
# Deploy with: agentcore deploy

# Only stdlib and bedrock_agentcore are imported at module level.
# boto3, strands, and all heavy dependencies are deferred to first invocation
# so the server starts well within Agent Core's 30-second cold start window.

import csv
import io
import uuid
from datetime import date, datetime, timedelta

from bedrock_agentcore import BedrockAgentCoreApp


# ---------------------------------------------------------------------------
# S3 helpers — boto3 imported lazily inside each function
# ---------------------------------------------------------------------------

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


def _generate_presigned_url(s3_uri: str, expiry_seconds: int = 3600) -> str:
    import boto3
    bucket, key = _parse_s3_uri(s3_uri)
    return boto3.client("s3").generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expiry_seconds
    )


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

CALENDAR — after the briefing, call schedule_study_blocks with the assignments file
  to generate a study schedule and upload it to S3. Tell the user it is ready and
  give them the presigned download URL.

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
    study blocks based on estimated hours and due dates, and uploads an ICS calendar
    file to S3. Returns a presigned download URL valid for 1 hour.

    Args:
        filepath: Local path or S3 URI to the CSV file with assignment data
        start_hour: Earliest hour to schedule study blocks, 24h format (default 9 = 9am)
        end_hour: Latest hour to end study blocks, 24h format (default 21 = 9pm)
        max_block_hours: Maximum hours per single study session (default 2.0)
        output_file: S3 URI for the output ICS file

    Returns:
        Summary of scheduled blocks and a presigned S3 download URL for the ICS file
    """
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
                f"SUMMARY:{ev['summary']}",
                f"DESCRIPTION:{ev['description']}",
                "STATUS:CONFIRMED",
                "SEQUENCE:0",
                "END:VEVENT",
            ]
        ics_lines.append("END:VCALENDAR")

        # RFC 5545 requires CRLF line endings and a trailing CRLF
        ics_content = "\r\n".join(ics_lines) + "\r\n"
        _write_s3_text(ics_content, output_file, content_type="text/calendar")
        download_url = _generate_presigned_url(output_file)

        summary = [f"Scheduled {len(events)} study block(s) — uploaded to {output_file}\n"]
        for ev in events:
            duration_mins = int((ev["end"] - ev["start"]).seconds / 60)
            summary.append(
                f"  {ev['start'].strftime('%a %b %d %I:%M %p')} – "
                f"{ev['end'].strftime('%I:%M %p')} ({duration_mins}min)  {ev['summary']}"
            )
        summary.append(f"\nDownload your schedule (link valid 1 hour):\n{download_url}")
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
            tools=[tool(load_assignments), tool(schedule_study_blocks), http_request],
        )
    return _agent


@app.entrypoint
def invoke(payload):
    user_message = payload.get("prompt", "Give me my daily briefing.")
    assignments_file = payload.get(
        "assignments_file",
        "s3://uofsc-awscc-strands-agent-workshop-assignments/assignments/assignments.csv"
    )
    full_prompt = f"{user_message}\nMy assignments file is '{assignments_file}'."
    result = _get_agent()(full_prompt)
    return {"result": str(result)}


app.run()
