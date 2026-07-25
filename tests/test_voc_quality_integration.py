import asyncio
import json
import threading
import time
from copy import deepcopy
from pathlib import Path
from datetime import datetime

import pandas as pd
import pytest
from streamlit.proto.Block_pb2 import Block
from streamlit.proto.Dataframe_pb2 import Dataframe
from streamlit.proto.LabelVisibility_pb2 import LabelVisibility
from streamlit.testing.v1 import AppTest

from dashboard.navigation import MENU_OPTIONS, SIDEBAR_MENU_OPTIONS
from dashboard.pages_top import voc_quality_view
from dashboard.services import voc_quality_service
from services import voc_background_job_service
from dashboard.services.voc_quality_service import (
    load_improvement_validity_rubric,
    load_independent_judge_rubric,
    load_quality_evidence_contract,
    load_quality_test_catalog,
    load_system_rubric,
    parse_agent_status_output,
    runtime_health,
    save_quality_rubric,
    summarize_a2a_events,
    test_case_summary as get_test_case_summary,
    validate_quality_rubric,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]


def _configure_temp_voc_run_store(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "voc_quality_runs")
    store._ACTIVE_RUN_IDS.clear()
    return store


def test_voc_quality_top_and_sidebar_menu_registered():
    assert "VOC 품질진단" in MENU_OPTIONS
    assert SIDEBAR_MENU_OPTIONS["VOC 품질진단"] == [
        "Dashboard",
        "Agent 관리",
        "테스트케이스",
        "품질 평가 기준",
        "수동 TC 수행",
        "일괄 TC 수행",
        "수행 이력",
        "개선안 타당성 검증",
        "장애·결함 관리",
        "품질 보고서",
        "사용자 가이드",
        "최종 인수·시연",
    ]
    assert voc_quality_view.ROUTES["Dashboard"] is voc_quality_view.render_dashboard
    assert voc_quality_view.ROUTES["수행 이력"] is voc_quality_view.render_voc_history
    assert voc_quality_view.ROUTES["개선안 타당성 검증"] is voc_quality_view.render_improvement_validity
    assert voc_quality_view.ROUTES["최종 인수·시연"] is voc_quality_view.render_acceptance


def test_voc_visual_design_metadata_covers_every_page():
    assert set(voc_quality_view.VOC_PAGE_META) == set(voc_quality_view.ROUTES)
    assert all(meta["icon"] for meta in voc_quality_view.VOC_PAGE_META.values())
    assert all(len(meta["flow"]) == 3 for meta in voc_quality_view.VOC_PAGE_META.values())


def test_voc_visual_design_shell_renders_header_flow_and_content():
    app = AppTest.from_file("tests/fixtures/voc_design_system_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    assert "품질 평가 기준 수립" in markdown
    assert ":blue-badge[단계 선택]" in markdown
    assert ":blue-badge[배점 조정]" in markdown
    assert ":blue-badge[검증·저장]" in markdown
    assert any(item.label == "평가 총점" for item in app.metric)
    assert any(item.label == "기준명" for item in app.text_input)


def test_voc_history_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_history_app.py", default_timeout=15)
    app.run()

    assert not app.exception


def test_voc_dashboard_renders_operational_quality_summary():
    app = AppTest.from_file("tests/fixtures/voc_dashboard_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert any(item.label == "기간" for item in app.date_input)
    dashboard_markup = "\n".join(item.value for item in app.markdown)
    assert "Agent 가동" in dashboard_markup
    assert "최신 Run 품질" in dashboard_markup
    assert "기간 미종결 결함" in dashboard_markup
    assert "우선 확인 사항" not in dashboard_markup
    assert "실행 기반과 Trace 현황" not in dashboard_markup
    assert "기간 Run 판정 추이" in dashboard_markup
    assert "기간 수행 이력" in dashboard_markup
    assert "최근 연결 판정" in dashboard_markup
    assert "PASS" in dashboard_markup
    assert "FAIL" in dashboard_markup
    assert "NOT_VERIFIED" in dashboard_markup
    assert "vqd-connection-option active fail" in dashboard_markup
    assert dashboard_markup.count("vqd-connection-option inactive") == 2
    assert [button.label for button in app.button[:2]] == ["조회", "새로고침"]
    assert any("· Run " in item.value and item.value.endswith("건") for item in app.caption)
    assert any(
        item.value == "Run별 PASS·검토·실패/오류 비율 · 최근 12건"
        for item in app.caption
    )
    assert "vqd-agent-grid" in dashboard_markup
    assert "vqd-agent-card good" in dashboard_markup
    assert "vqd-agent-card bad" in dashboard_markup
    assert len(app.get("vega_lite_chart")) == 2
    assert {"수행", "Run", "등록"}.issubset(app.dataframe[0].value.columns)


def test_agent_management_cards_show_start_time_and_stop_impact_without_summary_metrics():
    app = AppTest.from_file("tests/fixtures/voc_agent_management_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert not any(
        metric.label in {"전체 Agent", "정상 가동", "중지·확인 필요"}
        for metric in app.metric
    )
    rendered_text = "\n".join(item.value for item in [*app.markdown, *app.caption])
    warning_text = "\n".join(item.value for item in app.warning)
    assert "Report에 저장하지 않습니다" not in warning_text
    assert "런타임 폴더에서 직접 입력하세요" not in warning_text
    assert "실행 환경 연결됨" not in rendered_text
    assert rendered_text.count("기동 시간 ·") == 6
    assert rendered_text.count(":red-badge[중지 영향]") == 1
    assert "정책 개선안을 생성·보완할 수 없어" in rendered_text
    assert "기동 시간 · -" in rendered_text
    assert "6개 Agent 프로세스만 기동" in rendered_text
    assert "Test Case나 VOC 품질진단을 실행하지 않습니다" in rendered_text
    assert len(app.get("column")) == 6
    assert rendered_text.count("<div class='vqa-agent-head") == 6
    assert rendered_text.count("<svg") == 6
    assert ":material/smart_toy:" not in rendered_text


def test_agent_management_reuses_dashboard_agent_icon():
    agent = {
        "name": "Retriever",
        "healthy": True,
    }

    markup = voc_quality_view._agent_management_card_header(agent)

    assert voc_quality_view._dashboard_agent_svg_icon("Retriever") in markup
    assert "vqa-agent-head good" in markup
    assert "관련 VOC 검색" in markup


@pytest.mark.parametrize(
    ("action", "agent_name", "expected"),
    [
        ("start", None, "Interpreter 등 6개 Agent 프로세스를 기동하고 있습니다..."),
        ("restart", None, "Interpreter 등 6개 Agent 프로세스를 재기동하고 있습니다..."),
        ("stop", None, "Interpreter 등 6개 Agent 프로세스를 중지하고 있습니다..."),
        ("start", "retriever", "retriever Agent 프로세스를 기동하고 있습니다..."),
    ],
)
def test_agent_control_uses_agent_specific_progress_message(action, agent_name, expected):
    assert voc_quality_view._agent_control_progress_message(action, agent_name) == expected
    assert "VOC 품질진단 작업을 수행" not in expected


def test_agent_control_refreshes_after_command_completion(monkeypatch):
    class Clearable:
        def __init__(self):
            self.clear_count = 0

        def clear(self):
            self.clear_count += 1

    class Spinner:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    state = {}
    spinner_messages = []
    reruns = []
    management_snapshot = Clearable()
    monitor_snapshot = Clearable()
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view.st,
        "spinner",
        lambda message: spinner_messages.append(message) or Spinner(),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "run_agent_action",
        lambda action, agent_name=None: {"ok": True, "action": action, "agent_name": agent_name},
    )
    monkeypatch.setattr(voc_quality_view, "_load_agent_management_snapshot", management_snapshot)
    monkeypatch.setattr(voc_quality_view, "_load_goal_monitor_snapshot", monitor_snapshot)
    monkeypatch.setattr(voc_quality_view.st, "rerun", lambda: reruns.append(True))

    voc_quality_view._run_agent_control_and_refresh("start")

    assert spinner_messages == ["Interpreter 등 6개 Agent 프로세스를 기동하고 있습니다..."]
    assert state["voc_command_result"]["ok"] is True
    assert management_snapshot.clear_count == 1
    assert monitor_snapshot.clear_count == 1
    assert reruns == [True]


def test_agent_management_hides_success_command_details(monkeypatch):
    state = {
        "voc_command_result": {
            "ok": True,
            "duration_seconds": 2.26,
            "output": "[STOPPED] retriever (PID 16312)",
        }
    }
    rendered = []
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "success", lambda *args, **kwargs: rendered.append(args))
    monkeypatch.setattr(voc_quality_view.st, "code", lambda *args, **kwargs: rendered.append(args))

    voc_quality_view._show_command_result(show_success=False)

    assert rendered == []
    assert "voc_command_result" not in state


def test_agent_management_keeps_failed_command_details(monkeypatch):
    state = {
        "voc_command_result": {
            "ok": False,
            "return_code": 1,
            "output": "Agent stop failed",
        }
    }
    errors = []
    outputs = []
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "error", lambda message: errors.append(message))
    monkeypatch.setattr(voc_quality_view.st, "code", lambda output, **kwargs: outputs.append(output))

    voc_quality_view._show_command_result(show_success=False)

    assert errors == ["실행 실패 · 종료 코드 1"]
    assert outputs == ["Agent stop failed"]


