import io
import os
import re
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from core.paths import PROJECT_DIR


GITHUB_HTTPS_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?$",
    re.IGNORECASE,
)
GITHUB_SSH_PATTERN = re.compile(
    r"^git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EXCLUDED_LANGUAGE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "htmlcov",
    "node_modules",
}
EXCLUDED_LANGUAGE_FILE_PARTS = {
    "voc_quality_runtime\\Runs",
    "voc_quality_runtime/Runs",
}
LANGUAGE_BY_EXTENSION = {
    ".py": "Python",
    ".ps1": "PowerShell",
    ".psm1": "PowerShell",
    ".sh": "Shell",
    ".bat": "Batchfile",
    ".cmd": "Batchfile",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".jsonl": "JSON",
    ".md": "Markdown",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".sql": "SQL",
    ".dockerfile": "Dockerfile",
}
ARCHIVE_EXCLUDED_DIRS = EXCLUDED_LANGUAGE_DIRS | {
    ".streamlit",
    "RubricHistory",
    "voc_quality_runtime/Runs",
    "voc_quality_runtime\\Runs",
}
ARCHIVE_SECRET_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    "secrets.toml",
}


def run_git(arguments, *, project_dir=PROJECT_DIR, timeout=10):
    git_executable = shutil.which("git")
    if not git_executable:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": "Git 실행 파일을 찾을 수 없습니다.",
            "command": ["git", *arguments],
        }

    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            [git_executable, *arguments],
            cwd=Path(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "command": ["git", *arguments],
        }

    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "command": ["git", *arguments],
    }


def collect_git_environment(project_dir=PROJECT_DIR):
    git_executable = shutil.which("git")
    if not git_executable:
        return {
            "git_installed": False,
            "git_executable": "",
            "git_version": "",
            "is_repository": False,
            "repository_root": "",
            "user_name": "",
            "user_email": "",
            "local_user_name": "",
            "local_user_email": "",
            "remote_url": "",
            "branch": "",
            "credential_helper": "",
            "changed_files": [],
            "recent_commits": [],
            "token_available": token_available(),
        }

    version = run_git(["--version"], project_dir=project_dir)
    repository_check = run_git(
        ["rev-parse", "--is-inside-work-tree"],
        project_dir=project_dir,
    )
    is_repository = repository_check["ok"] and repository_check["stdout"] == "true"

    snapshot = {
        "git_installed": True,
        "git_executable": git_executable,
        "git_version": version["stdout"],
        "is_repository": is_repository,
        "repository_root": "",
        "user_name": "",
        "user_email": "",
        "local_user_name": "",
        "local_user_email": "",
        "remote_url": "",
        "branch": "",
        "credential_helper": _config_value(
            ["config", "--get", "credential.helper"],
            project_dir,
        ),
        "changed_files": [],
        "recent_commits": [],
        "token_available": token_available(),
    }
    if not is_repository:
        snapshot["user_name"] = _config_value(
            ["config", "--global", "--get", "user.name"],
            project_dir,
        )
        snapshot["user_email"] = _config_value(
            ["config", "--global", "--get", "user.email"],
            project_dir,
        )
        return snapshot

    snapshot.update(
        {
            "repository_root": _config_value(
                ["rev-parse", "--show-toplevel"],
                project_dir,
            ),
            "user_name": _config_value(
                ["config", "--get", "user.name"],
                project_dir,
            ),
            "user_email": _config_value(
                ["config", "--get", "user.email"],
                project_dir,
            ),
            "local_user_name": _config_value(
                ["config", "--local", "--get", "user.name"],
                project_dir,
            ),
            "local_user_email": _config_value(
                ["config", "--local", "--get", "user.email"],
                project_dir,
            ),
            "remote_url": _config_value(
                ["remote", "get-url", "origin"],
                project_dir,
            ),
            "branch": _config_value(
                ["branch", "--show-current"],
                project_dir,
            ),
            "changed_files": _output_lines(
                run_git(["status", "--short"], project_dir=project_dir)
            ),
            "recent_commits": _output_lines(
                run_git(
                    ["log", "-5", "--pretty=format:%h|%ad|%an|%s", "--date=short"],
                    project_dir=project_dir,
                )
            ),
        }
    )
    return snapshot


