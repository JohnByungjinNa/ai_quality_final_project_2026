import asyncio
import inspect
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
    load_test_cases,
    load_unified_quality_cases,
    parse_agent_status_output,
    runtime_health,
    save_quality_rubric,
    describe_batch_state_model,
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
    assert all(len(meta.get("flow", ())) in {0, 3} for meta in voc_quality_view.VOC_PAGE_META.values())
    assert voc_quality_view.VOC_PAGE_META["수동 TC 수행"]["flow"] == ()
    assert voc_quality_view.VOC_PAGE_META["일괄 TC 수행"]["flow"] == ()
    assert voc_quality_view.VOC_PAGE_META["테스트케이스"]["flow"] == ()
    assert voc_quality_view.VOC_PAGE_META["품질 평가 기준"]["flow"] == ()
    assert voc_quality_view.VOC_PAGE_META["개선안 타당성 검증"]["flow"] == ()


def test_voc_visual_design_shell_renders_header_flow_and_content():
    app = AppTest.from_file("tests/fixtures/voc_design_system_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    assert "품질 평가 기준 수립" in markdown
    assert ":blue-badge[단계 선택]" not in markdown
    assert ":blue-badge[배점 조정]" not in markdown
    assert ":blue-badge[검증·저장]" not in markdown
    assert any(item.label == "평가 총점" for item in app.metric)
    assert any(item.label == "기준명" for item in app.text_input)


def test_voc_history_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_history_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    rendered_markdown = "\n".join(item.value for item in app.markdown)
    rendered_caption = "\n".join(item.value for item in app.caption)
    assert ":blue-badge[Run 조회]" not in rendered_markdown
    assert ":blue-badge[결과 비교]" not in rendered_markdown
    assert ":blue-badge[증적 확인]" not in rendered_markdown
    assert "통과 Case" in rendered_caption
    assert "검토 필요 Case" in rendered_caption
    assert "실패·오류 Case" in rendered_caption
    assert "독립 LLM 평가 필요" in rendered_caption
    assert "후속 조치 Run" in rendered_caption
    history_columns = set(app.dataframe[0].value.columns)
    assert "선택" not in history_columns
    assert {"Run ID", "실행 시각", "유형", "상태"}.issubset(history_columns)
    assert "T" not in str(app.dataframe[0].value["실행 시각"].iloc[0])
    assert set(app.dataframe[0].proto.selection_mode) == {
        Dataframe.SelectionMode.SINGLE_ROW,
        Dataframe.SelectionMode.SINGLE_CELL,
    }
    assert any(button.label == "선택 Run 상세" for button in app.button)
    assert any(
        item.value == "Run 행을 선택하면 상세 팝업이 열리고, 다음 액션 대상도 함께 바뀝니다."
        for item in app.caption
    )


def test_voc_history_selected_run_detail_opens_in_dialog():
    app = AppTest.from_file("tests/fixtures/voc_history_app.py", default_timeout=15)
    app.run()

    detail_button = next(button for button in app.button if button.label == "선택 Run 상세")
    detail_button.click().run()

    assert not app.exception
    rendered_markdown = "\n".join(item.value for item in app.markdown)
    rendered_caption = "\n".join(item.value for item in app.caption)
    rendered_text = f"{rendered_markdown}\n{rendered_caption}"
    assert ":material/history: 실행 상세" in rendered_markdown
    assert "Run RUN-" in rendered_caption
    for label in ("Run 상태", "대상 Case", "독립 LLM 평가", "타당성·승인"):
        assert label in rendered_text
    assert any(
        {"Case ID", "질문", "상태", "다음 액션", "독립 LLM", "타당성", "승인"}.issubset(
            set(frame.value.columns)
        )
        for frame in app.dataframe
    )
    assert "증적 무결성 정상" in rendered_caption


def test_history_validity_review_rows_are_korean_and_safe():
    rows = voc_quality_view._history_validity_review_rows(
        [
            {
                "reviewer_role": "QA",
                "reviewer_name_or_id": "??? ???",
                "decision": "APPROVE",
                "comment": "??? ???",
                "from_state": "AI_REVIEWED",
                "to_state": "QA_REVIEWED",
                "reviewed_at": "2026-08-02T10:38:37",
            },
            {
                "reviewer_role": "BUSINESS",
                "reviewer_name_or_id": "TC-16 ??? ??",
                "decision": "APPROVE",
                "comment": "TC-16 ??? ?? ?? LLM PASS? ??? AI_PASS? ???? QA ?? ??",
                "from_state": "QA_REVIEWED",
                "to_state": "BUSINESS_APPROVED",
                "reviewed_at": "2026-08-02T10:40:01",
            },
        ]
    )

    assert rows.iloc[0]["단계"] == "QA 검토"
    assert rows.iloc[0]["결정"] == "승인"
    assert rows.iloc[0]["검토자"] == "검토자 미확인"
    assert rows.iloc[0]["상태 변화"] == "AI 평가 완료 → QA 검토 완료"
    assert rows.iloc[0]["검토 의견"] == "QA 검토 단계에서 승인 처리되었습니다. (AI 평가 완료 → QA 검토 완료)"
    assert rows.iloc[1]["단계"] == "업무 승인"
    assert rows.iloc[1]["검토자"] == "검토자 미확인"
    assert rows.iloc[1]["검토 의견"] == "업무 승인 단계에서 승인 처리되었습니다. (QA 검토 완료 → 업무 승인 완료)"
    assert "???" not in rows.iloc[1]["검토 의견"]


def test_voc_history_row_selection_opens_detail_dialog(monkeypatch):
    state = {
        voc_quality_view.HISTORY_TABLE_KEY: {
            "selection": {"rows": [0], "columns": [], "cells": [[1, "상태"]]}
        }
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    voc_quality_view._remember_history_run_selection(
        voc_quality_view.HISTORY_TABLE_KEY,
        ("RUN-01", "RUN-02"),
    )

    assert state[voc_quality_view.HISTORY_SELECTED_RUN_ID_KEY] == "RUN-02"
    assert state[voc_quality_view.HISTORY_DETAIL_DIALOG_RUN_ID_KEY] == "RUN-02"
    assert state[voc_quality_view.HISTORY_TABLE_KEY] == {
        "selection": {"rows": [1], "columns": [], "cells": []}
    }


def test_voc_history_dialog_dismiss_resets_table_selection_nonce(monkeypatch):
    state = {
        voc_quality_view.HISTORY_DETAIL_DIALOG_RUN_ID_KEY: "RUN-01",
        voc_quality_view.HISTORY_TABLE_NONCE_KEY: 4,
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    voc_quality_view._dismiss_history_detail_dialog()

    assert voc_quality_view.HISTORY_DETAIL_DIALOG_RUN_ID_KEY not in state
    assert state[voc_quality_view.HISTORY_TABLE_NONCE_KEY] == 5


def test_voc_history_execution_and_case_evidence_are_human_readable():
    app = AppTest.from_file(
        "tests/fixtures/voc_history_readable_detail_app.py",
        default_timeout=15,
    )
    app.run()

    assert not app.exception
    rendered_markdown = "\n".join(item.value for item in app.markdown)
    rendered_caption = "\n".join(item.value for item in app.caption)
    assert "Run 기본 정보" in rendered_markdown
    assert "적용 Rubric" in rendered_markdown
    assert "실행 모델" in rendered_markdown
    assert "VOC 분석 요약" in rendered_markdown
    assert "최종 개선안" in rendered_markdown
    assert "확인 근거" in rendered_markdown
    assert "잔여 위험" in rendered_markdown
    assert "보완 권고" in rendered_markdown
    assert "QA·업무 승인 이력" in rendered_markdown
    assert "실행 Trace ID: trace-demo" in rendered_caption
    metric_labels = {metric.label for metric in app.metric}
    assert {"수행 상태", "내부 판정", "유효 판정", "자동 판정", "승인 단계"}.issubset(
        metric_labels
    )
    dataframe_columns = [set(frame.value.columns) for frame in app.dataframe]
    assert {"평가 단계", "버전", "무결성 Hash"} in dataframe_columns
    assert {"평가 항목", "점수", "배점", "판정 근거"} in dataframe_columns


def test_voc_dashboard_renders_operational_quality_summary():
    app = AppTest.from_file("tests/fixtures/voc_dashboard_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert any(item.label == "기간" for item in app.date_input)
    dashboard_markup = "\n".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert "Agent 가동" in dashboard_markup
    assert "최신 Run 품질" in dashboard_markup
    assert "조치 필요" in dashboard_markup
    assert "실행·증적 연동 준비도" in dashboard_markup
    assert "vqd-status-row vqd-integration-row" in dashboard_markup
    assert "독립 LLM 평가와 AWS 증적 저장에 필요한 연결 상태" not in dashboard_markup
    assert "조치 필요 현황" in dashboard_markup
    assert "평가 필요" in dashboard_markup
    assert "보완·재시험 필요" in dashboard_markup
    assert "QA 검토 대기" in dashboard_markup
    assert "업무 승인 대기" in dashboard_markup
    assert "미종결 결함" in dashboard_markup
    assert "우선 확인 사항" not in dashboard_markup
    assert "실행 기반과 Trace 현황" not in dashboard_markup
    assert "기간 미종결 결함·후보" not in dashboard_markup
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
            item.value == "Run별 통과·검토·실패/오류 비율 · 최근 12건"
        for item in app.caption
    )
    assert "vqd-agent-grid" in dashboard_markup
    assert "vqd-agent-card good" in dashboard_markup
    assert "vqd-agent-card bad" in dashboard_markup
    assert len(app.get("vega_lite_chart")) == 2
    assert {"구분", "대상", "다음 조치", "상태", "수행/등록", "Run"}.issubset(
        app.dataframe[0].value.columns
    )


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
    assert rendered_text.count(":material/smart_toy:") <= 1


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
        ("start", None, "Interpreter 등 6개 Agent 프로세스를 시작하고 있습니다..."),
        ("restart", None, "Interpreter 등 6개 Agent 프로세스를 재기동하고 있습니다..."),
        ("stop", None, "Interpreter 등 6개 Agent 프로세스를 중지하고 있습니다..."),
        ("start", "retriever", "retriever Agent 프로세스를 시작하고 있습니다..."),
    ],
)
def test_agent_control_uses_agent_specific_progress_message(action, agent_name, expected):
    assert voc_quality_view._agent_control_progress_message(action, agent_name) == expected
    assert "VOC 품질진단 작업을 수행" not in expected


def test_gemini_credential_check_reports_missing_sdk_without_scope_error(monkeypatch):
    import builtins

    original_import = builtins.__import__

    def import_without_google_genai(name, *args, **kwargs):
        if name == "google" or name.startswith("google.genai"):
            raise ImportError("cannot import name 'genai' from 'google'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(
        voc_quality_service,
        "_agent_env_first",
        lambda _names: ("configured-test-key", ".env", "GEMINI_API_KEY"),
    )
    monkeypatch.setattr(builtins, "__import__", import_without_google_genai)

    result = voc_quality_service.check_gemini_agent_credential()

    assert result["ok"] is False
    assert result["status"] == "SDK_MISSING"
    assert "google-genai" in result["message"]


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

    state = {
        "agent_control_confirm_nonce": 4,
        "agent_quick_test_result_interpreter": {"ok": True},
        "agent_quick_test_result_retriever": {"ok": False},
        "unrelated_state": "keep",
    }
    spinner_messages = []
    reruns = []
    management_snapshot = Clearable()
    monitor_snapshot = Clearable()
    stopped_snapshot = {
        "checked_at": "2026-07-29T20:00:00+09:00",
        "total": 6,
        "running": 0,
        "agents": [
            {"key": key, "status": "STOPPED"}
            for key in ("interpreter", "retriever", "summarizer", "evaluator", "critic", "improver")
        ],
    }
    running_snapshot = {
        "checked_at": "2026-07-29T20:00:05+09:00",
        "total": 6,
        "running": 6,
        "agents": [
            {"key": key, "status": "RUNNING"}
            for key in ("interpreter", "retriever", "summarizer", "evaluator", "critic", "improver")
        ],
    }
    snapshots = iter([stopped_snapshot, running_snapshot])
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
    monkeypatch.setattr(voc_quality_view, "agent_status_snapshot", lambda: next(snapshots))
    monkeypatch.setattr(voc_quality_view, "_load_agent_management_snapshot", management_snapshot)
    monkeypatch.setattr(voc_quality_view, "_load_goal_monitor_snapshot", monitor_snapshot)
    monkeypatch.setattr(voc_quality_view.st, "rerun", lambda: reruns.append(True))

    voc_quality_view._run_agent_control_and_refresh("start")

    assert spinner_messages == ["Interpreter 등 6개 Agent 프로세스를 시작하고 있습니다..."]
    assert state["voc_command_result"]["ok"] is True
    assert state["agent_control_confirm_nonce"] == 5
    assert "agent_quick_test_result_interpreter" not in state
    assert "agent_quick_test_result_retriever" not in state
    assert state["unrelated_state"] == "keep"
    assert management_snapshot.clear_count == 1
    assert monitor_snapshot.clear_count == 1
    assert reruns == [True]
    assert state["agent_control_feedback"]["title"] == "전체 Agent 시작 완료"
    assert state["agent_control_latest_snapshot"] == running_snapshot


def test_agent_control_start_skips_already_running_agents(monkeypatch):
    snapshot = {
        "checked_at": "2026-07-29T20:00:00+09:00",
        "total": 6,
        "running": 5,
        "agents": [
            {"key": "interpreter", "status": "RUNNING"},
            {"key": "retriever", "status": "RUNNING"},
            {"key": "summarizer", "status": "RUNNING"},
            {"key": "evaluator", "status": "RUNNING"},
            {"key": "critic", "status": "RUNNING"},
            {"key": "improver", "status": "STOPPED"},
        ],
    }
    calls = []
    monkeypatch.setattr(voc_quality_view, "agent_status_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        voc_quality_view,
        "run_agent_action",
        lambda action, agent_name=None: calls.append((action, agent_name)) or {
            "ok": True,
            "return_code": 0,
            "output": f"{agent_name} started",
            "duration_seconds": 0.2,
        },
    )

    result = voc_quality_view._run_agent_control_command("start")

    assert result["ok"] is True
    assert calls == [("start", "improver")]
    assert "[건너뜀] interpreter 이미 실행 중" in result["output"]
    assert "improver started" in result["output"]


def test_agent_control_can_complete_without_forced_rerun(monkeypatch):
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

    state = {"agent_control_confirm_nonce": 0}
    running_snapshot = {
        "checked_at": "2026-07-29T20:00:05+09:00",
        "total": 6,
        "running": 6,
        "agents": [
            {"key": key, "status": "RUNNING"}
            for key in ("interpreter", "retriever", "summarizer", "evaluator", "critic", "improver")
        ],
    }
    reruns = []
    management_snapshot = Clearable()
    monitor_snapshot = Clearable()
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "spinner", lambda message: Spinner())
    monkeypatch.setattr(voc_quality_view, "agent_status_snapshot", lambda: running_snapshot)
    monkeypatch.setattr(
        voc_quality_view,
        "run_agent_action",
        lambda action, agent_name=None: {
            "ok": True,
            "return_code": 0,
            "output": "already running",
            "duration_seconds": 0,
        },
    )
    monkeypatch.setattr(voc_quality_view, "_load_agent_management_snapshot", management_snapshot)
    monkeypatch.setattr(voc_quality_view, "_load_goal_monitor_snapshot", monitor_snapshot)
    monkeypatch.setattr(voc_quality_view.st, "rerun", lambda: reruns.append(True))

    voc_quality_view._run_agent_control_and_refresh("start", rerun_after=False)

    assert reruns == []
    assert state["agent_control_feedback"]["title"] == "전체 Agent 시작 완료"
    assert state["agent_control_latest_snapshot"] == running_snapshot
    assert management_snapshot.clear_count == 1
    assert monitor_snapshot.clear_count == 1


