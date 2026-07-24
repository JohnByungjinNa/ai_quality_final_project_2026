import json
import os
import subprocess
from types import SimpleNamespace

from services import k6_service
from services.k6_service import K6RunSettings, build_k6_script, normalize_k6_summary


def test_build_k6_script_contains_thresholds_and_target_url():
    settings = K6RunSettings(
        target_url="http://localhost:8000/health",
        vus=5,
        duration_seconds=30,
        ramp_up_seconds=10,
        p95_threshold_ms=1500,
        failure_rate_threshold_pct=2.5,
        checks_threshold_pct=97.0,
    )

    script = build_k6_script(settings)

    assert "http://localhost:8000/health" in script
    assert "target: 5" in script
    assert "p(95)<1500" in script
    assert "rate<0.0250" in script
    assert "rate>0.9700" in script


def test_normalize_k6_summary_converts_ms_and_rates():
    summary = {
        "metrics": {
            "http_reqs": {"count": 200, "rate": 20},
            "http_req_failed": {"rate": 0.015},
            "http_req_duration": {"avg": 1850, "p(90)": 3200, "p(95)": 3920, "p(99)": 5000},
            "checks": {"rate": 0.985},
            "vus_max": {"value": 20},
        }
    }

    normalized = normalize_k6_summary(summary)

    assert normalized["total_requests"] == 200
    assert normalized["failure_rate"] == 1.5
    assert normalized["avg_duration_seconds"] == 1.85
    assert normalized["p95_duration_seconds"] == 3.92
    assert normalized["checks_rate"] == 98.5
    assert normalized["vus"] == 20


def configure_run_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(k6_service, "K6_RUNS_DIR", tmp_path)
    monkeypatch.setattr(k6_service, "ACTIVE_RUN_FILE", tmp_path / "_active_run.json")
    monkeypatch.setattr(k6_service, "START_LOCK_FILE", tmp_path / "_start.lock")


def sample_settings():
    return K6RunSettings(
        target_url="http://127.0.0.1:8501/_stcore/health",
        vus=1,
        duration_seconds=10,
        ramp_up_seconds=0,
    )


def test_background_start_returns_immediately_and_writes_running_history(monkeypatch, tmp_path):
    configure_run_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(k6_service, "get_k6_executable", lambda: "k6.exe")

    class FakeProcess:
        pid = 4321

    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append(kwargs)
        return FakeProcess()

    monkeypatch.setattr(k6_service.subprocess, "Popen", fake_popen)

    result = k6_service.start_k6_test_background(sample_settings())

    assert result["ok"] is True
    assert result["status"] == "RUNNING"
    assert result["worker_pid"] == 4321
    record_path = tmp_path / result["run_id"] / "run_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    active = json.loads((tmp_path / "_active_run.json").read_text(encoding="utf-8"))
    assert record["status"] == "RUNNING"
    assert active["run_id"] == result["run_id"]
    assert (tmp_path / result["run_id"] / "script.js").exists()
    if os.name == "nt":
        assert popen_calls[0]["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_k6_child_process_uses_no_console_window_on_windows(monkeypatch, tmp_path):
    configure_run_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(k6_service, "get_k6_executable", lambda: "k6.exe")
    monkeypatch.setattr(k6_service, "save_latest_summary", lambda raw, record: None)
    run_calls = []

    def fake_run(*args, **kwargs):
        run_calls.append(kwargs)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(k6_service.subprocess, "run", fake_run)

    result = k6_service.run_k6_test(sample_settings(), run_id="20260715_120000")

    assert result["ok"] is True
    if os.name == "nt":
        assert run_calls[0]["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_background_start_blocks_duplicate_active_run(monkeypatch, tmp_path):
    configure_run_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(k6_service, "get_k6_executable", lambda: "k6.exe")
    monkeypatch.setattr(k6_service, "_process_is_running", lambda pid: True)
    k6_service.write_json(
        tmp_path / "_active_run.json",
        {"run_id": "active-1", "status": "RUNNING", "worker_pid": 1234},
    )

    result = k6_service.start_k6_test_background(sample_settings())

    assert result["ok"] is False
    assert "이미 k6 테스트가 실행 중" in result["error"]
    assert list(tmp_path.glob("*/run_record.json")) == []


def test_background_stop_terminates_worker_tree_and_preserves_history(monkeypatch, tmp_path):
    configure_run_paths(monkeypatch, tmp_path)
    run_id = "20260715_100000"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    running = {
        "run_id": run_id,
        "status": "RUNNING",
        "worker_pid": 9876,
        "created_at": "2026-07-15T10:00:00",
        "settings": {"target_url": "http://localhost:8000/health"},
    }
    k6_service.write_json(run_dir / "run_record.json", running)
    k6_service.write_json(tmp_path / "_active_run.json", running)
    terminated = []
    monkeypatch.setattr(k6_service, "_terminate_process_tree", lambda pid: terminated.append(pid) or True)

    result = k6_service.stop_k6_test(run_id)

    assert result["ok"] is True
    assert terminated == [9876]
    final = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
    assert final["status"] == "STOPPED"
    assert final["return_code"] == -2
    assert not (tmp_path / "_active_run.json").exists()


def test_stale_background_worker_is_recorded_as_error(monkeypatch, tmp_path):
    configure_run_paths(monkeypatch, tmp_path)
    run_id = "20260715_100100"
    run_dir = tmp_path / run_id
    run_dir.mkdir(parents=True)
    running = {
        "run_id": run_id,
        "status": "RUNNING",
        "worker_pid": 5555,
        "created_at": "2026-07-15T10:01:00",
        "settings": {},
    }
    k6_service.write_json(run_dir / "run_record.json", running)
    k6_service.write_json(tmp_path / "_active_run.json", running)
    monkeypatch.setattr(k6_service, "_process_is_running", lambda pid: False)

    assert k6_service.get_active_k6_run() == {}
    final = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
    assert final["status"] == "ERROR"
    assert "worker" in final["error"]
    assert not (tmp_path / "_active_run.json").exists()


def test_k6_run_lookup_rejects_path_traversal(monkeypatch, tmp_path):
    configure_run_paths(monkeypatch, tmp_path)

    assert k6_service.load_k6_run("../../outside") == {}
    assert k6_service.run_k6_worker("../../outside") == 2