def collect_repository_home(project_dir=PROJECT_DIR, *, max_files=80):
    snapshot = collect_git_environment(project_dir)
    project_dir = Path(project_dir)
    repository_root = Path(snapshot["repository_root"] or project_dir)

    snapshot.update(
        {
            "owner": "",
            "repo_name": repository_root.name,
            "branches": [],
            "tags": [],
            "file_entries": [],
            "status_entries": [],
            "contributors": [],
            "language_stats": [],
            "readme_text": "",
            "readme_path": "",
            "latest_commit": {},
            "ahead_behind": {"ahead": 0, "behind": 0, "label": ""},
            "is_github_remote": is_github_remote_url(snapshot["remote_url"]),
        }
    )

    owner, repo_name = parse_github_remote(snapshot["remote_url"])
    if owner:
        snapshot["owner"] = owner
    if repo_name:
        snapshot["repo_name"] = repo_name

    if not snapshot["git_installed"] or not snapshot["is_repository"]:
        return snapshot

    snapshot["branches"] = _output_lines(
        run_git(["branch", "--format=%(refname:short)"], project_dir=project_dir)
    )
    snapshot["tags"] = _output_lines(
        run_git(["tag", "--sort=-creatordate"], project_dir=project_dir)
    )
    snapshot["status_entries"] = parse_status_entries(snapshot["changed_files"])
    snapshot["file_entries"] = collect_root_file_entries(repository_root, max_files=max_files)
    snapshot["contributors"] = collect_contributors(project_dir)
    snapshot["language_stats"] = collect_language_stats(repository_root)
    snapshot["readme_path"], snapshot["readme_text"] = read_readme(repository_root)
    snapshot["latest_commit"] = latest_commit(project_dir)
    snapshot["ahead_behind"] = collect_ahead_behind(project_dir, snapshot["branch"])
    return snapshot


def parse_github_remote(remote_url):
    value = str(remote_url or "").strip()
    if not value:
        return "", ""
    if value.startswith("git@github.com:"):
        repo_path = value.split(":", 1)[1]
    else:
        parsed = urlparse(value)
        if parsed.hostname != "github.com":
            return "", ""
        repo_path = parsed.path.strip("/")
    parts = repo_path.removesuffix(".git").strip("/").split("/")
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def parse_status_entries(changed_files):
    entries = []
    for raw in changed_files:
        status_code = raw[:2].strip() or "?"
        path = raw[3:].strip() if len(raw) > 3 else raw.strip()
        entries.append(
            {
                "status": status_code,
                "label": status_label(status_code),
                "path": path,
            }
        )
    return entries


def status_label(status_code):
    code = str(status_code or "?")
    if "?" in code:
        return "추가 전"
    if "A" in code:
        return "추가"
    if "M" in code:
        return "수정"
    if "D" in code:
        return "삭제"
    if "R" in code:
        return "이름 변경"
    if "C" in code:
        return "복사"
    return "변경"


def collect_root_file_entries(repository_root, *, max_files=80):
    entries = []
    root = Path(repository_root)
    if not root.exists():
        return entries
    for item in sorted(root.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower())):
        if item.name in {".git", ".venv", "__pycache__"}:
            continue
        try:
            stat = item.stat()
        except OSError:
            continue
        relative_path = item.name
        last_change = run_git(
            ["log", "-1", "--pretty=format:%s|%cr", "--", relative_path],
            project_dir=root,
            timeout=5,
        )
        commit_message = "아직 커밋 기록 없음"
        commit_age = "방금 전"
        if last_change["ok"] and last_change["stdout"]:
            parts = last_change["stdout"].split("|", 1)
            commit_message = parts[0] if parts else commit_message
            commit_age = parts[1] if len(parts) > 1 else commit_age
        entries.append(
            {
                "type": "dir" if item.is_dir() else "file",
                "name": item.name,
                "path": relative_path,
                "commit_message": commit_message,
                "age": commit_age,
                "size": stat.st_size,
            }
        )
        if len(entries) >= max_files:
            break
    return entries


