# Written by Ty Bennett
# Cloud-deployed version — reads/writes CSV and ICS via S3 instead of local filesystem.
# AWS credentials come from the execution environment (IAM role, Lambda, EC2, etc.)

import csv
import io
import time
import uuid
from datetime import date, datetime, timedelta

import boto3
from botocore.exceptions import ClientError
from strands import Agent, tool
from strands.models import BedrockModel
from strands_tools import http_request


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


def _open_csv(filepath: str):
    """
    Return a file-like object for CSV parsing.
    Supports both local paths and s3:// URIs.
    """
    if filepath.startswith("s3://"):
        return io.StringIO(_read_s3_text(filepath))
    return open(filepath, newline="")


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

def load_system_prompt(filepath: str = "system_prompt.txt") -> str:
    """Load system prompt — supports local path or S3 URI."""
    try:
        if filepath.startswith("s3://"):
            return _read_s3_text(filepath)
        with open(filepath, "r") as f:
            return f.read()
    except (FileNotFoundError, ClientError) as e:
        raise FileNotFoundError(f"System prompt not found: {filepath}") from e


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
        _model = BedrockModel(model_id="amazon.nova-pro-v1:0")
        _agent = Agent(
            model=_model,
            system_prompt=load_system_prompt(),
            tools=[load_assignments, schedule_study_blocks, http_request],
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
                          output_file: str = "s3://uofsc-awscc-strands-agent-workshop-assignments/schedules/study_schedule.ics") -> str:
    """
    Reads the assignment CSV from a local path or S3 URI, calculates prioritized
    study blocks based on estimated hours and due dates, and writes an ICS calendar
    file to a local path or back to S3. Assignments are scheduled starting from the
    next available slot today, capped at max_block_hours per session with 30-minute
    breaks in between. Completed assignments are skipped.

    Args:
        filepath: Local path or S3 URI to CSV file with assignment data
        start_hour: Earliest hour to schedule study blocks, 24h format (default 9 = 9am)
        end_hour: Latest hour to end study blocks, 24h format (default 21 = 9pm)
        max_block_hours: Maximum hours per single study session (default 2.0)
        output_file: Local path or S3 URI for the output ICS file

    Returns:
        Summary of all scheduled blocks and where the ICS file was saved
    """
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
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Academic Advisor Agent//Study Scheduler//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
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
        ics_content = "\r\n".join(ics_lines)

        # Write ICS to S3 or local path
        if output_file.startswith("s3://"):
            _write_s3_text(ics_content, output_file,
                           content_type="text/calendar")
            destination = f"uploaded to {output_file}"
        else:
            with open(output_file, "w") as out:
                out.write(ics_content)
            destination = f"saved to {output_file}"

        summary = [f"Scheduled {len(events)} study block(s) — {destination}\n"]
        for ev in events:
            duration_mins = int((ev["end"] - ev["start"]).seconds / 60)
            summary.append(
                f"  {ev['start'].strftime('%a %b %d %I:%M %p')} – "
                f"{ev['end'].strftime('%I:%M %p')} ({duration_mins}min)  {
                    ev['summary']}"
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
    _get_agent()("""Give me my daily briefing and schedule study blocks on my calendar.
        My assignments file is at this presigned URL
        'https://uofsc-awscc-strands-agent-workshop-assignments.s3.us-east-1.amazonaws.com/assignments/assignments.csv?response-content-disposition=inline&X-Amz-Content-Sha256=UNSIGNED-PAYLOAD&X-Amz-Security-Token=IQoJb3JpZ2luX2VjEL%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F%2FwEaCXVzLWVhc3QtMSJGMEQCIHxFhmtgajRm68Nm93MCveBl8VoPe1TeDXhwu9OSSV5BAiBSfs9JatZ4BtMc8BYTMCPDbqLCsWh4SJAWislIx%2FuhJirCAwiH%2F%2F%2F%2F%2F%2F%2F%2F%2F%2F8BEAAaDDk3MDU0NzM0NjA3NyIM2bzLD%2BswnNumx3DsKpYD%2BPpNdUqLQZ7%2FeV%2FoVPDDxPgr8HSb1pL6C0%2BxwBqAUg7nqsXh9DHHX2aN5qTqIJNnhTehWj4rOxKSF0%2FwYDrfUl7N9Fryt0FXLtZAkA6Ico7sJQTuevvXfnGBVbAw71i00If%2FBsqTQfUQydjEYNcbQDIQjAXSVMl%2FA%2FpSiGjSWiyOglhAyKUdxynXYt9I8FDglEP53kYJMVzeQAdX5%2BQXCNftoX9clzAikYSpUnkbsdoUJjRg%2Ba7%2FAOeL4NGMX58HBGI9DnZ%2FzwaalFsGQ0%2B4FvVotymMjp9njC53Uc%2F%2BNiHVgTDXBq9LYY9ZTQv7diR0uqFh%2FS92NKUqLOT4ff2gs8C25R0%2BLSeB%2FiU58uKIYyW4sBmw1h2dS02uZzTZTmdhdmyEvuhoc9ogAY5bL6lGk0lhu4JyzOJggkMnwwXpJLB0M36ovX0LiGg8r66cQ8gsTL%2FO4ksfvZWucY5LA69OXPfx%2F0%2FnF4mv%2FTOLK8zMil6TRxSs6JXPFYP%2FOUmHk7GSA2xProsrV4WUxozis8HzpH5zO9Oa2jDqp%2FbOBjrfAmndANz3Be%2Fogzct6w2X%2FNN%2Bq2ecnfgtyyN%2Fxov8ijbTInd3w%2FO99KEKb86Ecx9qTmDZkEUJtYE3WZzHIC89X%2F7QR%2BP5usTiYNqevJZrMZ2ls1axtaSuGk3iBdM5QJpjKSaNuS%2FA8msWXmuvTAv8nKt2Sys0MUl17NVkxgP9EaLS88ViTr93kqjgXdLEvERN%2B0eq89E3oNZiRVGg%2FeFgJIoN4NsZIzWRg%2FwvovDDwhfBNJ2wssi1ySK%2BLNFjzPcw270d1D%2BJakzJd8c9aypwOz24lh%2FLFNM9fjdyQrcZgCC0tMgnR4XT%2F%2BaxWiKp7nq3X2IGPKWM4jW4WOlz3lqB71uWMPTuimbxum6rz44JcbHfEtvUFQmKShtlhvYE4jpuO4xdEuZcAR6czlEpoMdkW2Z4Fs00wMszyiyZpgkVfyd6WMyYvoFk%2BkOjtgChdYnD32yP6%2B7Pz%2FCb7LAw1snSqw%3D%3D&X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=ASIA6D6JBHKO5IITVASE%2F20260414%2Fus-east-1%2Fs3%2Faws4_request&X-Amz-Date=20260414T060437Z&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature=83556c75d395ba9ddbce6935bc14e514ff251e719647152a34335d9bee915155' .""")