def test_voc_dashboard_charts_use_project_tone_and_disable_wheel_scale():
    runs = [
        {
            "run_id": "RUN-1",
            "started_at": "2026-07-16T20:00:00+09:00",
            "counts": {"PASS": 30, "REVIEW_REQUIRED": 3, "FAIL": 1, "ERROR": 1, "NOT_RUN": 0},
        },
        {
            "run_id": "RUN-2",
            "started_at": "2026-07-16T21:00:00+09:00",
            "counts": {"PASS": 33, "REVIEW_REQUIRED": 1, "FAIL": 0, "ERROR": 0, "NOT_RUN": 1},
        },
    ]

    status_spec = voc_quality_view._build_voc_run_status_chart(runs).to_dict()
    history_spec = voc_quality_view._build_voc_run_history_chart(runs).to_dict()

    assert status_spec["encoding"]["color"]["scale"]["range"] == list(
        voc_quality_view.VOC_RUN_STATUS_COLORS.values()
    )
    status_legend = status_spec["encoding"]["color"]["legend"]
    assert status_legend["direction"] == "horizontal"
    assert status_legend["columns"] == len(voc_quality_view.VOC_RUN_STATUS_COLORS)
    assert status_legend["gridAlign"] == "all"
    assert voc_quality_view.VOC_OVERVIEW_PANEL_HEIGHT == 390
    assert history_spec["mark"]["interpolate"] == "monotone"
    assert history_spec["encoding"]["color"]["scale"]["range"] == list(
        voc_quality_view.VOC_HISTORY_COLORS.values()
    )
    assert "params" not in status_spec
    assert "params" not in history_spec


def test_voc_dashboard_agent_status_uses_icon_cards():
    markup = voc_quality_view._dashboard_agent_cards({
        "agents": [
            {"name": "Interpreter", "port": 6101, "healthy": True, "status": "RUNNING", "pid": "101"},
            {"name": "Critic", "port": 6105, "healthy": False, "status": "STOPPED", "pid": "-"},
        ]
    })

    assert markup.count("vqd-agent-card") == 2
    assert markup.count("<svg") == 2
    assert "vqd-agent-card good" in markup
    assert "vqd-agent-card bad" in markup


def test_voc_dashboard_connection_status_marks_only_current_value_active():
    markup = voc_quality_view._dashboard_a2a_status_panel({
        "decision": "NOT_VERIFIED",
        "recent_minutes": 30,
        "reason": "최근 완전 Trace가 없습니다.",
    })

    assert "vqd-connection-option active not-verified" in markup
    assert markup.count("vqd-connection-option inactive") == 2
    assert "최근 완전 Trace가 없습니다." in markup
    assert "최근 30분 기준" in markup


