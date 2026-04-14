#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = REPO_ROOT / ".bedrock_agentcore.yaml"
DEFAULT_ASSIGNMENTS = "s3://uofsc-awscc-strands-agent-workshop-assignments/assignments/assignments.csv"


def detect_default_agent() -> str | None:
    if not DEFAULT_CONFIG.exists():
        return None
    for line in DEFAULT_CONFIG.read_text().splitlines():
        if line.startswith("default_agent:"):
            return line.split(":", 1)[1].strip()
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Invoke the deployed Bedrock Agent Core agent.")
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Give me my daily briefing and schedule study blocks on my calendar.",
        help="Prompt to send to the agent.",
    )
    parser.add_argument(
        "--assignments-file",
        default=DEFAULT_ASSIGNMENTS,
        help="Assignments CSV path or s3:// URI.",
    )
    parser.add_argument(
        "--output-file",
        default="study_schedule.ics",
        help="Desired ICS filename or s3:// URI.",
    )
    parser.add_argument(
        "--agent",
        default=os.getenv("BEDROCK_AGENTCORE_AGENT") or detect_default_agent(),
        help="Agent Core agent name.",
    )
    parser.add_argument("--session-id", default=None, help="Optional Agent Core session id.")
    parser.add_argument("--local", action="store_true", help="Invoke local runtime.")
    parser.add_argument("--dev", action="store_true", help="Invoke local dev server.")
    parser.add_argument("--port", type=int, default=8080, help="Local/dev port.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.agent and not args.local and not args.dev:
        raise SystemExit("No agent name found. Pass --agent or set BEDROCK_AGENTCORE_AGENT.")

    payload = {
        "prompt": args.prompt,
        "assignments_file": args.assignments_file,
        "output_file": args.output_file,
    }

    cmd = ["agentcore", "invoke", json.dumps(payload)]
    if args.agent:
        cmd.extend(["--agent", args.agent])
    if args.session_id:
        cmd.extend(["--session-id", args.session_id])
    if args.local:
        cmd.append("--local")
    if args.dev:
        cmd.append("--dev")
    if args.local or args.dev:
        cmd.extend(["--port", str(args.port)])

    print("Running:", " ".join(cmd), file=sys.stderr)
    completed = subprocess.run(cmd, cwd=REPO_ROOT)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
