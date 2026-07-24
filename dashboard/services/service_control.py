import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

from core.paths import PROJECT_DIR, REPORTS_DIR

try:
    from config import GRAFANA_URL as CONFIG_GRAFANA_URL
    from config import PROMETHEUS_URL as CONFIG_PROMETHEUS_URL
except Exception:
    CONFIG_GRAFANA_URL = "http://localhost:3000"
    CONFIG_PROMETHEUS_URL = "http://localhost:9090"


FASTAPI_BASE_URL = os.getenv("FASTAPI_URL", "http://localhost:8000").rstrip("/")
PROMETHEUS_BASE_URL = os.getenv("PROMETHEUS_URL", CONFIG_PROMETHEUS_URL).rstrip("/")
GRAFANA_BASE_URL = os.getenv("GRAFANA_URL", CONFIG_GRAFANA_URL).rstrip("/")

RUNTIME_FILE = REPORTS_DIR / "service_runtime.json"
SERVICE_CONFIG_FILE = REPORTS_DIR / "service_management_config.json"
DOCKER_DESKTOP_EXE = Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe")
PROMETHEUS_SOURCE_CONFIG_FILE = PROJECT_DIR / "docker" / "prometheus.yml"
PROMETHEUS_TEMP_DIR = REPORTS_DIR / "runtime" / "prometheus_demo"
PROMETHEUS_TEMP_CONFIG_FILE = PROMETHEUS_TEMP_DIR / "prometheus.yml"
PROMETHEUS_TEMP_OVERRIDE_FILE = PROMETHEUS_TEMP_DIR / "compose.override.yml"

SERVICE_IDS = ("grafana", "prometheus", "fastapi")
RUNTIME_MODES = ("docker", "local", "external")
DEFAULT_SERVICE_CONFIG = {
    "grafana": "docker",
    "prometheus": "docker",
    "fastapi": "local",
}
MODE_LABELS = {
    "docker": "Docker Compose",
    "local": "로컬 실행",
    "external": "외부 관리",
    "desktop": "Docker Desktop",
}
COMPOSE_SERVICE_NAMES = {
    "grafana": "grafana",
    "prometheus": "prometheus",
    "fastapi": "api",
}
CONTAINER_NAMES = {
    "grafana": "ai-quality-2026-grafana",
    "prometheus": "ai-quality-2026-prometheus",
    "fastapi": "ai-quality-2026-api",
}
LOCAL_LOG_FILES = {
    "grafana": REPORTS_DIR / "grafana_service.log",
    "prometheus": REPORTS_DIR / "prometheus_service.log",
    "fastapi": REPORTS_DIR / "fastapi_service.log",
}
HTTP_TIMEOUT_SECONDS = 0.8
HTTP_CONNECT_TIMEOUT_SECONDS = 0.25
LOCAL_START_TIMEOUT_SECONDS = 20
LOCAL_STOP_TIMEOUT_SECONDS = 15
COMPOSE_START_TIMEOUT_SECONDS = {
    "grafana": 120,
    "prometheus": 45,
    "fastapi": 45,
}


def load_service_config():
    stored = _read_json(SERVICE_CONFIG_FILE)
    config = dict(DEFAULT_SERVICE_CONFIG)
    for service_id in SERVICE_IDS:
        env_name = f"{service_id.upper()}_RUNTIME_MODE"
        requested = os.getenv(env_name) or stored.get(service_id)
        if requested in RUNTIME_MODES:
            config[service_id] = requested
    return config


def save_service_config(config):
    normalized = {}
    for service_id in SERVICE_IDS:
        mode = config.get(service_id, DEFAULT_SERVICE_CONFIG[service_id])
        if mode not in RUNTIME_MODES:
            raise ValueError(f"지원하지 않는 실행 방식입니다: {service_id}={mode}")
        normalized[service_id] = mode
    _write_json(SERVICE_CONFIG_FILE, normalized)
    return normalized


def get_service_capabilities(config=None):
    config = config or load_service_config()
    capabilities = {}
    for service_id in SERVICE_IDS:
        executable = get_local_executable(service_id)
        capabilities[service_id] = {
            "mode": config[service_id],
            "mode_label": MODE_LABELS[config[service_id]],
            "local_available": bool(executable),
            "local_executable": str(executable or ""),
        }
    return capabilities


