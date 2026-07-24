import threading
import time
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.pages_top import service_management
from dashboard.services import service_control


def test_service_snapshot_runs_health_checks_in_parallel(monkeypatch):
    barrier = threading.Barrier(4)
    requested = []

    def fake_check(name, url):
        requested.append((name, url))
        barrier.wait(timeout=1)
        return {"name": name, "ok": False, "status_code": None}

    monkeypatch.setattr(service_control, "_check_http", fake_check)

    snapshot = service_control.collect_service_snapshot()

    assert set(snapshot) == {"grafana", "prometheus", "fastapi"}
    assert len(requested) == 4
    assert all("/ask" not in url for _, url in requested)
    assert [check["name"] for check in snapshot["fastapi"]["checks"]] == [
        "FastAPI /health",
        "FastAPI /metrics",
    ]


def test_management_snapshot_collects_runtime_and_services_concurrently(monkeypatch):
    service_management.collect_management_snapshot.clear()

    def slow_services():
        time.sleep(0.12)
        return {"source": "services"}

    def slow_runtime():
        time.sleep(0.12)
        return {"source": "runtime"}

    monkeypatch.setattr(service_management, "collect_service_snapshot", slow_services)
    monkeypatch.setattr(service_management, "collect_runtime_status", slow_runtime)

    started = time.perf_counter()
    snapshot = service_management.collect_management_snapshot()
    elapsed = time.perf_counter() - started

    assert snapshot == {
        "services": {"source": "services"},
        "runtime": {"source": "runtime"},
    }
    assert elapsed < 0.21
    service_management.collect_management_snapshot.clear()


def test_localhost_health_checks_use_ipv4_loopback():
    assert (
        service_control._normalize_local_url("http://localhost:8000/health?full=1")
        == "http://127.0.0.1:8000/health?full=1"
    )
    assert service_control._normalize_local_url("http://example.com/health") == "http://example.com/health"


def test_service_runtime_modes_are_saved_and_loaded(monkeypatch, tmp_path):
    config_path = tmp_path / "service_management_config.json"
    monkeypatch.setattr(service_control, "SERVICE_CONFIG_FILE", config_path)
    for service_id in service_control.SERVICE_IDS:
        monkeypatch.delenv(f"{service_id.upper()}_RUNTIME_MODE", raising=False)

    saved = service_control.save_service_config(
        {"grafana": "external", "prometheus": "local", "fastapi": "docker"}
    )

    assert saved == {"grafana": "external", "prometheus": "local", "fastapi": "docker"}
    assert service_control.load_service_config() == saved


def test_compose_service_start_does_not_auto_start_docker(monkeypatch):
    monkeypatch.setattr(service_control, "_service_http_running", lambda service_id: False)
    monkeypatch.setattr(
        service_control,
        "_docker_status",
        lambda: {"ok": False, "label": "중지", "message": "not running"},
    )
    commands = []
    docker_start_calls = []
    monkeypatch.setattr(
        service_control,
        "_start_docker_engine",
        lambda: docker_start_calls.append(True) or {"ok": True, "message": "unexpected"},
    )
    monkeypatch.setattr(
        service_control,
        "_run_command",
        lambda command, timeout: commands.append(command) or {"ok": True, "stdout": "", "stderr": ""},
    )

    result = service_control.run_service_action("grafana", "start", "docker")

    assert result["ok"] is False
    assert "Docker Engine을 별도로 시작" in result["message"]
    assert commands == []
    assert docker_start_calls == []


def test_docker_mode_control_message_explains_runtime_dependency():
    message = service_control._control_message(
        "grafana",
        "docker",
        running=False,
        locally_managed=False,
        container_running=False,
        capabilities={"grafana": {"local_available": False}},
    )

    assert "Docker Engine 위에서 실행" in message
    assert "Engine 필수" in message
    assert "--no-deps" in message


