import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from core.paths import K6_RUNS_DIR, PROJECT_DIR


ACTIVE_RUN_FILE = K6_RUNS_DIR / "_active_run.json"
START_LOCK_FILE = K6_RUNS_DIR / "_start.lock"
WORKER_SCRIPT = Path(__file__).with_name("k6_worker.py")
ACTIVE_STATUSES = {"STARTING", "RUNNING", "STOPPING"}
FINAL_STATUSES = {"PASS", "FAIL", "ERROR", "STOPPED"}


@dataclass
class K6RunSettings:
    target_url: str
    vus: int = 10
    duration_seconds: int = 60
    ramp_up_seconds: int = 10
    p95_threshold_ms: int = 3000
    failure_rate_threshold_pct: float = 1.0
    checks_threshold_pct: float = 95.0
    think_time_seconds: float = 1.0


def get_k6_executable():
    return shutil.which("k6")


def get_k6_version():
    executable = get_k6_executable()
    if not executable:
        return ""

    try:
        completed = subprocess.run(
            [executable, "version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""

    return (completed.stdout or completed.stderr or "").strip()


def is_k6_available():
    return bool(get_k6_executable())


def start_k6_test_background(settings):
    validate_settings(settings)
    executable = get_k6_executable()
    if not executable:
        return {
            "ok": False,
            "error": "k6 실행 파일을 찾을 수 없습니다. k6를 설치한 뒤 다시 실행해주세요.",
            "settings": asdict(settings),
        }

    K6_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    lock_fd = _acquire_start_lock()
    if lock_fd is None:
        return {"ok": False, "error": "다른 k6 실행 요청을 처리 중입니다. 잠시 후 다시 시도해주세요."}

    record_path = None
    run_id = None
    try:
        active = get_active_k6_run()
        if active:
            return {
                "ok": False,
                "error": f"이미 k6 테스트가 실행 중입니다. Run ID: {active.get('run_id', '-')}",
                "active_run": active,
            }

        run_id = _new_run_id()
        run_dir = K6_RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        script_path = run_dir / "script.js"
        summary_path = run_dir / "summary.json"
        record_path = run_dir / "run_record.json"
        worker_log_path = run_dir / "worker.log"
        script_path.write_text(build_k6_script(settings), encoding="utf-8")

        now = datetime.now().isoformat(timespec="seconds")
        record = {
            "run_id": run_id,
            "created_at": now,
            "started_at": now,
            "finished_at": None,
            "updated_at": now,
            "status": "STARTING",
            "worker_pid": None,
            "settings": asdict(settings),
            "return_code": None,
            "summary_path": str(summary_path),
            "script_path": str(script_path),
            "worker_log_path": str(worker_log_path),
            "stdout": "",
            "stderr": "",
            "summary": {},
            "raw_summary": {},
        }
        write_json(record_path, record)
        write_json(ACTIVE_RUN_FILE, record)

        worker_log = worker_log_path.open("a", encoding="utf-8")
        popen_kwargs = {
            "cwd": str(PROJECT_DIR),
            "stdin": subprocess.DEVNULL,
            "stdout": worker_log,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            popen_kwargs["start_new_session"] = True

        try:
            process = subprocess.Popen(
                [sys.executable, str(WORKER_SCRIPT), run_id],
                **popen_kwargs,
            )
        finally:
            worker_log.close()

        record.update(
            {
                "status": "RUNNING",
                "worker_pid": process.pid,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        write_json(record_path, record)
        write_json(ACTIVE_RUN_FILE, record)
        return {**record, "ok": True, "error": ""}
    except (OSError, ValueError) as exc:
        if record_path and run_id:
            record = load_json(record_path)
            record.update(
                {
                    "status": "ERROR",
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                    "error": str(exc),
                }
            )
            write_json(record_path, record)
            _clear_active_run(run_id)
        return {"ok": False, "error": str(exc), "run_id": run_id}
    finally:
        _release_start_lock(lock_fd)


def run_k6_worker(run_id):
    if not _valid_run_id(run_id):
        return 2
    record_path = K6_RUNS_DIR / run_id / "run_record.json"
    record = load_json(record_path)
    if not record:
        return 2

    current = load_json(ACTIVE_RUN_FILE)
    if current.get("run_id") != run_id or current.get("status") == "STOPPED":
        return 3

    now = datetime.now().isoformat(timespec="seconds")
    record.update(
        {
            "status": "RUNNING",
            "worker_pid": os.getpid(),
            "started_at": record.get("started_at") or now,
            "updated_at": now,
        }
    )
    write_json(record_path, record)
    write_json(ACTIVE_RUN_FILE, record)

    try:
        settings = K6RunSettings(**record["settings"])
        result = run_k6_test(
            settings,
            run_id=run_id,
            created_at=record.get("created_at"),
            started_at=record.get("started_at"),
            worker_pid=os.getpid(),
            worker_log_path=record.get("worker_log_path"),
        )
        return 0 if result.get("ok") else 1
    except Exception as exc:  # worker must always leave a durable terminal record
        failed = load_json(record_path) or record
        failed.update(
            {
                "status": "ERROR",
                "finished_at": datetime.now().isoformat(timespec="seconds"),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "error": str(exc),
                "stderr": str(exc),
            }
        )
        write_json(record_path, failed)
        return 1
    finally:
        _clear_active_run(run_id)


def run_k6_test(
    settings,
    run_id=None,
    created_at=None,
    started_at=None,
    worker_pid=None,
    worker_log_path=None,
):
    validate_settings(settings)
    executable = get_k6_executable()
    if not executable:
        return {
            "ok": False,
            "error": "k6 실행 파일을 찾을 수 없습니다. k6를 설치한 뒤 다시 실행해주세요.",
            "settings": asdict(settings),
        }

    run_id = run_id or _new_run_id()
    run_dir = K6_RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    script_path = run_dir / "script.js"
    summary_path = run_dir / "summary.json"
    record_path = run_dir / "run_record.json"
    script_path.write_text(build_k6_script(settings), encoding="utf-8")

    timeout_seconds = max(settings.duration_seconds + settings.ramp_up_seconds + 90, 120)
    command = [
        executable,
        "run",
        "--summary-export",
        str(summary_path),
        str(script_path),
    ]

    run_kwargs = {}
    if os.name == "nt":
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            **run_kwargs,
        )
    except subprocess.TimeoutExpired as exc:
        record = build_run_record(
            run_id,
            settings,
            summary_path,
            script_path,
            return_code=-1,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + "\nk6 실행 시간이 초과되었습니다.",
            status="ERROR",
            created_at=created_at,
            started_at=started_at,
            worker_pid=worker_pid,
            worker_log_path=worker_log_path,
        )
        write_json(record_path, record)
        return {**record, "ok": False, "error": "k6 실행 시간이 초과되었습니다."}
    except OSError as exc:
        record = build_run_record(
            run_id,
            settings,
            summary_path,
            script_path,
            return_code=-1,
            stdout="",
            stderr=str(exc),
            status="ERROR",
            created_at=created_at,
            started_at=started_at,
            worker_pid=worker_pid,
            worker_log_path=worker_log_path,
        )
        write_json(record_path, record)
        return {**record, "ok": False, "error": str(exc)}

    raw_summary = load_json(summary_path)
    normalized = normalize_k6_summary(raw_summary)
    record = build_run_record(
        run_id,
        settings,
        summary_path,
        script_path,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        normalized=normalized,
        raw_summary=raw_summary,
        status="PASS" if completed.returncode == 0 else "FAIL",
        created_at=created_at,
        started_at=started_at,
        worker_pid=worker_pid,
        worker_log_path=worker_log_path,
    )
    write_json(record_path, record)
    save_latest_summary(raw_summary, record)

    return {
        **record,
        "ok": completed.returncode == 0,
        "error": "" if completed.returncode == 0 else "k6 실행이 실패했습니다. 로그를 확인해주세요.",
    }


def get_active_k6_run():
    active = load_json(ACTIVE_RUN_FILE)
    if not active or active.get("status") not in ACTIVE_STATUSES:
        return {}

    worker_pid = active.get("worker_pid")
    if worker_pid and _process_is_running(worker_pid):
        return active

    if active.get("status") in {"STARTING", "RUNNING"} and _seconds_since(active.get("created_at")) < 15:
        return active

    run_id = active.get("run_id")
    record_path = K6_RUNS_DIR / str(run_id) / "run_record.json"
    record = load_json(record_path) or active
    record.update(
        {
            "status": "ERROR",
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error": "백그라운드 worker가 예기치 않게 종료되었습니다.",
        }
    )
    write_json(record_path, record)
    _clear_active_run(run_id)
    return {}


def stop_k6_test(run_id=None):
    active = load_json(ACTIVE_RUN_FILE)
    if not active or active.get("status") not in ACTIVE_STATUSES:
        return {"ok": False, "error": "실행 중인 k6 테스트가 없습니다."}
    if run_id and active.get("run_id") != run_id:
        return {"ok": False, "error": "요청한 실행 ID가 현재 실행 중인 테스트와 다릅니다."}

    active.update(
        {
            "status": "STOPPING",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    record_path = K6_RUNS_DIR / active["run_id"] / "run_record.json"
    write_json(record_path, active)
    write_json(ACTIVE_RUN_FILE, active)

    worker_pid = active.get("worker_pid")
    terminated = bool(worker_pid and _terminate_process_tree(worker_pid))
    final = load_json(record_path) or active
    final.update(
        {
            "status": "STOPPED",
            "return_code": -2,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "error": "사용자 요청으로 k6 테스트를 중지했습니다.",
        }
    )
    write_json(record_path, final)
    _clear_active_run(active["run_id"])
    return {
        **final,
        "ok": terminated or not worker_pid,
        "error": "" if terminated or not worker_pid else "worker 프로세스를 중지하지 못했습니다.",
    }


def load_k6_run(run_id):
    if not _valid_run_id(str(run_id)):
        return {}
    return load_json(K6_RUNS_DIR / str(run_id) / "run_record.json")


def validate_settings(settings):
    if not settings.target_url:
        raise ValueError("대상 URL을 입력해주세요.")
    if not settings.target_url.startswith(("http://", "https://")):
        raise ValueError("대상 URL은 http:// 또는 https://로 시작해야 합니다.")
    if settings.vus < 1:
        raise ValueError("동시 사용자는 1 이상이어야 합니다.")
    if settings.duration_seconds < 1:
        raise ValueError("테스트 시간은 1초 이상이어야 합니다.")


def build_k6_script(settings):
    stable_duration = max(settings.duration_seconds - settings.ramp_up_seconds, 1)
    if settings.ramp_up_seconds > 0:
        executor_options = f"""
  stages: [
    {{ duration: '{settings.ramp_up_seconds}s', target: {settings.vus} }},
    {{ duration: '{stable_duration}s', target: {settings.vus} }},
    {{ duration: '5s', target: 0 }},
  ],"""
    else:
        executor_options = f"""
  vus: {settings.vus},
  duration: '{settings.duration_seconds}s',"""

    target_url = json.dumps(settings.target_url)
    think_time = json.dumps(float(settings.think_time_seconds))
    failure_rate = settings.failure_rate_threshold_pct / 100
    checks_rate = settings.checks_threshold_pct / 100

    return f"""import http from 'k6/http';
import {{ check, sleep }} from 'k6';

export const options = {{{executor_options}
  thresholds: {{
    http_req_duration: ['p(95)<{settings.p95_threshold_ms}'],
    http_req_failed: ['rate<{failure_rate:.4f}'],
    checks: ['rate>{checks_rate:.4f}'],
  }},
}};

const TARGET_URL = {target_url};

export default function () {{
  const res = http.get(TARGET_URL);
  check(res, {{
    'status is 2xx or 3xx': (r) => r.status >= 200 && r.status < 400,
    'body returned': (r) => r.body !== null && r.body.length >= 0,
  }});
  sleep({think_time});
}}
"""


def build_run_record(
    run_id,
    settings,
    summary_path,
    script_path,
    return_code,
    stdout,
    stderr,
    normalized=None,
    raw_summary=None,
    status=None,
    created_at=None,
    started_at=None,
    worker_pid=None,
    worker_log_path=None,
):
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "run_id": run_id,
        "created_at": created_at or now,
        "started_at": started_at or created_at or now,
        "finished_at": now,
        "updated_at": now,
        "status": status or ("PASS" if return_code == 0 else "FAIL"),
        "worker_pid": worker_pid,
        "settings": asdict(settings),
        "return_code": return_code,
        "summary_path": str(summary_path),
        "script_path": str(script_path),
        "worker_log_path": worker_log_path or "",
        "stdout": stdout[-4000:] if stdout else "",
        "stderr": stderr[-4000:] if stderr else "",
        "summary": normalized or {},
        "raw_summary": raw_summary or {},
    }


def save_latest_summary(raw_summary, record):
    latest_path = PROJECT_DIR / "reports" / "k6_summary.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = raw_summary if raw_summary else {}
    if isinstance(payload, dict):
        payload = {
            **payload,
            "run_id": record["run_id"],
            "created_at": record["created_at"],
            "settings": record["settings"],
            "normalized": record["summary"],
        }
    write_json(latest_path, payload)


def load_recent_runs(limit=10):
    if not K6_RUNS_DIR.exists():
        return []

    records = []
    for record_path in sorted(K6_RUNS_DIR.glob("*/run_record.json"), reverse=True):
        record = load_json(record_path)
        if record:
            records.append(record)
        if len(records) >= limit:
            break
    return records


def _new_run_id():
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base
    suffix = 1
    while (K6_RUNS_DIR / candidate).exists():
        candidate = f"{base}_{suffix:02d}"
        suffix += 1
    return candidate


def _valid_run_id(run_id):
    return bool(re.fullmatch(r"\d{8}_\d{6}(?:_\d{2})?", run_id))


def _acquire_start_lock():
    for attempt in range(2):
        try:
            return os.open(START_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if attempt == 0 and _file_age_seconds(START_LOCK_FILE) > 30:
                START_LOCK_FILE.unlink(missing_ok=True)
                continue
            return None
    return None


def _release_start_lock(lock_fd):
    if lock_fd is None:
        return
    try:
        os.close(lock_fd)
    finally:
        START_LOCK_FILE.unlink(missing_ok=True)


def _clear_active_run(run_id):
    active = load_json(ACTIVE_RUN_FILE)
    if active.get("run_id") == run_id:
        ACTIVE_RUN_FILE.unlink(missing_ok=True)


def _process_is_running(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _terminate_process_tree(pid):
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return completed.returncode == 0
        os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
        return True
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return False


def _seconds_since(value):
    try:
        return max((datetime.now() - datetime.fromisoformat(value)).total_seconds(), 0)
    except (TypeError, ValueError):
        return float("inf")


def _file_age_seconds(path):
    try:
        return max(time.time() - path.stat().st_mtime, 0)
    except OSError:
        return float("inf")


def normalize_k6_summary(summary):
    metrics = summary.get("metrics", {}) if isinstance(summary, dict) else {}
    return {
        "total_requests": metric_value(metrics, "http_reqs", "count"),
        "failure_rate": metric_value(metrics, "http_req_failed", "rate") * 100,
        "avg_duration_seconds": metric_value(metrics, "http_req_duration", "avg") / 1000,
        "p95_duration_seconds": metric_value(metrics, "http_req_duration", "p(95)") / 1000,
        "p90_duration_seconds": metric_value(metrics, "http_req_duration", "p(90)") / 1000,
        "p99_duration_seconds": metric_value(metrics, "http_req_duration", "p(99)") / 1000,
        "throughput": metric_value(metrics, "http_reqs", "rate"),
        "checks_rate": metric_value(metrics, "checks", "rate") * 100,
        "vus": metric_value(metrics, "vus_max", "value") or metric_value(metrics, "vus", "value"),
    }


def metric_value(metrics, metric_name, key):
    metric = metrics.get(metric_name, {})
    if not isinstance(metric, dict):
        return 0
    if key == "rate" and metric_name == "checks":
        passes = metric.get("passes")
        fails = metric.get("fails")
        if passes is not None and fails is not None:
            total = float(passes or 0) + float(fails or 0)
            return float(passes or 0) / total if total else 0
        if "value" in metric:
            return float(metric.get("value", 0) or 0)
    try:
        return float(metric.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def load_json(path):
    try:
        path = Path(path)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