def collect_service_snapshot(config=None):
    config = config or load_service_config()
    check_targets = [
        ("grafana", "Grafana", f"{GRAFANA_BASE_URL}/api/health"),
        ("prometheus", "Prometheus", f"{PROMETHEUS_BASE_URL}/-/ready"),
        ("fastapi_health", "FastAPI /health", f"{FASTAPI_BASE_URL}/health"),
        ("fastapi_metrics", "FastAPI /metrics", f"{FASTAPI_BASE_URL}/metrics"),
    ]
    with ThreadPoolExecutor(max_workers=len(check_targets)) as executor:
        results = executor.map(
            lambda target: (target[0], _check_http(target[1], target[2])),
            check_targets,
        )
    checks = dict(results)
    runtime = _read_runtime()
    capabilities = get_service_capabilities(config)
    docker_service_ids = [service_id for service_id in SERVICE_IDS if config[service_id] == "docker"]
    with ThreadPoolExecutor(max_workers=max(len(docker_service_ids), 1)) as executor:
        container_results = executor.map(
            lambda service_id: (service_id, _container_is_running(service_id)),
            docker_service_ids,
        )
    container_states = dict(container_results)

    service_checks = {
        "grafana": [checks["grafana"]],
        "prometheus": [checks["prometheus"]],
        "fastapi": [checks["fastapi_health"], checks["fastapi_metrics"]],
    }
    snapshot = {}
    for service_id in SERVICE_IDS:
        mode = config[service_id]
        checks_for_service = service_checks[service_id]
        running = all(check["ok"] for check in checks_for_service)
        managed_pid = runtime.get(f"{service_id}_pid")
        locally_managed = bool(managed_pid and _process_is_running(managed_pid))
        container_running = container_states.get(service_id, False)
        snapshot[service_id] = {
            "name": _service_name(service_id),
            "running": running,
            "checks": checks_for_service,
            "mode": mode,
            "mode_label": MODE_LABELS[mode],
            "managed_pid": managed_pid if locally_managed else None,
            "locally_managed": locally_managed,
            "container_running": container_running,
            "local_available": capabilities[service_id]["local_available"],
            "local_executable": capabilities[service_id]["local_executable"],
            "control_message": _control_message(
                service_id,
                mode,
                running,
                locally_managed,
                container_running,
                capabilities,
            ),
            "temporary_config": (
                service_id == "prometheus" and _prometheus_temporary_config_exists()
            ),
        }
        if snapshot[service_id]["temporary_config"]:
            snapshot[service_id]["control_message"] = (
                "시연용 임시 수집 설정 적용 중: Windows 로컬 FastAPI·qa-observer를 수집합니다. "
                "Prometheus 또는 시스템 종료 시 제거되며 원본 YAML은 변경하지 않습니다."
            )
    return snapshot


def collect_runtime_status(config=None):
    config = config or load_service_config()
    return {
        "docker": _docker_status(),
        "config": config,
        "capabilities": get_service_capabilities(config),
        "urls": {
            "Grafana": GRAFANA_BASE_URL,
            "Prometheus": PROMETHEUS_BASE_URL,
            "FastAPI": FASTAPI_BASE_URL,
        },
    }


def run_service_action(service_id, action, mode=None):
    if service_id not in {"docker", *SERVICE_IDS}:
        return {"ok": False, "message": f"알 수 없는 서비스입니다: {service_id}"}
    if action not in {"start", "stop"}:
        return {"ok": False, "message": f"알 수 없는 작업입니다: {action}"}

    if service_id == "docker":
        return _start_docker_engine() if action == "start" else _stop_docker_engine()

    selected_mode = mode or load_service_config()[service_id]
    if selected_mode not in RUNTIME_MODES:
        return {"ok": False, "message": f"지원하지 않는 실행 방식입니다: {selected_mode}"}
    if selected_mode == "external":
        return {
            "ok": False,
            "message": f"{_service_name(service_id)}는 외부 관리 모드입니다. 이 화면에서는 상태만 조회합니다.",
        }
    if action == "start" and _service_http_running(service_id):
        return {"ok": True, "message": f"{_service_name(service_id)}가 이미 실행 중입니다."}

    if selected_mode == "docker":
        return _run_compose_action(service_id, action)
    return _run_local_action(service_id, action)


