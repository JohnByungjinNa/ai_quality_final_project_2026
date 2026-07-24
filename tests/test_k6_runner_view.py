from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.pages_top.k6_runner_view import (
    build_execution_stages,
    current_execution_stage_index,
    estimate_k6_duration,
    format_execution_stage_option,
    format_compact_duration,
)
from dashboard.services.k6_service import K6RunSettings


def test_k6_background_runner_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/k6_background_runner_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert any("k6" in button.label.lower() for button in app.button)


def test_k6_runner_uses_background_status_fragment():
    source = Path("dashboard/pages_top/k6_runner_view.py").read_text(encoding="utf-8")

    assert '@st.fragment(run_every="2s")' in source
    assert "@st.dialog(" in source
    assert "start_k6_test_background" in source
    assert "stop_k6_test" in source


def test_k6_execution_dialog_renders_stages_and_settings():
    app = AppTest.from_file("tests/fixtures/k6_execution_dialog_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert len(app.dataframe) == 2
    assert len(app.segmented_control) == 1
    assert app.segmented_control[0].value == "▶ 3 k6 수행"
    assert any("테스트 중지" in button.label for button in app.button)
    assert sum("닫기" in button.label for button in app.button) == 1


def test_dialog_close_button_is_above_progress_and_only_clears_dialog_state(monkeypatch):
    source = Path("dashboard/pages_top/k6_runner_view.py").read_text(encoding="utf-8")
    close_button = source.index('key=f"k6_dialog_close_{run_id}"')
    progress_bar = source.index("st.progress(progress", close_button)
    state = {"k6_execution_dialog_run_id": "20260715_120000"}
    monkeypatch.setattr("dashboard.pages_top.k6_runner_view.st.session_state", state)

    from dashboard.pages_top.k6_runner_view import close_k6_execution_dialog

    close_k6_execution_dialog()

    assert close_button < progress_bar
    assert "k6_execution_dialog_run_id" not in state


def test_main_page_hides_active_progress_and_offers_dialog_launcher():
    app = AppTest.from_file("tests/fixtures/k6_active_main_page_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert len(app.metric) == 0
    assert any("수행 화면 열기" in button.label for button in app.button)
    assert not any("실행 중지" in button.label for button in app.button)


def test_expected_duration_includes_ramp_down_and_result_buffer():
    estimate = estimate_k6_duration(
        K6RunSettings(
            target_url="http://localhost:8000/health",
            duration_seconds=60,
            ramp_up_seconds=10,
        )
    )

    assert estimate["stable_seconds"] == 50
    assert estimate["ramp_down_seconds"] == 5
    assert estimate["k6_seconds"] == 65
    assert estimate["minimum_total_seconds"] == 67
    assert estimate["maximum_total_seconds"] == 75
    assert estimate["breakdown"] == "Ramp-up 10초 + 유지 50초 + 종료 5초"


def test_expected_duration_without_ramp_up_uses_fixed_load_duration():
    estimate = estimate_k6_duration(
        {
            "duration_seconds": 120,
            "ramp_up_seconds": 0,
        }
    )

    assert estimate["k6_seconds"] == 120
    assert estimate["ramp_down_seconds"] == 0
    assert estimate["expected_range_label"] == "2분 2초~2분 10초"
    assert format_compact_duration(60) == "1분"


def test_execution_stages_follow_worker_status():
    running = build_execution_stages({"status": "RUNNING"})
    completed = build_execution_stages({"status": "PASS"})
    stopped = build_execution_stages({"status": "STOPPED"})

    assert [stage["상태"] for stage in running] == ["완료", "완료", "진행 중", "대기", "대기"]
    assert [stage["상태"] for stage in completed] == ["완료", "완료", "완료", "완료", "PASS"]
    assert stopped[2]["상태"] == "중지"
    assert stopped[3]["상태"] == "완료"


def test_current_execution_stage_selector_follows_worker_status():
    assert current_execution_stage_index("STARTING") == 1
    assert current_execution_stage_index("RUNNING") == 2
    assert current_execution_stage_index("FINALIZING") == 3
    assert current_execution_stage_index("PASS") == 4
    assert current_execution_stage_index("FAIL") == 4
    assert current_execution_stage_index("STOPPING") == 2

    running_stages = build_execution_stages({"status": "RUNNING"})
    options = [
        format_execution_stage_option(index, stage, 2)
        for index, stage in enumerate(running_stages)
    ]
    assert options == [
        "✓ 1 설정 검증",
        "✓ 2 worker 시작",
        "▶ 3 k6 수행",
        "○ 4 결과 저장",
        "○ 5 완료",
    ]