def configure_prometheus_temporary_paths(monkeypatch, tmp_path):
    source_config = tmp_path / "source-prometheus.yml"
    source_config.write_text(
        'scrape_configs:\n  - targets: ["api:8000"]\n  - targets: ["qa-observer:8010"]\n',
        encoding="utf-8",
    )
    temp_dir = tmp_path / "runtime" / "prometheus_demo"
    monkeypatch.setattr(service_control, "PROMETHEUS_SOURCE_CONFIG_FILE", source_config)
    monkeypatch.setattr(service_control, "PROMETHEUS_TEMP_DIR", temp_dir)
    monkeypatch.setattr(service_control, "PROMETHEUS_TEMP_CONFIG_FILE", temp_dir / "prometheus.yml")
    monkeypatch.setattr(service_control, "PROMETHEUS_TEMP_OVERRIDE_FILE", temp_dir / "compose.override.yml")
    return source_config, temp_dir


def test_compose_service_start_uses_temporary_override_and_no_deps(monkeypatch, tmp_path):
    source_config, temp_dir = configure_prometheus_temporary_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(service_control, "_service_http_running", lambda service_id: False)
    monkeypatch.setattr(
        service_control,
        "_docker_status",
        lambda: {"ok": True, "label": "실행중", "message": ""},
    )
    commands = []

    def fake_run(command, timeout):
        commands.append(command)
        return {"ok": True, "stdout": "", "stderr": ""}

    monkeypatch.setattr(service_control, "_run_command", fake_run)
    monkeypatch.setattr(service_control, "_wait_until", lambda probe, expected, timeout: True)

    result = service_control.run_service_action("prometheus", "start", "docker")

    assert result["ok"] is True
    assert len(commands) == 1
    assert commands[0][:2] == ["docker", "compose"]
    assert commands[0][-4:] == ["up", "-d", "--no-deps", "prometheus"]
    assert str(temp_dir / "compose.override.yml") in commands[0]
    assert '"api:8000"' in source_config.read_text(encoding="utf-8")
    temporary_config = (temp_dir / "prometheus.yml").read_text(encoding="utf-8")
    assert '"host.docker.internal:8000"' in temporary_config
    assert '"host.docker.internal:8010"' in temporary_config