def stop_related_services():
    config = load_service_config()
    if _prometheus_temporary_config_exists():
        config["prometheus"] = "docker"
    results = [run_service_action(service_id, "stop", config[service_id]) for service_id in reversed(SERVICE_IDS)]
    cleanup_prometheus_temporary_config()
    return results


def cleanup_prometheus_temporary_config():
    """Remove demo-only files only after the Prometheus container is stopped."""
    if _container_is_running("prometheus"):
        return False
    _remove_prometheus_temporary_config_files()
    return True


def get_local_executable(service_id):
    if service_id == "fastapi":
        return Path(sys.executable)

    env_name = f"{service_id.upper()}_EXECUTABLE"
    configured = os.getenv(env_name)
    if configured and Path(configured).is_file():
        return Path(configured)

    command_names = {
        "prometheus": ("prometheus", "prometheus.exe"),
        "grafana": ("grafana", "grafana.exe", "grafana-server", "grafana-server.exe"),
    }[service_id]
    for command_name in command_names:
        resolved = shutil.which(command_name)
        if resolved:
            return Path(resolved)

    candidates = {
        "prometheus": [Path(r"C:\prometheus\prometheus.exe")],
        "grafana": [
            Path(r"C:\Program Files\GrafanaLabs\grafana\bin\grafana.exe"),
            Path(r"C:\Program Files\GrafanaLabs\grafana\bin\grafana-server.exe"),
        ],
    }[service_id]
    return next((path for path in candidates if path.is_file()), None)


def _run_compose_action(service_id, action):
    docker = _docker_status()
    if not docker["ok"]:
        if action == "stop" and service_id == "prometheus":
            _remove_prometheus_temporary_config_files()
            return {
                "ok": True,
                "message": "Docker Engine이 중지되어 Prometheus도 중지 상태입니다. 시연용 임시 설정을 제거했습니다.",
            }
        return {
            "ok": False,
            "message": "Docker Engine이 중지되어 있습니다. Docker Engine을 별도로 시작한 뒤 다시 시도해주세요.",
        }

    compose_service = COMPOSE_SERVICE_NAMES[service_id]
    if action == "start":
        if service_id == "prometheus":
            prepared = _prepare_prometheus_temporary_config()
            if not prepared["ok"]:
                return prepared
            command = _prometheus_compose_command("up", "-d", "--no-deps", compose_service)
        else:
            command = ["docker", "compose", "up", "-d", "--no-deps", compose_service]
        result = _run_command(
            command,
            timeout=120,
        )
    else:
        result = _run_command(["docker", "compose", "stop", compose_service], timeout=45)

    if result["ok"] and action == "start":
        readiness_timeout = COMPOSE_START_TIMEOUT_SECONDS[service_id]
        container_ready = _wait_until(
            lambda: _container_is_running(service_id),
            expected=True,
            timeout=readiness_timeout,
        )
        endpoint_ready = _wait_until(
            lambda: _service_http_running(service_id),
            expected=True,
            timeout=readiness_timeout,
        )
        if container_ready and endpoint_ready:
            temporary_note = (
                " Windows 로컬 FastAPI·qa-observer 수집용 임시 설정을 적용했습니다."
                if service_id == "prometheus"
                else ""
            )
            return {
                "ok": True,
                "message": (
                    f"{_service_name(service_id)}를 Docker Compose로 시작했고 endpoint 응답을 확인했습니다."
                    f"{temporary_note}"
                ),
            }
        if service_id == "prometheus" and not container_ready:
            _remove_prometheus_temporary_config_files()
        logs = _compose_log_tail(compose_service)
        return {
            "ok": False,
            "message": (
                f"{_service_name(service_id)} 컨테이너 시작 후 endpoint가 준비되지 않았습니다. "
                f"포트 충돌·설정·컨테이너 로그를 확인해주세요.{_detail_suffix(logs)}"
            ),
        }
    if result["ok"]:
        stopped = _wait_until(
            lambda: _container_is_running(service_id),
            expected=False,
            timeout=LOCAL_STOP_TIMEOUT_SECONDS,
        )
        if stopped:
            if service_id == "prometheus":
                _remove_prometheus_temporary_config_files()
            return {
                "ok": True,
                "message": (
                    f"{_service_name(service_id)} Docker 컨테이너 중지를 확인했습니다."
                    + (" 시연용 임시 설정을 제거했습니다." if service_id == "prometheus" else "")
                ),
            }
        return {
            "ok": False,
            "message": f"{_service_name(service_id)} 중지 명령 후에도 컨테이너가 실행 중입니다.",
        }
    return {
        "ok": False,
        "message": f"{_service_name(service_id)} Docker {action} 실패: {result['stderr'] or result['stdout']}",
    }


