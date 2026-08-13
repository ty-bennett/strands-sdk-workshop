# Written by Ty Bennett
# Fully hosted on AWS via Bedrock Agent Core.
# Deploy with: agentcore deploy   (was 'agentcore launch' in older toolkit versions)
#
# This is the deployment demo: one agent, two tools, one answer.
# The point is the hosting story, not the domain logic.
#
# Only stdlib and bedrock_agentcore are imported at module level.
# strands and boto3 are deferred to the first invocation so the server
# starts well within Agent Core's 30-second cold start window.

import csv
import io
import os
from datetime import date, datetime

from bedrock_agentcore import BedrockAgentCoreApp


DEFAULT_ASSIGNMENTS_FILE = os.getenv(
    "ASSIGNMENTS_FILE",
    "s3://uofsc-awscc-strands-agent-workshop-assignments/assignments/assignments.csv",
)


SYSTEM_PROMPT = """You are a sharp academic advisor giving a student their briefing.

Call get_today to find out what today's date is, then call load_assignments
to read the student's assignment list.

Structure your response exactly like this:

SITUATION — one blunt sentence on how heavy this week is

TODAY — bullets for what must happen today, in priority order

THIS WEEK — the handful of things worth starting now, with rough hours each

Keep it tight. Direct. No filler."""


# ---------------------------------------------------------------------------
# Tools — plain functions here; @tool is applied lazily inside _get_agent()
# so that importing strands stays off the cold-start path.
# ---------------------------------------------------------------------------

def get_today() -> str:
    """
    Returns today's date. Call this first so the briefing knows what
    "due today" and "due this week" actually mean.

    Returns:
        Today's date, e.g. "Thursday, August 13 2026"
    """
    return datetime.now().strftime("%A, %B %d %Y")


def load_assignments(filepath: str = DEFAULT_ASSIGNMENTS_FILE) -> str:
    """
    Reads an assignment CSV from a local path or an S3 URI and returns the
    pending assignments sorted by urgency. Completed assignments are skipped.

    Args:
        filepath: Local path or S3 URI, e.g.
            s3://uofsc-awscc-strands-agent-workshop-assignments/assignments/assignments.csv

    Returns:
        Formatted list of pending assignments, most urgent first
    """
    try:
        if filepath.startswith("s3://"):
            import boto3
            bucket, key = filepath.replace("s3://", "").split("/", 1)
            body = boto3.client("s3").get_object(Bucket=bucket, Key=key)["Body"]
            f = io.StringIO(body.read().decode("utf-8"))
        else:
            f = open(filepath, newline="")
    except Exception as exc:
        return f"Could not read assignment file {filepath}: {exc}"

    try:
        today = date.today()
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            return "Malformed CSV file: unable to read header row"

        required = {"course", "assignment", "due_date", "estimated_hours", "status"}
        missing = required - set(reader.fieldnames)
        if missing:
            return f"Missing required columns: {', '.join(sorted(missing))}"

        rows = []
        for row in reader:
            if row.get("status", "").strip().lower() == "complete":
                continue
            try:
                due = datetime.strptime(row["due_date"].strip(), "%Y-%m-%d").date()
            except (ValueError, KeyError):
                continue  # skip rows with an unusable due date
            try:
                hours = float(row.get("estimated_hours", "1").strip() or "1")
            except ValueError:
                hours = 1.0

            days_left = (due - today).days
            # Lower score = more urgent: soon-and-long beats far-and-short.
            rows.append(((2.0 * days_left) + hours, days_left, due, hours, row))

        if not rows:
            return "No pending assignments found."

        rows.sort(key=lambda r: r[0])

        lines = [f"Today is {today.strftime('%a %b %d')}. "
                 f"{len(rows)} pending assignment(s), most urgent first:\n"]
        for _, days_left, due, hours, row in rows:
            if days_left < 0:
                when = f"OVERDUE by {abs(days_left)}d"
            elif days_left == 0:
                when = "DUE TODAY"
            else:
                when = f"in {days_left}d"
            lines.append(
                f"  [{row['course']}] {row['assignment']}"
                f" — due {due.strftime('%a %b %d')} ({when}, ~{hours}h)"
            )
        return "\n".join(lines)

    except csv.Error as exc:
        return f"Malformed CSV file: {exc}"
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
        # Heavy imports deferred here — this runs on first invocation,
        # not during cold start.
        from strands import Agent, tool
        from strands.models import BedrockModel

        _agent = Agent(
            model=BedrockModel(model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0"),
            system_prompt=SYSTEM_PROMPT,
            tools=[tool(get_today), tool(load_assignments)],
        )
    return _agent


@app.entrypoint
def invoke(payload):
    """
    Agent Core calls this with the JSON body of each invocation.

    Example:
        agentcore invoke '{"prompt": "Give me my briefing."}'
    """
    user_message = payload.get("prompt", "Give me my briefing.")
    assignments_file = payload.get("assignments_file", DEFAULT_ASSIGNMENTS_FILE)

    prompt = f"{user_message}\nMy assignments file is '{assignments_file}'."

    return {"result": str(_get_agent()(prompt))}


if __name__ == "__main__":
    app.run()