def test_agent_management_hides_stale_start_error_when_all_agents_are_running(monkeypatch):
    state = {
        "agent_control_feedback": {
            "ok": False,
            "command_ok": False,
            "action": "start",
        },
        "agent_control_log": {
            "command_ok": False,
            "action": "start",
        },
    }
    snapshot = {
        "total": 6,
        "running": 6,
        "agents": [
            {"status": "RUNNING", "healthy": True}
            for _ in range(6)
        ],
    }
    calls = []
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *args, **kwargs: calls.append("heading"))
    monkeypatch.setattr(voc_quality_view, "_render_agent_control_feedback", lambda: calls.append("feedback"))
    monkeypatch.setattr(voc_quality_view, "_render_agent_control_log", lambda: calls.append("log"))
    monkeypatch.setattr(voc_quality_view, "_render_agent_credential_feedback", lambda: calls.append("credential"))

    voc_quality_view._render_agent_management_messages(snapshot)

    assert calls == []


@pytest.mark.parametrize(
    "result_key",
    [
        "agent_openai_credential_result",
        "agent_anthropic_credential_result",
        "agent_gemini_credential_result",
    ],
)
def test_agent_management_renders_each_provider_credential_result_independently(
    monkeypatch,
    result_key,
):
    state = {result_key: {"ok": True, "status": "PASS"}}
    snapshot = {
        "total": 6,
        "running": 6,
        "agents": [
            {"status": "RUNNING", "healthy": True}
            for _ in range(6)
        ],
    }
    calls = []
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view.st,
        "markdown",
        lambda *args, **kwargs: calls.append("heading"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_control_feedback",
        lambda: calls.append("feedback"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_control_log",
        lambda: calls.append("log"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_credential_feedback",
        lambda: calls.append("credential"),
    )

    voc_quality_view._render_agent_management_messages(snapshot)

    assert calls == ["heading", "credential"]


def test_agent_management_shows_recent_success_log_without_redundant_success_card(monkeypatch):
    state = {
        "agent_control_feedback": {
            "ok": True,
            "command_ok": True,
            "action": "start",
        },
        "agent_control_log": {
            "command_ok": True,
            "action": "start",
        },
    }
    snapshot = {
        "total": 6,
        "running": 6,
        "agents": [
            {"status": "RUNNING", "healthy": True}
            for _ in range(6)
        ],
    }
    calls = []
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *args, **kwargs: calls.append("heading"))
    monkeypatch.setattr(voc_quality_view, "_render_agent_control_feedback", lambda: calls.append("feedback"))
    monkeypatch.setattr(voc_quality_view, "_render_agent_control_log", lambda: calls.append("log"))
    monkeypatch.setattr(voc_quality_view, "_render_agent_credential_feedback", lambda: calls.append("credential"))

    voc_quality_view._render_agent_management_messages(snapshot)

    assert calls == ["heading", "log"]


def test_agent_management_bulk_controls_use_background_job_instead_of_blocking_spinner():
    render_source = inspect.getsource(voc_quality_view.render_agents)
    monitor_source = inspect.getsource(voc_quality_view._render_agent_control_job_monitor)

    assert '_start_agent_control_background("start")' in render_source
    assert '_start_agent_control_background("restart")' in render_source
    assert '_start_agent_control_background("stop")' in render_source
    assert "rerun_after=False" not in render_source
    assert '@st.fragment(run_every="1s")' in monitor_source
    assert 'st.rerun(scope="app")' in monitor_source


def test_start_agent_control_background_creates_job_and_resets_transient_state(monkeypatch):
    class Clearable:
        def __init__(self):
            self.clear_count = 0

        def clear(self):
            self.clear_count += 1

    state = {
        "agent_control_confirm_nonce": 2,
        "agent_control_feedback": {"title": "old"},
        "agent_quick_test_result_interpreter": {"ok": True},
    }
    calls = []
    management_snapshot = Clearable()
    monitor_snapshot = Clearable()
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view, "_load_agent_management_snapshot", management_snapshot)
    monkeypatch.setattr(voc_quality_view, "_load_goal_monitor_snapshot", monitor_snapshot)
    monkeypatch.setattr(
        voc_quality_view,
        "start_background_job",
        lambda kind, target_id, worker, *args, progress=None, **kwargs: calls.append(
            {
                "kind": kind,
                "target_id": target_id,
                "worker": worker,
                "args": args,
                "progress": progress,
            }
        ) or "agent-job-1",
    )

    voc_quality_view._start_agent_control_background("start")

    assert state[voc_quality_view.AGENT_CONTROL_JOB_KEY] == "agent-job-1"
    assert state["agent_control_confirm_nonce"] == 3
    assert "agent_control_feedback" not in state
    assert "agent_quick_test_result_interpreter" not in state
    assert management_snapshot.clear_count == 1
    assert monitor_snapshot.clear_count == 1
    assert calls[0]["kind"] == "agent-control"
    assert calls[0]["target_id"] == "start:all"
    assert calls[0]["args"] == ("start", None, None)
    assert "요청 접수" in calls[0]["progress"]["lines"][0]


def test_agent_control_monitor_completes_running_start_when_target_state_is_reached(monkeypatch):
    class Clearable:
        def __init__(self):
            self.clear_count = 0

        def clear(self):
            self.clear_count += 1

    state = {voc_quality_view.AGENT_CONTROL_JOB_KEY: "agent-job-1"}
    running_snapshot = {
        "checked_at": "2026-07-31T09:10:05+09:00",
        "total": 6,
        "running": 6,
        "agents": [
            {"key": key, "status": "RUNNING", "healthy": True}
            for key in ("interpreter", "retriever", "summarizer", "evaluator", "critic", "improver")
        ],
    }
    running_job = {
        "job_id": "agent-job-1",
        "target_id": "start:all",
        "status": "RUNNING",
        "started_at": "2026-07-31T09:10:00+09:00",
        "progress": {"action": "start", "target": "전체 Agent"},
    }
    reruns = []
    discarded = []
    management_snapshot = Clearable()
    monitor_snapshot = Clearable()

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view, "background_job_snapshot", lambda job_id: running_job)
    monkeypatch.setattr(voc_quality_view, "agent_status_snapshot", lambda: running_snapshot)
    monkeypatch.setattr(voc_quality_view, "_load_agent_management_snapshot", management_snapshot)
    monkeypatch.setattr(voc_quality_view, "_load_goal_monitor_snapshot", monitor_snapshot)
    monkeypatch.setattr(voc_quality_view, "discard_background_job", lambda job_id: discarded.append(job_id))
    monkeypatch.setattr(voc_quality_view.st, "rerun", lambda **kwargs: reruns.append(kwargs))
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_control_running_panel",
        lambda _job: pytest.fail("목표 상태에 도달한 작업은 진행 중 패널을 계속 표시하지 않아야 합니다."),
    )

    getattr(
        voc_quality_view._render_agent_control_job_monitor,
        "__wrapped__",
        voc_quality_view._render_agent_control_job_monitor,
    )()

    assert voc_quality_view.AGENT_CONTROL_JOB_KEY not in state
    assert state["agent_control_feedback"]["title"] == "전체 Agent 시작 완료"
    assert state["agent_control_latest_snapshot"] == running_snapshot
    assert state["voc_command_result"]["ok"] is True
    assert management_snapshot.clear_count == 1
    assert monitor_snapshot.clear_count == 1
    assert discarded == ["agent-job-1"]
    assert reruns == [{"scope": "app"}]


def test_agent_control_monitor_does_not_complete_restart_from_old_running_state(monkeypatch):
    state = {voc_quality_view.AGENT_CONTROL_JOB_KEY: "agent-job-1"}
    old_running_snapshot = {
        "checked_at": "2026-07-31T09:10:05+09:00",
        "total": 6,
        "running": 6,
        "agents": [
            {
                "key": key,
                "status": "RUNNING",
                "healthy": True,
                "started_at": "2026-07-31T09:00:00+09:00",
            }
            for key in ("interpreter", "retriever", "summarizer", "evaluator", "critic", "improver")
        ],
    }
    running_job = {
        "job_id": "agent-job-1",
        "target_id": "restart:all",
        "status": "RUNNING",
        "started_at": "2026-07-31T09:10:00+09:00",
        "progress": {"action": "restart", "target": "전체 Agent"},
    }
    rendered = []
    reruns = []

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view, "background_job_snapshot", lambda job_id: running_job)
    monkeypatch.setattr(voc_quality_view, "agent_status_snapshot", lambda: old_running_snapshot)
    monkeypatch.setattr(voc_quality_view, "_render_agent_control_running_panel", lambda job: rendered.append(job))
    monkeypatch.setattr(voc_quality_view.st, "rerun", lambda **kwargs: reruns.append(kwargs))

    getattr(
        voc_quality_view._render_agent_control_job_monitor,
        "__wrapped__",
        voc_quality_view._render_agent_control_job_monitor,
    )()

    assert rendered == [running_job]
    assert state[voc_quality_view.AGENT_CONTROL_JOB_KEY] == "agent-job-1"
    assert "agent_control_feedback" not in state
    assert reruns == []


