import csv
import os
from datetime import date, datetime, timedelta
from strands import Agent, tool
from strands.models import BedrockModel

from dotenv import load_dotenv
load_dotenv()


model = BedrockModel(model_id="amazon.nova-pro-v1:0")


def calculate_priority_score(days_remaining: int, estimated_hours: float,
                             days_until_due_weight: float = 2.0,
                             effort_weight: float = 1.0) -> float:
    """
    Calculate priority score for an assignment.
    Lower score = higher priority (more urgent).
    """
    return (days_until_due_weight * days_remaining) + (effort_weight * estimated_hours)


@tool
def load_assignments(filepath: str, days_until_due_weight: float = 2.0,
                     effort_weight: float = 1.0) -> str:
    """
    Reads an assignment CSV file, categorizes assignments by deadline, and returns
    formatted text organized into buckets: overdue, due today, due this week, and upcoming.
    Skips completed assignments and sorts each bucket by priority score.

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
            bucket_name = key.replace('_', ' ').upper()
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
                          max_block_hours: float = 2.0) -> str:
    """
    Reads the assignment CSV, calculates prioritized study blocks based on estimated
    hours and due dates, and returns a plain-text schedule of when to study what.
    Assignments are scheduled starting from the next available slot today, capped
    at max_block_hours per session with 30-minute breaks in between.
    Completed assignments are skipped.

    Args:
        filepath: Path to CSV file with assignment data
        start_hour: Earliest hour to schedule study blocks, 24h format (default 9 = 9am)
        end_hour: Latest hour to end study blocks, 24h format (default 21 = 9pm)
        max_block_hours: Maximum hours per single study session (default 2.0)

    Returns:
        Plain-text list of study blocks with start/end times and assignment details
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

        blocks = []
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

                blocks.append(
                    f"  {current_slot.strftime('%a %b %d %I:%M %p')} – "
                    f"{block_end.strftime('%I:%M %p')}  "
                    f"[{asgn['course']}] {asgn['assignment']} "
                    f"(due {asgn['due'].strftime('%a %b %d')})"
                )

                remaining -= block
                current_slot = block_end
                if remaining > 0:
                    current_slot += timedelta(minutes=30)

        lines = [f"Calculated {len(blocks)} study block(s):\n"] + blocks
        return "\n".join(lines)

    except csv.Error as e:
        return f"Malformed CSV file: {str(e)}"
    finally:
        f.close()


# agent
agent = Agent(
    model=model,
    system_prompt="""You are a sharp academic advisor giving a student their morning briefing.
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

    CALENDAR — after the briefing, call schedule_study_blocks with the 
    assignments file to generate specific study blocks
    Keep it tight. Direct. No filler.
    """,
    tools=[load_assignments, schedule_study_blocks],
)

if __name__ == "__main__":
    agent("""Give me my daily briefing and calculate my study blocks. Do not output to .ics file
        My assignments file is 'assignments.csv'.""")