def _prepare_prometheus_temporary_config():
    try:
        source = PROMETHEUS_SOURCE_CONFIG_FILE.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "message": f"Prometheus 원본 설정을 읽지 못했습니다: {exc}"}

    replacements = {
        '"api:8000"': '"host.docker.internal:8000"',
        '"qa-observer:8010"': '"host.docker.internal:8010"',
    }
    temporary = source
    for original, local_target in replacements.items():
        if original not in temporary:
            return {
                "ok": False,
                "message": f"Prometheus 원본 설정에서 임시 전환 대상 {original}을 찾지 못했습니다.",
            }
        temporary = temporary.replace(original, local_target)

    override = f"""services:
  prometheus:
    volumes:
      - type: bind
        source: {PROMETHEUS_TEMP_CONFIG_FILE.as_posix()}
        target: /etc/prometheus/prometheus.yml
        read_only: true
"""
    try:
        PROMETHEUS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
        _write_text_atomic(PROMETHEUS_TEMP_CONFIG_FILE, temporary)
        _write_text_atomic(PROMETHEUS_TEMP_OVERRIDE_FILE, override)
    except OSError as exc:
        _remove_prometheus_temporary_config_files()
        return {"ok": False, "message": f"Prometheus 시연용 임시 설정 생성 실패: {exc}"}
    return {"ok": True, "message": "Prometheus 시연용 임시 설정을 생성했습니다."}


def _prometheus_compose_command(*arguments):
    return [
        "docker",
        "compose",
        "-f",
        str(PROJECT_DIR / "docker-compose.yml"),
        "-f",
        str(PROMETHEUS_TEMP_OVERRIDE_FILE),
        *arguments,
    ]


def _prometheus_temporary_config_exists():
    return PROMETHEUS_TEMP_CONFIG_FILE.is_file() and PROMETHEUS_TEMP_OVERRIDE_FILE.is_file()


def _remove_prometheus_temporary_config_files():
    for path in (PROMETHEUS_TEMP_OVERRIDE_FILE, PROMETHEUS_TEMP_CONFIG_FILE):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        PROMETHEUS_TEMP_DIR.rmdir()
    except OSError:
        pass