def collect_contributors(project_dir=PROJECT_DIR):
    result = run_git(
        ["shortlog", "-sne", "--all"],
        project_dir=project_dir,
        timeout=10,
    )
    rows = []
    for line in _output_lines(result):
        match = re.match(r"\s*(\d+)\s+(.+?)(?:\s+<([^>]+)>)?\s*$", line)
        if not match:
            continue
        rows.append(
            {
                "commits": int(match.group(1)),
                "name": match.group(2).strip(),
                "email": match.group(3) or "",
            }
        )
    return rows


def collect_language_stats(repository_root):
    root = Path(repository_root)
    totals = {}
    total_bytes = 0
    if not root.exists():
        return []
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [directory for directory in dirs if directory not in EXCLUDED_LANGUAGE_DIRS]
        for filename in files:
            path = Path(current_root) / filename
            relative = str(path.relative_to(root))
            if any(part in relative for part in EXCLUDED_LANGUAGE_FILE_PARTS):
                continue
            extension = path.suffix.lower()
            if filename.lower() == "dockerfile":
                extension = ".dockerfile"
            language = LANGUAGE_BY_EXTENSION.get(extension)
            if not language:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            totals[language] = totals.get(language, 0) + size
            total_bytes += size
    if total_bytes <= 0:
        return []
    return [
        {
            "language": language,
            "bytes": size,
            "percent": round((size / total_bytes) * 100, 1),
        }
        for language, size in sorted(totals.items(), key=lambda item: item[1], reverse=True)
    ]


def read_readme(repository_root):
    root = Path(repository_root)
    for candidate in ("README.md", "README.MD", "readme.md"):
        path = root / candidate
        if path.exists():
            try:
                return candidate, path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return candidate, ""
    return "", ""


def latest_commit(project_dir=PROJECT_DIR):
    result = run_git(
        ["log", "-1", "--pretty=format:%h|%H|%cr|%an|%s"],
        project_dir=project_dir,
        timeout=10,
    )
    if not result["ok"] or not result["stdout"]:
        return {}
    parts = result["stdout"].split("|", 4)
    if len(parts) != 5:
        return {}
    return {
        "short_hash": parts[0],
        "hash": parts[1],
        "age": parts[2],
        "author": parts[3],
        "message": parts[4],
    }


def collect_ahead_behind(project_dir, branch):
    if not branch:
        return {"ahead": 0, "behind": 0, "label": ""}
    upstream = run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        project_dir=project_dir,
        timeout=5,
    )
    if not upstream["ok"] or not upstream["stdout"]:
        return {"ahead": 0, "behind": 0, "label": "upstream 미설정"}
    counts = run_git(
        ["rev-list", "--left-right", "--count", f"{upstream['stdout']}...HEAD"],
        project_dir=project_dir,
        timeout=10,
    )
    if not counts["ok"] or not counts["stdout"]:
        return {"ahead": 0, "behind": 0, "label": upstream["stdout"]}
    try:
        behind, ahead = [int(part) for part in counts["stdout"].split()]
    except (TypeError, ValueError):
        ahead, behind = 0, 0
    return {"ahead": ahead, "behind": behind, "label": upstream["stdout"]}