def test_prometheus_stop_removes_temporary_files(monkeypatch, tmp_path):
    _, temp_dir = configure_prometheus_temporary_paths(monkeypatch, tmp_path)
    prepared = service_control._prepare_prometheus_temporary_config()
    assert prepared["ok"] is True

    monkeypatch.setattr(
        service_control,
        "_docker_status",
        lambda: {"ok": True, "label": "실행중", "message": ""},
    )
    monkeypatch.setattr(
        service_control,
        "_run_command",
        lambda command, timeout: {"ok": True, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(service_control, "_wait_until", lambda probe, expected, timeout: True)

    result = service_control.run_service_action("prometheus", "stop", "docker")

    assert result["ok"] is True
    assert "임시 설정을 제거" in result["message"]
    assert not (temp_dir / "prometheus.yml").exists()
    assert not (temp_dir / "compose.override.yml").exists()


def test_shutdown_stops_temporary_prometheus_as_docker_even_if_saved_mode_changed(monkeypatch):
    monkeypatch.setattr(
        service_control,
        "load_service_config",
        lambda: {"grafana": "docker", "prometheus": "local", "fastapi": "local"},
    )
    monkeypatch.setattr(service_control, "_prometheus_temporary_config_exists", lambda: True)
    actions = []
    monkeypatch.setattr(
        service_control,
        "run_service_action",
        lambda service_id, action, mode: actions.append((service_id, action, mode)) or {"ok": True},
    )
    monkeypatch.setattr(service_control, "cleanup_prometheus_temporary_config", lambda: True)

    service_control.stop_related_services()

    assert ("prometheus", "stop", "docker") in actions


def test_non_prometheus_compose_start_does_not_use_temporary_override(monkeypatch):
    monkeypatch.setattr(service_control, "_service_http_running", lambda service_id: False)
    monkeypatch.setattr(
        service_control,
        "_docker_status",
        lambda: {"ok": True, "label": "실행중", "message": ""},
    )
    commands = []
    monkeypatch.setattr(
        service_control,
        "_run_command",
        lambda command, timeout: commands.append(command) or {"ok": True, "stdout": "", "stderr": ""},
    )
    monkeypatch.setattr(service_control, "_wait_until", lambda probe, expected, timeout: True)

    result = service_control.run_service_action("grafana", "start", "docker")

    assert result["ok"] is True
    assert commands == [["docker", "compose", "up", "-d", "--no-deps", "grafana"]]


def test_docker_service_start_opens_confirmation_even_when_engine_is_stopped():
    service = {
        "running": False,
        "mode": "docker",
        "container_running": False,
    }

    start_disabled, stop_disabled = service_management.get_action_disabled(
        "prometheus", service, {"ok": False}
    )

    assert start_disabled is False
    assert stop_disabled is True


def test_external_service_mode_is_read_only():
    result = service_control.run_service_action("grafana", "stop", "external")

    assert result["ok"] is False
    assert "상태만 조회" in result["message"]


def test_local_stop_does_not_kill_unmanaged_process(monkeypatch, tmp_path):
    runtime_path = tmp_path / "service_runtime.json"
    monkeypatch.setattr(service_control, "RUNTIME_FILE", runtime_path)
    terminated = []
    monkeypatch.setattr(
        service_control,
        "_terminate_pid",
        lambda pid: terminated.append(pid) or True,
    )

    result = service_control.run_service_action("fastapi", "stop", "local")

    assert result["ok"] is False
    assert "외부 프로세스는 안전을 위해 종료하지 않습니다" in result["message"]
    assert terminated == []


def test_container_names_match_current_compose_project():
    assert service_control.CONTAINER_NAMES == {
        "grafana": "ai-quality-2026-grafana",
        "prometheus": "ai-quality-2026-prometheus",
        "fastapi": "ai-quality-2026-api",
    }


def test_compose_file_has_no_service_lifecycle_dependencies():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "depends_on:" not in compose
    assert "GRAFANA_URL: http://grafana:3000" in compose


def test_service_management_page_renders_independent_controls():
    app = AppTest.from_file("tests/fixtures/service_management_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    labels = [button.label for button in app.button]
    assert labels.count("시작") == 4
    assert labels.count("중지") == 4

    app.button("service_independent_start_fastapi").click().run()

    assert not app.exception
    assert any("오조작 방지 확인" in checkbox.label for checkbox in app.checkbox)
    assert any(button.label == "실행" for button in app.button)


def test_service_action_confirmation_is_rendered_as_dialog():
    app = AppTest.from_file("tests/fixtures/service_action_dialog_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert any("오조작 방지 확인" in checkbox.label for checkbox in app.checkbox)
    assert not any(text_input.label == "확인 문구" for text_input in app.text_input)
    assert any(button.label == "실행" for button in app.button)
    assert any(button.label == "취소" for button in app.button)

    execute_button = next(button for button in app.button if button.label == "실행")
    assert execute_button.disabled is True

    app.checkbox[0].set_value(True).run()

    execute_button = next(button for button in app.button if button.label == "실행")
    assert execute_button.disabled is False


def test_local_start_reports_failure_when_endpoint_does_not_become_ready(monkeypatch, tmp_path):
    class FakeProcess:
        pid = 4321

    log_path = tmp_path / "fastapi.log"
    monkeypatch.setitem(service_control.LOCAL_LOG_FILES, "fastapi", log_path)
    monkeypatch.setattr(service_control, "get_local_executable", lambda service_id: Path("python.exe"))
    monkeypatch.setattr(
        service_control,
        "_local_start_spec",
        lambda service_id, executable: (["python.exe"], tmp_path),
    )
    monkeypatch.setattr(service_control.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    monkeypatch.setattr(service_control, "_wait_until", lambda probe, expected, timeout: False)
    terminated = []
    monkeypatch.setattr(service_control, "_terminate_pid", lambda pid: terminated.append(pid) or True)

    result = service_control._start_local_service("fastapi")

    assert result["ok"] is False
    assert "endpoint" in result["message"]
    assert terminated == [4321]


def test_unhealthy_managed_local_process_can_be_stopped():
    service = {
        "running": False,
        "mode": "local",
        "local_available": True,
        "locally_managed": True,
    }

    start_disabled, stop_disabled = service_management.get_action_disabled(
        "fastapi", service, {"ok": False}
    )

    assert start_disabled is True
    assert stop_disabled is False


def test_unhealthy_running_container_can_be_stopped():
    service = {
        "running": False,
        "mode": "docker",
        "container_running": True,
    }

    start_disabled, stop_disabled = service_management.get_action_disabled(
        "prometheus", service, {"ok": True}
    )

    assert start_disabled is True
    assert stop_disabled is False