def _write_text_atomic(path, content):
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(content, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _run_local_action(service_id, action):
    if action == "start":
        return _start_local_service(service_id)
    return _stop_local_service(service_id)


def _start_local_service(service_id):
    executable = get_local_executable(service_id)
    if not executable:
        env_name = f"{service_id.upper()}_EXECUTABLE"
        return {
            "ok": False,
            "message": f"{_service_name(service_id)} 로컬 실행 파일이 없습니다. 설치 후 {env_name}을 설정해주세요.",
        }

    command, cwd = _local_start_spec(service_id, executable)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOCAL_LOG_FILES[service_id].open("a", encoding="utf-8")
    popen_kwargs = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True

    try:
        process = subprocess.Popen(command, **popen_kwargs)
    except OSError as exc:
        return {"ok": False, "message": f"{_service_name(service_id)} 로컬 시작 실패: {exc}"}
    finally:
        log_file.close()

    endpoint_ready = _wait_until(
        lambda: _service_http_running(service_id),
        expected=True,
        timeout=LOCAL_START_TIMEOUT_SECONDS,
    )
    if not endpoint_ready:
        _terminate_pid(process.pid)
        details = _local_log_tail(service_id)
        return {
            "ok": False,
            "message": (
                f"{_service_name(service_id)} 프로세스 PID={process.pid}를 생성했지만 "
                f"endpoint가 {LOCAL_START_TIMEOUT_SECONDS}초 안에 응답하지 않았습니다."
                f"{_detail_suffix(details)}"
            ),
        }

    runtime = _read_runtime()
    runtime[f"{service_id}_pid"] = process.pid
    runtime[f"{service_id}_mode"] = "local"
    runtime[f"{service_id}_started_at"] = time.time()
    _write_runtime(runtime)
    return {
        "ok": True,
        "message": (
            f"{_service_name(service_id)} 로컬 프로세스를 시작하고 endpoint 응답을 확인했습니다. "
            f"PID={process.pid}"
        ),
    }


def _stop_local_service(service_id):
    runtime = _read_runtime()
    pid_key = f"{service_id}_pid"
    pid = runtime.get(pid_key)
    if not pid:
        return {
            "ok": False,
            "message": f"이 화면에서 시작한 {_service_name(service_id)} 로컬 프로세스가 없습니다. 외부 프로세스는 안전을 위해 종료하지 않습니다.",
        }

    stopped = _terminate_pid(pid)
    if stopped:
        endpoint_stopped = _wait_until(
            lambda: _service_http_running(service_id),
            expected=False,
            timeout=LOCAL_STOP_TIMEOUT_SECONDS,
        )
        if endpoint_stopped:
            runtime.pop(pid_key, None)
            runtime.pop(f"{service_id}_mode", None)
            runtime.pop(f"{service_id}_started_at", None)
            _write_runtime(runtime)
            return {
                "ok": True,
                "message": f"{_service_name(service_id)} 로컬 프로세스와 endpoint 중지를 확인했습니다.",
            }
        return {
            "ok": False,
            "message": (
                f"{_service_name(service_id)} PID {pid}을 종료했지만 endpoint가 계속 응답합니다. "
                "같은 포트의 다른 프로세스를 확인해주세요."
            ),
        }
    return {"ok": False, "message": f"{_service_name(service_id)} PID {pid}을 중지하지 못했습니다."}


def _local_start_spec(service_id, executable):
    if service_id == "fastapi":
        return (
            [
                str(executable),
                "-m",
                "uvicorn",
                "api_app:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
            PROJECT_DIR,
        )
    if service_id == "prometheus":
        data_dir = REPORTS_DIR / "prometheus_data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return (
            [
                str(executable),
                f"--config.file={PROJECT_DIR / 'prometheus.yml'}",
                "--web.listen-address=:9090",
                f"--storage.tsdb.path={data_dir}",
            ],
            PROJECT_DIR,
        )

    home_path = executable.parent.parent
    if executable.stem.lower() == "grafana":
        command = [str(executable), "server", "--homepath", str(home_path)]
    else:
        command = [str(executable), "--homepath", str(home_path)]
    return command, home_path


def _start_docker_engine():
    status = _docker_status()
    if status["ok"]:
        return {"ok": True, "message": "Docker Engine이 이미 실행 중입니다."}
    if not shutil.which("docker"):
        return {"ok": False, "message": "Docker CLI를 찾을 수 없습니다."}

    result = _run_command(["docker", "desktop", "start"], timeout=20)
    requested = result["ok"]
    fallback_error = ""
    if not requested and os.name == "nt" and DOCKER_DESKTOP_EXE.is_file():
        try:
            subprocess.Popen(
                [str(DOCKER_DESKTOP_EXE)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            requested = True
        except OSError as exc:
            fallback_error = str(exc)
    if not requested:
        reason = fallback_error or result["stderr"] or result["stdout"]
        return {"ok": False, "message": f"Docker Desktop 시작 실패: {reason}"}

    ready = _wait_until(lambda: _docker_status()["ok"], expected=True, timeout=60)
    if ready:
        return {
            "ok": True,
            "message": "Docker Engine 시작과 응답 준비를 확인했습니다. 다른 서비스는 자동 시작하지 않았습니다.",
        }
    return {
        "ok": False,
        "message": "Docker Desktop을 실행했지만 Engine이 60초 안에 준비되지 않았습니다. Docker Desktop 화면의 오류를 확인해주세요.",
    }


def _stop_docker_engine():
    if not _docker_status()["ok"]:
        return {"ok": True, "message": "Docker Engine이 이미 중지되어 있습니다."}
    result = _run_command(["docker", "desktop", "stop"], timeout=60)
    stopped = result["ok"] and _wait_until(
        lambda: _docker_status()["ok"], expected=False, timeout=30
    )
    if stopped:
        _remove_prometheus_temporary_config_files()
        return {
            "ok": True,
            "message": (
                "Docker Desktop을 중지했습니다. 실행 중이던 Docker 컨테이너도 함께 중지되며 "
                "Prometheus 시연용 임시 설정을 제거했습니다."
            ),
        }
    return {"ok": False, "message": f"Docker Desktop 중지 실패: {result['stderr'] or result['stdout']}"}


def _control_message(service_id, mode, running, locally_managed, container_running, capabilities):
    if mode == "external":
        return "외부 관리: 상태만 조회하며 시작·중지는 비활성화됩니다."
    if mode == "local" and not capabilities[service_id]["local_available"]:
        return f"로컬 실행 파일 없음: {service_id.upper()}_EXECUTABLE 설정 필요"
    if mode == "local" and running and not locally_managed:
        return "외부에서 시작된 로컬 서비스로 감지되어 중지 보호가 적용됩니다."
    if mode == "docker":
        if running and not container_running:
            return "endpoint는 응답하지만 이 프로젝트의 Docker 컨테이너가 아닙니다. 실행 방식을 확인해주세요."
        if container_running and not running:
            return "컨테이너는 실행 중이지만 health endpoint가 응답하지 않습니다. 중지 또는 로그 확인이 가능합니다."
        return (
            "Docker Engine 위에서 실행됩니다(Engine 필수). "
            "다른 컨테이너는 건드리지 않고 이 서비스만 --no-deps 방식으로 제어합니다."
        )
    return "이 화면에서 시작한 로컬 프로세스만 안전하게 제어합니다."


def _check_http(name, url):
    try:
        timeout = httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=HTTP_CONNECT_TIMEOUT_SECONDS)
        response = httpx.get(_normalize_local_url(url), timeout=timeout, trust_env=False)
        return {"name": name, "ok": response.status_code < 400, "status_code": response.status_code}
    except httpx.HTTPError:
        return {"name": name, "ok": False, "status_code": None}


def _normalize_local_url(url):
    parsed = urlsplit(url)
    if parsed.hostname != "localhost":
        return url
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((parsed.scheme, f"127.0.0.1{port}", parsed.path, parsed.query, parsed.fragment))


def _run_command(command, timeout):
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc)}
    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _docker_status():
    if not shutil.which("docker"):
        return {"ok": False, "label": "설치 안 됨", "message": "Docker CLI를 찾을 수 없습니다."}
    result = _run_command(["docker", "version", "--format", "{{.Server.Version}}"], timeout=3)
    if result["ok"] and result["stdout"]:
        return {"ok": True, "label": f"실행중 ({result['stdout']})", "message": ""}
    message = result["stderr"] or result["stdout"] or "Docker Engine 응답 없음"
    return {"ok": False, "label": "중지", "message": message}