def create_commit(message, project_dir=PROJECT_DIR):
    if not str(message).strip():
        return {"ok": False, "message": "커밋 메시지를 입력하세요.", "detail": ""}
    snapshot = collect_git_environment(project_dir)
    if not snapshot["is_repository"]:
        return {"ok": False, "message": "Git 저장소가 아닙니다.", "detail": ""}
    if not snapshot["changed_files"]:
        return {"ok": False, "message": "커밋할 변경사항이 없습니다.", "detail": ""}
    if not snapshot["user_name"] or not snapshot["user_email"]:
        return {"ok": False, "message": "커밋 사용자 이름과 이메일을 먼저 등록하세요.", "detail": ""}

    add_result = run_git(["add", "-A"], project_dir=project_dir, timeout=20)
    if not add_result["ok"]:
        return {
            "ok": False,
            "message": "변경사항을 스테이징하지 못했습니다.",
            "detail": add_result["stderr"] or add_result["stdout"],
        }
    commit_result = run_git(["commit", "-m", message.strip()], project_dir=project_dir, timeout=30)
    if commit_result["ok"]:
        return {
            "ok": True,
            "message": "커밋을 생성했습니다.",
            "detail": commit_result["stdout"],
        }
    return {
        "ok": False,
        "message": "커밋 생성에 실패했습니다.",
        "detail": commit_result["stderr"] or commit_result["stdout"],
    }


def fetch_origin(project_dir=PROJECT_DIR):
    return _git_action_message(
        run_git(["fetch", "origin", "--prune"], project_dir=project_dir, timeout=45),
        success="origin 최신 정보를 가져왔습니다.",
        failure="origin fetch에 실패했습니다.",
    )


def pull_current_branch(project_dir=PROJECT_DIR):
    return _git_action_message(
        run_git(["pull", "--ff-only"], project_dir=project_dir, timeout=60),
        success="현재 브랜치를 fast-forward 방식으로 갱신했습니다.",
        failure="pull에 실패했습니다. 로컬 변경 또는 원격 이력을 확인하세요.",
    )


def push_current_branch(project_dir=PROJECT_DIR):
    snapshot = collect_git_environment(project_dir)
    if not snapshot["branch"]:
        return {"ok": False, "message": "현재 브랜치를 확인할 수 없습니다.", "detail": ""}
    result = run_git(
        ["push", "-u", "origin", snapshot["branch"]],
        project_dir=project_dir,
        timeout=60,
    )
    return _git_action_message(
        result,
        success=f"{snapshot['branch']} 브랜치를 origin에 push했습니다.",
        failure="push에 실패했습니다. 인증 또는 원격 이력을 확인하세요.",
    )


def save_project_to_github(message, project_dir=PROJECT_DIR):
    snapshot = collect_repository_home(project_dir)
    if not snapshot["git_installed"]:
        return {"ok": False, "message": "Git이 설치되어 있지 않습니다.", "detail": ""}
    if not snapshot["is_repository"]:
        return {"ok": False, "message": "현재 폴더가 Git 저장소가 아닙니다.", "detail": ""}
    if not snapshot["remote_url"]:
        return {"ok": False, "message": "origin 원격 저장소가 등록되어 있지 않습니다.", "detail": ""}

    details = []
    if snapshot["changed_files"]:
        commit_result = create_commit(message, project_dir=project_dir)
        details.append(f"[commit] {commit_result['message']}\n{commit_result.get('detail', '')}".strip())
        if not commit_result["ok"]:
            return {
                "ok": False,
                "message": commit_result["message"],
                "detail": "\n\n".join(details),
            }
    elif snapshot["ahead_behind"]["ahead"] <= 0:
        return {
            "ok": True,
            "message": "저장할 변경사항이 없습니다. GitHub와 동기화할 새 커밋도 없습니다.",
            "detail": "",
        }

    push_result = push_current_branch(project_dir=project_dir)
    details.append(f"[push] {push_result['message']}\n{push_result.get('detail', '')}".strip())
    return {
        "ok": push_result["ok"],
        "message": (
            "현재 프로젝트 변경사항을 GitHub에 저장했습니다."
            if push_result["ok"]
            else push_result["message"]
        ),
        "detail": "\n\n".join(details),
    }


