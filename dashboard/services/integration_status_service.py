from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from core.paths import PROJECT_DIR, VOC_QUALITY_RUNS_DIR


AWS_PROFILE = "JohnNa-QA"
AWS_REGION = "ap-northeast-2"
AI_PROVIDER_KEYS = {
    "OpenAI": ("OPENAI_API_KEY",),
    "Anthropic": ("ANTHROPIC_API_KEY",),
    "Gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"),
}
SECRET_NAMES = {name for names in AI_PROVIDER_KEYS.values() for name in names}


def collect_integration_status(
    *,
    project_dir: Path = PROJECT_DIR,
    home_dir: Path | None = None,
    environ: dict[str, str] | None = None,
    verify_aws: bool = True,
) -> dict:
    project_dir = Path(project_dir)
    home_dir = Path(home_dir) if home_dir is not None else Path.home()
    environment = dict(os.environ if environ is None else environ)
    configured_secrets = _configured_secret_names(project_dir, environment)
    providers = [
        {
            "name": provider,
            "configured": any(name in configured_secrets for name in names),
            "status": (
                "설정됨 · 호출 전 검증 필요"
                if any(name in configured_secrets for name in names)
                else "미설정"
            ),
        }
        for provider, names in AI_PROVIDER_KEYS.items()
    ]
    aws = _aws_status(
        project_dir=project_dir,
        home_dir=home_dir,
        environment=environment,
        verify_session=verify_aws,
    )
    evidence = _evidence_status(project_dir)
    voc = _latest_voc_status(project_dir)
    configured_count = sum(1 for provider in providers if provider["configured"])
    return {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "aws": aws,
        "ai": {
            "providers": providers,
            "configured_count": configured_count,
            "total_count": len(providers),
            "all_configured": configured_count == len(providers),
        },
        "evidence": evidence,
        "voc": voc,
    }


def start_aws_browser_login(
    *,
    project_dir: Path = PROJECT_DIR,
    home_dir: Path | None = None,
    environ: dict[str, str] | None = None,
    platform_name: str | None = None,
) -> dict:
    project_dir = Path(project_dir)
    home_dir = Path(home_dir) if home_dir is not None else Path.home()
    environment = dict(os.environ if environ is None else environ)
    if (platform_name or os.name) != "nt":
        return {"ok": False, "message": "상단 AWS 로그인 실행은 현재 Windows 환경에서만 지원합니다."}
    aws_cli = _resolve_aws_cli(home_dir, environment)
    if not aws_cli:
        return {"ok": False, "message": "AWS CLI가 설치되어 있지 않습니다."}

    safe_aws_cli = str(aws_cli).replace("'", "''")
    command = (
        "$Host.UI.RawUI.WindowTitle='AWS JohnNa-QA Login'; "
        f"& '{safe_aws_cli}' login --profile '{AWS_PROFILE}' --region '{AWS_REGION}'; "
        "if ($LASTEXITCODE -eq 0) { "
        "Write-Host 'AWS login completed. The dashboard status will update automatically.' -ForegroundColor Green; "
        "Start-Sleep -Seconds 3 "
        "} else { "
        "Write-Host 'AWS login failed. Review the message above.' -ForegroundColor Red; "
        "Read-Host 'Press Enter to close' "
        "}"
    )
    try:
        process = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            cwd=project_dir,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    except OSError:
        return {"ok": False, "message": "AWS 로그인 창을 열 수 없습니다."}
    return {
        "ok": True,
        "message": "AWS 로그인 창과 브라우저 인증을 시작했습니다.",
        "process_id": process.pid,
    }


