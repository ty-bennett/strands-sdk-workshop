#!/usr/bin/env python3
import argparse
import json
import os
import shlex
from pathlib import Path

import boto3


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_AGENT_NAME = "hosted_agent_kjr92"
DEFAULT_TOKEN_PATH = REPO_ROOT / "agents" / "token.json"
DEFAULT_CREDENTIALS_PATH = REPO_ROOT / "agents" / "credentials.json"
DEFAULT_S3_PREFIX = "s3://uofsc-awscc-strands-agent-workshop-assignments/agentcore/google-auth/"
DEFAULT_SCHEDULE_PREFIX = "s3://uofsc-awscc-strands-agent-workshop-assignments/schedules/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare Google Calendar auth for agent_core_agent.py cloud deployment."
    )
    parser.add_argument("--agent", default=DEFAULT_AGENT_NAME, help="Agent Core agent name.")
    parser.add_argument("--token-file", default=str(DEFAULT_TOKEN_PATH), help="Local Google token.json path.")
    parser.add_argument(
        "--credentials-file",
        default=str(DEFAULT_CREDENTIALS_PATH),
        help="Local Google credentials.json path.",
    )
    parser.add_argument(
        "--s3-prefix",
        default=DEFAULT_S3_PREFIX,
        help="S3 prefix where the auth JSON files should be uploaded.",
    )
    parser.add_argument(
        "--schedule-prefix",
        default=DEFAULT_SCHEDULE_PREFIX,
        help="Default S3 prefix where generated ICS files should be stored.",
    )
    parser.add_argument(
        "--calendars",
        default=os.getenv("GOOGLE_CALENDARS", "primary,tybennett924@gmail.com,school schedule"),
        help="Comma-separated calendar names/IDs.",
    )
    parser.add_argument(
        "--print-env-file",
        action="store_true",
        help="Also write a local .agentcore-google-auth.env file with the resulting env vars.",
    )
    return parser.parse_args()


def parse_s3_uri(uri: str) -> tuple[str, str]:
    path = uri.replace("s3://", "", 1)
    bucket, key = path.split("/", 1)
    return bucket, key


def upload_json(local_path: Path, destination_uri: str) -> None:
    bucket, key = parse_s3_uri(destination_uri)
    content = json.loads(local_path.read_text())
    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(content).encode("utf-8"),
        ContentType="application/json",
    )


def join_s3(prefix: str, filename: str) -> str:
    return f"{prefix.rstrip('/')}/{filename}"


def main() -> int:
    args = parse_args()
    token_path = Path(args.token_file).expanduser().resolve()
    credentials_path = Path(args.credentials_file).expanduser().resolve()

    if not token_path.exists():
        raise SystemExit(f"Missing token file: {token_path}")
    if not credentials_path.exists():
        raise SystemExit(f"Missing credentials file: {credentials_path}")

    # Validate JSON before upload.
    json.loads(token_path.read_text())
    json.loads(credentials_path.read_text())

    token_uri = join_s3(args.s3_prefix, "token.json")
    credentials_uri = join_s3(args.s3_prefix, "credentials.json")

    upload_json(token_path, token_uri)
    upload_json(credentials_path, credentials_uri)

    env_pairs = [
        ("GOOGLE_CALENDAR_TOKEN_URI", token_uri),
        ("GOOGLE_CALENDAR_CREDENTIALS_URI", credentials_uri),
        ("GOOGLE_CALENDARS", args.calendars),
        ("STUDY_SCHEDULE_S3_PREFIX", args.schedule_prefix),
    ]

    print("Uploaded Google auth files:")
    print(f"  token: {token_uri}")
    print(f"  credentials: {credentials_uri}")
    print()
    print("Deploy command:")
    deploy_cmd = ["agentcore", "deploy", "-a", args.agent, "-auc"]
    for key, value in env_pairs:
        deploy_cmd.extend(["--env", f"{key}={value}"])
    print(" ".join(shlex.quote(part) for part in deploy_cmd))

    if args.print_env_file:
        env_path = REPO_ROOT / ".agentcore-google-auth.env"
        lines = [f"export {key}={shlex.quote(value)}" for key, value in env_pairs]
        env_path.write_text("\n".join(lines) + "\n")
        print()
        print(f"Wrote env file: {env_path}")
        print(f"Source it with: source {shlex.quote(str(env_path))}")

    print()
    print("Runtime requirements:")
    print("  The Agent Core execution role must be able to read those S3 objects.")
    print("  Redeploy after changing token.json or credentials.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