def download_project_from_github(project_dir=PROJECT_DIR):
    snapshot = collect_git_environment(project_dir)
    if not snapshot["git_installed"]:
        return {"ok": False, "message": "Git이 설치되어 있지 않습니다.", "detail": ""}
    if not snapshot["is_repository"]:
        return {"ok": False, "message": "현재 폴더가 Git 저장소가 아닙니다.", "detail": ""}
    if not snapshot["remote_url"]:
        return {"ok": False, "message": "origin 원격 저장소가 등록되어 있지 않습니다.", "detail": ""}
    if snapshot["changed_files"]:
        return {
            "ok": False,
            "message": "로컬 변경사항이 있어 다운로드를 중단했습니다.",
            "detail": "먼저 Git 저장으로 현재 변경사항을 커밋·push하거나, 변경사항을 별도로 정리한 뒤 Git 다운로드를 실행하세요.",
        }

    fetch_result = fetch_origin(project_dir=project_dir)
    pull_result = pull_current_branch(project_dir=project_dir)
    return {
        "ok": fetch_result["ok"] and pull_result["ok"],
        "message": (
            "GitHub의 최신 변경사항을 현재 프로젝트에 다운로드했습니다."
            if fetch_result["ok"] and pull_result["ok"]
            else pull_result["message"] if not pull_result["ok"] else fetch_result["message"]
        ),
        "detail": "\n\n".join(
            [
                f"[fetch] {fetch_result['message']}\n{fetch_result.get('detail', '')}".strip(),
                f"[pull] {pull_result['message']}\n{pull_result.get('detail', '')}".strip(),
            ]
        ),
    }


def create_branch(branch_name, project_dir=PROJECT_DIR):
    branch_name = str(branch_name or "").strip()
    if not branch_name:
        return {"ok": False, "message": "생성할 브랜치 이름을 입력하세요.", "detail": ""}
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch_name):
        return {
            "ok": False,
            "message": "브랜치 이름은 영문, 숫자, /, -, _, . 만 사용할 수 있습니다.",
            "detail": "",
        }
    result = run_git(["switch", "-c", branch_name], project_dir=project_dir, timeout=20)
    return _git_action_message(
        result,
        success=f"{branch_name} 브랜치를 생성하고 전환했습니다.",
        failure="브랜치 생성에 실패했습니다.",
    )


def clone_repository(remote_url, target_directory, project_dir=PROJECT_DIR):
    remote_url = str(remote_url or "").strip()
    target_directory = str(target_directory or "").strip()
    if not remote_url:
        return {"ok": False, "message": "Clone할 GitHub 원격 주소가 없습니다.", "detail": ""}
    if not target_directory:
        return {"ok": False, "message": "Clone 대상 폴더를 입력하세요.", "detail": ""}

    snapshot = collect_git_environment(project_dir)
    repository_root = Path(snapshot["repository_root"] or project_dir).resolve()
    target_path = Path(target_directory).expanduser()
    if not target_path.is_absolute():
        target_path = (repository_root.parent / target_path).resolve()
    else:
        target_path = target_path.resolve()

    if target_path == repository_root or repository_root in target_path.parents:
        return {
            "ok": False,
            "message": "현재 프로젝트 폴더 안에는 Clone을 수행하지 않습니다.",
            "detail": "중첩 Git 저장소가 생기면 현재 프로젝트 관리가 혼란스러워질 수 있습니다. 프로젝트와 같은 상위 폴더의 새 폴더를 지정하세요.",
        }

    parent = target_path.parent
    if not parent.exists():
        return {
            "ok": False,
            "message": "Clone 대상의 상위 폴더가 존재하지 않습니다.",
            "detail": str(parent),
        }
    if target_path.exists() and any(target_path.iterdir()):
        return {
            "ok": False,
            "message": "Clone 대상 폴더가 비어 있지 않습니다.",
            "detail": str(target_path),
        }

    result = run_git(
        ["clone", remote_url, str(target_path)],
        project_dir=parent,
        timeout=120,
    )
    return _git_action_message(
        result,
        success=f"GitHub 저장소를 Clone했습니다: {target_path}",
        failure="Clone 수행에 실패했습니다. 원격 주소, 인증, 대상 폴더를 확인하세요.",
    )