def logout_aws_session(
    *,
    project_dir: Path = PROJECT_DIR,
    home_dir: Path | None = None,
    environ: dict[str, str] | None = None,
) -> dict:
    """Clear only the temporary AWS login credentials for the dashboard profile."""
    project_dir = Path(project_dir)
    home_dir = Path(home_dir) if home_dir is not None else Path.home()
    environment = dict(os.environ if environ is None else environ)
    aws_cli = _resolve_aws_cli(home_dir, environment)
    if not aws_cli:
        return {"ok": False, "message": "AWS CLI가 설치되어 있지 않습니다."}

    command_environment = dict(environment)
    command_environment.update(
        {
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
    )
    try:
        completed = subprocess.run(
            [
                aws_cli,
                "logout",
                "--profile",
                AWS_PROFILE,
                "--region",
                AWS_REGION,
                "--no-cli-pager",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=command_environment,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "AWS 로그아웃 응답 시간이 초과되었습니다."}
    except OSError:
        return {"ok": False, "message": "AWS 로그아웃을 실행할 수 없습니다."}
    if completed.returncode != 0:
        return {"ok": False, "message": "AWS 로그아웃에 실패했습니다."}
    return {"ok": True, "message": "AWS 임시 로그인 세션을 종료했습니다."}


def _configured_secret_names(project_dir: Path, environment: dict[str, str]) -> set[str]:
    configured = {
        name
        for name in SECRET_NAMES
        if _is_configured_secret(environment.get(name, ""))
    }
    candidates = (project_dir / ".env", project_dir / "voc_quality_runtime" / ".env")
    for path in candidates:
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            name = name.strip()
            if name not in SECRET_NAMES or name in configured:
                continue
            value = value.strip().strip("'\"")
            if _is_configured_secret(value):
                configured.add(name)
    return configured


def _is_configured_secret(value: str) -> bool:
    normalized = str(value or "").strip()
    return bool(
        normalized
        and not normalized.upper().startswith(("YOUR_", "CHANGE_ME", "REPLACE_ME"))
        and not (normalized.startswith("${") and normalized.endswith("}"))
    )


def _aws_status(
    *,
    project_dir: Path,
    home_dir: Path,
    environment: dict[str, str],
    verify_session: bool,
) -> dict:
    aws_cli = _resolve_aws_cli(home_dir, environment)
    config_path = home_dir / ".aws" / "config"
    profile_configured = _has_aws_profile(config_path, AWS_PROFILE)
    authenticated = False
    session_status = "not_checked"
    if not aws_cli:
        session_status = "cli_missing"
    elif not profile_configured:
        session_status = "profile_missing"
    elif verify_session:
        authenticated, session_status = _verify_aws_session(
            aws_cli,
            project_dir=project_dir,
            environment=environment,
        )
    return {
        "profile": AWS_PROFILE,
        "region": AWS_REGION,
        "cli_installed": bool(aws_cli),
        "profile_configured": profile_configured,
        "authenticated": authenticated,
        "session_status": session_status,
    }


def _resolve_aws_cli(home_dir: Path, environment: dict[str, str]) -> str:
    executable = shutil.which("aws", path=environment.get("PATH"))
    if executable:
        return executable
    user_install = home_dir / "AppData" / "Local" / "Programs" / "Amazon" / "AWSCLIV2" / "aws.exe"
    return str(user_install) if user_install.exists() else ""


def _has_aws_profile(config_path: Path, profile: str) -> bool:
    try:
        content = config_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    pattern = rf"(?im)^\s*\[(?:profile\s+)?{re.escape(profile)}\]\s*$"
    return re.search(pattern, content) is not None


def _verify_aws_session(
    aws_cli: str,
    *,
    project_dir: Path,
    environment: dict[str, str],
) -> tuple[bool, str]:
    command_environment = dict(environment)
    command_environment.update(
        {
            "AWS_CLI_AUTO_PROMPT": "off",
            "AWS_EC2_METADATA_DISABLED": "true",
        }
    )
    try:
        completed = subprocess.run(
            [
                aws_cli,
                "sts",
                "get-caller-identity",
                "--profile",
                AWS_PROFILE,
                "--region",
                AWS_REGION,
                "--query",
                "Arn",
                "--output",
                "text",
                "--no-cli-pager",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=4,
            env=command_environment,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except OSError:
        return False, "check_failed"
    if completed.returncode != 0:
        return False, "login_required"
    if str(completed.stdout or "").strip().endswith(f":user/{AWS_PROFILE}"):
        return True, "authenticated"
    return False, "unexpected_principal"


def _evidence_status(project_dir: Path) -> dict:
    config_dir = project_dir / "config" / "aws"
    configuration_ready = all(
        (config_dir / name).exists()
        for name in (
            "voc-qa-bucket-policy.json",
            "voc-qa-lifecycle.json",
            "voc-qa-operator-policy.json",
        )
    )
    manifests = sorted(
        (project_dir / "reports" / "voc_quality_runs").glob("*/evidence/aws_s3_manifest.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    latest = {}
    if manifests:
        try:
            payload = json.loads(manifests[0].read_text(encoding="utf-8"))
            latest = {
                "run_id": str(payload.get("run_id") or manifests[0].parents[1].name),
                "generated_at_utc": str(payload.get("generated_at_utc") or ""),
                "file_count": len(payload.get("files") or []),
            }
        except (OSError, json.JSONDecodeError):
            latest = {"run_id": manifests[0].parents[1].name, "generated_at_utc": "", "file_count": 0}
    return {
        "configuration_ready": configuration_ready,
        "upload_count": len(manifests),
        "latest": latest,
    }


def _latest_voc_status(project_dir: Path) -> dict:
    runs_dir = project_dir / "reports" / "voc_quality_runs"
    if project_dir == PROJECT_DIR:
        runs_dir = VOC_QUALITY_RUNS_DIR
    summaries = []
    for path in runs_dir.glob("*/summary.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        payload["_mtime"] = path.stat().st_mtime
        summaries.append(payload)
    if not summaries:
        return {"available": False}
    latest = max(
        summaries,
        key=lambda item: (str(item.get("finished_at") or ""), float(item.get("_mtime") or 0)),
    )
    counts = latest.get("counts") or {}
    attention_count = sum(
        int(counts.get(status) or 0)
        for status in ("FAIL", "ERROR", "REVIEW_REQUIRED", "NOT_RUN")
    )
    return {
        "available": True,
        "run_id": str(latest.get("run_id") or ""),
        "status": str(latest.get("status") or "UNKNOWN"),
        "finished_at": str(latest.get("finished_at") or ""),
        "pass_count": int(counts.get("PASS") or 0),
        "attention_count": attention_count,
        "deployment_decision": str(latest.get("deployment_decision") or "NOT_VERIFIED"),
    }