def test_agent_quick_test_uses_fragment_to_avoid_full_card_rerender():
    fragment_source = inspect.getsource(voc_quality_view._render_agent_quick_test_fragment)
    render_source = inspect.getsource(voc_quality_view.render_agents)

    assert "@st.fragment" in fragment_source
    assert "test_agent_rpc" in fragment_source
    assert "_render_agent_quick_test_fragment(agent)" in render_source
    assert "test_agent_rpc(" not in render_source


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
    monkeypatch.setattr(voc_quality_view, "_sync_goal_testcase_recent_artifacts", lambda case: None)
    monkeypatch.setattr(voc_quality_view, "pipeline_trace_events", lambda *_args: {})
    monkeypatch.setattr(
        voc_quality_view,
        "_live_testcase_pipeline",
        lambda: render_order.append("pipeline"),
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
    monkeypatch.setattr(
        voc_quality_view,
        "_render_manual_followup_flow",
        lambda case_id: render_order.append(f"followup:{case_id}"),
    )

    voc_quality_view.render_goal_monitor()

    assert render_order == [
        "selector",
        "pipeline",
        "result:TC-01",
        "judge-select:TC-01",
        "judge-result:TC-01",
        "followup:TC-01",
    ]


def test_goal_monitor_keeps_pipeline_below_selector_after_completion_focus(monkeypatch):
    render_order = []
    state = {
        "goal_testcase_selected_case_id": "TC-01",
        "goal_testcase_focus_result": True,
        "goal_testcase_result": {"case": {"case_id": "TC-01"}},
    }

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view, "_goal_testcase_selector", lambda: render_order.append("selector"))
    monkeypatch.setattr(voc_quality_view, "_sync_goal_testcase_recent_artifacts", lambda case: None)
    monkeypatch.setattr(voc_quality_view, "pipeline_trace_events", lambda *_args: {})
    monkeypatch.setattr(
        voc_quality_view,
        "_live_testcase_pipeline",
        lambda: render_order.append("pipeline"),
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
        "_render_goal_judge_step",
        lambda case: render_order.append(f"judge-select:{case['case_id']}"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_goal_judge_result",
        lambda case_id: render_order.append(f"judge-result:{case_id}"),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_manual_followup_flow",
        lambda case_id: render_order.append(f"followup:{case_id}"),
    )

    voc_quality_view.render_goal_monitor()

    assert render_order == [
        "selector",
        "pipeline",
        "result:TC-01",
        "judge-select:TC-01",
        "judge-result:TC-01",
        "followup:TC-01",
    ]


def test_goal_monitor_always_mounts_live_pipeline_fragment(monkeypatch):
    render_order = []
    state = {}

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view, "_ensure_goal_testcase_selection", lambda: None)
    monkeypatch.setattr(voc_quality_view, "_goal_testcase_selector", lambda: render_order.append("selector"))
    monkeypatch.setattr(voc_quality_view, "_selected_goal_testcase", lambda: None)
    monkeypatch.setattr(
        voc_quality_view,
        "_live_testcase_pipeline",
        lambda: render_order.append("pipeline"),
    )

    voc_quality_view.render_goal_monitor()

    assert render_order == ["selector", "pipeline"]


def test_goal_testcase_selector_uses_user_facing_title():
    import inspect

    source = inspect.getsource(voc_quality_view._goal_testcase_selector.__wrapped__)

    assert 'st.markdown("### Test Case 선택 실행")' in source
    assert "?? ?? ? ? ???? ??" not in source
    assert 'st.button(\n            "Agent 파이프라인 실행"' in source
    assert "읽기 전용 목록입니다." not in source
    assert "horizontal=True" in source
    assert 'st.markdown("### test_cases.json 선택 실행")' not in source


def test_policy_terms_section_is_split_for_collapsible_rendering():
    terms, body = voc_quality_view._split_policy_terms_section(
        "0.용어 정의\n- 청구 진행 상태: 보험금 청구 처리 단계\n1. 앱 표시 개선\n- 진행 상태를 노출합니다."
    )

    assert "청구 진행 상태" in terms
    assert "0.용어 정의" not in body
    assert "1. 앱 표시 개선" in body


def test_pipeline_result_message_suppresses_internal_a2a_completion_text():
    assert voc_quality_view._pipeline_result_message(
        {"message": "Pipeline completed via agent-to-agent calls"}
    ) == "VOC 테스트 실행 완료"


def test_manual_followup_flow_model_waits_for_independent_judge():
    model = voc_quality_view._manual_followup_flow_model(
        {
            "mode": "voc",
            "case": {"case_id": "TC-01", "question": "보험금 청구 진행 상태가 앱에 표시되지 않습니다."},
            "run_id": "RUN-MANUAL-01",
            "evidence_status": "PASS",
            "execution": {"ok": True, "result": {"ok": True}},
        },
        "TC-01",
        candidate={},
    )

    assert model["visible"] is True
    assert model["action_code"] == "RUN_JUDGE"
    assert model["target"]["enabled"] is False
    assert model["target"]["button_label"] == "위에서 독립 LLM 평가 실행"


def test_manual_followup_flow_model_links_judge_result_to_validity_page():
    model = voc_quality_view._manual_followup_flow_model(
        {
            "mode": "voc",
            "case": {"case_id": "TC-01", "question": "보험금 청구 진행 상태가 앱에 표시되지 않습니다."},
            "run_id": "RUN-MANUAL-01",
            "evidence_status": "PASS",
            "execution": {"ok": True, "result": {"ok": True}},
            "judge_result": {"decision": "PASS", "total_score": 91},
        },
        "TC-01",
        candidate={
            "run_id": "RUN-MANUAL-01",
            "case_id": "TC-01",
            "judge_status": "PASS",
            "judge_score": 91,
            "validity_status": "NOT_RUN",
            "workflow_state": "DRAFT",
            "immediate_hold_count": 0,
            "formal_approval": False,
        },
    )

    assert model["action_code"] == "RUN_VALIDITY"
    assert model["target"]["enabled"] is True
    assert model["target"]["page"] == voc_quality_view.VOC_VALIDITY_PAGE_NAME
    assert model["target"]["button_label"] == "타당성 평가로 이동"


def test_manual_followup_flow_model_links_review_required_to_run_evidence():
    model = voc_quality_view._manual_followup_flow_model(
        {
            "mode": "voc",
            "case": {"case_id": "TC-01", "question": "보험금 청구 진행 상태가 앱에 표시되지 않습니다."},
            "run_id": "RUN-MANUAL-01",
            "evidence_status": "PASS",
            "execution": {"ok": True, "result": {"ok": True}},
            "judge_result": {"decision": "REVIEW_REQUIRED", "total_score": 76},
        },
        "TC-01",
        candidate={
            "run_id": "RUN-MANUAL-01",
            "case_id": "TC-01",
            "judge_status": "REVIEW_REQUIRED",
            "judge_score": 76,
            "validity_status": "NOT_RUN",
            "workflow_state": "DRAFT",
            "immediate_hold_count": 0,
            "formal_approval": False,
        },
    )

    assert model["action_code"] == "REVIEW_PIPELINE_RESULT"
    assert model["target"]["enabled"] is True
    assert model["target"]["page"] == "history_detail"
    assert model["target"]["button_label"] == "Run 증적 확인"
    assert "바로 타당성 검증으로 넘기지 않고" in model["target"]["detail"]


def test_history_detail_target_moves_to_history_page(monkeypatch):
    state = {}
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    voc_quality_view._apply_history_next_action_target(
        {
            "page": "history_detail",
            "run_id": "RUN-MANUAL-01",
            "case_id": "TC-01",
            "action_code": "REVIEW_PIPELINE_RESULT",
        }
    )

    assert state["current_menu"] == voc_quality_view.VOC_QUALITY_MENU_NAME
    assert state["current_sub_menu"] == voc_quality_view.VOC_HISTORY_PAGE_NAME
    assert state[voc_quality_view.HISTORY_SELECTED_RUN_ID_KEY] == "RUN-MANUAL-01"
    assert state[voc_quality_view.HISTORY_DETAIL_DIALOG_RUN_ID_KEY] == "RUN-MANUAL-01"


