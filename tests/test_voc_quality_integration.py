import asyncio
import json
from copy import deepcopy
from pathlib import Path
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.navigation import MENU_OPTIONS, SIDEBAR_MENU_OPTIONS
from dashboard.pages_top import voc_quality_view
from dashboard.services import voc_quality_service
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
    assert "품질 평가 기준" in markdown
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
    assert "실행 환경 연결됨" not in rendered_text
    assert rendered_text.count("기동 시간 ·") == 6
    assert rendered_text.count(":red-badge[중지 영향]") == 1
    assert "정책 개선안을 생성·보완할 수 없어" in rendered_text
    assert "기동 시간 · -" in rendered_text


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
    assert 'st.markdown("### test_cases.json 선택 실행")' not in source


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
    assert html.index("테스트 수행 준비") < html.index("수행 준비 중")
    assert "flow2-preparation active" in html
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
    assert state[table_key] == {
        "selection": {"rows": [2], "columns": [], "cells": []}
    }


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
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["전체 실행 대상"] == "35건"
    assert metrics["VOC 질문형"] == "20건"
    assert metrics["추가 검증 Case"] == "15건"
    assert metrics["구현 상태"] == "26건 완료"
    assert any(item.value == "현재 조건에 맞는 Case 35건" for item in app.caption)

    catalog_table = app.dataframe[0].value
    assert len(catalog_table) == 35
    assert set(catalog_table["Case ID"]) >= {"TC-01", "FT-01", "AG-01", "QG-01"}


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

    assert segmented_labels == ["평가 기준 구분"]
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
    assert [control.label for control in app.segmented_control] == ["평가 기준 구분"]
    assert any(slider.label == "intent" for slider in app.slider)
    assert any(slider.label == "배포 가능 시작 점수" for slider in app.slider)
    assert any(button.label == "평가 기준 저장" for button in app.button)
    intent = next(slider for slider in app.slider if slider.label == "intent")
    assert intent.min == 0
    assert intent.max == 5
    assert any(":primary[100 / 100점]" in item.value for item in app.markdown)

    intent.set_value(4).run()

    assert not app.exception
    assert next(button for button in app.button if button.label == "평가 기준 저장").disabled
    assert any(":red[99 / 100점]" in item.value for item in app.markdown)
    assert any("100점까지 +1점 조정" in item.value for item in app.caption)


def test_rubric_criterion_range_uses_remaining_total_budget():
    rubric = deepcopy(load_system_rubric())
    items = rubric["categories"]

    assert voc_quality_view._rubric_total(items) == 100
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (0, 5)

    items["interpreter"]["criteria"]["intent"] = 3

    assert voc_quality_view._rubric_total(items) == 98
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "intent") == (0, 5)
    assert voc_quality_view._rubric_criterion_range(items, "interpreter", "keywords") == (0, 6)


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