def build_project_source_archive(project_dir=PROJECT_DIR):
    root = Path(project_dir).resolve()
    snapshot = collect_git_environment(root)
    repo_name = Path(snapshot["repository_root"] or root).name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{repo_name}_source_{stamp}.zip"
    buffer = io.BytesIO()
    included_count = 0

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            relative_text = str(relative).replace("\\", "/")
            if _should_exclude_from_archive(relative_text, path.name):
                continue
            try:
                archive.write(path, relative_text)
                included_count += 1
            except OSError:
                continue

    buffer.seek(0)
    return {
        "ok": included_count > 0,
        "message": f"프로젝트 소스 ZIP을 준비했습니다. 포함 파일 {included_count}개",
        "filename": filename,
        "data": buffer.getvalue(),
        "included_count": included_count,
    }


def readiness_checks(snapshot):
    return [
        {
            "item": "Git 설치",
            "ready": snapshot["git_installed"],
            "detail": snapshot["git_version"] or "Git을 먼저 설치하세요.",
        },
        {
            "item": "저장소",
            "ready": snapshot["is_repository"],
            "detail": snapshot["repository_root"] or "저장소 초기화가 필요합니다.",
        },
        {
            "item": "사용자 정보",
            "ready": bool(snapshot["user_name"] and snapshot["user_email"]),
            "detail": (
                f"{snapshot['user_name']} <{snapshot['user_email']}>"
                if snapshot["user_name"] and snapshot["user_email"]
                else "이름과 이메일을 등록하세요."
            ),
        },
        {
            "item": "원격 저장소",
            "ready": bool(snapshot["remote_url"]),
            "detail": snapshot["remote_url"] or "origin 주소를 등록하세요.",
        },
    ]


def configure_repository(
    user_name,
    user_email,
    remote_url,
    *,
    initialize=False,
    project_dir=PROJECT_DIR,
):
    project_dir = Path(project_dir)
    validation_error = validate_git_settings(user_name, user_email, remote_url)
    if validation_error:
        return {"ok": False, "message": validation_error, "steps": []}

    snapshot = collect_git_environment(project_dir)
    if not snapshot["git_installed"]:
        return {
            "ok": False,
            "message": "Git이 설치되어 있지 않아 환경을 등록할 수 없습니다.",
            "steps": [],
        }

    steps = []
    if not snapshot["is_repository"]:
        if not initialize:
            return {
                "ok": False,
                "message": "Git 저장소가 아닙니다. 저장소 초기화에 동의해 주세요.",
                "steps": [],
            }
        init_result = run_git(["init"], project_dir=project_dir)
        steps.append(_step_result("Git 저장소 초기화", init_result))
        if not init_result["ok"]:
            return _configuration_failure(steps)
        branch_result = run_git(
            ["symbolic-ref", "HEAD", "refs/heads/main"],
            project_dir=project_dir,
        )
        steps.append(_step_result("기본 브랜치 main 설정", branch_result))
        if not branch_result["ok"]:
            return _configuration_failure(steps)

    for label, arguments in (
        ("사용자 이름 등록", ["config", "--local", "user.name", user_name.strip()]),
        ("사용자 이메일 등록", ["config", "--local", "user.email", user_email.strip()]),
    ):
        result = run_git(arguments, project_dir=project_dir)
        steps.append(_step_result(label, result))
        if not result["ok"]:
            return _configuration_failure(steps)

    current_remote = run_git(["remote", "get-url", "origin"], project_dir=project_dir)
    remote_arguments = (
        ["remote", "set-url", "origin", remote_url.strip()]
        if current_remote["ok"]
        else ["remote", "add", "origin", remote_url.strip()]
    )
    remote_result = run_git(remote_arguments, project_dir=project_dir)
    steps.append(_step_result("origin 원격 저장소 등록", remote_result))
    if not remote_result["ok"]:
        return _configuration_failure(steps)

    return {
        "ok": True,
        "message": "이 프로젝트의 Git 환경 등록을 완료했습니다.",
        "steps": steps,
    }