def test_history_validity_target_filters_by_run_not_case(monkeypatch):
    class FakeSessionState(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    state = FakeSessionState()
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    voc_quality_view._apply_history_next_action_target(
        {
            "page": voc_quality_view.VOC_VALIDITY_PAGE_NAME,
            "run_id": "RUN-MANUAL-01",
            "case_id": "TC-01",
            "action_code": "RUN_VALIDITY",
        }
    )

    assert state["current_menu"] == voc_quality_view.VOC_QUALITY_MENU_NAME
    assert state["current_sub_menu"] == voc_quality_view.VOC_VALIDITY_PAGE_NAME
    assert state["voc_validity_selected_key"] == "RUN-MANUAL-01::TC-01"
    assert state["voc_validity_candidate_query"] == "RUN-MANUAL-01"
    assert state["voc_validity_candidate_status"] == "전체"
    assert state["voc_validity_focus_action_code"] == "RUN_VALIDITY"
    assert state["voc_validity_focus_target_key"] == "RUN-MANUAL-01::TC-01"
    assert state["voc_validity_evaluation_focus_once"] is True
    assert "개선안 타당성 평가를 실행" in state["voc_validity_focus_notice"]


def test_validity_candidate_sync_uses_artifact_judge_pass_when_summary_is_stale():
    candidate = {
        "run_id": "RUN-MANUAL-01",
        "case_id": "TC-01",
        "judge_status": "NOT_RUN",
        "judge_score": None,
        "validity_status": "NOT_RUN",
        "workflow_state": "DRAFT",
    }
    artifacts = {
        "judge_result": {
            "decision": "PASS",
            "total_score": 87,
            "provider": "gemini",
            "model": "gemini-2.5-pro",
        }
    }

    synced = voc_quality_view._sync_validity_candidate_from_artifacts(candidate, artifacts)
    gate = voc_quality_view._validity_judge_gate_model(synced, artifacts)

    assert synced["judge_status"] == "PASS"
    assert synced["judge_score"] == 87
    assert synced["judge_provider"] == "gemini"
    assert gate["blocked"] is False
    assert gate["next_title"] == "타당성 평가 진행 가능"


@pytest.mark.parametrize(
    ("workflow_state", "expected_action", "expected_button"),
    [
        ("AI_REVIEWED", "QA_REVIEW", "QA 검토로 이동"),
        ("QA_REVIEWED", "BUSINESS_APPROVAL", "업무 승인으로 이동"),
    ],
)
def test_manual_followup_flow_model_links_validity_to_human_approval(
    workflow_state,
    expected_action,
    expected_button,
):
    model = voc_quality_view._manual_followup_flow_model(
        {
            "mode": "voc",
            "case": {"case_id": "TC-01", "question": "보험금 청구 진행 상태가 앱에 표시되지 않습니다."},
            "run_id": "RUN-MANUAL-01",
            "evidence_status": "PASS",
            "execution": {"ok": True, "result": {"ok": True}},
            "judge_result": {"decision": "PASS", "total_score": 91},
        },
        "TC-01",
        candidate={
            "run_id": "RUN-MANUAL-01",
            "case_id": "TC-01",
            "judge_status": "PASS",
            "judge_score": 91,
            "validity_status": "AI_PASS",
            "validity_score": 88,
            "workflow_state": workflow_state,
            "immediate_hold_count": 0,
            "formal_approval": False,
        },
    )

    assert model["action_code"] == expected_action
    assert model["target"]["enabled"] is True
    assert model["target"]["page"] == voc_quality_view.VOC_VALIDITY_PAGE_NAME
    assert model["target"]["button_label"] == expected_button


def test_goal_pipeline_uses_compact_inline_guide():
    import inspect

    source = inspect.getsource(voc_quality_view.render_goal_monitor)

    assert 'st.markdown("### 실시간 Agent 파이프라인")' in source
    assert "?? ? 2? ?? ? ?? ? ?? Trace ??" not in source
    assert "실행 중에는 현재 흐름을 2초 간격으로 확인하고" not in source
    assert "horizontal=True" in source


def test_manual_result_renders_human_readable_judgment_evidence():
    app = AppTest.from_file("tests/fixtures/voc_manual_result_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    markdown = "\n".join(item.value for item in app.markdown)
    success_text = "\n".join(item.value for item in app.success)
    assert "보험금 청구 진행 상태가 앱에 표시되지 않습니다." in markdown
    assert "vqa-voc-question-card" in markdown
    assert "Pipeline completed via agent-to-agent calls" not in success_text
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
    assert "claude-haiku-4-5" in app.button[1].label
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
    assert "실행 Trace 사유 미기록·추정" in html


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


def test_pipeline_run_summary_uses_selected_case_for_recent_trace(monkeypatch):
    monkeypatch.setattr(
        voc_quality_view.st,
        "session_state",
        {
            "goal_testcase_selected_case_id": "TC-16",
            "goal_testcase_result": {
                "mode": "voc",
                "case": {"case_id": "TC-14"},
                "execution": {"ok": True, "result": {"ok": True}},
            },
        },
    )

    summary = voc_quality_view._pipeline_run_summary({"events": []}, running=False)

    assert summary["case_id"] == "TC-16"


def test_sync_goal_testcase_recent_artifacts_restores_selected_case_result(monkeypatch):
    state = {}
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view,
        "list_voc_run_history",
        lambda: [
            {
                "run_id": "RUN-1",
                "run_dir": "reports/voc_quality_runs/RUN-1",
                "selected_case_ids": ["TC-16"],
                "case_results": [
                    {
                        "case_id": "TC-16",
                        "status": "REVIEW_REQUIRED",
                        "started_at": "2026-07-17T10:00:00+09:00",
                        "finished_at": "2026-07-17T10:00:04+09:00",
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(
        voc_quality_view,
        "load_voc_case_history_detail",
        lambda run_id, case_id: {
            "pipeline_result": {
                "run_id": run_id,
                "case_id": case_id,
                "mode": "voc",
                "execution": {"ok": True, "result": {"ok": True}},
            },
            "trace": {"trace_id": "trace-16", "events": []},
        },
    )

    voc_quality_view._sync_goal_testcase_recent_artifacts(
        {"case_id": "TC-16", "question": "TC-16 ??? ??"}
    )

    assert state["goal_testcase_result"]["case"]["case_id"] == "TC-16"
    assert state["goal_testcase_result"]["case"]["question"] == "TC-16 ??? ??"
    assert state["goal_testcase_trace_id"] == "trace-16"
    assert state["goal_testcase_started_at"] == "2026-07-17T10:00:00+09:00"


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
            "model": "claude-haiku-4-5",
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
    assert any("독립 LLM 평가 결과" in item.value for item in app.markdown)
    assert any("Provider별 독립 LLM 평가 비교" in item.value for item in app.markdown)
    comparison_tables = [
        dataframe.value
        for dataframe in app.dataframe
        if "평가 Provider" in dataframe.value.columns
    ]
    assert comparison_tables
    assert set(comparison_tables[0]["평가 Provider"]) == {"OpenAI", "Anthropic"}
    assert "수행 시간" in comparison_tables[0].columns
    openai_row = comparison_tables[0].loc[
        comparison_tables[0]["평가 Provider"] == "OpenAI"
    ].iloc[0]
    assert openai_row["수행 시간"] == "9.1초"
    assert openai_row["평가 시각"] == "2026-07-31 12:00:00"
    dimension_tables = [
        dataframe.value
        for dataframe in app.dataframe
        if "평가 차원" in dataframe.value.columns
    ]
    assert dimension_tables[0].iloc[0]["평가 차원"] == "accuracy"


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
        "load_unified_quality_cases",
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
        goal_testcase_completed_at="2026-07-17T10:00:05+09:00",
        goal_testcase_preparation={"status": "COMPLETED"},
        goal_testcase_agent_snapshot={"stale": True},
    )
    captured = {}
    clear_calls = []

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
    monkeypatch.setattr(voc_quality_view._load_goal_monitor_snapshot, "clear", lambda: clear_calls.append(True))

    voc_quality_view._start_goal_testcase_pipeline("TC-01")

    assert state["goal_testcase_job_id"] == "manual-job-1"
    assert state["goal_testcase_running_case_id"] == "TC-01"
    assert "goal_testcase_result" not in state
    assert "goal_testcase_trace_id" not in state
    assert "goal_testcase_completed_at" not in state
    assert "goal_testcase_agent_snapshot" not in state
    assert state["goal_testcase_focus_pipeline_once"] is True
    assert state["goal_testcase_preparation"]["status"] == "RUNNING"
    assert state["goal_testcase_preparation"]["steps"][0]["status"] == "active"
    assert state["goal_testcase_preparation"]["steps"][1]["status"] == "waiting"
    assert captured["args"][:2] == ("manual-pipeline", "TC-01")
    assert captured["kwargs"]["progress"]["preparation"]["status"] == "RUNNING"
    assert captured["kwargs"]["progress"]["preparation"]["steps"][0]["status"] == "active"
    assert clear_calls == [True]


def test_manual_pipeline_start_callback_requests_full_app_rerun(monkeypatch):
    calls = []
    reruns = []

    monkeypatch.setattr(
        voc_quality_view,
        "_start_goal_testcase_pipeline",
        lambda case_id: calls.append(case_id),
    )
    monkeypatch.setattr(
        voc_quality_view.st,
        "rerun",
        lambda *, scope="app": reruns.append(scope),
    )

    voc_quality_view._start_goal_testcase_pipeline_and_rerun("TC-01")

    assert calls == ["TC-01"]
    assert reruns == ["app"]


def test_goal_pipeline_focus_anchor_stays_mounted_and_scrolls_once(monkeypatch):
    state = {"goal_testcase_focus_pipeline_once": True}
    rendered = []

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view.st,
        "html",
        lambda body, **kwargs: rendered.append((body, kwargs)),
    )

    voc_quality_view._render_goal_pipeline_focus_anchor_once()
    voc_quality_view._render_goal_pipeline_focus_anchor_once()

    assert len(rendered) == 2
    assert "goal-pipeline-scroll-anchor" in rendered[0][0]
    assert "scrollIntoView" in rendered[0][0]
    assert rendered[0][1]["unsafe_allow_javascript"] is True
    assert "goal-pipeline-scroll-anchor" in rendered[1][0]
    assert "scrollIntoView" not in rendered[1][0]
    assert rendered[1][1]["unsafe_allow_javascript"] is False
    assert "goal_testcase_focus_pipeline_once" not in state


def test_goal_result_focus_anchor_stays_mounted_and_scrolls_once(monkeypatch):
    state = {"goal_testcase_focus_result": True}
    rendered = []

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view.st,
        "html",
        lambda body, **kwargs: rendered.append((body, kwargs)),
    )

    voc_quality_view._render_goal_result_focus_anchor_once()
    voc_quality_view._render_goal_result_focus_anchor_once()

    assert len(rendered) == 2
    assert "goal-result-scroll-anchor" in rendered[0][0]
    assert "scrollIntoView" in rendered[0][0]
    assert rendered[0][1]["unsafe_allow_javascript"] is True
    assert "goal-result-scroll-anchor" in rendered[1][0]
    assert "scrollIntoView" not in rendered[1][0]
    assert rendered[1][1]["unsafe_allow_javascript"] is False
    assert "goal_testcase_focus_result" not in state


def test_goal_judge_result_focus_anchor_stays_mounted_and_scrolls_once(monkeypatch):
    state = {"goal_judge_result_focus_once": True}
    rendered = []

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view.st,
        "html",
        lambda body, **kwargs: rendered.append((body, kwargs)),
    )

    voc_quality_view._render_goal_judge_result_focus_anchor_once()
    voc_quality_view._render_goal_judge_result_focus_anchor_once()

    assert len(rendered) == 2
    assert "goal-judge-result-scroll-anchor" in rendered[0][0]
    assert "scrollIntoView" in rendered[0][0]
    assert rendered[0][1]["unsafe_allow_javascript"] is True
    assert "goal-judge-result-scroll-anchor" in rendered[1][0]
    assert "scrollIntoView" not in rendered[1][0]
    assert rendered[1][1]["unsafe_allow_javascript"] is False
    assert "goal_judge_result_focus_once" not in state


def test_live_testcase_pipeline_renders_recent_snapshot_without_active_job(monkeypatch):
    state = {
        "goal_testcase_selected_case_id": "TC-01",
        "goal_testcase_started_at": "2026-07-31T13:00:00+09:00",
        "goal_testcase_trace_id": "trace-recent",
        "goal_testcase_preparation": {"status": "COMPLETED"},
    }
    calls = []

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(
        voc_quality_view,
        "_selected_goal_testcase",
        lambda: {"case_id": "TC-01"},
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_sync_goal_testcase_recent_artifacts",
        lambda case: calls.append(("sync", case["case_id"])),
    )
    monkeypatch.setattr(
        voc_quality_view,
        "pipeline_trace_events",
        lambda started_at, trace_id: {
            "trace_id": trace_id,
            "events": [],
            "started_at": started_at,
        },
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_pipeline_comparison",
        lambda snapshot, running, preparation=None: calls.append(
            ("render", snapshot["trace_id"], running, preparation)
        ),
    )

    getattr(voc_quality_view._live_testcase_pipeline, "__wrapped__", voc_quality_view._live_testcase_pipeline)()

    assert calls == [
        ("sync", "TC-01"),
        ("render", "trace-recent", False, {"status": "COMPLETED"}),
    ]


def test_live_testcase_pipeline_renders_running_preparation_immediately(monkeypatch):
    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    preparation = voc_quality_view._new_manual_preparation_progress()
    state = State(
        goal_testcase_job_id="manual-job-1",
        goal_testcase_started_at="2026-07-31T13:00:00+09:00",
        goal_testcase_running_case_id="TC-01",
        goal_testcase_preparation=preparation,
    )
    calls = []
    running_job = {
        "job_id": "manual-job-1",
        "target_id": "TC-01",
        "status": "RUNNING",
        "done": False,
        "progress": {"preparation": preparation},
    }

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view, "background_job_snapshot", lambda job_id: running_job)
    monkeypatch.setattr(
        voc_quality_view,
        "pipeline_trace_events",
        lambda started_at, trace_id: {
            "trace_id": "",
            "events": [],
            "started_at": started_at,
        },
    )
    monkeypatch.setattr(
        voc_quality_view,
        "_render_agent_pipeline_comparison",
        lambda snapshot, running, preparation=None: calls.append(
            (snapshot["started_at"], running, preparation)
        ),
    )

    getattr(voc_quality_view._live_testcase_pipeline, "__wrapped__", voc_quality_view._live_testcase_pipeline)()

    assert calls == [("2026-07-31T13:00:00+09:00", True, preparation)]
    assert state["goal_testcase_preparation"] == preparation


def test_live_testcase_pipeline_completion_focuses_result_with_app_rerun(monkeypatch):
    class State(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    preparation = voc_quality_view._new_manual_preparation_progress()
    completed_result = {
        "case": {"case_id": "TC-01"},
        "mode": "voc",
        "execution": {"ok": True, "result": {"ok": True}},
    }
    agent_snapshot = {"agents": []}
    state = State(
        goal_testcase_job_id="manual-job-1",
        goal_testcase_started_at="2026-07-31T13:00:00+09:00",
        goal_testcase_running_case_id="TC-01",
    )
    completed_job = {
        "job_id": "manual-job-1",
        "target_id": "TC-01",
        "status": "COMPLETED",
        "done": True,
        "progress": {"preparation": preparation},
        "result": {
            "testcase_result": completed_result,
            "agent_snapshot": agent_snapshot,
        },
    }
    discarded = []
    clear_calls = []
    reruns = []

    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    monkeypatch.setattr(voc_quality_view, "background_job_snapshot", lambda job_id: completed_job)
    monkeypatch.setattr(voc_quality_view, "discard_background_job", lambda job_id: discarded.append(job_id))
    monkeypatch.setattr(voc_quality_view._load_goal_monitor_snapshot, "clear", lambda: clear_calls.append(True))
    monkeypatch.setattr(voc_quality_view.st, "rerun", lambda **kwargs: reruns.append(kwargs))

    getattr(voc_quality_view._live_testcase_pipeline, "__wrapped__", voc_quality_view._live_testcase_pipeline)()

    assert state["goal_testcase_result"] == completed_result
    assert state["goal_testcase_agent_snapshot"] == agent_snapshot
    assert state["goal_testcase_preparation"] == preparation
    assert state["goal_testcase_focus_result"] is True
    assert "goal_testcase_job_id" not in state
    assert discarded == ["manual-job-1"]
    assert clear_calls == [True]
    assert reruns == [{"scope": "app"}]


def test_embedded_voc_runtime_is_complete():
    health = runtime_health()
    assert health["ok"], health["missing"]
    assert Path(health["runtime_dir"]) == PROJECT_DIR / "voc_quality_runtime"


def test_testcase_distribution_and_rubric_total():
    summary = get_test_case_summary()
    assert summary["total"] == 35
    assert summary["categories"] == {
        "normal_voc": 8,
        "ambiguous_question": 3,
        "compound_complaint": 3,
        "no_data": 2,
        "typo_or_ungrammatical": 2,
        "fault_condition": 2,
        "isolated_fault": 6,
        "agent_role_quality": 6,
        "quality_gate": 3,
    }
    rubric = load_system_rubric()
    assert rubric["total_points"] == 100
    assert sum(category["max_points"] for category in rubric["categories"].values()) == 100


def test_unified_quality_cases_merge_35_catalog_with_legacy_execution_details():
    legacy = load_test_cases()
    unified = load_unified_quality_cases()
    cases = {item["case_id"]: item for item in unified["cases"]}

    assert len(legacy["cases"]) == 20
    assert len(cases) == 35
    assert cases["TC-01"]["execution_type"] == "voc_pipeline"
    assert cases["TC-01"]["question"]
    assert cases["TC-01"]["execution"]["runner"] == "scripts/run-voc.py"
    assert cases["TC-19"]["execution_type"] == "fault_proxy"
    assert cases["TC-19"]["execution"]["fault_case_id"] == "FT-01"
    assert cases["FT-01"]["execution_type"] == "isolated_fault"
    assert cases["FT-01"]["execution"]["fault_case_id"] == "FT-01"
    assert cases["AG-01"]["execution_type"] == "agent_role_quality"
    assert cases["QG-01"]["execution_type"] == "quality_gate"


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


def test_testcase_page_ignores_stale_row_selection_after_group_filter_change():
    app = AppTest.from_file(
        "tests/fixtures/voc_testcase_catalog_app.py", default_timeout=15
    )
    app.run()
    app.session_state["voc_testcase_catalog_table"] = {
        "selection": {"rows": [34], "columns": [], "cells": []}
    }
    app.session_state["voc_testcase_selected_case_id"] = "QG-03"

    app.selectbox[0].set_value("quality_gate").run()

    assert not app.exception
    catalog_table = app.dataframe[0].value
    assert len(catalog_table) == 3
    assert set(catalog_table["Case ID"]) == {"QG-01", "QG-02", "QG-03"}
    headings = [item.value for item in app.markdown]
    assert "**QG-03** · 개선안 타당성·배포 게이트" in headings


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


def test_catalog_upload_error_cards_identify_case_and_field():
    cards = voc_quality_view._catalog_upload_error_cards([
        "TC-01: 필수 필드 누락 ['acceptance', 'execution']",
        "TC-02: execution.expected_task must be summary, policy, or both",
        "TC-03: name가 필요합니다.",
        "cases[4]: 객체 형식이어야 합니다.",
        "total_cases(34)와 cases 건수(35)가 다릅니다.",
        "JSON 파일을 해석할 수 없습니다: Expecting value",
    ])

    assert cards[0] == {
        "case_ref": "TC-01",
        "field": "acceptance, execution",
        "message": "필수 필드 누락 ['acceptance', 'execution']",
    }
    assert cards[1]["case_ref"] == "TC-02"
    assert cards[1]["field"] == "execution.expected_task"
    assert cards[2]["case_ref"] == "TC-03"
    assert cards[2]["field"] == "name"
    assert cards[3]["case_ref"] == "cases[4]"
    assert cards[3]["field"] == "Case 형식"
    assert cards[4]["case_ref"] == "카탈로그"
    assert cards[4]["field"] == "cases"
    assert cards[5]["case_ref"] == "카탈로그"
    assert cards[5]["field"] == "JSON 형식"


def test_quality_catalog_defines_exactly_35_unique_cases():
    catalog = load_quality_test_catalog()
    cases = catalog["cases"]
    case_ids = [item["case_id"] for item in cases]
    by_id = {item["case_id"]: item for item in cases}

    assert catalog["schema_version"] == "2.0"
    assert catalog["suite_id"] == "VOC-QA-35"
    assert catalog["total_cases"] == len(cases) == 35
    assert len(case_ids) == len(set(case_ids))
    assert all(item.get("execution_type") and isinstance(item.get("execution"), dict) for item in cases)
    assert by_id["TC-01"]["execution"]["question"]
    assert by_id["TC-19"]["execution"]["fault_case_id"] == "FT-01"
    assert by_id["FT-01"]["execution"]["fault_case_id"] == "FT-01"
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


def test_validity_candidate_rows_remove_empty_select_column_and_localize_statuses():
    rows = voc_quality_view._validity_candidate_rows(
        [
            {
                "run_id": "RUN-20260726-000000-000000-abcd",
                "case_id": "TC-01",
                "started_at": "2026-07-26T10:00:00+09:00",
                "run_type": "BATCH",
                "question": "보험금 청구 진행 상태가 앱에 표시되지 않습니다.",
                "judge_status": "NOT_RUN",
                "judge_score": None,
                "validity_status": "AI_PASS",
                "validity_score": 88,
                "workflow_state": "QA_REVIEWED",
                "formal_approval": False,
                "review_action_label": "업무 승인 가능",
            }
        ],
        selected_key="RUN-20260726-000000-000000-abcd::TC-01",
    )

    assert "선택" not in rows.columns
    assert list(rows.columns) == [
        "Case ID",
        "질문",
        "다음 조치",
        "개선안 타당성",
        "타당성 점수",
        "승인 단계",
        "독립 LLM 평가",
        "독립 LLM 점수",
        "수행 유형",
        "수행 일시",
        "정식 승인",
        "Run ID",
    ]
    row = rows.iloc[0]
    assert row["수행 유형"] == "일괄 수행"
    assert row["독립 LLM 평가"] == "미실행"
    assert row["개선안 타당성"] == "AI 평가 통과"
    assert row["승인 단계"] == "QA 검토 완료"
    assert row["다음 조치"] == "업무 승인 가능"


def test_quality_rubric_menu_exposes_three_separate_stages(monkeypatch):
    assert voc_quality_view.RUBRIC_STAGE_OPTIONS == (
        "내부 파이프라인 품질",
        "독립 LLM 평가",
        "개선안 타당성 평가",
    )

    judge_rows = voc_quality_view._rubric_rows(
        load_independent_judge_rubric()["dimensions"]
    )
    validity_rows = voc_quality_view._rubric_rows(
        load_improvement_validity_rubric()["dimensions"]
    )
    assert sum(row["배점"] for row in judge_rows) == 100
    assert sum(row["배점"] for row in validity_rows) == 100
    assert all("통과 하한" in row for row in judge_rows + validity_rows)

    rendered = []
    tab_labels = []
    monkeypatch.setattr(voc_quality_view.st, "markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view.st, "caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(voc_quality_view, "_render_rubric_stage_tab_style", lambda: None)

    def select_stage(label, *_args, **_kwargs):
        tab_labels.append(label)
        return "독립 LLM 평가"

    monkeypatch.setattr(
        voc_quality_view.st,
        "radio",
        select_stage,
    )
    monkeypatch.setattr(voc_quality_view, "_render_rubric_management", rendered.append)

    voc_quality_view.render_rubric()

    assert tab_labels == ["수정할 평가 단계"]
    assert rendered == ["독립 LLM 평가"]


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
    assert [control.label for control in app.radio] == ["수정할 평가 단계"]
    stage_tab_css = app.get("html")[0].proto.body
    assert "border-bottom-color:#2f6fb0" in stage_tab_css
    assert "background:#eaf3fc" in stage_tab_css
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
    assert app.radio[0].proto.label_visibility.value == LabelVisibility.COLLAPSED
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
    assert [item.label for item in app.status] == ["즉시 실패·보류 규칙"]
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
        "내부 파이프라인 품질": ("해당 없음", True),
        "독립 LLM 평가": ("anthropic", False),
        "개선안 타당성 평가": ("해당 없음", True),
    }
    expected_rubric_types = {
        "내부 파이프라인 품질": "internal_pipeline",
        "독립 LLM 평가": "independent_judge",
        "개선안 타당성 평가": "improvement_validity",
    }
    for stage, expected_provider in expected_provider_states.items():
        app.radio[0].set_value(stage).run()

        assert not app.exception
        header_columns = app.get("column")[:7]
        expected_weights = [1.0, 1.8, 1.4, 0.8, 0.8, 0.78, 1.32]
        expected_total = sum(expected_weights)
        assert len(app.get("column")) == 9
        assert [column.proto.weight for column in header_columns] == pytest.approx(
            [weight / expected_total for weight in expected_weights]
        )
        assert all(
            column.proto.vertical_alignment == Block.Column.BOTTOM
            for column in header_columns
        )
        save_state_column_children = list(header_columns[5].children.values())
        save_column_children = list(header_columns[6].children.values())
        assert getattr(save_state_column_children[0], "type", None) == "flex_container"
        assert save_column_children[0].label == "평가 기준 저장"
        assert [item.label for item in app.text_input[:2]] == ["Rubric 버전", "기준명"]
        provider = next(
            item for item in app.selectbox if item.label == "기본 평가 Provider"
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
    assert intent.min == 1
    assert intent.max == 5

    intent.set_value(5).run()

    assert not app.exception
    draft = app.session_state["rubric_edit_internal_pipeline_draft"]
    assert draft["categories"]["interpreter"]["criteria"]["intent"] == 5
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
    def criteria_panel(app):
        dialog = next(
            child
            for child in app._tree[2].children.values()
            if getattr(child, "type", None) == "dialog"
        )
        return dialog[0][1]

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
    improver_criteria_panel = criteria_panel(app)
    navigation_style = next(
        item.proto.body
        for item in app.get("html")
        if "min-height: 430px" in item.proto.body
    )

    assert not app.exception
    assert len(improver_sliders) == 5
    assert improver_criteria_panel.proto.height_config.use_content
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
    assert criteria_panel(app).proto.height_config.use_content


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
    app.radio[0].set_value("독립 LLM 평가").run()

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
        for item in app.markdown
    )
    assert all(
        "평가 항목 합계 점수" not in item.value
        for item in app.markdown
    )
    assert all(
        "모든 평가 항목의 세부 배점을 합산한 최종 점수입니다." not in item.value
        for item in app.caption
    )


def test_rubric_save_control_state_enables_only_valid_versioned_changes():
    no_change = voc_quality_view._rubric_save_control_state(
        has_changes=False,
        needs_version_change=False,
        validation_errors=[],
        last_save_message=None,
        saved_signature=None,
        draft_signature="same",
    )
    saved = voc_quality_view._rubric_save_control_state(
        has_changes=False,
        needs_version_change=False,
        validation_errors=[],
        last_save_message="변경완료",
        saved_signature="same",
        draft_signature="same",
    )
    version_missing = voc_quality_view._rubric_save_control_state(
        has_changes=True,
        needs_version_change=True,
        validation_errors=[],
        last_save_message=None,
        saved_signature=None,
        draft_signature="changed",
    )
    invalid_total = voc_quality_view._rubric_save_control_state(
        has_changes=True,
        needs_version_change=False,
        validation_errors=["평가 항목 배점 합계는 100이어야 합니다. 현재 합계: 102"],
        last_save_message=None,
        saved_signature=None,
        draft_signature="changed",
    )
    valid_change = voc_quality_view._rubric_save_control_state(
        has_changes=True,
        needs_version_change=False,
        validation_errors=[],
        last_save_message=None,
        saved_signature=None,
        draft_signature="changed",
    )

    assert no_change["label"] == "변경없음"
    assert no_change["disabled"] is True
    assert saved["label"] == "변경완료"
    assert saved["disabled"] is True
    assert version_missing["label"] == "변경발생"
    assert version_missing["disabled"] is True
    assert version_missing["focus_version"] is True
    assert "Rubric 버전" in version_missing["help"]
    assert invalid_total["label"] == "변경발생"
    assert invalid_total["disabled"] is True
    assert "저장 전 확인 필요" in invalid_total["help"]
    assert valid_change["label"] == "변경발생"
    assert valid_change["disabled"] is False


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


def test_rubric_criterion_range_allows_narrow_temporary_budget_variance():
    rubric = deepcopy(load_system_rubric())
    items = rubric["categories"]

    assert voc_quality_view._rubric_total(items) == 100
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (1, 5)

    items["interpreter"]["criteria"]["intent"] = 2

    assert voc_quality_view._rubric_total(items) == 99
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (0, 4)
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "keywords") == (1, 5)

    items["interpreter"]["criteria"]["intent"] = 0
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (0, 2)


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
    assert next(metric.value for metric in app.metric if metric.label == "상태") == "진행 중"
    progress = app.get("progress")
    assert len(progress) == 1
    assert progress[0].value == 50
    assert "전체 예상 진행률 50%" in progress[0].proto.text
    assert "완료 2 / 4건" in progress[0].proto.text
    assert any("stProgress" in item.value and "24px" in item.value for item in app.markdown)
    assert any("닫기" in button.label for button in app.button)


def test_batch_case_results_for_display_uses_korean_status_labels():
    frame = voc_quality_view._batch_case_results_for_display([
        {
            "case_id": "TC-01",
            "status": "NOT_RUN",
            "mode": "voc",
            "attempt_count": 0,
            "judge_status": "ERROR",
            "judge_score": None,
            "judge_independence_grade": "-",
            "message": "대기",
            "finished_at": "-",
        }
    ])

    assert list(frame.columns) == [
        "케이스 ID",
        "상태",
        "수행 유형",
        "시도",
        "독립 LLM 평가 상태",
        "독립 LLM 평가 점수",
        "독립성",
        "처리 내용",
        "완료 시각",
    ]
    assert frame.iloc[0]["상태"] == "미실행"
    assert frame.iloc[0]["수행 유형"] == "VOC"
    assert frame.iloc[0]["독립 LLM 평가 상태"] == "오류"


def test_batch_selector_state_defaults_to_all_cases_and_first_group(monkeypatch):
    state = {}
    cases = [
        {"case_id": "TC-01", "group": "voc"},
        {"case_id": "TC-02", "group": "voc"},
        {"case_id": "QG-01", "group": "gate"},
    ]
    groups = {"voc": {"label": "VOC"}, "gate": {"label": "Gate"}}
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    selection = voc_quality_view._ensure_batch_selection_state(cases, groups)

    assert selection["selected_ids"] == ["TC-01", "TC-02", "QG-01"]
    assert selection["active_group"] == "voc"
    assert state[voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY] == ["TC-01", "TC-02", "QG-01"]
    assert state[voc_quality_view.BATCH_ACTIVE_GROUP_KEY] == "voc"


def test_batch_group_rows_show_full_partial_and_empty_states():
    group_keys = ("voc", "gate", "agent")
    cases_by_group = {
        "voc": [{"case_id": "TC-01"}, {"case_id": "TC-02"}],
        "gate": [{"case_id": "QG-01"}],
        "agent": [{"case_id": "AG-01"}],
    }
    groups = {
        "voc": {"label": "VOC"},
        "gate": {"label": "Gate"},
        "agent": {"label": "Agent"},
    }

    rows = voc_quality_view._batch_group_table_rows(
        group_keys,
        cases_by_group,
        groups,
        ["TC-01", "QG-01"],
    )

    assert "선택" not in rows.columns
    assert rows.loc[0, "상태"] == "부분 선택"
    assert rows.loc[0, "현황"] == "1 / 2건"
    assert rows.loc[1, "상태"] == "전체 선택"
    assert rows.loc[2, "상태"] == "미선택"


def test_batch_combined_selection_rows_merge_groups_and_cases():
    group_keys = ("voc", "gate")
    cases_by_group = {
        "voc": [
            {"case_id": "TC-01", "name": "첫 번째", "implementation_status": "IMPLEMENTED"},
            {"case_id": "TC-02", "name": "두 번째", "implementation_status": "DEFINED"},
        ],
        "gate": [{"case_id": "QG-01", "name": "게이트", "implementation_status": "DEFINED"}],
    }
    groups = {"voc": {"label": "VOC"}, "gate": {"label": "Gate"}}

    rows = voc_quality_view._batch_combined_selection_rows(
        group_keys,
        cases_by_group,
        groups,
        ["TC-01", "QG-01"],
    )

    assert "선택" not in rows.columns
    assert list(rows.columns)[:6] == ["체크", "구분", "대상", "이름", "구현 상태", "선택 현황"]
    assert rows.loc[0, "_kind"] == "group"
    assert rows.loc[0, "구분"] == "그룹"
    assert rows.loc[0, "대상"] == "VOC"
    assert bool(rows.loc[0, "체크"]) is False
    assert rows.loc[0, "구현 상태"] == "부분 선택"
    assert rows.loc[1, "_kind"] == "case"
    assert rows.loc[1, "구분"] == "Case"
    assert bool(rows.loc[1, "체크"]) is True
    assert bool(rows.loc[3, "체크"]) is True


def test_batch_group_table_rows_show_visual_selection_state():
    group_keys = ("voc", "gate")
    cases_by_group = {
        "voc": [
            {"case_id": "TC-01", "name": "첫 번째", "implementation_status": "IMPLEMENTED"},
            {"case_id": "TC-02", "name": "두 번째", "implementation_status": "DEFINED"},
        ],
        "gate": [{"case_id": "QG-01", "name": "게이트", "implementation_status": "DEFINED"}],
    }
    groups = {"voc": {"label": "VOC"}, "gate": {"label": "Gate"}}

    rows = voc_quality_view._batch_group_table_rows(
        group_keys,
        cases_by_group,
        groups,
        ["TC-01", "QG-01"],
    )

    assert list(rows.columns)[:4] == ["그룹", "상태", "현황", "실행 가능"]
    assert rows.loc[0, "상태"] == "부분 선택"
    assert rows.loc[0, "현황"] == "1 / 2건"
    assert rows.loc[1, "상태"] == "전체 선택"


def test_batch_group_toggle_selects_or_clears_entire_group(monkeypatch):
    state = {
        voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY: ["TC-01"],
        voc_quality_view.BATCH_GROUP_TOGGLE_KEY: {"row": 0, "label": "◩"},
    }
    group_keys = ("voc", "gate")
    group_case_ids = {"voc": ("TC-01", "TC-02"), "gate": ("QG-01",)}
    all_case_ids = ("TC-01", "TC-02", "QG-01")
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    voc_quality_view._toggle_batch_group_selection_from_click(
        group_keys,
        group_case_ids,
        all_case_ids,
    )

    assert state[voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY] == ["TC-01", "TC-02"]
    assert state[voc_quality_view.BATCH_ACTIVE_GROUP_KEY] == "voc"

    voc_quality_view._toggle_batch_group_selection_from_click(
        group_keys,
        group_case_ids,
        all_case_ids,
    )

    assert state[voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY] == []


def test_batch_combined_editor_group_and_case_checkbox_updates_selection(monkeypatch):
    state = {
        voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY: ["TC-01", "QG-01"],
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    group_keys = ("voc", "gate")
    cases_by_group = {
        "voc": [{"case_id": "TC-01"}, {"case_id": "TC-02"}],
        "gate": [{"case_id": "QG-01"}],
    }
    original = voc_quality_view._batch_combined_selection_rows(
        group_keys,
        cases_by_group,
        {"voc": {"label": "VOC"}, "gate": {"label": "Gate"}},
        ["TC-01", "QG-01"],
    )
    edited = original.copy()
    edited.loc[0, "체크"] = True

    selected, changed = voc_quality_view._apply_batch_combined_editor_selection(
        original,
        edited,
        ("TC-01", "TC-02", "QG-01"),
        cases_by_group,
    )

    assert changed is True
    assert selected == ["TC-01", "TC-02", "QG-01"]

    original = voc_quality_view._batch_combined_selection_rows(
        group_keys,
        cases_by_group,
        {"voc": {"label": "VOC"}, "gate": {"label": "Gate"}},
        selected,
    )
    edited = original.copy()
    edited.loc[2, "체크"] = False

    selected, changed = voc_quality_view._apply_batch_combined_editor_selection(
        original,
        edited,
        ("TC-01", "TC-02", "QG-01"),
        cases_by_group,
    )

    assert changed is True
    assert selected == ["TC-01", "QG-01"]


def test_batch_case_row_selection_preserves_other_group_choices(monkeypatch):
    state = {
        voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY: ["TC-01", "QG-01"],
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)

    selected = voc_quality_view._apply_batch_case_row_selection(
        ("TC-01", "TC-02"),
        [1],
        ("TC-01", "TC-02", "QG-01"),
    )

    assert selected == ["TC-02", "QG-01"]
    assert state[voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY] == ["TC-02", "QG-01"]


def test_batch_case_selection_rows_show_active_group_cases_only():
    rows = voc_quality_view._batch_case_selection_rows(
        [
            {"case_id": "TC-01", "name": "첫 번째", "implementation_status": "IMPLEMENTED"},
            {"case_id": "TC-02", "name": "두 번째", "implementation_status": "DEFINED"},
        ],
        ["TC-02"],
    )

    assert list(rows.columns)[:4] == ["체크", "케이스 ID", "상태", "이름"]
    assert bool(rows.loc[0, "체크"]) is False
    assert bool(rows.loc[1, "체크"]) is True
    assert rows.loc[0, "상태"] == "실행 구현 완료"
    assert rows.loc[1, "상태"] == "정의됨 · 후속 구현"


def test_batch_case_editor_selection_preserves_other_group_choices(monkeypatch):
    state = {
        voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY: ["TC-01", "QG-01"],
    }
    monkeypatch.setattr(voc_quality_view.st, "session_state", state)
    original = voc_quality_view._batch_case_selection_rows(
        [{"case_id": "TC-01"}, {"case_id": "TC-02"}],
        ["TC-01", "QG-01"],
    )
    edited = original.copy()
    edited.loc[0, "체크"] = False
    edited.loc[1, "체크"] = True

    selected, changed = voc_quality_view._apply_batch_case_editor_selection(
        original,
        edited,
        ("TC-01", "TC-02", "QG-01"),
    )

    assert changed is True
    assert selected == ["TC-02", "QG-01"]
    assert state[voc_quality_view.BATCH_SELECTED_CASE_IDS_KEY] == ["TC-02", "QG-01"]


def test_batch_execution_uses_list_selector_instead_of_dropdowns():
    import inspect

    source = inspect.getsource(voc_quality_view.render_batch_execution)
    selector_source = inspect.getsource(voc_quality_view._render_batch_case_selector)

    assert "_render_batch_case_selector" in source
    assert "segmented_control" not in source
    assert "multiselect" not in source
    assert "data_editor" in selector_source
    assert "CheckboxColumn" in selector_source
    assert "ButtonColumn" not in selector_source
    assert "column_order=[\"체크\", \"케이스 ID\", \"상태\", \"이름\"]" in selector_source
    assert "실행 대상 리스트" not in selector_source
    assert "검증 그룹" in selector_source
    assert "_batch_case_selection_rows" in selector_source
    assert "_batch_combined_selection_rows" not in selector_source
    assert "전체선택" in selector_source
    assert "실행가능" in selector_source
    assert "선택해제" in selector_source
    assert "보기" in selector_source
    assert "Case 선택" in selector_source
    assert "_render_batch_selection_mini_summary" in selector_source
    assert "독립 LLM 평가 옵션" in selector_source
    assert "_render_batch_judge_selection_badge(judge_config)" in selector_source


def test_batch_judge_selection_summary_shows_selected_provider_and_model(monkeypatch):
    monkeypatch.setattr(
        voc_quality_view,
        "judge_provider_options",
        lambda: [
            {
                "provider": "anthropic",
                "label": "Anthropic",
                "default_model": "claude-opus-4-6",
            },
            {
                "provider": "openai",
                "label": "OpenAI",
                "default_model": "gpt-5.2",
            },
        ],
    )

    enabled_summary = voc_quality_view._judge_config_summary(
        {"enabled": True, "provider": "openai", "model": "gpt-5.2"}
    )
    disabled_summary = voc_quality_view._judge_config_summary(
        {"enabled": False, "provider": "anthropic", "model": "claude-opus-4-6"}
    )

    assert enabled_summary["label"] == "OpenAI · gpt-5.2"
    assert disabled_summary["label"] == "독립 LLM 평가 미실행"


def test_batch_execution_explains_close_and_server_shutdown_behavior():
    import inspect

    source = inspect.getsource(voc_quality_view._render_batch_execution_safety_notice)

    assert "일괄 수행 중 화면을 닫으면?" in source
    assert "st.expander" in source
    assert "expanded=False" in source
    assert "Streamlit 서버가 살아 있으면" in source
    assert "서버 프로세스를 끄면" in source
    assert "완료된 Case 결과는 즉시 저장" in source
    assert "중지 요청" in source


def test_batch_preflight_readiness_replaces_count_metrics_with_actionable_state():
    good_state = voc_quality_view._batch_preflight_display_state(
        {
            "ok": True,
            "selected_count": 3,
            "implemented_count": 3,
            "pending_count": 0,
            "warnings": [],
            "blockers": [],
        }
    )
    pending_state = voc_quality_view._batch_preflight_display_state(
        {
            "ok": True,
            "selected_count": 4,
            "implemented_count": 3,
            "pending_count": 1,
            "warnings": [],
            "blockers": [],
        }
    )
    blocked_state = voc_quality_view._batch_preflight_display_state(
        {
            "ok": False,
            "selected_count": 4,
            "implemented_count": 4,
            "pending_count": 0,
            "warnings": [],
            "blockers": ["6개 Agent가 모두 RUNNING 상태가 아닙니다."],
        }
    )
    render_source = inspect.getsource(voc_quality_view.render_batch_execution)

    assert good_state["title"] == "실행 준비 완료"
    assert pending_state["title"] == "실행 가능 · 후속 구현 포함"
    assert blocked_state["title"] == "실행 차단"
    assert "_render_batch_preflight_readiness(preflight)" in render_source
    assert 'st.metric("선택"' not in render_source
    assert 'st.metric("실행 가능"' not in render_source
    assert 'st.metric("후속 구현"' not in render_source
    assert 'st.metric("에이전트"' not in render_source


def test_batch_active_run_restores_from_running_history(monkeypatch):
    monkeypatch.setattr(voc_quality_view.st, "session_state", {})
    monkeypatch.setattr(
        voc_quality_view,
        "list_voc_run_history",
        lambda: [
            {
                "run_id": "RUN-MANUAL",
                "run_type": "MANUAL",
                "status": "RUNNING",
                "started_at": "2026-07-26T09:00:00+09:00",
                "selected_case_ids": ["TC-99"],
            },
            {
                "run_id": "RUN-BATCH-ACTIVE",
                "run_type": "BATCH",
                "status": "RUNNING",
                "started_at": "2026-07-26T10:00:00+09:00",
                "selected_case_ids": ["TC-01", "TC-02"],
            },
        ],
    )
    monkeypatch.setattr(
        voc_quality_view,
        "get_batch_run_progress",
        lambda run_id: {
            "run_id": run_id,
            "status": "RUNNING",
            "total": 2,
            "completed": 1,
            "estimated_total_seconds": 90,
            "verification_scope": {"selected_case_ids": ["TC-01", "TC-02"]},
        },
    )

    state = voc_quality_view._active_batch_run_state()

    assert state["active"] is True
    assert state["run_id"] == "RUN-BATCH-ACTIVE"
    assert state["restored"] is True
    assert voc_quality_view.st.session_state[voc_quality_view.BATCH_RUN_ID_KEY] == "RUN-BATCH-ACTIVE"
    assert voc_quality_view.st.session_state[voc_quality_view.BATCH_CASE_IDS_KEY] == ["TC-01", "TC-02"]


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


def test_improvement_validity_rubric_requires_complete_decision_and_hold_rules():
    rubric = deepcopy(load_improvement_validity_rubric())
    assert rubric["version"] == "개선안RB1.6"
    assert validate_quality_rubric("improvement_validity", rubric) == []

    invalid = deepcopy(rubric)
    invalid["automatic_decisions"][0]["requires_all_pass_floors"] = False
    invalid["automatic_decisions"][1]["decision"] = "AI_PASS"
    invalid["immediate_hold_rules"].remove("judge_error_or_not_run")

    errors = validate_quality_rubric("improvement_validity", invalid)

    assert any("중복" in error for error in errors)
    assert any("AI 통과 판정" in error for error in errors)
    assert any("즉시 보류 규칙" in error for error in errors)


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


def test_no_data_case_safe_hold_is_not_pipeline_error(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)

    def fake_run_voc(_question, save_report=False, timeout_seconds=180, task_override=None):
        return {
            "ok": True,
            "result": {
                "ok": False,
                "summary": "현재 VOC 데이터에서 직접적으로 일치하는 사례를 찾지 못했습니다. 추가 로그 또는 주문번호 기반 확인이 필요합니다.",
                "policy": "",
                "trace": "audit_trace_id=t-no-data; retrieved=0; no_related_data",
                "message": "현재 VOC 데이터에서 직접적으로 일치하는 사례를 찾지 못했습니다. 추가 로그 또는 주문번호 기반 확인이 필요합니다.",
            },
        }

    monkeypatch.setattr(voc_quality_service, "run_voc_analysis", fake_run_voc)
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {"trace_id": "trace-no-data", "events": [{"status": "success"}]},
    )
    monkeypatch.setattr(
        voc_quality_service.voc_judge_service,
        "evaluate_independent_judge",
        lambda **_kwargs: {
            "status": "PASS",
            "decision": "PASS",
            "total_score": 91,
            "dimension_scores": {},
            "provider": "gemini",
            "model": "judge-model",
            "independence_grade": "A",
            "attempts": [{"attempt": 1, "status": "SUCCESS"}],
        },
    )

    result = voc_quality_service.run_test_case(
        "TC-16",
        judge_config={"enabled": True, "provider": "gemini", "model": "judge-model"},
    )
    stored = store.load_voc_run(result["run_id"])
    artifacts = store.load_case_artifacts(result["run_id"], "TC-16")
    execution_result = artifacts["pipeline_result"]["execution"]["result"]

    assert result["evidence_status"] == "PASS"
    assert stored["summary"]["counts"]["PASS"] == 1
    assert execution_result["ok"] is True
    assert execution_result["safe_no_data_hold"] is True
    assert "단정하지 않고 답변을 보류" in execution_result["policy"]


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


def test_batch_state_model_defines_35_case_verification_cycle():
    model = describe_batch_state_model()
    scope = model["verification_scope"]

    assert model["model_version"] == "2026-07-31.step3"
    assert model["suite_id"] == "VOC-QA-35"
    assert scope["catalog_total_cases"] == 35
    assert scope["selected_count"] == 35
    assert scope["executable_count"] == 26
    assert scope["pending_count"] == 9
    assert set(model["case_execution_statuses"]) == {
        "PASS", "FAIL", "ERROR", "NOT_RUN", "REVIEW_REQUIRED"
    }
    assert set(model["validity_review_actions"]) == {
        "VALIDITY_EVALUATION_REQUIRED",
        "REWORK_REQUIRED",
        "QA_REVIEW",
        "BUSINESS_APPROVAL",
        "FORMAL_APPROVED",
        "NO_ACTION",
    }
    assert set(model["menu_io"]) == {
        "batch_execution", "execution_history", "improvement_validity"
    }
    assert "validity_result.json" in " ".join(model["menu_io"]["improvement_validity"]["outputs"])


def test_batch_run_persists_verification_scope_metadata(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    catalog = load_quality_test_catalog()
    case_ids = [item["case_id"] for item in catalog["cases"]]

    run = voc_quality_service.start_batch_run(case_ids, max_retries=0)
    manifest = store.load_voc_run(run["run_id"])["manifest"]
    scope = manifest["run_metadata"]["verification_scope"]

    assert manifest["state_model_version"] == "2026-07-31.step3"
    assert manifest["run_metadata"]["state_model"]["menu_io"]["batch_execution"]["state_owner"] == "run_id"
    assert scope["catalog_total_cases"] == 35
    assert scope["selected_count"] == 35
    assert scope["executable_count"] == 26
    assert scope["pending_count"] == 9

    progress = voc_quality_service.get_batch_run_progress(run["run_id"])
    assert progress["verification_scope"]["pending_count"] == 9
    assert progress["state_model_version"] == "2026-07-31.step3"

    voc_quality_service.request_batch_stop(run["run_id"])
    voc_quality_service.execute_batch_run(run["run_id"], case_ids, max_retries=0)


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


def test_batch_retest_applies_rework_instruction_to_execution_question(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    captured = {}

    def fake_run_voc(question, save_report=False, timeout_seconds=180, task_override=None):
        captured.update(
            question=question,
            save_report=save_report,
            timeout_seconds=timeout_seconds,
            task_override=task_override,
        )
        return {"ok": True, "result": {"ok": True, "summary": "ok", "policy": "improved"}}

    monkeypatch.setattr(voc_quality_service, "run_voc_analysis", fake_run_voc)
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {"trace_id": "trace-rework", "events": []},
    )
    instruction = "VOC ID와 정량 KPI를 보완하고 실행계획을 다시 작성하세요."

    run = voc_quality_service.start_batch_run(
        ["TC-01"],
        parent_run_id="RUN-PARENT",
        max_retries=0,
        rework_instruction=instruction,
    )
    result = voc_quality_service.execute_batch_run(
        run["run_id"], ["TC-01"], max_retries=0, backoff_base_seconds=0
    )

    manifest = store.load_voc_run(run["run_id"])["manifest"]
    assert manifest["run_type"] == "RETEST"
    assert manifest["run_metadata"]["parent_run_id"] == "RUN-PARENT"
    assert manifest["run_metadata"]["rework_instruction"] == instruction
    assert "[RETEST 보완 지시]" in captured["question"]
    assert instruction in captured["question"]

    run_dir = Path(result["run_dir"])
    snapshot = json.loads(
        (run_dir / "snapshots" / "selected_test_cases.json").read_text(encoding="utf-8")
    )
    assert "[RETEST 보완 지시]" not in json.dumps(snapshot, ensure_ascii=False)
    artifact = json.loads(
        (run_dir / "cases" / "TC-01" / "pipeline_result.json").read_text(encoding="utf-8")
    )
    assert artifact["rework_instruction_applied"] is True
    assert artifact["rework_instruction"] == instruction


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


def test_history_verification_scope_model_marks_full_suite_and_retest_parent():
    parent_run_id = "RUN-20260726-000000-000000-abcd"
    model = voc_quality_view._history_verification_scope_model(
        {
            "state_model_version": "2026-07-26.step3",
            "run_type": "RETEST",
            "selected_case_ids": ["TC-01"],
            "run_metadata": {
                "parent_run_id": parent_run_id,
                "verification_scope": {
                    "catalog_total_cases": 35,
                    "selected_count": 35,
                    "executable_count": 26,
                    "pending_count": 9,
                    "execution_type_counts": {
                        "voc_pipeline": 18,
                        "fault_proxy": 2,
                        "isolated_fault": 6,
                        "agent_role_quality": 6,
                        "quality_gate": 3,
                    },
                },
            },
        },
        {"total": 35},
    )

    assert model["state_model_version"] == "2026-07-26.step3"
    assert model["is_full_suite"] is True
    assert model["is_retest"] is True
    assert model["parent_run_id"] == parent_run_id
    assert model["executable_count"] == 26
    assert model["pending_count"] == 9


def test_history_rows_surface_scope_counts_and_retest_parent(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    parent_run_id = "RUN-20260726-000000-000000-abcd"
    run = store.start_voc_run(
        run_type="RETEST",
        selected_case_ids=["TC-01"],
        suite_id="VOC-QA-35",
        catalog_version="2.0",
        test_case_hash="abc123",
        rubric_versions={"internal_pipeline": {"version": "1.0", "sha256": "hash"}},
        model_snapshot={"summary": {"provider": "openai", "model": "test"}},
        judge_enabled=False,
        environment_fingerprint={"fingerprint_sha256": "env"},
        run_metadata={
            "parent_run_id": parent_run_id,
            "verification_scope": {
                "catalog_total_cases": 35,
                "selected_count": 1,
                "executable_count": 1,
                "pending_count": 0,
                "execution_type_counts": {"voc_pipeline": 1},
            },
        },
        snapshots={"selected_test_cases.json": {"cases": [{"case_id": "TC-01"}]}},
    )
    _complete_minimal_run(store, run)

    row = voc_quality_service.list_voc_run_history()[0]

    assert row["run_type"] == "RETEST"
    assert row["parent_run_id"] == parent_run_id
    assert row["verification_scope"]["catalog_total_cases"] == 35
    assert row["executable_count"] == 1
    assert row["pending_count"] == 0


def test_rubric_reevaluation_plan_is_saved_without_mutating_run_results(monkeypatch, tmp_path):
    store = _configure_temp_voc_run_store(monkeypatch, tmp_path)
    old_versions = {
        "internal_pipeline": {"version": "A2A1.5", "sha256": "same-internal"},
        "independent_judge": {"version": "J1.0", "sha256": "same-judge"},
        "improvement_validity": {"version": "V1.0", "sha256": "old-validity"},
    }
    current_versions = {
        "internal_pipeline": {"version": "A2A1.5", "sha256": "same-internal"},
        "independent_judge": {"version": "J1.0", "sha256": "same-judge"},
        "improvement_validity": {"version": "V1.0", "sha256": "new-validity"},
    }
    monkeypatch.setattr(
        voc_quality_service,
        "_current_voc_rubric_versions",
        lambda: deepcopy(current_versions),
    )
    run = store.start_voc_run(
        run_type="MANUAL",
        selected_case_ids=["TC-01"],
        suite_id="VOC-QA-35",
        catalog_version="2.0",
        test_case_hash="abc123",
        rubric_versions=deepcopy(old_versions),
        model_snapshot={"summary": {"provider": "openai", "model": "test"}},
        judge_enabled=True,
        environment_fingerprint={"fingerprint_sha256": "env"},
        snapshots={"selected_test_cases.json": {"cases": [{"case_id": "TC-01"}]}},
    )
    store.save_case_artifacts(
        run["run_id"],
        "TC-01",
        pipeline_result={
            "mode": "voc",
            "execution": {
                "ok": True,
                "question": "VOC 질문",
                "result": {"ok": True, "summary": "요약", "policy": "개선안"},
            },
        },
        trace={"trace_id": "trace-1", "events": []},
        rule_result={"status": "PASS"},
        judge_result={"decision": "PASS", "total_score": 88},
    )
    store.complete_voc_run(
        run["run_id"],
        [{"case_id": "TC-01", "status": "PASS", "judge_status": "PASS", "attempt_count": 1}],
        lifecycle_status="COMPLETED",
    )

    saved = voc_quality_service.save_voc_rubric_reevaluation_plan(run["run_id"])
    plan = saved["plan"]
    loaded = store.load_voc_run(run["run_id"])
    row = voc_quality_service.list_voc_run_history()[0]

    assert plan["status"] == "REEVALUATION_READY"
    assert plan["changed_scopes"] == ["improvement_validity"]
    assert plan["eligible_case_ids"] == ["TC-01"]
    assert plan["actions"][0]["method"] == "VALIDITY_REEVALUATION"
    assert loaded["rubric_reevaluation_plan"]["status"] == "REEVALUATION_READY"
    assert loaded["summary"]["case_results"][0]["status"] == "PASS"
    assert row["rubric_reevaluation_plan_status"] == "REEVALUATION_READY"


def test_history_rubric_plan_targets_follow_up_execution_buttons():
    plan = {
        "actions": [
            {
                "label": "독립 LLM 평가",
                "method": "JUDGE_REEVALUATION",
                "target_count": 2,
                "target_case_ids": ["TC-01", "TC-02"],
            },
            {
                "label": "개선안 타당성 평가",
                "method": "VALIDITY_REEVALUATION",
                "target_count": 1,
                "target_case_ids": ["TC-03"],
            },
            {
                "label": "내부 파이프라인",
                "method": "RETEST_REQUIRED",
                "target_count": 35,
                "target_case_ids": ["TC-01"],
            },
        ]
    }

    targets = voc_quality_view._history_rubric_plan_next_targets("RUN-1", plan)

    assert [target["button_label"] for target in targets] == [
        "독립 LLM 재평가 열기",
        "타당성 재평가로 이동",
        "RETEST 준비로 이동",
    ]
    assert targets[0]["page"] == "history_detail"
    assert targets[0]["case_id"] == "TC-01"
    assert targets[1]["page"] == voc_quality_view.VOC_VALIDITY_PAGE_NAME
    assert targets[1]["case_id"] == "TC-03"
    assert targets[2]["page"] == voc_quality_view.VOC_BATCH_PAGE_NAME


def test_history_judge_reevaluation_context_explains_no_auto_supplement():
    detail = {
        "manifest": {
            "rubric_versions": {
                "independent_judge": {"version": "J1.0", "sha256": "old"}
            }
        },
        "rubric_reevaluation_plan": {
            "actions": [
                {
                    "method": "JUDGE_REEVALUATION",
                    "target_case_ids": ["TC-01"],
                }
            ]
        },
    }
    artifacts = {
        "judge_result": {
            "decision": "REVIEW_REQUIRED",
            "total_score": 76,
            "provider": "anthropic",
            "model": "claude-haiku-4-5",
            "independence_hold": True,
            "independence_hold_reason": "동일 Provider 계열 응답 영향 가능성",
            "dimension_scores": {
                "accuracy": {"score": 17, "max_points": 25, "reason": "원인 연결 일부 부족"},
                "groundedness": {"score": 18, "max_points": 23, "reason": "근거 충족"},
            },
            "risks": ["VOC 근거 연결이 약합니다."],
            "recommendations": ["담당자와 KPI를 더 구체화하세요."],
        }
    }

    context = voc_quality_view._history_judge_reevaluation_context_model(
        "TC-01",
        artifacts,
        detail,
        current_judge_rubric={
            "version": "J1.1",
            "sha256": "new",
            "dimensions": {
                "accuracy": {"label": "정확성", "max_points": 25, "pass_floor": 18},
                "groundedness": {"label": "근거성", "max_points": 23, "pass_floor": 18},
            },
        },
    )

    assert context["rubric_changed"] is True
    assert "독립 LLM 평가 Rubric 기준 변경 대상입니다." in context["reasons"]
    assert "기존 독립 LLM 판정이 검토 필요 상태입니다." in context["reasons"]
    assert any("독립성 보류" in item for item in context["blockers"])
    assert any("총점 기준 미달: 76 / 80점" in item for item in context["blockers"])
    assert any("세부 항목 하한 미달: 정확성 17 / 18점" in item for item in context["blockers"])
    assert any("위험 지적" in item for item in context["blockers"])
    assert any("보완 권고" in item for item in context["blockers"])
    assert any("같은 원인이 남으면" in item for item in context["review_focus"])
    assert "저장된 Agent 파이프라인 결과" in context["reuses"]
    assert "Agent 개선안 내용" in context["not_changed"]
    assert context["stored_rubric_version"] == "J1.0"
    assert context["current_rubric_version"] == "J1.1"


def test_history_judge_reevaluation_result_model_links_pass_to_validity():
    result = {
        "run_id": "RUN-1",
        "case_id": "TC-01",
        "judge_result": {
            "decision": "PASS",
            "total_score": 86,
            "provider": "gemini",
            "model": "gemini-3.5-flash-lite",
            "evaluated_at": "2026-07-31T10:10:11+09:00",
            "evaluation_history": [
                {"decision": "REVIEW_REQUIRED", "total_score": 76}
            ],
        },
    }

    model = voc_quality_view._history_judge_reevaluation_result_model(
        result,
        current_judge_rubric={"version": "J1.1", "dimensions": {}},
    )

    assert model["before_decision"] == "REVIEW_REQUIRED"
    assert model["after_decision"] == "PASS"
    assert model["decision_changed"] is True
    assert model["score_delta"] == "+10점 상승"
    assert model["next_action"]["target"]["enabled"] is True
    assert model["next_action"]["target"]["page"] == voc_quality_view.VOC_VALIDITY_PAGE_NAME
    assert model["next_action"]["target"]["action_code"] == "RUN_VALIDITY"
    assert model["next_action"]["target"]["button_label"] == "타당성 평가로 이동"
    assert model["next_action"]["target"]["case_id"] == "TC-01"


def test_history_judge_reevaluation_progress_model_shows_running_state():
    model = voc_quality_view._history_judge_reevaluation_progress_model(
        {
            "status": "RUNNING",
            "started_at": "2026-07-31T10:00:00+09:00",
            "updated_at": "2026-07-31T10:00:02+09:00",
            "progress": {
                "percent": 52,
                "stage": "독립 LLM 요청",
                "detail": "선택한 Provider와 모델로 동일 결과를 재평가하고 있습니다.",
            },
        }
    )

    assert model["status"] == "RUNNING"
    assert model["percent"] == 52
    assert model["fraction"] == 0.52
    assert model["stage"] == "독립 LLM 요청"
    assert "재평가" in model["detail"]


def test_history_judge_reevaluation_progress_model_completes_to_result_focus():
    model = voc_quality_view._history_judge_reevaluation_progress_model(
        {
            "status": "COMPLETED",
            "done": True,
            "progress": {"percent": 92, "stage": "결과 저장"},
        }
    )

    assert model["percent"] == 100
    assert model["fraction"] == 1.0
    assert model["stage"] == "독립 LLM 재평가 완료"
    assert "결과 영역으로 이동" in model["detail"]
    assert (
        voc_quality_view._history_judge_reevaluation_focus_key("RUN-1", "TC-01")
        == "voc_history_judge_reevaluation_focus::RUN-1::TC-01"
    )


def test_history_judge_reevaluation_result_model_keeps_review_on_blockers():
    result = {
        "run_id": "RUN-1",
        "case_id": "TC-01",
        "judge_result": {
            "decision": "REVIEW_REQUIRED",
            "total_score": 76,
            "provider": "anthropic",
            "model": "claude-haiku-4-5",
            "dimension_scores": {
                "accuracy": {"score": 17, "max_points": 25, "reason": "원인 일부 부족"},
            },
            "evaluation_history": [
                {"decision": "REVIEW_REQUIRED", "total_score": 75}
            ],
        },
    }

    model = voc_quality_view._history_judge_reevaluation_result_model(
        result,
        current_judge_rubric={
            "version": "J1.1",
            "dimensions": {
                "accuracy": {"label": "정확성", "max_points": 25, "pass_floor": 18},
            },
        },
    )

    assert model["after_decision"] == "REVIEW_REQUIRED"
    assert model["next_action"]["target"]["enabled"] is False
    assert model["next_action"]["label"] == "검토 필요 원인 확인"
    assert any("총점 기준 미달" in item for item in model["blockers"])
    assert any("세부 항목 하한 미달: 정확성 17 / 18점" in item for item in model["blockers"])


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


def test_history_retest_pair_auto_selects_latest_linked_retest():
    history = [
        {
            "run_id": "RUN-BASE",
            "run_type": "MANUAL",
            "status": "COMPLETED",
            "started_at": "2026-07-31T09:00:00+09:00",
        },
        {
            "run_id": "RUN-RETEST-OLD",
            "run_type": "RETEST",
            "status": "COMPLETED",
            "parent_run_id": "RUN-BASE",
            "started_at": "2026-07-31T10:00:00+09:00",
        },
        {
            "run_id": "RUN-RETEST-NEW",
            "run_type": "RETEST",
            "status": "COMPLETED",
            "parent_run_id": "RUN-BASE",
            "started_at": "2026-07-31T11:00:00+09:00",
        },
    ]

    basis = voc_quality_view._history_retest_pair_basis(history, history[0])

    assert basis["enabled"] is True
    assert basis["baseline_run_id"] == "RUN-BASE"
    assert basis["candidate_run_id"] == "RUN-RETEST-NEW"
    assert basis["candidate_count"] == 2


def test_history_retest_pair_uses_parent_when_retest_is_selected():
    history = [
        {
            "run_id": "RUN-BASE",
            "run_type": "BATCH",
            "status": "COMPLETED",
            "started_at": "2026-07-31T09:00:00+09:00",
        },
        {
            "run_id": "RUN-RETEST",
            "run_type": "RETEST",
            "status": "COMPLETED",
            "parent_run_id": "RUN-BASE",
            "started_at": "2026-07-31T10:00:00+09:00",
        },
    ]

    basis = voc_quality_view._history_retest_pair_basis(history, history[1])

    assert basis["enabled"] is True
    assert basis["mode"] == "selected_retest"
    assert basis["baseline_run_id"] == "RUN-BASE"
    assert basis["candidate_run_id"] == "RUN-RETEST"


def test_history_retest_comparison_plan_disables_button_when_versions_differ(monkeypatch):
    history = [
        {
            "run_id": "RUN-BASE",
            "run_type": "MANUAL",
            "status": "COMPLETED",
            "started_at": "2026-07-31T09:00:00+09:00",
        },
        {
            "run_id": "RUN-RETEST",
            "run_type": "RETEST",
            "status": "COMPLETED",
            "parent_run_id": "RUN-BASE",
            "started_at": "2026-07-31T10:00:00+09:00",
        },
    ]
    monkeypatch.setattr(
        voc_quality_view,
        "compare_voc_runs",
        lambda *_args: {
            "compatible": False,
            "compatibility_differences": ["rubric_versions"],
        },
    )

    plan = voc_quality_view._history_retest_comparison_plan(history, history[0])

    assert plan["enabled"] is False
    assert plan["pair_key"] == "RUN-BASE::RUN-RETEST"
    assert plan["state_label"] == "기준 불일치"
    assert "rubric_versions" in plan["detail"]


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