def _container_is_running(service_id):
    result = _run_command(
        ["docker", "inspect", "--format", "{{.State.Running}}", CONTAINER_NAMES[service_id]],
        timeout=3,
    )
    return result["ok"] and result["stdout"].strip().lower() == "true"


def _service_http_running(service_id):
    if service_id == "grafana":
        return _check_http("Grafana", f"{GRAFANA_BASE_URL}/api/health")["ok"]
    if service_id == "prometheus":
        return _check_http("Prometheus", f"{PROMETHEUS_BASE_URL}/-/ready")["ok"]
    return _check_http("FastAPI /health", f"{FASTAPI_BASE_URL}/health")["ok"]


def _process_is_running(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _terminate_pid(pid):
    try:
        if os.name == "nt":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            return completed.returncode == 0
        os.killpg(os.getpgid(int(pid)), signal.SIGTERM)
        return True
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return False


def _wait_until(probe, expected, timeout, interval=0.25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if bool(probe()) is expected:
                return True
        except Exception:
            pass
        time.sleep(interval)
    try:
        return bool(probe()) is expected
    except Exception:
        return False


def _local_log_tail(service_id, max_chars=1800):
    path = LOCAL_LOG_FILES[service_id]
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-max_chars:].strip()
    except OSError:
        return ""


def _compose_log_tail(compose_service, max_chars=1800):
    result = _run_command(
        ["docker", "compose", "logs", "--no-color", "--tail", "30", compose_service],
        timeout=15,
    )
    return (result["stdout"] or result["stderr"])[-max_chars:].strip()


def _detail_suffix(details):
    return f"\n\n최근 로그:\n{details}" if details else ""


def _service_name(service_id):
    return {
        "docker": "Docker Engine",
        "grafana": "Grafana",
        "prometheus": "Prometheus",
        "fastapi": "FastAPI",
    }[service_id]


def _read_runtime():
    return _read_json(RUNTIME_FILE)


def _write_runtime(data):
    _write_json(RUNTIME_FILE, data)


def _read_json(path):
    try:
        path = Path(path)
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