def verify_remote_connection(project_dir=PROJECT_DIR):
    snapshot = collect_git_environment(project_dir)
    if not snapshot["is_repository"]:
        return {
            "ok": False,
            "message": "먼저 Git 저장소를 초기화하세요.",
            "detail": "",
        }
    if not snapshot["remote_url"]:
        return {
            "ok": False,
            "message": "먼저 origin 원격 저장소를 등록하세요.",
            "detail": "",
        }

    result = run_git(
        ["ls-remote", "--heads", "origin"],
        project_dir=project_dir,
        timeout=15,
    )
    if result["ok"]:
        branch_count = len(_output_lines(result))
        return {
            "ok": True,
            "message": f"GitHub 연결을 확인했습니다. 원격 브랜치 {branch_count}개를 조회했습니다.",
            "detail": "",
        }
    return {
        "ok": False,
        "message": "GitHub 원격 저장소에 연결하지 못했습니다.",
        "detail": result["stderr"] or result["stdout"],
    }


def validate_git_settings(user_name, user_email, remote_url):
    if not str(user_name).strip():
        return "사용자 이름을 입력하세요."
    if not EMAIL_PATTERN.fullmatch(str(user_email).strip()):
        return "올바른 이메일 주소를 입력하세요."
    if not is_github_remote_url(remote_url):
        return (
            "GitHub 저장소 주소는 https://github.com/소유자/저장소.git 또는 "
            "git@github.com:소유자/저장소.git 형식이어야 합니다."
        )
    return ""


def is_github_remote_url(remote_url):
    value = str(remote_url).strip()
    if GITHUB_HTTPS_PATTERN.fullmatch(value) or GITHUB_SSH_PATTERN.fullmatch(value):
        return True
    parsed = urlparse(value)
    return (
        parsed.scheme == "ssh"
        and parsed.hostname == "github.com"
        and len(parsed.path.strip("/").split("/")) == 2
    )


def token_available():
    return bool(os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))


def _config_value(arguments, project_dir):
    result = run_git(arguments, project_dir=project_dir)
    return result["stdout"] if result["ok"] else ""


def _output_lines(result):
    if not result["ok"] or not result["stdout"]:
        return []
    return [line for line in result["stdout"].splitlines() if line.strip()]


def _step_result(label, result):
    return {
        "step": label,
        "ok": result["ok"],
        "detail": result["stderr"] or result["stdout"],
    }


def _configuration_failure(steps):
    failed_step = next((step for step in reversed(steps) if not step["ok"]), None)
    detail = failed_step["detail"] if failed_step else ""
    return {
        "ok": False,
        "message": f"Git 환경 등록 중 오류가 발생했습니다. {detail}".strip(),
        "steps": steps,
    }


def _should_exclude_from_archive(relative_text, filename):
    normalized = relative_text.replace("\\", "/")
    parts = normalized.split("/")
    if any(part in ARCHIVE_EXCLUDED_DIRS for part in parts):
        return True
    if filename in ARCHIVE_SECRET_FILENAMES:
        return True
    if filename.startswith(".env") and filename != ".env.example":
        return True
    if normalized == ".streamlit/secrets.toml" or normalized.endswith("/secrets.toml"):
        return True
    excluded_prefixes = (
        "voc_quality_runtime/Runs/",
        "voc_quality_runtime/quality_diagnosis/RubricHistory/",
    )
    return any(normalized.startswith(prefix) for prefix in excluded_prefixes)


def _git_action_message(result, *, success, failure):
    return {
        "ok": result["ok"],
        "message": success if result["ok"] else failure,
        "detail": result["stderr"] or result["stdout"],
    }