def test_goal_monitor_renders_result_below_agent_pipeline(monkeypatch):
    render_order = []
    state = {"goal_testcase_selected_case_id": "TC-01"}

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view, "_goal_testcase_selector", lambda: render_order.append("selector"))
    monkeypatch.setattr(voc_quality_view, "pipeline_trace_events", lambda *_args: {})
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_pipeline_comparison",
        lambda *_args, **_kwargs: render_order.append("pipeline"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_goal_testcase_result",
        lambda case_id: render_order.append(f"result:{case_id}"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_selected_goal_testcase",
        lambda: {"case_id": "TC-01"},
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_goal_execution_step",
        lambda case: render_order.append(f"pipeline-action:{case['case_id']}"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_goal_judge_step",
        lambda case: render_order.append(f"judge-select:{case['case_id']}"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_goal_judge_result",
        lambda case_id: render_order.append(f"judge-result:{case_id}"),
    )

    voc_quality_view.render_goal_monitor()

    assert render_order == [
        "selector",
        "pipeline-action:TC-01",
        "pipeline",
        "result:TC-01",
        "judge-select:TC-01",
        "judge-result:TC-01",
    ]


def test_goal_testcase_selector_uses_user_facing_title():
    import inspect

    source = inspect.getsource(voc_quality_view._goal_testcase_selector.__wrapped__)

    assert 'st.markdown("### Test Case 선택 실행")' in source
    assert 'st.caption("읽기 전용 · 행 클릭으로 선택")' in source
    assert "읽기 전용 목록입니다." not in source
    assert "horizontal=True" in source
    assert 'st.markdown("### test_cases.json 선택 실행")' not in source


def test_goal_pipeline_uses_compact_inline_guide():
    import inspect

    source = inspect.getsource(voc_quality_view.render_goal_monitor)

    assert 'st.markdown("### 실시간 Agent Pipeline")' in source
    assert 'st.caption("실행 중 2초 갱신 · 종료 후 최근 Trace 유지")' in source
    assert "실행 중에는 현재 흐름을 2초 간격으로 확인하고" not in source
    assert "horizontal=True" in source


def test_manual_result_renders_human_readable_judgment_evidence():
    app = AppTest.from_file("tests/fixtures/voc_manual_result_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert any("판정 근거" in info.value for info in app.info)
    assert any("질문 해석과 검색 범위" in markdown.value for markdown in app.markdown)
    assert any("요약 후보 평가와 선택 근거" in markdown.value for markdown in app.markdown)
    assert any("Critic 검토와 반영 결과" in markdown.value for markdown in app.markdown)
    assert any("Agent 실행 이력" in markdown.value for markdown in app.markdown)
    assert not app.json


def test_manual_judge_provider_cards_default_to_anthropic_and_switch_on_click():
    app = AppTest.from_file(
        "tests/fixtures/voc_manual_judge_cards_app.py",
        default_timeout=15,
    )
    app.run()

    assert not app.exception
    assert "카드를 클릭하여 선택" in app.button[0].label
    assert "✓ 현재 선택" in app.button[1].label
    assert "gpt-5.2" in app.button[0].label
    assert "claude-opus-4-6" in app.button[1].label
    assert app.session_state["goal_TC-01_judge_provider"] == "anthropic"

    app.button[0].click().run()

    assert not app.exception
    assert app.session_state["goal_TC-01_judge_provider"] == "openai"
    assert "✓ 현재 선택" in app.button[0].label
    assert "카드를 클릭하여 선택" in app.button[1].label


def test_trace_started_event_becomes_completed_after_pipeline_advances():
    events = [
        {"source": "Improver", "target": "Critic", "operation": "ReviewPolicy", "status": "started"},
        {"source": "Critic", "target": "Improver", "operation": "RefinePolicy", "status": "started"},
    ]

    assert voc_quality_view._trace_event_display_statuses(events, running=True) == [
        "completed",
        "started",
    ]
    assert voc_quality_view._trace_event_display_statuses(events, running=False) == [
        "completed",
        "ended",
    ]


def test_trace_display_events_merges_started_and_success_into_one_step():
    events = [
        {
            "timestamp": "2026-07-17T10:00:00+09:00",
            "source": "Summarizer",
            "target": "Critic",
            "operation": "ReviewPolicy",
            "status": "started",
            "input_keywords": ["개선안"],
        },
        {
            "timestamp": "2026-07-17T10:00:03+09:00",
            "source": "Summarizer",
            "target": "Critic",
            "operation": "ReviewPolicy",
            "status": "success",
            "duration_ms": 3000,
        },
    ]

    display = voc_quality_view._trace_display_events(events)

    assert len(display) == 1
    assert display[0]["status"] == "success"
    assert display[0]["started_at"] == "2026-07-17T10:00:00+09:00"
    assert display[0]["input_keywords"] == ["개선안"]


def test_manual_pipeline_renders_every_raw_log_below_merged_agent_calls(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {"goal_testcase_started_at": "2026-07-17T10:00:00+09:00"},
    )
    monkeypatch.setattr(voc_quality_view.st, "html", rendered.append)
    snapshot = {
        "trace_id": "trace-raw-1",
        "events": [
            {
                "timestamp": "2026-07-17T10:00:00+09:00",
                "source": "Orchestrator",
                "target": "Interpreter",
                "operation": "ParseQuestion",
                "status": "started",
            },
            {
                "timestamp": "2026-07-17T10:00:02+09:00",
                "source": "Orchestrator",
                "target": "Interpreter",
                "operation": "ParseQuestion",
                "status": "success",
                "duration_ms": 2000,
            },
        ],
    }

    voc_quality_view._render_agent_pipeline_v2(snapshot, running=True)

    html = rendered[0]
    assert html.index("실시간 실행 이벤트(Agent 호출)") < html.index(
        "실시간 실행 이벤트(원본 로그)"
    )
    assert "Agent 호출 1건" in html
    assert "원본 로그 2건 · 전체 표시" in html
    assert 'data-event-count="2"' in html
    assert "started·success·failure 로그를 병합하거나 상태를 보정하지 않고 그대로 표시" in html
    assert ".flow2-trace-track{display:flex;align-items:flex-start;" in html
    assert '<details class="flow2-trace flow2-raw-trace">' in html
    assert '<details class="flow2-trace flow2-raw-trace" open>' not in html
    assert "content:'펼치기 ＋'" in html
    assert ".flow2-raw-trace[open] .flow2-raw-summary:after{content:'접기 −'}" in html
    raw_section = html.split("실시간 실행 이벤트(원본 로그)", maxsplit=1)[1]
    assert "#01" in raw_section
    assert "#02" in raw_section
    assert "<em>시작</em>" in raw_section
    assert "<em>성공</em>" in raw_section


def test_trace_display_events_preserves_repeated_agent_calls_without_omission():
    events = [
        {
            "timestamp": "2026-07-17T10:00:00+09:00",
            "source": "Critic",
            "target": "Improver",
            "operation": "RefinePolicy",
            "status": "started",
        },
        {
            "timestamp": "2026-07-17T10:00:01+09:00",
            "source": "Critic",
            "target": "Improver",
            "operation": "RefinePolicy",
            "status": "started",
        },
        {
            "timestamp": "2026-07-17T10:00:02+09:00",
            "source": "Critic",
            "target": "Improver",
            "operation": "RefinePolicy",
            "status": "success",
        },
        {
            "timestamp": "2026-07-17T10:00:03+09:00",
            "source": "Critic",
            "target": "Improver",
            "operation": "RefinePolicy",
            "status": "success",
        },
    ]

    display = voc_quality_view._trace_display_events(events)

    assert len(display) == 2
    assert [item["status"] for item in display] == ["success", "success"]
    assert [item["started_at"] for item in display] == [
        "2026-07-17T10:00:00+09:00",
        "2026-07-17T10:00:01+09:00",
    ]


@pytest.mark.parametrize(
    ("previous_target", "target", "operation", "expected_transition", "expected_label"),
    [
        ("Improver", "Critic", "ReviewPolicy", "Agent 6 → Agent 5", "개선안 재검토"),
        ("Critic", "Improver", "RefinePolicy", "Agent 5 → Agent 6", "수정 요청 반영"),
        ("Critic", "Summarizer", "UnknownReturn", "Agent 5 → Agent 3", "이전 단계 재호출"),
        ("Improver", "Evaluator", "UnknownReview", "Agent 6 → Agent 4", "이전 단계 재호출"),
    ],
)
def test_trace_flow_explanation_covers_feedback_and_unknown_reverse_routes(
    previous_target,
    target,
    operation,
    expected_transition,
    expected_label,
):
    flow = voc_quality_view._trace_flow_explanation(
        {
            "source": "Summarizer",
            "target": target,
            "operation": operation,
            "status": "success",
        },
        {
            "source": "Summarizer",
            "target": previous_target,
            "operation": "Previous",
            "status": "success",
        },
    )

    assert flow["transition"] == expected_transition
    assert flow["label"] == expected_label
    assert flow["reason"]
    assert flow["inferred"] is operation.startswith("Unknown")


def test_all_known_pipeline_operations_have_explicit_flow_reasons():
    for operation in voc_quality_view.TRACE_FLOW_EXPLANATIONS:
        flow = voc_quality_view._trace_flow_explanation(
            {
                "source": "Summarizer",
                "target": "Critic",
                "operation": operation,
                "status": "success",
            }
        )
        assert flow["reason"]
        assert flow["inferred"] is False


def test_manual_pipeline_timeline_explains_policy_feedback_loop(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {"goal_testcase_started_at": "2026-07-17T10:00:00+09:00"},
    )
    monkeypatch.setattr(voc_quality_view.st, "html", rendered.append)
    snapshot = {
        "trace_id": "trace-feedback",
        "events": [
            {
                "timestamp": "2026-07-17T10:00:01+09:00",
                "source": "Summarizer",
                "target": "Improver",
                "operation": "ImprovePolicy",
                "status": "success",
            },
            {
                "timestamp": "2026-07-17T10:00:02+09:00",
                "source": "Summarizer",
                "target": "Critic",
                "operation": "ReviewPolicy",
                "status": "success",
            },
            {
                "timestamp": "2026-07-17T10:00:03+09:00",
                "source": "Summarizer",
                "target": "Improver",
                "operation": "RefinePolicy",
                "status": "success",
            },
        ],
    }

    voc_quality_view._render_agent_pipeline_v2(snapshot, running=False)

    html = rendered[0]
    assert "Agent 6 → Agent 5 · 개선안 재검토" in html
    assert "Agent 5 → Agent 6 · 수정 요청 반영" in html
    assert "확정하기 전에 품질과 실행 가능성을 확인" in html
    assert "수정이 필요하다고 판단" in html
    assert "Trace 사유 미기록·추정" in html


def test_pipeline_run_summary_names_current_agent_number(monkeypatch):
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {
            "goal_testcase_started_at": "2026-07-17T10:00:00+09:00",
            "goal_testcase_running_case_id": "TC-01",
        },
    )
    snapshot = {
        "events": [
            {
                "timestamp": "2026-07-17T10:00:02+09:00",
                "source": "Improver",
                "target": "Critic",
                "operation": "ReviewPolicy",
                "status": "started",
            }
        ]
    }

    summary = voc_quality_view._pipeline_run_summary(snapshot, running=True)

    assert summary["state"] == "running"
    assert summary["label"] == "Agent 5 · Critic 수행 중"
    assert summary["active_agent_number"] == 5
    assert summary["active_agent_name"] == "Critic"


def test_pipeline_run_summary_exposes_completed_status_and_run_metrics(monkeypatch):
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {
            "goal_testcase_started_at": "2026-07-17T10:00:00+09:00",
            "goal_testcase_completed_at": "2026-07-17T10:00:05+09:00",
            "goal_testcase_result": {
                "mode": "voc",
                "case": {"case_id": "TC-01"},
                "execution": {"ok": True, "result": {"ok": True}},
            },
        },
    )
    snapshot = {
        "events": [
            {
                "timestamp": "2026-07-17T10:00:00+09:00",
                "source": "Orchestrator",
                "target": "Interpreter",
                "operation": "ParseQuestion",
                "status": "started",
            },
            {
                "timestamp": "2026-07-17T10:00:05+09:00",
                "source": "Orchestrator",
                "target": "Interpreter",
                "operation": "ParseQuestion",
                "status": "success",
            },
        ]
    }

    summary = voc_quality_view._pipeline_run_summary(snapshot, running=False)

    assert summary == {
        "state": "completed",
        "label": "수행 완료",
        "case_id": "TC-01",
        "steps": 1,
        "successes": 1,
        "failures": 0,
        "duration_seconds": 5.0,
        "active_agent_number": None,
        "active_agent_name": "",
    }


def test_manual_pipeline_timeline_starts_with_active_preparation_card(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {
            "goal_testcase_started_at": "2026-07-17T10:00:00+09:00",
            "goal_testcase_running_case_id": "TC-01",
        },
    )
    monkeypatch.setattr(voc_quality_view.st, "html", rendered.append)

    voc_quality_view._render_agent_pipeline_v2({"trace_id": "", "events": []}, running=True)

    html = rendered[0]
    assert html.index("테스트 수행 준비") < html.index("진행 중")
    assert "flow2-preparation active" in html
    assert html.count('<article class="flow2-preparation') == 3
    assert "준비 단계 1–3" in html
    assert "준비 단계 4–5" in html
    assert ".flow2-preparation{position:relative;width:280px;min-width:280px;height:154px" in html
    assert (
        f"min-width:280px;height:{voc_quality_view.MANUAL_EVENT_CARD_HEIGHT}px"
        in html
    )
    assert "0/5 완료 · 순서대로 처리 중" in html
    assert "Agent 실행 상태 점검" in html
    assert "Run 폴더 생성" in html
    assert "Rubric과 Test Case 스냅샷 저장" in html
    assert "증적 파일 준비" in html
    assert "별도 Python 프로세스 시작" in html


def test_manual_pipeline_preparation_card_completes_after_first_event(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {"goal_testcase_started_at": "2026-07-17T10:00:00+09:00"},
    )
    monkeypatch.setattr(voc_quality_view.st, "html", rendered.append)
    snapshot = {
        "trace_id": "trace-1",
        "events": [
            {
                "timestamp": "2026-07-17T10:00:01+09:00",
                "source": "Orchestrator",
                "target": "Interpreter",
                "operation": "ParseQuestion",
                "status": "started",
            }
        ],
    }

    voc_quality_view._render_agent_pipeline_v2(snapshot, running=True)

    html = rendered[0]
    assert "flow2-preparation completed" in html
    assert "준비 완료" in html
    assert html.index("테스트 수행 준비") < html.index("ParseQuestion")


def test_manual_pipeline_preparation_card_visualizes_each_step_status(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {
            "goal_testcase_started_at": "2026-07-17T10:00:00+09:00",
            "goal_testcase_running_case_id": "TC-01",
        },
    )
    monkeypatch.setattr(voc_quality_view.st, "html", rendered.append)
    preparation = voc_quality_view._new_manual_preparation_progress()
    preparation["steps"][0]["status"] = "success"
    preparation["steps"][1]["status"] = "success"
    preparation["steps"][2]["status"] = "active"
    preparation["current_step"] = 3

    voc_quality_view._render_agent_pipeline_v2(
        {"trace_id": "", "events": []},
        running=True,
        preparation=preparation,
    )

    html = rendered[0]
    assert "2/5 완료 · 순서대로 처리 중" in html
    assert html.count("class='success'") == 2
    assert html.count("class='active'") == 1
    assert html.count("class='waiting'") == 2
    assert "Rubric과 Test Case 스냅샷 저장" in html


def test_manual_pipeline_preflight_runs_inside_background_task(monkeypatch):
    captured = {}
    snapshot = {"all_running": False, "agents": []}
    monkeypatch.setattr(voc_quality_view, "agent_status_snapshot", lambda: snapshot)

    def fake_run(case_id, timeout_seconds, judge_config):
        captured.update(
            case_id=case_id,
            timeout_seconds=timeout_seconds,
            judge_config=judge_config,
        )
        return {"case": {"case_id": case_id}}

    monkeypatch.setattr(voc_quality_view, "run_test_case", fake_run)

    result = voc_quality_view._execute_goal_testcase("TC-01")

    assert result["agent_snapshot"] is snapshot
    assert result["testcase_result"]["case"]["case_id"] == "TC-01"
    assert captured == {
        "case_id": "TC-01",
        "timeout_seconds": 20,
        "judge_config": {
            "enabled": False,
            "provider": "anthropic",
            "model": "claude-opus-4-6",
        },
    }


def test_manual_pipeline_background_job_completes_all_preparation_steps(monkeypatch):
    monkeypatch.setattr(
        voc_quality_view,
        "agent_status_snapshot",
        lambda: {"all_running": True, "agents": []},
    )

    def fake_run(case_id, timeout_seconds, judge_config, progress_callback=None):
        assert timeout_seconds == 180
        assert progress_callback is not None
        progress_callback(2, "active")
        for step in (2, 3, 4, 5):
            progress_callback(step, "success")
        return {"case": {"case_id": case_id}}

    monkeypatch.setattr(voc_quality_view, "run_test_case", fake_run)
    job_id = voc_background_job_service.start_background_job(
        "manual-pipeline-test",
        "TC-01",
        voc_quality_view._execute_goal_testcase,
        "TC-01",
        progress={
            "preparation": voc_quality_view._new_manual_preparation_progress()
        },
    )

    deadline = time.time() + 3
    snapshot = None
    while time.time() < deadline:
        snapshot = voc_background_job_service.background_job_snapshot(job_id)
        if snapshot and snapshot["done"]:
            break
        time.sleep(0.01)

    preparation = snapshot["progress"]["preparation"]
    assert snapshot["status"] == "COMPLETED"
    assert preparation["status"] == "COMPLETED"
    assert [step["status"] for step in preparation["steps"]] == ["success"] * 5
    voc_background_job_service.discard_background_job(job_id)


def test_voc_background_job_continues_without_page_render_cycle():
    started = threading.Event()
    release = threading.Event()

    def worker(job_id):
        voc_background_job_service.update_background_job(
            job_id,
            progress={"stage": "running"},
        )
        started.set()
        assert release.wait(2)
        return {"ok": True}

    job_id = voc_background_job_service.start_background_job(
        "test",
        "TC-01",
        worker,
    )
    assert started.wait(2)
    assert voc_background_job_service.background_job_snapshot(job_id)["status"] == "RUNNING"

    release.set()
    deadline = time.time() + 3
    snapshot = None
    while time.time() < deadline:
        snapshot = voc_background_job_service.background_job_snapshot(job_id)
        if snapshot and snapshot["done"]:
            break
        time.sleep(0.01)

    assert snapshot["status"] == "COMPLETED"
    assert snapshot["result"] == {"ok": True}
    voc_background_job_service.discard_background_job(job_id)


def test_manual_judge_result_renders_directly_as_evaluation_section():
    app = AppTest.from_file(
        "tests/fixtures/voc_manual_judge_result_app.py",
        default_timeout=15,
    )
    app.run()

    assert not app.exception
    assert {metric.label for metric in app.metric} == {"판정", "총점", "독립성", "수행 시간"}
    assert any("독립 LLM 평가/판정 결과" in item.value for item in app.markdown)
    assert app.dataframe[0].value.iloc[0]["평가 차원"] == "accuracy"


def test_pipeline_evidence_parsers_tolerate_invalid_or_partial_values():
    assert voc_quality_view._parse_json_mapping("not-json") == {}
    assert voc_quality_view._parse_json_mapping({"task": "both"}) == {"task": "both"}
    assert voc_quality_view._parse_pipeline_trace_summary(
        "audit_trace_id=trace-1; retrieved=8; summary_refined"
    ) == {
        "values": {"audit_trace_id": "trace-1", "retrieved": "8"},
        "flags": ["summary_refined"],
    }


def test_goal_testcase_cell_click_selects_its_row(monkeypatch):
    table_key = "goal_testcase_table_1"
    state = {
        "goal_testcase_selected_case_id": "TC-01",
        table_key: {
            "selection": {
                "rows": [0],
                "columns": [],
                "cells": [[2, "질문"]],
            }
        }
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    voc_quality_view._remember_goal_testcase_selection(
        table_key,
        ["TC-01", "TC-02", "TC-03", "TC-04"],
    )

    assert state["goal_testcase_selected_case_id"] == "TC-03"
    assert state["goal_testcase_selection_changed"] is True
    assert state[table_key] == {
        "selection": {"rows": [2], "columns": [], "cells": []}
    }


def test_manual_pipeline_initializes_selected_case_before_first_button_click(
    monkeypatch,
):
    state = {}
    cases = [
        {"case_id": "TC-01", "question": "첫 번째 질문"},
        {"case_id": "TC-02", "question": "두 번째 질문"},
    ]
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view,
        "load_test_cases",
        lambda: {"cases": cases},
    )

    selected = voc_quality_view._ensure_goal_testcase_selection()

    assert selected == cases[0]
    assert state["goal_testcase_selected_case_id"] == "TC-01"


def test_manual_pipeline_first_click_callback_starts_background_job(monkeypatch):
    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    state = State(
        goal_testcase_result={"stale": True},
        goal_testcase_trace_id="old-trace",
    )
    captured = {}

    def fake_start_background_job(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "manual-job-1"

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view,
        "start_background_job",
        fake_start_background_job,
    )

    voc_quality_view._start_goal_testcase_pipeline("TC-01")

    assert state["goal_testcase_job_id"] == "manual-job-1"
    assert state["goal_testcase_running_case_id"] == "TC-01"
    assert "goal_testcase_result" not in state
    assert "goal_testcase_trace_id" not in state
    assert captured["args"][:2] == ("manual-pipeline", "TC-01")
    assert captured["kwargs"]["progress"]["preparation"]["status"] == "RUNNING"


def test_embedded_voc_runtime_is_complete():
    health = runtime_health()
    assert health["ok"], health["missing"]
    assert Path(health["runtime_dir"]) == PROJECT_DIR / "voc_quality_runtime"


def test_testcase_distribution_and_rubric_total():
    summary = get_test_case_summary()
    assert summary["total"] == 20
    assert summary["categories"] == {
        "normal_voc": 8,
        "ambiguous_question": 3,
        "compound_complaint": 3,
        "no_data": 2,
        "typo_or_ungrammatical": 2,
        "fault_condition": 2,
    }
    rubric = load_system_rubric()
    assert rubric["total_points"] == 100
    assert sum(category["max_points"] for category in rubric["categories"].values()) == 100


def test_testcase_page_uses_same_35_case_catalog_as_batch_execution():
    app = AppTest.from_file(
        "tests/fixtures/voc_testcase_catalog_app.py", default_timeout=15
    )
    app.run()

    assert not app.exception
    hidden_catalog_guide = (
        "일괄 TC 수행과 동일한 통합 카탈로그를 기준으로 관리합니다. "
        "VOC 질문형 Case뿐 아니라 장애 주입·Agent 역할·품질 게이트 Case도 포함합니다."
    )
    assert all(item.value != hidden_catalog_guide for item in app.caption)
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["전체 실행 대상"] == "35건"
    assert metrics["VOC 질문형"] == "20건"
    assert metrics["추가 검증 Case"] == "15건"
    assert metrics["구현 상태"] == "26건 완료"
    headings = [item.value for item in app.markdown]
    assert "#### :material/target: 실행 대상 요약" in headings
    assert "#### :material/bar_chart: 검증 영역별 Case 구성" in headings
    assert "#### :material/search: Case 탐색" in headings
    assert "#### :material/list_alt: Case 목록" in headings
    assert "#### 통합 테스트케이스 목록" not in headings
    assert "#### :material/description: Case 상세" in headings
    assert len(app.get("vega_lite_chart")) == 1
    assert len(app.get("column")) == 11
    assert any(
        item.value == "검색 결과 35건 · 행을 선택하면 우측에서 상세 확인"
        for item in app.caption
    )

    catalog_table = app.dataframe[0].value
    assert len(catalog_table) == 35
    assert list(catalog_table.columns) == ["Case ID", "검증 영역", "이름", "구현 상태"]
    assert set(catalog_table["Case ID"]) >= {"TC-01", "FT-01", "AG-01", "QG-01"}
    assert set(app.dataframe[0].proto.selection_mode) == {
        Dataframe.SelectionMode.SINGLE_ROW_REQUIRED,
        Dataframe.SelectionMode.SINGLE_CELL,
    }
    assert json.loads(app.dataframe[0].proto.selection_default)["selection"]["rows"] == [0]
    layout_columns = app.get("column")
    assert layout_columns[6].proto.weight < layout_columns[7].proto.weight
    assert layout_columns[8].proto.weight == pytest.approx(
        layout_columns[5].proto.weight
    )
    column_config = json.loads(app.dataframe[0].proto.columns)
    assert column_config["이름"]["width"] == 150
    assert column_config["구현 상태"]["width"] == 130
    assert "**TC-01** · 모바일 앱 자동차보험 갱신 오류" in headings


def test_testcase_group_chart_hides_validation_area_axis_title():
    rows = pd.DataFrame(
        [
            {"검증 영역": "VOC 기능", "Case 수": 20},
            {"검증 영역": "장애 주입", "Case 수": 6},
        ]
    )

    spec = voc_quality_view._build_testcase_group_chart(rows).to_dict()

    assert spec["encoding"]["y"]["title"] is None
    assert spec["encoding"]["y"]["field"] == "검증 영역"
    assert spec["encoding"]["x"]["title"] is None


def test_quality_catalog_defines_exactly_35_unique_cases():
    catalog = load_quality_test_catalog()
    cases = catalog["cases"]
    case_ids = [item["case_id"] for item in cases]

    assert catalog["suite_id"] == "VOC-QA-35"
    assert catalog["total_cases"] == len(cases) == 35
    assert len(case_ids) == len(set(case_ids))
    assert catalog["baseline_claim"]["status"] == "PENDING_EVIDENCE"
    assert catalog["baseline_claim"]["expected_summary"] == {
        "total": 35,
        "passed": 33,
        "failed": 2,
    }


def test_judge_validity_and_evidence_contracts_are_consistent():
    judge = load_independent_judge_rubric()
    validity = load_improvement_validity_rubric()
    evidence = load_quality_evidence_contract()

    assert sum(item["max_points"] for item in judge["dimensions"].values()) == 100
    assert sum(item["max_points"] for item in validity["dimensions"].values()) == 100
    assert judge["judge_provider_policy"] == "runtime_configurable"
    assert judge["default_provider"] == "anthropic"
    assert "QA_REVIEWED" in validity["workflow_states"]
    assert "BUSINESS_APPROVED" in validity["workflow_states"]
    assert set(evidence["execution_statuses"]) == {
        "PASS", "FAIL", "ERROR", "NOT_RUN", "REVIEW_REQUIRED"
    }
    assert set(evidence["model_independence_grades"]) == {"A", "B", "C"}
    assert set(evidence["run_lifecycle_statuses"]) == {
        "RUNNING", "COMPLETED", "ERROR", "INTERRUPTED"
    }


def test_quality_rubric_menu_exposes_three_separate_stages(monkeypatch):
    assert voc_quality_view.RUBRIC_STAGE_OPTIONS == (
        "내부 Pipeline 품질",
        "독립 LLM Judge",
        "개선안 타당성",
    )

    judge_rows = voc_quality_view._rubric_rows(
        load_independent_judge_rubric()["dimensions"]
    )
    validity_rows = voc_quality_view._rubric_rows(
        load_improvement_validity_rubric()["dimensions"]
    )
    assert sum(row["배점"] for row in judge_rows) == 100
    assert sum(row["배점"] for row in validity_rows) == 100
    assert all("PASS 하한" in row for row in judge_rows + validity_rows)

    rendered = []
    segmented_labels = []
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view.st, "caption", lambda *_args, **_kwargs: None)

    def select_stage(label, *_args, **_kwargs):
        segmented_labels.append(label)
        return "독립 LLM Judge"

    monkeypatch.setattr(
        voc_quality_view.st,
        "segmented_control",
        select_stage,
    )
    monkeypatch.setattr(voc_quality_view, "_render_rubric_management", rendered.append)

    voc_quality_view.render_rubric()

    assert segmented_labels == ["수정할 평가 단계"]
    assert rendered == ["독립 LLM Judge"]


def test_rubric_decision_boundaries_keep_adjacent_ranges_linked():
    rubric = load_system_rubric()
    spec = voc_quality_view.QUALITY_RUBRIC_SPECS["internal_pipeline"]

    linked = voc_quality_view._link_decision_ranges(
        rubric["deployment_decisions"],
        spec,
        boundary_index=1,
        boundary_score=82,
    )

    assert linked[0] == {"decision": "배포 가능", "min": 90, "max": 100}
    assert linked[1] == {
        "decision": "조건부 배포 가능 — 개선 후 재검증",
        "min": 82,
        "max": 89.99,
    }
    assert linked[2]["min"] == 70
    assert linked[2]["max"] == 81.99
    assert linked[3]["min"] == 0
    assert linked[3]["max"] == 69.99
    assert list(voc_quality_view._decision_display_frame(linked, spec).columns)[0] == "decision"


def test_unified_rubric_page_renders_gauges_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_rubric_app.py", default_timeout=30)
    app.run()

    assert not app.exception
    assert [control.label for control in app.segmented_control] == ["수정할 평가 단계"]
    markdown = [item.value for item in app.markdown]
    captions = [item.value for item in app.caption]
    assert "## 평가 기준 구분 선택" not in markdown
    assert "## 평가 기준 설정" not in markdown
    assert "조회하고 수정할 품질 평가 단계를 선택하세요." not in captions
    assert all("조회와 관리를 한 화면에 통합했습니다" not in item for item in captions)
    assert all(
        item.value != "총점·세부 배점·판정 구간 검증을 통과했습니다."
        for item in app.success
    )
    assert app.segmented_control[0].proto.label_visibility.value == LabelVisibility.COLLAPSED
    assert all(slider.label != "의도 파악 (intent)" for slider in app.slider)
    assert any(slider.label == "배포 가능 시작 점수" for slider in app.slider)
    assert any(button.label == "평가 기준 저장" for button in app.button)
    assert any(button.label == "판정 구간 미리보기" for button in app.button)
    assert all(item.label != "평가 항목명" for item in app.text_input)
    assert "### 항목별 배점 설정" in markdown
    assert "#### ① 평가 항목 선택" not in markdown
    assert "### 판정 구간" in markdown
    total_index = next(
        index
        for index, value in enumerate(markdown)
        if "100 / 100점" in value
    )
    assert total_index < markdown.index("### 판정 구간")
    assert "##### 평가 항목 합계 점수" not in markdown
    assert all(
        "모든 평가 항목의 세부 배점을 합산한 최종 점수입니다." not in item
        for item in captions
    )
    assert [item.label for item in app.status] == ["즉시 FAIL·보류 규칙"]
    assert all(
        getattr(item, "type", "") != "status"
        for item in app._tree[0].children.values()
    )
    assert "#### ② Interpreter 해석 정확성 · 세부 배점" not in markdown
    item_table = next(
        item
        for item in app.dataframe
        if item.key == "rubric_edit_internal_pipeline_widget_item_table"
    )
    assert set(item_table.proto.selection_mode) == {
        Dataframe.SelectionMode.SINGLE_ROW_REQUIRED,
        Dataframe.SelectionMode.SINGLE_CELL,
    }
    assert json.loads(item_table.proto.selection_default)["selection"]["rows"] == [0]
    assert len(app.get("vega_lite_chart")) == 0
    assert len(app.get("progress")) == 0
    assert any("100 / 100점" in item.value for item in app.markdown)
    assert all(
        getattr(item, "key", None) != "rubric_edit_internal_pipeline_save"
        for item in app._tree[0].children.values()
    )

    next(
        button
        for button in app.button
        if button.label == "판정 구간 미리보기"
    ).click().run()

    assert not app.exception
    assert len(app.dataframe) == 2
    assert list(app.dataframe[1].value.columns)[:3] == ["decision", "min", "max"]


def test_rubric_stage_header_keeps_the_same_controls_and_compact_json_actions():
    app = AppTest.from_file("tests/fixtures/voc_rubric_app.py", default_timeout=30)
    app.run()

    expected_provider_states = {
        "내부 Pipeline 품질": ("해당 없음", True),
        "독립 LLM Judge": ("anthropic", False),
        "개선안 타당성": ("해당 없음", True),
    }
    expected_rubric_types = {
        "내부 Pipeline 품질": "internal_pipeline",
        "독립 LLM Judge": "independent_judge",
        "개선안 타당성": "improvement_validity",
    }
    for stage, expected_provider in expected_provider_states.items():
        app.segmented_control[0].set_value(stage).run()

        assert not app.exception
        assert [item.label for item in app.text_input[:2]] == ["Rubric 버전", "기준명"]
        provider = next(
            item for item in app.selectbox if item.label == "기본 Judge Provider"
        )
        assert (provider.value, provider.disabled) == expected_provider
        assert any(item.label == "JSON D/L" for item in app.get("download_button"))
        assert any(
            item.proto.popover.label == "JSON Up"
            for item in app.get("popover")
        )
        save_button = next(
            item for item in app.button if item.label == "평가 기준 저장"
        )
        assert save_button.key == (
            f"rubric_edit_{expected_rubric_types[stage]}_save"
        )


def test_rubric_detail_dialog_renders_existing_scoring_controls():
    app = AppTest.from_file(
        "tests/fixtures/voc_rubric_detail_dialog_app.py",
        default_timeout=30,
    )
    app.run()

    assert not app.exception
    assert "#### Interpreter 해석 정확성" in [
        item.value for item in app.markdown
    ]
    assert len(app.get("vega_lite_chart")) == 1
    assert any(button.label == "설정 완료" for button in app.button)
    intent = app.slider[0]
    assert intent.label == "의도 파악 (intent)"
    assert intent.min == 0
    assert intent.max == 4

    intent.set_value(4).run()

    assert not app.exception
    draft = app.session_state["rubric_edit_internal_pipeline_draft"]
    assert draft["categories"]["interpreter"]["criteria"]["intent"] == 4
    assert draft["categories"]["interpreter"]["max_points"] == 14


def test_rubric_detail_dialog_navigates_to_previous_and_next_items():
    app = AppTest.from_file(
        "tests/fixtures/voc_rubric_detail_dialog_app.py",
        default_timeout=30,
    )
    app.run()

    assert not app.exception
    assert app._tree[2][0].proto.dialog.width == Block.Dialog.MEDIUM
    navigation_style = app.get("html")[0].proto.body
    assert "background: #F2F6FB" in navigation_style
    assert "border: 1px solid #B9CBE0" in navigation_style
    assert app.button[0].label == "< 이전"
    assert app.button[0].help == "이전 · 성능"
    assert app.button[1].label == "다음 >"
    assert app.button[1].help == "다음 · Retriever 검색 관련성"

    app.button[1].click().run()

    assert not app.exception
    assert "#### Retriever 검색 관련성" in [
        item.value for item in app.markdown
    ]
    assert app.session_state["rubric_edit_internal_pipeline_selected_item"] == "retriever"
    assert app.button[0].label == "< 이전"
    assert app.button[0].help == "이전 · Interpreter 해석 정확성"

    app.button[0].click().run()

    assert not app.exception
    assert "#### Interpreter 해석 정확성" in [
        item.value for item in app.markdown
    ]


def test_improver_detail_dialog_has_stable_content_height_without_scroll():
    app = AppTest.from_file("tests/fixtures/voc_rubric_app.py", default_timeout=30)
    app.session_state[
        "rubric_edit_internal_pipeline_selected_item_detail_dialog_request"
    ] = "improver"
    app.run()

    improver_sliders = [
        slider
        for slider in app.slider
        if "widget_improver_criterion" in str(slider.key)
    ]
    criteria_panel = app._tree[2][0][0][1]
    navigation_style = app.get("html")[0].proto.body

    assert not app.exception
    assert len(improver_sliders) == 5
    assert criteria_panel.proto.height_config.use_content
    assert "min-height: 430px" in navigation_style
    assert "overflow: visible" in navigation_style

    next(
        button
        for button in app.button
        if button.key == "rubric_detail_next_internal_pipeline_improver"
    ).click().run()

    assert not app.exception
    assert "#### Agent 연계 품질" in [
        item.value for item in app.markdown
    ]
    assert app._tree[2][0][0][1].proto.height_config.use_content


def test_rubric_detail_dialog_closes_after_navigation_with_one_done_click():
    app = AppTest.from_file("tests/fixtures/voc_rubric_app.py", default_timeout=30)
    app.session_state[
        "rubric_edit_internal_pipeline_selected_item"
    ] = "interpreter"
    app.session_state[
        "rubric_edit_internal_pipeline_selected_item_detail_dialog_request"
    ] = "interpreter"
    app.run()

    next(
        button
        for button in app.button
        if button.key == "rubric_detail_next_internal_pipeline_interpreter"
    ).click().run()
    next(
        button
        for button in app.button
        if button.key == "rubric_detail_previous_internal_pipeline_retriever"
    ).click().run()
    next(
        button
        for button in app.button
        if button.key == "rubric_detail_next_internal_pipeline_interpreter"
    ).click().run()
    next(
        button
        for button in app.button
        if button.key == "rubric_detail_done_internal_pipeline_retriever"
    ).click().run()

    assert not app.exception
    assert all(
        "rubric_detail_" not in str(button.key)
        for button in app.button
    )
    assert (
        "rubric_edit_internal_pipeline_selected_item_detail_dialog_item"
        not in app.session_state
    )
    assert (
        "rubric_edit_internal_pipeline_selected_item_detail_dialog_item_opened"
        not in app.session_state
    )
    assert (
        "rubric_edit_internal_pipeline_selected_item_detail_dialog_request"
        not in app.session_state
    )


def test_rubric_stage_switch_clears_all_open_dialog_state():
    app = AppTest.from_file("tests/fixtures/voc_rubric_app.py", default_timeout=30)
    app.session_state[
        "rubric_edit_internal_pipeline_selected_item_detail_dialog_request"
    ] = "interpreter"
    app.run()

    next(
        button
        for button in app.button
        if button.key == "rubric_detail_next_internal_pipeline_interpreter"
    ).click().run()
    app.segmented_control[0].set_value("독립 LLM Judge").run()

    assert not app.exception
    assert all(
        "rubric_detail_" not in str(button.key)
        for button in app.button
    )
    assert all(
        "detail_dialog" not in str(key)
        for key in app.session_state.filtered_state
    )


def test_rubric_total_summary_only_shows_score_and_adjustment_guidance():
    app = AppTest.from_file(
        "tests/fixtures/voc_rubric_total_summary_app.py",
        default_timeout=15,
    )
    app.run()

    assert not app.exception
    assert any("99 / 100점" in item.value for item in app.markdown)
    assert any("배점 조정 필요" in item.value for item in app.markdown)
    assert any(
        "100점까지 +1점 조정이 필요합니다." in item.value
        for item in app.caption
    )
    assert all(
        "평가 항목 합계 점수" not in item.value
        for item in app.markdown
    )
    assert all(
        "모든 평가 항목의 세부 배점을 합산한 최종 점수입니다." not in item.value
        for item in app.caption
    )


def test_rubric_row_selection_resolves_the_clicked_item():
    item_ids = ["interpreter", "retriever", "improver"]

    assert (
        voc_quality_view._selected_rubric_item_id(
            item_ids,
            {"selection": {"rows": [0], "cells": [[2, "평가 항목"]]}},
            "interpreter",
        )
        == "improver"
    )
    assert (
        voc_quality_view._selected_rubric_item_id(
            item_ids,
            {"selection": {"rows": []}},
            "retriever",
        )
        == "retriever"
    )
    assert (
        voc_quality_view._table_selected_row_index(
            {"selection": {"rows": [0], "cells": [[1, "배점"]]}},
            len(item_ids),
        )
        == 1
    )


def test_cell_click_is_promoted_to_checked_row_for_rubric_and_case_catalog(
    monkeypatch,
):
    rubric_table_key = "rubric_table"
    catalog_table_key = "catalog_table"
    session_state = {
        rubric_table_key: {
            "selection": {
                "rows": [0],
                "columns": [],
                "cells": [[2, "평가 항목"]],
            }
        },
        catalog_table_key: {
            "selection": {
                "rows": [0],
                "columns": [],
                "cells": [[1, "이름"]],
            }
        },
        "rubric_selected": "interpreter",
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", session_state)

    voc_quality_view._sync_rubric_item_selection(
        rubric_table_key,
        "rubric_selected",
        ["interpreter", "retriever", "improver"],
    )
    voc_quality_view._remember_catalog_case_selection(
        catalog_table_key,
        ["TC-01", "TC-02", "TC-03"],
    )

    assert session_state["rubric_selected"] == "improver"
    assert session_state["rubric_selected_detail_dialog_request"] == "improver"
    assert session_state["voc_testcase_selected_case_id"] == "TC-02"
    assert session_state[rubric_table_key] == {
        "selection": {"rows": [2], "columns": [], "cells": []}
    }
    assert session_state[catalog_table_key] == {
        "selection": {"rows": [1], "columns": [], "cells": []}
    }


def test_rubric_version_edit_suppresses_stale_item_dialog_request(monkeypatch):
    table_key = "rubric_table"
    selected_key = "rubric_selected"
    session_state = {
        table_key: {
            "selection": {
                "rows": [0],
                "columns": [],
                "cells": [[2, "평가 항목"]],
            }
        },
        selected_key: "interpreter",
        f"{selected_key}_suppress_detail_dialog_once": True,
        f"{selected_key}_detail_dialog_request": "interpreter",
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", session_state)

    voc_quality_view._sync_rubric_item_selection(
        table_key,
        selected_key,
        ["interpreter", "retriever", "improver"],
    )

    assert session_state[selected_key] == "interpreter"
    assert f"{selected_key}_detail_dialog_request" in session_state


def test_rubric_criterion_labels_and_weight_chart_are_bilingual_and_emphasized():
    assert voc_quality_view._rubric_criterion_label("recall") == "검색 재현율 (recall)"
    assert (
        voc_quality_view._rubric_criterion_label("complaint_to_root_cause")
        == "불만-근본원인 연결 (complaint_to_root_cause)"
    )
    rubric_sets = [
        (load_system_rubric(), "categories"),
        (load_independent_judge_rubric(), "dimensions"),
        (load_improvement_validity_rubric(), "dimensions"),
    ]
    criterion_ids = {
        criterion_id
        for rubric, items_key in rubric_sets
        for item in rubric[items_key].values()
        for criterion_id in item["criteria"]
    }
    assert criterion_ids <= set(voc_quality_view.RUBRIC_CRITERION_KO_LABELS)

    spec = voc_quality_view._build_rubric_weight_chart(
        "Retriever 검색 관련성",
        13,
    ).to_dict()
    chart_values = spec["datasets"]
    flattened_rows = [row for rows in chart_values.values() for row in rows]

    assert any(row.get("배점") == 13 for row in flattened_rows)
    assert any(row.get("배점") == 87 for row in flattened_rows)
    assert "#1769AA" in str(spec)
    assert "전체 100점 중" in str(spec)
    assert spec["height"] == voc_quality_view.RUBRIC_WEIGHT_CHART_HEIGHT
    assert voc_quality_view.RUBRIC_ITEM_PANEL_HEIGHT == 460
    assert (
        voc_quality_view.RUBRIC_CRITERIA_PANEL_MIN_HEIGHT
        < voc_quality_view.RUBRIC_ITEM_PANEL_HEIGHT
    )


def test_rubric_criterion_range_uses_remaining_total_budget():
    rubric = deepcopy(load_system_rubric())
    items = rubric["categories"]

    assert voc_quality_view._rubric_total(items) == 100
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (0, 4)

    items["interpreter"]["criteria"]["intent"] = 3

    assert voc_quality_view._rubric_total(items) == 99
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (0, 4)
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "keywords") == (0, 5)


def test_batch_progress_dialog_renders_eta_and_thick_progress_bar():
    app = AppTest.from_file(
        "tests/fixtures/voc_batch_progress_dialog_app.py",
        default_timeout=15,
    )
    app.run()

    assert not app.exception
    assert {metric.label for metric in app.metric}.issuperset(
        {"상태", "예상 진행률", "예상 소요시간", "예상 남은 시간"}
    )
    progress = app.get("progress")
    assert len(progress) == 1
    assert progress[0].value == 50
    assert "전체 예상 진행률 50%" in progress[0].proto.text
    assert "완료 2 / 4건" in progress[0].proto.text
    assert any("stProgress" in item.value and "24px" in item.value for item in app.markdown)
    assert any("닫기" in button.label for button in app.button)


def test_batch_eta_uses_completed_case_average(monkeypatch):
    monkeypatch.setattr(voc_quality_view.st, "session_state", {})
    started_at = datetime.fromisoformat("2026-07-17T00:00:00+09:00")
    timing = voc_quality_view._batch_timing(
        {
            "run_id": "RUN-TEST",
            "status": "RUNNING",
            "started_at": started_at.isoformat(),
            "total": 4,
            "completed": 2,
            "judge_config": {"enabled": False},
        },
        now=datetime.fromisoformat("2026-07-17T00:02:00+09:00"),
    )

    assert timing == {
        "elapsed_seconds": 120,
        "estimated_total_seconds": 240,
        "remaining_seconds": 120,
    }


def test_batch_progress_moves_before_first_case_finishes(monkeypatch):
    monkeypatch.setattr(voc_quality_view.st, "session_state", {})
    started_at = datetime.fromisoformat("2026-07-17T00:00:00+09:00")
    now = datetime.fromisoformat("2026-07-17T00:00:20+09:00")
    progress = {
        "run_id": "RUN-FIRST-CASE",
        "status": "RUNNING",
        "started_at": started_at.isoformat(),
        "total": 4,
        "completed": 0,
        "estimated_total_seconds": 195,
        "runtime_progress": {
            "phase": "RUNNING",
            "current_position": 1,
            "current_case_id": "TC-01",
            "current_case_started_at": (
                datetime.fromisoformat("2026-07-17T00:00:10+09:00").isoformat()
            ),
        },
    }

    timing = voc_quality_view._batch_timing(progress, now=now)
    fraction = voc_quality_view._batch_progress_fraction(progress, timing, now=now)

    assert timing["estimated_total_seconds"] == 195
    assert 0.05 < fraction < 0.275


def test_quality_rubric_validation_rejects_invalid_scores_and_ranges():
    rubric = deepcopy(load_independent_judge_rubric())
    assert validate_quality_rubric("independent_judge", rubric) == []

    rubric["dimensions"]["accuracy"]["criteria"]["question_relevance"] = 99
    rubric["decisions"][1]["min_score"] = 70
    errors = validate_quality_rubric("independent_judge", rubric)

    assert any("세부 기준 합계" in error for error in errors)
    assert any("중복 또는 누락" in error for error in errors)


def test_quality_rubric_save_creates_backup_and_audit_log(tmp_path, monkeypatch):
    rubric = deepcopy(load_system_rubric())
    target = tmp_path / "quality_diagnosis" / "system_quality_rubric.json"
    target.parent.mkdir(parents=True)
    target.write_text(__import__("json").dumps(rubric, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(voc_quality_service, "VOC_RUNTIME_DIR", tmp_path)

    same_version_change = deepcopy(rubric)
    same_version_change["categories"]["interpreter"]["label"] = "변경된 항목명"
    rejected = save_quality_rubric("internal_pipeline", same_version_change, source="test")
    assert not rejected["ok"]
    assert any("버전도 변경" in error for error in rejected["errors"])

    rubric["version"] = "1.1"
    result = save_quality_rubric("internal_pipeline", rubric, source="test")

    assert result["ok"] and result["changed"]
    assert Path(result["backup_path"]).exists()
    assert (target.parent / "RubricHistory" / "rubric_changes.jsonl").exists()
    assert voc_quality_service.load_quality_rubric("internal_pipeline")["version"] == "1.1"


def test_secret_env_was_not_copied():
    assert not (PROJECT_DIR / "voc_quality_runtime" / ".env").exists()
    assert (PROJECT_DIR / "voc_quality_runtime" / ".env.example").exists()


def test_agent_status_output_is_parsed_for_all_six_agents():
    output = "\n".join([
        "interpreter  port=6101 pid=101 started_at=2026-07-17T14:00:01+09:00 status=RUNNING",
        "retriever    port=6102 pid=102 started_at=2026-07-17T14:00:02+09:00 status=RUNNING",
        "summarizer   port=6103 pid=103 started_at=2026-07-17T14:00:03+09:00 status=RUNNING",
        "evaluator    port=6104 pid=104 started_at=2026-07-17T14:00:04+09:00 status=RUNNING",
        "critic       port=6105 pid=105 started_at=2026-07-17T14:00:05+09:00 status=RUNNING",
        "improver     port=6106 pid=106 started_at=2026-07-17T14:00:06+09:00 status=RUNNING",
    ])
    rows = parse_agent_status_output(output)
    assert len(rows) == 6
    assert all(row["healthy"] for row in rows)
    assert rows[0]["started_at"] == "2026-07-17T14:00:01+09:00"


def test_agent_status_parser_keeps_legacy_output_compatible():
    rows = parse_agent_status_output("interpreter  port=6101 pid=101 status=RUNNING")

    assert rows[0]["healthy"] is True
    assert rows[0]["started_at"] == ""


def test_complete_a2a_trace_requires_every_expected_link():
    links = [
        ("Orchestrator", "Interpreter"),
        ("Orchestrator", "Summarizer"),
        ("Summarizer", "Retriever"),
        ("Retriever", "Summarizer"),
        ("Summarizer", "Evaluator"),
        ("Summarizer", "Critic"),
        ("Summarizer", "Improver"),
    ]
    timestamp = datetime.now().astimezone().isoformat()
    events = [
        {
            "trace_id": "trace-ok",
            "timestamp": timestamp,
            "source": source,
            "target": target,
            "status": "success",
            "duration_ms": 1,
        }
        for source, target in links
    ]
    assert summarize_a2a_events(events)["decision"] == "PASS"


def test_fault_test_case_uses_isolated_fault_runner(monkeypatch, tmp_path):
    captured = {}
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)

    def fake_run_cmd(script, arguments, timeout):
        captured.update(script=script, arguments=arguments, timeout=timeout)
        return {"ok": True, "output": "PASS"}

    monkeypatch.setattr(voc_quality_service, "_run_cmd", fake_run_cmd)
    result = voc_quality_service.run_test_case("TC-19")

    assert result["mode"] == "fault"
    assert result["fault_id"] == "FT-01"
    assert result["evidence_status"] == "REVIEW_REQUIRED"
    assert captured["script"].name == "fault-tests.cmd"
    assert captured["arguments"] == ["--case", "FT-01"]
    stored = store.load_voc_run(result["run_id"])
    assert stored["manifest"]["run_type"] == "MANUAL"
    assert stored["summary"]["counts"]["REVIEW_REQUIRED"] == 1
    case_dir = Path(result["run_dir"]) / "cases" / "TC-19"
    assert (case_dir / "pipeline_result.json").exists()
    assert (case_dir / "trace.json").exists()
    assert (case_dir / "rule_result.json").exists()


def test_normal_test_case_runs_voc_and_saves_report(monkeypatch, tmp_path):
    captured = {}
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)

    def fake_run_voc(question, save_report=False, timeout_seconds=180, task_override=None):
        captured.update(
            question=question,
            save_report=save_report,
            timeout_seconds=timeout_seconds,
            task_override=task_override,
        )
        return {
            "ok": True,
            "result": {
                "ok": True,
                "summary": "연락처 010-1234-5678, qa@example.com",
            },
            "api_key": "sk-proj-this-value-must-be-redacted",
        }

    monkeypatch.setattr(voc_quality_service, "run_voc_analysis", fake_run_voc)
    result = voc_quality_service.run_test_case("TC-01")

    assert result["mode"] == "voc"
    assert captured["question"] == "모바일 앱에서 자동차 보험을 갱신하려는데 오류가 계속 발생합니다."
    assert captured["save_report"] is True
    assert captured["timeout_seconds"] == 180
    assert captured["task_override"] == "both"
    assert result["evidence_status"] == "REVIEW_REQUIRED"
    stored = store.load_voc_run(result["run_id"])
    assert stored["manifest"]["selected_case_ids"] == ["TC-01"]
    assert stored["manifest"]["test_case_hash"]
    assert set(stored["manifest"]["rubric_versions"]) == {
        "internal_pipeline", "independent_judge", "improvement_validity"
    }
    pipeline_text = (
        Path(result["run_dir"]) / "cases" / "TC-01" / "pipeline_result.json"
    ).read_text(encoding="utf-8")
    assert "sk-proj-this-value-must-be-redacted" not in pipeline_text
    assert "[REDACTED_CREDENTIAL]" in pipeline_text
    assert "010-1234-5678" not in pipeline_text
    assert "qa@example.com" not in pipeline_text
    assert "[REDACTED_PHONE]" in pipeline_text
    assert "[REDACTED_EMAIL]" in pipeline_text


def test_batch_run_executes_implemented_cases_and_records_pending_cases(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    catalog = load_quality_test_catalog()
    case_ids = [item["case_id"] for item in catalog["cases"]]

    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {"ok": True, "result": {"ok": True, "summary": "ok"}},
    )
    monkeypatch.setattr(
        voc_quality_service,
        "_run_cmd",
        lambda *_args, **_kwargs: {"ok": True, "output": "PASS", "return_code": 0},
    )
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {"trace_id": "trace-batch", "events": []},
    )

    run = voc_quality_service.start_batch_run(case_ids, max_retries=0)
    result = voc_quality_service.execute_batch_run(
        run["run_id"], case_ids, max_retries=0, backoff_base_seconds=0
    )

    assert result["manifest"]["status"] == "COMPLETED"
    assert result["summary"]["counts"]["REVIEW_REQUIRED"] == 26
    assert result["summary"]["counts"]["NOT_RUN"] == 9
    assert result["summary"]["counts"]["ERROR"] == 0
    assert len(result["summary"]["case_results"]) == 35
    stored = store.load_voc_run(run["run_id"])
    assert stored["manifest"]["run_type"] == "BATCH"
    assert stored["manifest"]["run_metadata"]["execution_policy"] == "SEQUENTIAL"
    progress = voc_quality_service.get_batch_run_progress(run["run_id"])
    assert progress["started_at"]
    assert progress["finished_at"]


def test_batch_run_persists_initial_phase_and_runtime_updates(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = voc_quality_service.start_batch_run(["TC-01"], max_retries=0)

    initial = voc_quality_service.get_batch_run_progress(run["run_id"])
    assert initial["runtime_progress"]["phase"] == "PREFLIGHT"
    assert initial["estimated_total_seconds"] == 60

    store.update_voc_run_progress(
        run["run_id"],
        [],
        runtime_progress={
            "phase": "PREPARING",
            "phase_label": "처리 준비 중",
            "message": "실행 환경을 준비하고 있습니다.",
        },
    )
    store.update_voc_run_progress(run["run_id"], [])

    persisted = voc_quality_service.get_batch_run_progress(run["run_id"])
    assert persisted["runtime_progress"]["phase"] == "PREPARING"
    assert persisted["runtime_progress"]["phase_label"] == "처리 준비 중"

    assert voc_quality_service.request_batch_stop(run["run_id"])
    voc_quality_service.execute_batch_run(run["run_id"], ["TC-01"])


def test_batch_run_retries_429_and_preserves_attempt_history(monkeypatch, tmp_path):
    _configure_temp_voc_run_store(monkeypatch, tmp_path)
    calls = {"count": 0}

    def fake_run_voc(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"ok": False, "result": {"ok": False, "error": "HTTP 429 rate limit"}}
        return {"ok": True, "result": {"ok": True, "summary": "recovered"}}

    monkeypatch.setattr(voc_quality_service, "run_voc_analysis", fake_run_voc)
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {"trace_id": "trace-retry", "events": []},
    )
    run = voc_quality_service.start_batch_run(["TC-01"], max_retries=2)
    result = voc_quality_service.execute_batch_run(
        run["run_id"], ["TC-01"], max_retries=2, backoff_base_seconds=0
    )

    assert calls["count"] == 2
    assert result["summary"]["counts"]["REVIEW_REQUIRED"] == 1
    assert result["summary"]["case_results"][0]["attempt_count"] == 2
    artifact = json.loads(
        (Path(result["run_dir"]) / "cases" / "TC-01" / "pipeline_result.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["ok"] for item in artifact["attempts"]] == [False, True]
    assert artifact["attempts"][0]["transient"] is True


def test_batch_run_records_timeout_after_retry_exhaustion(monkeypatch, tmp_path):
    _configure_temp_voc_run_store(monkeypatch, tmp_path)
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {
            "ok": False,
            "result": {"ok": False, "error": "DEADLINE_EXCEEDED timeout"},
        },
    )
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {"trace_id": "trace-timeout", "events": []},
    )
    run = voc_quality_service.start_batch_run(["TC-01"], max_retries=1)
    result = voc_quality_service.execute_batch_run(
        run["run_id"], ["TC-01"], max_retries=1, backoff_base_seconds=0
    )

    assert result["manifest"]["status"] == "COMPLETED"
    assert result["summary"]["counts"]["ERROR"] == 1
    assert result["summary"]["case_results"][0]["attempt_count"] == 2


def test_batch_stop_marks_remaining_cases_not_run(monkeypatch, tmp_path):
    _configure_temp_voc_run_store(monkeypatch, tmp_path)
    case_ids = ["TC-01", "TC-02", "FT-01"]
    run = voc_quality_service.start_batch_run(case_ids)
    assert voc_quality_service.request_batch_stop(run["run_id"])

    result = voc_quality_service.execute_batch_run(run["run_id"], case_ids)

    assert result["manifest"]["status"] == "INTERRUPTED"
    assert result["summary"]["counts"]["NOT_RUN"] == 3
    assert all(item["attempt_count"] == 0 for item in result["summary"]["case_results"])


def test_batch_run_blocks_duplicate_active_selection(monkeypatch, tmp_path):
    _configure_temp_voc_run_store(monkeypatch, tmp_path)
    voc_quality_service._ACTIVE_BATCH_SIGNATURES.clear()
    voc_quality_service._BATCH_STOP_EVENTS.clear()
    first = voc_quality_service.start_batch_run(["TC-01", "TC-02"])

    with pytest.raises(RuntimeError, match=first["run_id"]):
        voc_quality_service.start_batch_run(["TC-02", "TC-01"])

    voc_quality_service.request_batch_stop(first["run_id"])
    voc_quality_service.execute_batch_run(first["run_id"], ["TC-01", "TC-02"])


def test_batch_retest_links_parent_run(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = voc_quality_service.start_batch_run(["TC-01"], parent_run_id="RUN-PARENT")
    voc_quality_service.request_batch_stop(run["run_id"])
    voc_quality_service.execute_batch_run(run["run_id"], ["TC-01"])

    manifest = store.load_voc_run(run["run_id"])["manifest"]
    assert manifest["run_type"] == "RETEST"
    assert manifest["run_metadata"]["parent_run_id"] == "RUN-PARENT"


def _start_minimal_voc_run(store):
    return store.start_voc_run(
        run_type="MANUAL",
        selected_case_ids=["TC-01"],
        suite_id="VOC-QA-35",
        catalog_version="1.0",
        test_case_hash="abc123",
        rubric_versions={"internal_pipeline": {"version": "1.0", "sha256": "hash"}},
        model_snapshot={"summary": {"provider": "openai", "model": "test"}},
        judge_enabled=False,
        environment_fingerprint={"fingerprint_sha256": "env"},
        snapshots={"selected_test_cases.json": {"cases": [{"case_id": "TC-01"}]}},
    )


def test_voc_run_store_recovers_incomplete_run_after_restart(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = _start_minimal_voc_run(store)
    store._ACTIVE_RUN_IDS.clear()

    recovered = store.recover_incomplete_runs()
    loaded = store.load_voc_run(run["run_id"])

    assert recovered == [run["run_id"]]
    assert loaded["manifest"]["status"] == "INTERRUPTED"
    assert loaded["manifest"]["finished_at"]
    assert loaded["summary"]["counts"]["NOT_RUN"] == 1
    assert store.list_voc_runs()[0]["run_id"] == run["run_id"]


def test_voc_run_store_generates_unique_ids_and_surfaces_corrupt_manifest(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    first = _start_minimal_voc_run(store)
    second = _start_minimal_voc_run(store)
    assert first["run_id"] != second["run_id"]

    corrupt_dir = store.VOC_QUALITY_RUNS_DIR / "RUN-20260716-120000-000000-abcd"
    corrupt_dir.mkdir(parents=True)
    (corrupt_dir / "manifest.json").write_text("{invalid", encoding="utf-8")
    entries = store.rebuild_run_index()
    corrupt = next(item for item in entries if item["run_id"] == corrupt_dir.name)

    assert corrupt["status"] == "ERROR"
    assert "integrity_error" in corrupt


def test_voc_run_store_rejects_unsafe_snapshot_path_before_creating_run(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="스냅샷 경로"):
        store.start_voc_run(
            run_type="MANUAL",
            selected_case_ids=["TC-01"],
            suite_id="VOC-QA-35",
            catalog_version="1.0",
            test_case_hash="hash",
            rubric_versions={},
            model_snapshot={},
            judge_enabled=False,
            environment_fingerprint={},
            snapshots={"../outside.json": {}},
        )
    assert not store.VOC_QUALITY_RUNS_DIR.exists()


def _complete_minimal_run(store, run, status="PASS"):
    store.save_case_artifacts(
        run["run_id"],
        "TC-01",
        pipeline_result={"ok": True},
        trace={"trace_id": "trace-1", "events": []},
        rule_result={"status": status},
    )
    return store.complete_voc_run(
        run["run_id"],
        [{"case_id": "TC-01", "status": status, "attempt_count": 1}],
        lifecycle_status="COMPLETED",
    )


def test_history_listing_does_not_interrupt_run_owned_by_another_process(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = _start_minimal_voc_run(store)
    store._ACTIVE_RUN_IDS.clear()

    rows = store.list_voc_runs()

    assert rows[0]["status"] == "RUNNING"
    assert store.load_voc_run(run["run_id"])["manifest"]["status"] == "RUNNING"


def test_history_integrity_zip_and_delete_keep_index_in_sync(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = _start_minimal_voc_run(store)
    _complete_minimal_run(store, run)

    integrity = store.verify_run_integrity(run["run_id"])
    evidence_zip = store.build_run_evidence_zip(run["run_id"])
    deleted = store.delete_voc_runs([run["run_id"]])

    assert integrity["ok"], integrity["errors"]
    assert evidence_zip.startswith(b"PK")
    assert deleted["deleted_count"] == 1
    assert not Path(run["run_dir"]).exists()
    assert store.list_voc_runs() == []


def test_history_refuses_to_delete_running_run(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = _start_minimal_voc_run(store)

    with pytest.raises(ValueError, match="실행 중인 Run"):
        store.delete_voc_runs([run["run_id"]])

    assert Path(run["run_dir"]).exists()


def test_retest_comparison_requires_parent_and_same_versions(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    baseline = _start_minimal_voc_run(store)
    _complete_minimal_run(store, baseline, status="FAIL")
    candidate = store.start_voc_run(
        run_type="RETEST",
        selected_case_ids=["TC-01"],
        suite_id="VOC-QA-35",
        catalog_version="1.0",
        test_case_hash="abc123",
        rubric_versions={"internal_pipeline": {"version": "1.0", "sha256": "hash"}},
        model_snapshot={"summary": {"provider": "openai", "model": "test"}},
        judge_enabled=False,
        environment_fingerprint={"fingerprint_sha256": "env"},
        run_metadata={"parent_run_id": baseline["run_id"]},
    )
    _complete_minimal_run(store, candidate, status="PASS")

    comparison = voc_quality_service.compare_voc_runs(
        baseline["run_id"], candidate["run_id"]
    )

    assert comparison["compatible"] is True
    assert comparison["valid_retest_pair"] is True
    assert comparison["comparison_type"] == "RETEST_BEFORE_AFTER"
    assert comparison["case_comparison"][0]["baseline_status"] == "FAIL"
    assert comparison["case_comparison"][0]["candidate_status"] == "PASS"


def test_run_history_calculates_progress_without_false_success_rate(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    run = _start_minimal_voc_run(store)
    _complete_minimal_run(store, run, status="REVIEW_REQUIRED")

    row = voc_quality_service.list_voc_run_history()[0]

    assert row["completion_rate"] == 100.0
    assert row["success_rate"] is None
    assert row["deployment_decision"] == "미판정"


def test_individual_agent_action_passes_only_valid_agent(monkeypatch):
    captured = {}

    def fake_run_cmd(script, arguments, timeout):
        captured.update(script=script, arguments=arguments, timeout=timeout)
        return {"ok": True}

    monkeypatch.setattr(voc_quality_service, "_run_cmd", fake_run_cmd)
    voc_quality_service.run_agent_action("stop", "retriever")

    assert captured["script"].name == "agents.cmd"
    assert captured["arguments"] == ["stop", "retriever"]


def test_retriever_matches_related_voc_when_word_order_and_spacing_differ(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT_DIR / "voc_quality_runtime"))
    from voc_quality_runtime.agents.retriever import RetrieverAgent

    csv_path = PROJECT_DIR / "voc_quality_runtime" / "voc.csv"
    agent = RetrieverAgent()
    tc01 = asyncio.run(agent.run(
        str(csv_path),
        ["자동차보험 갱신 오류", "모바일 앱 오류"],
        30,
    ))
    tc02 = asyncio.run(agent.run(
        str(csv_path),
        ["보험금 청구", "진행 상태", "앱 표시 오류"],
        30,
    ))

    assert tc01 and tc01[0].startswith("CUST041 ")
    assert tc02 and tc02[0].startswith("CUST054 ")


def test_retriever_does_not_guess_from_one_ambiguous_phrase(monkeypatch):
    monkeypatch.syspath_prepend(str(PROJECT_DIR / "voc_quality_runtime"))
    from voc_quality_runtime.agents.retriever import RetrieverAgent

    csv_path = PROJECT_DIR / "voc_quality_runtime" / "voc.csv"
    result = asyncio.run(RetrieverAgent().run(str(csv_path), ["처리 지연"], 30))

    assert result == []
