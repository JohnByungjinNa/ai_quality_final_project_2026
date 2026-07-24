import os
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = DASHBOARD_DIR.parent
WORKSPACE_DIR = PROJECT_DIR.parent
UPLOADS_FILE = PROJECT_DIR / "data" / "testcases" / "testcase_uploads.json"


def load_registered_testcase_uploads():
    if not UPLOADS_FILE.exists():
        return []

    try:
        with UPLOADS_FILE.open("r", encoding="utf-8") as file:
            uploads = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []

    return sorted(
        [upload for upload in uploads if upload.get("data")],
        key=lambda upload: (upload.get("uploaded_at", ""), upload.get("id", "")),
        reverse=True,
    )


def _run_command(command, timeout=180, env=None):
    process_env = os.environ.copy()
    process_env["PYTHONIOENCODING"] = "utf-8"
    process_env["PYTHONUTF8"] = "1"
    if env:
        process_env.update(env)

    completed = subprocess.run(
        command,
        cwd=WORKSPACE_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
        env=process_env,
    )
    return {
        "command": " ".join(map(str, command)),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def parse_pytest_summary(output):
    passed_match = re.search(r"(?P<passed>\d+)\s+passed", output)
    failed_match = re.search(r"(?P<failed>\d+)\s+failed", output)
    seconds_match = re.search(r"in\s+(?P<seconds>[\d.]+)s", output)

    return {
        "passed": int(passed_match.group("passed")) if passed_match else 0,
        "failed": int(failed_match.group("failed")) if failed_match else 0,
        "seconds": float(seconds_match.group("seconds")) if seconds_match else None,
    }


def parse_coverage_percent(output):
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+(?P<coverage>\d+)%", output)
    return int(match.group("coverage")) if match else None


def run_pytest(include_coverage=False, testcase_upload_id=None):
    env = {}
    if testcase_upload_id:
        env["AIQA_TESTCASE_UPLOAD_ID"] = testcase_upload_id

    command = [
        sys.executable,
        "-m",
        "pytest",
        str(PROJECT_DIR / "tests"),
        "-q",
        "--tb=short",
    ]

    if include_coverage:
        coverage_file = Path(tempfile.gettempdir()) / f"aiqa_coverage_{os.getpid()}_{time.time_ns()}"
        env["COVERAGE_FILE"] = str(coverage_file)
        command.extend(
            [
                f"--cov={PROJECT_DIR}",
                "--cov-report=term-missing",
            ]
        )

    result = _run_command(command, env=env)
    combined_output = f"{result['stdout']}\n{result['stderr']}"
    result["summary"] = parse_pytest_summary(combined_output)
    result["coverage"] = parse_coverage_percent(combined_output)
    return result
