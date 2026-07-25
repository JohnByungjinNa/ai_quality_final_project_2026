from __future__ import annotations

import base64
import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from functools import partial
from html import escape
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from services.voc_background_job_service import (
    background_job_snapshot,
    discard_background_job,
    start_background_job,
    update_background_job,
)
from services.voc_quality_service import (
    REPORT_CATEGORIES,
    QUALITY_RUBRIC_SPECS,
    a2a_trace_snapshot,
    agent_status_snapshot,
    audit_summary,
    batch_preflight,
    build_voc_acceptance_snapshot,
    build_voc_quality_report,
    compare_voc_runs,
    compare_voc_improvement_answers,
    create_voc_defect,
    delete_voc_run_history,
    download_voc_run_evidence,
    execute_batch_run,
    get_batch_run_progress,
    judge_independence_preview,
    judge_provider_options,
    list_reports,
    list_voc_defects,
    list_voc_run_history,
    latest_voc_full_run_id,
    load_guide,
    load_improvement_validity_rubric,
    list_improvement_validity_candidates,
    load_independent_judge_rubric,
    load_quality_test_catalog,
    load_quality_rubric,
    load_voc_case_history_detail,
    load_voc_defect,
    load_voc_run_history_detail,
    load_system_rubric,
    load_test_cases,
    pipeline_trace_events,
    read_report,
    reevaluate_voc_run_case,
    evaluate_voc_improvement_validity,
    generate_voc_acceptance_evidence,
    generate_voc_quality_report,
    review_voc_improvement_validity,
    run_agent_action,
    run_diagnostics,
    run_test_case,
    run_voc_analysis,
    runtime_health,
    save_quality_rubric,
    save_quality_test_catalog,
    test_case_summary,
    test_agent_rpc,
    transition_voc_defect,
    request_batch_stop,
    start_batch_run,
    validate_quality_rubric,
    validate_quality_test_catalog,
    validity_provider_options,
)


RUBRIC_STAGE_OPTIONS = (
    "내부 Pipeline 품질",
    "독립 LLM Judge",
    "개선안 타당성",
)
RUBRIC_STAGE_TYPES = {
    RUBRIC_STAGE_OPTIONS[0]: "internal_pipeline",
    RUBRIC_STAGE_OPTIONS[1]: "independent_judge",
    RUBRIC_STAGE_OPTIONS[2]: "improvement_validity",
}

MANUAL_JUDGE_PROVIDERS = (
    {
        "provider": "openai",
        "label": "OpenAI",
        "model": "gpt-5.2",
        "number": 1,
    },
    {
        "provider": "anthropic",
        "label": "Anthropic",
        "model": "claude-opus-4-6",
        "number": 2,
    },
)

MANUAL_PREPARATION_STEPS = (
    "Agent 실행 상태 점검",
    "Run 폴더 생성",
    "Rubric과 Test Case 스냅샷 저장",
    "증적 파일 준비",
    "별도 Python 프로세스 시작",
)
MANUAL_EVENT_CARD_HEIGHT = 154


AGENT_PIPELINE = (
    ("Interpreter", "질문 의도 해석", "6101"),
    ("Retriever", "관련 VOC 검색", "6102"),
    ("Summarizer", "요약 후보 생성", "6103"),
    ("Evaluator", "최적 후보 평가", "6104"),
    ("Critic", "요약·정책 검토", "6105"),
    ("Improver", "개선안 생성", "6106"),
)

VOC_RUN_STATUS_COLORS = {
    "PASS": "#155A96",
    "REVIEW_REQUIRED": "#2F75B5",
    "FAIL": "#5599D2",
    "ERROR": "#7EAED4",
    "NOT_RUN": "#A9CAE7",
}
VOC_HISTORY_COLORS = {
    "PASS율": "#155A96",
    "검토율": "#5599D2",
    "실패·오류율": "#A9CAE7",
}
VOC_OVERVIEW_PANEL_HEIGHT = 390

VOC_STATUS_LABELS = {
    "PASS": "통과",
    "FAIL": "실패",
    "ERROR": "오류",
    "REVIEW_REQUIRED": "검토 필요",
    "NOT_RUN": "미실행",
    "RUNNING": "진행 중",
    "COMPLETED": "완료",
    "INTERRUPTED": "중단됨",
    "SUCCESS": "성공",
    "DRAFT": "초안",
    "PENDING": "대기",
    "CONFIRMED": "확인됨",
    "OPEN": "접수",
    "ANALYZED": "분석 완료",
    "FIXED": "조치 완료",
    "RETESTED": "재시험 완료",
    "CLOSED": "종결",
    "RESOLVED": "해결",
    "IMPLEMENTED": "실행 구현 완료",
    "DEFINED": "정의됨 · 후속 구현",
    "MANUAL": "수동 수행",
    "BATCH": "일괄 수행",
    "RETEST": "재시험",
    "VOC": "VOC",
    "FAULT": "장애 시험",
    "AI_PASS": "AI 통과",
    "AI_REVIEWED": "AI 검토 완료",
    "REVISION_REQUIRED": "수정 필요",
    "REJECTED": "반려",
    "APPROVE": "승인",
    "APPROVED": "승인 완료",
    "FORMAL_APPROVED": "정식 승인",
    "NOT_APPROVED": "미승인",
    "BUSINESS_APPROVED": "업무 승인",
    "BUSINESS_REVIEW_REQUIRED": "업무 검토 필요",
    "HUMAN_REVIEW_REQUIRED": "사람 검토 필요",
    "REMAINING_CASE_REVIEW_REQUIRED": "잔여 Case 검토 필요",
    "READY_FOR_UAT": "UAT 준비 완료",
    "HOLD": "보류",
    "EVIDENCE_DRAFT": "증적 초안",
    "NOT_CONFIGURED": "미설정",
    "CONFIGURED": "설정됨",
    "NOT_AVAILABLE": "확인 불가",
    "UNKNOWN": "미확인",
    "STOPPED": "중지",
    "STARTING/FAILED": "시작 실패",
    "CRITICAL": "치명",
    "HIGH": "높음",
    "MEDIUM": "중간",
    "LOW": "낮음",
    "INTERFACE_BRANCH": "연계·분기",
    "API_RATE_LIMIT": "API 제한",
    "AGENT_FAILURE": "Agent 장애",
    "DATA": "데이터",
    "PERFORMANCE": "성능",
    "OTHER": "기타",
}


def _voc_status_label(value, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value)
    return VOC_STATUS_LABELS.get(text, text)


def _voc_status_counts_for_display(counts: dict | None) -> dict:
    return {_voc_status_label(key): value for key, value in (counts or {}).items()}

VOC_PAGE_META = {
    "Dashboard": {
        "icon": "dashboard",
        "title": "VOC 품질 Dashboard",
        "description": "실행 환경부터 품질 판정, 독립 Judge, 결함과 A2A 연결 상태를 한눈에 확인합니다.",
        "group": "현황",
        "flow": ("기간 설정", "품질 비교", "이슈 확인"),
    },
    "수동 TC 수행": {
        "icon": "fact_check",
        "title": "수동 TC 수행",
        "description": "Test Case를 선택해 Agent Pipeline과 독립 LLM 평가 근거를 단계별로 확인합니다.",
        "group": "실행",
        "flow": ("Case 선택", "Pipeline 실행", "판정 확인"),
    },
    "일괄 TC 수행": {
        "icon": "playlist_play",
        "title": "일괄 TC 수행",
        "description": "다수 Test Case를 백그라운드로 실행하고 단계·예상시간·결과를 추적합니다.",
        "group": "실행",
        "flow": ("대상 구성", "백그라운드 실행", "결과 집계"),
    },
    "수행 이력": {
        "icon": "history",
        "title": "수행 이력",
        "description": "Run별 품질 판정과 Case 증적을 비교하고 재평가·다운로드까지 연결합니다.",
        "group": "추적",
        "flow": ("Run 조회", "결과 비교", "증적 확인"),
    },
    "개선안 타당성 검증": {
        "icon": "verified",
        "title": "개선안 타당성 검증",
        "description": "VOC 개선안의 원인 연결성, 실행 가능성, 책임·일정·위험을 독립적으로 검증합니다.",
        "group": "평가",
        "flow": ("후보 선택", "자동 평가", "승인 검토"),
    },
    "Agent 관리": {
        "icon": "smart_toy",
        "title": "Agent 관리",
        "description": "6개 Agent의 실행 상태와 포트·PID를 확인하고 안전하게 제어합니다.",
        "group": "운영",
        "flow": ("상태 확인", "제어 승인", "실행 결과"),
    },
    "VOC 분석": {
        "icon": "query_stats",
        "title": "VOC 분석",
        "description": "자연어 VOC를 Agent에 전달해 요약, 정책 개선안과 Trace를 생성합니다.",
        "group": "분석",
        "flow": ("질문 입력", "Agent 분석", "개선안 확인"),
    },
    "테스트케이스": {
        "icon": "checklist",
        "title": "VOC 테스트케이스",
        "description": "의도·키워드·필수 요소·금지 요소 기반의 품질 Test Case를 조회합니다.",
        "group": "기준",
        "flow": ("Case 탐색", "조건 확인", "대상 활용"),
    },
    "품질 평가 기준": {
        "icon": "tune",
        "title": "품질 평가 기준 수립",
        "description": "Pipeline·독립 Judge·개선안 타당성의 배점과 판정 구간을 시각적으로 관리합니다.",
        "group": "기준",
        "flow": ("단계 선택", "배점 조정", "검증·저장"),
    },
    "장애·결함 관리": {
        "icon": "bug_report",
        "title": "장애·결함 관리",
        "description": "품질 결함과 격리 장애시험을 등록하고 상태·심각도·증적을 추적합니다.",
        "group": "결함",
        "flow": ("유형 선택", "결함 처리", "상태 추적"),
    },
    "A2A Trace": {
        "icon": "hub",
        "title": "gRPC 연결·A2A Trace",
        "description": "Agent 간 실제 호출 경로와 성공·실패, 처리시간 및 전달 정보를 확인합니다.",
        "group": "추적",
        "flow": ("Trace 집계", "연결 진단", "Report 확인"),
    },
    "품질 보고서": {
        "icon": "article",
        "title": "품질 보고서",
        "description": "Run 증적을 정량 분석하고 승인 판단에 필요한 보고서를 생성합니다.",
        "group": "보고",
        "flow": ("Run 선택", "수치 대조", "증적 생성"),
    },
    "사용자 가이드": {
        "icon": "menu_book",
        "title": "사용자 가이드",
        "description": "VOC 품질진단의 실행·이식·운영 절차를 목적별로 확인합니다.",
        "group": "안내",
        "flow": ("가이드 선택", "절차 확인", "실행 적용"),
    },
    "최종 인수·시연": {
        "icon": "approval",
        "title": "최종 인수·시연",
        "description": "전체 Run의 품질 게이트와 잔여 위험을 대조해 최종 UAT 준비 상태를 판단합니다.",
        "group": "승인",
        "flow": ("Run 연결", "Gate 검증", "인수 증적"),
    },
}


def _render_voc_design_system() -> None:
    st.html(
        """
        <style>
        .st-key-voc_page_hero {
            background:linear-gradient(118deg,#f4f9ff 0%,#ffffff 62%,#edf5fd 100%);
            border:1px solid #bfd4e9!important;border-left:5px solid #155a96!important;
            border-radius:14px!important;padding:16px 20px!important;margin:0 0 14px;
            box-shadow:0 7px 20px rgba(21,90,150,.08);
        }
        .st-key-voc_page_hero h2{color:#0b4478!important;font-size:25px!important;letter-spacing:-.6px;margin:0!important}
        .st-key-voc_page_hero [data-testid="stCaptionContainer"]{color:#526a83!important;line-height:1.5}
        .st-key-voc_page_flow{background:rgba(255,255,255,.72);border:1px solid #d3e2f0;border-radius:10px;padding:9px 12px!important}
        .st-key-voc_page_content>div[data-testid="stVerticalBlock"]{gap:.72rem}
        .st-key-voc_page_content div[data-testid="stVerticalBlockBorderWrapper"]{
            border-color:#c8d9ee!important;border-radius:11px!important;
            background:linear-gradient(145deg,#ffffff 0%,#fbfdff 100%);
            box-shadow:0 3px 12px rgba(21,90,150,.045);
        }
        .st-key-voc_page_content [data-testid="stMetric"]{
            min-height:82px;padding:11px 13px;border:1px solid #d1dfed;border-radius:10px;
            background:linear-gradient(145deg,#fff,#f5f9fd);box-shadow:0 2px 8px rgba(21,90,150,.04)
        }
        .st-key-voc_page_content [data-testid="stMetricLabel"]{color:#4a6078;font-weight:700}
        .st-key-voc_page_content [data-testid="stMetricValue"]{color:#0b4f91;letter-spacing:-.5px}
        .st-key-voc_page_content div[data-testid="stForm"]{
            border:1px solid #d2e0ee;border-radius:11px;padding:12px 14px;background:#f8fbfe;
        }
        .st-key-voc_page_content [data-testid="stWidgetLabel"] p{font-weight:650;color:#334f6c}
        .st-key-voc_page_content [data-testid="stDataFrame"]{border:1px solid #cfdeec;border-radius:10px;overflow:hidden}
        .st-key-voc_page_content [data-testid="stAlert"]{border-radius:9px;border-left-width:4px}
        .st-key-voc_page_content [data-testid="stExpander"]{border-color:#cfdeec!important;border-radius:10px!important;background:#fbfdff}
        .st-key-voc_page_content [data-testid="stProgress"] [role="progressbar"]{height:10px;border-radius:8px}
        .st-key-voc_page_content button{transition:transform .12s ease,box-shadow .12s ease}
        .st-key-voc_page_content button:hover{transform:translateY(-1px);box-shadow:0 3px 9px rgba(21,90,150,.11)}
        .st-key-voc_page_content h3{color:#153f6d!important;letter-spacing:-.3px;margin-top:.3rem!important}
        .st-key-voc_page_content h4{color:#24557f!important;letter-spacing:-.2px}
        @media(max-width:800px){.st-key-voc_page_hero{padding:14px!important}.st-key-voc_page_hero h2{font-size:21px!important}}
        </style>
        """
    )


def _render_voc_page_header(sub_menu: str) -> None:
    meta = VOC_PAGE_META[sub_menu]
    with st.container(border=True, key="voc_page_hero"):
        if sub_menu == "Dashboard":
            st.session_state["voc_dashboard_header_rendered"] = True
            header_col, control_col = st.columns([1.45, 1.1], vertical_alignment="bottom")
            with header_col:
                st.markdown(f"## :material/{meta['icon']}: {meta['title']}")
                st.caption(meta["description"])
            with control_col:
                today = date.today()
                selected_range = st.session_state.get(
                    "voc_dashboard_filter_range",
                    (today - timedelta(days=6), today),
                )
                with st.form("voc_dashboard_filters", border=False):
                    filter_columns = st.columns([2.2, 0.9, 0.95], vertical_alignment="bottom")
                    with filter_columns[0]:
                        selected_range = st.date_input(
                            "기간",
                            value=selected_range,
                            max_value=today,
                            key="voc_dashboard_filter_range",
                        )
                    with filter_columns[1]:
                        submitted = st.form_submit_button(
                            "조회",
                            icon=":material/search:",
                            type="primary",
                            width="stretch",
                        )
                    with filter_columns[2]:
                        refresh_requested = st.form_submit_button(
                            "새로고침",
                            icon=":material/refresh:",
                            width="stretch",
                        )
                st.session_state["voc_dashboard_filter_submitted"] = bool(submitted)
                st.session_state["voc_dashboard_filter_refresh_requested"] = bool(refresh_requested)
        else:
            if sub_menu == "Agent 관리":
                with st.container(
                    horizontal=True,
                    horizontal_alignment="distribute",
                    vertical_alignment="center",
                    gap="small",
                ):
                    st.markdown(f"## :material/{meta['icon']}: {meta['title']}")
                    if st.button(
                        "상태 새로고침",
                        type="primary",
                        width="content",
                        icon=":material/refresh:",
                        key="agent_header_refresh",
                    ):
                        _load_agent_management_snapshot.clear()
                        _load_goal_monitor_snapshot.clear()
                        st.rerun()
                st.caption(
                    f"{meta['description']} 전체 시작은 Interpreter 등 6개 Agent 프로세스만 기동하며 "
                    "Test Case나 VOC 품질진단을 실행하지 않습니다. 전체 또는 개별 제어는 관리 스크립트가 "
                    "생성한 PID만 대상으로 하며, 외부 프로세스가 점유한 포트는 종료하지 않습니다."
                )
            else:
                st.markdown(f"## :material/{meta['icon']}: {meta['title']}")
                st.caption(meta["description"])
                st.markdown(
                    " ".join(
                        f":blue-badge[{item}]"
                        for item in meta.get("flow", ())
                    )
                )


def _new_manual_preparation_progress() -> dict:
    return {
        "status": "RUNNING",
        "current_step": 1,
        "steps": [
            {"number": index, "label": label, "status": "waiting"}
            for index, label in enumerate(MANUAL_PREPARATION_STEPS, start=1)
        ],
    }


def _update_manual_preparation(job_id: str, step_number: int, status: str) -> None:
    if not job_id:
        return
    job = background_job_snapshot(job_id) or {}
    preparation = deepcopy(
        job.get("progress", {}).get("preparation")
        or _new_manual_preparation_progress()
    )
    for step in preparation["steps"]:
        if step["number"] == step_number:
            step["status"] = status
        elif step["number"] < step_number and step["status"] in {"waiting", "active"}:
            step["status"] = "success"
    preparation["current_step"] = step_number
    if status == "failure":
        preparation["status"] = "ERROR"
    elif all(step["status"] == "success" for step in preparation["steps"]):
        preparation["status"] = "COMPLETED"
    else:
        preparation["status"] = "RUNNING"
    update_background_job(job_id, progress={"preparation": preparation})


def _execute_goal_testcase(job_id: str, case_id: str | None = None) -> dict:
    """Agent 사전 점검과 TC 실행을 모두 백그라운드에서 수행합니다."""
    if case_id is None:
        case_id, job_id = job_id, ""
    _update_manual_preparation(job_id, 1, "active")
    try:
        agent_snapshot = agent_status_snapshot()
        _update_manual_preparation(job_id, 1, "success")
        timeout_seconds = 180 if agent_snapshot.get("all_running") else 20
        judge_config = {
            "enabled": False,
            "provider": "anthropic",
            "model": "claude-opus-4-6",
        }
        if job_id:
            testcase_result = run_test_case(
                case_id,
                timeout_seconds,
                judge_config,
                progress_callback=lambda step, status: _update_manual_preparation(
                    job_id, step, status
                ),
            )
        else:
            testcase_result = run_test_case(case_id, timeout_seconds, judge_config)
        return {"testcase_result": testcase_result, "agent_snapshot": agent_snapshot}
    except Exception:
        job = background_job_snapshot(job_id) or {}
        preparation = job.get("progress", {}).get("preparation", {})
        current_step = int(preparation.get("current_step") or 1)
        _update_manual_preparation(job_id, current_step, "failure")
        raise


def _execute_goal_judge(
    _job_id: str,
    run_id: str,
    case_id: str,
    judge_config: dict,
) -> dict:
    return reevaluate_voc_run_case(run_id, case_id, judge_config)


@st.cache_resource
def _batch_executor():
    return ThreadPoolExecutor(max_workers=1, thread_name_prefix="voc-batch")


def _judge_config_controls(key_prefix: str, *, fault_only: bool = False) -> dict:
    options = judge_provider_options()
    enabled = st.toggle(
        "독립 LLM Judge 평가",
        key=f"{key_prefix}_judge_enabled",
        help="Pipeline 성공 후 별도 LLM이 100점 Rubric으로 최종 결과를 평가합니다.",
    )
    default = next((item for item in options if item["provider"] == "anthropic"), options[0])
    if not enabled:
        return {"enabled": False, "provider": default["provider"], "model": default["default_model"]}

    provider = st.selectbox(
        "Judge Provider",
        [item["provider"] for item in options],
        format_func=lambda value: next(item["label"] for item in options if item["provider"] == value),
        key=f"{key_prefix}_judge_provider",
    )
    selected = next(item for item in options if item["provider"] == provider)
    model = st.text_input(
        "Judge 모델",
        value=selected["default_model"],
        key=f"{key_prefix}_judge_model_{provider}",
    )
    independence = judge_independence_preview(provider, model)
    if selected["credential_configured"]:
        st.caption(
            f"자격 증명 설정됨 · 예상 독립성 {independence['grade']} · {independence['reason']}"
        )
    else:
        st.error(f"{selected['label']} API 자격 증명이 설정되지 않았습니다.")
    if fault_only:
        st.info("격리 장애 Case는 개선안이 없으므로 Judge가 NOT_RUN으로 기록됩니다.")
    return {
        "enabled": enabled,
        "provider": provider,
        "model": model,
        "timeout_seconds": 90,
        "max_retries": 2,
    }


def _select_manual_judge(state_key: str, provider: str):
    st.session_state[state_key] = provider


@st.cache_data(max_entries=2, show_spinner=False)
def _manual_judge_logo_data_uri(provider: str) -> str:
    logo_path = Path(__file__).resolve().parents[1] / "assets" / "providers" / f"{provider}.svg"
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _manual_judge_config_controls(key_prefix: str, *, fault_only: bool = False) -> dict:
    options = {item["provider"]: item for item in judge_provider_options()}
    state_key = f"{key_prefix}_judge_provider"
    st.session_state.setdefault(state_key, "anthropic")
    selected_provider = st.session_state[state_key]
    if selected_provider not in {item["provider"] for item in MANUAL_JUDGE_PROVIDERS}:
        selected_provider = "anthropic"
        st.session_state[state_key] = selected_provider

    card_classes = []
    for item in MANUAL_JUDGE_PROVIDERS:
        state = "selected" if item["provider"] == selected_provider else "inactive"
        logo_uri = _manual_judge_logo_data_uri(item["provider"])
        card_classes.append(
            f".st-key-{key_prefix}_judge_select_{item['provider']} button{{"
            "height:178px;border-radius:14px;display:flex;flex-direction:column;"
            "justify-content:flex-end;align-items:flex-start;padding:18px 20px;"
            "font-size:14px;font-weight:700;white-space:pre-line;transition:all .18s ease;"
            f"background-image:url('{logo_uri}');background-repeat:no-repeat;"
            "background-position:18px 18px;background-size:auto 48px;"
            + (
                "background-color:#f4f9ff;border:2px solid #1d65a6;"
                "color:#174f85;box-shadow:0 6px 18px rgba(29,101,166,.13)"
                if state == "selected"
                else
                "background-color:#eef1f4;border:1px solid #ccd3da;"
                "color:#697684;box-shadow:none;filter:grayscale(1);opacity:.72"
            )
            + "}"
        )
    st.html(
        "<style>"
        + "".join(card_classes)
        + "</style>"
    )

    st.markdown("#### Judge Provider 선택")
    st.caption(
        "내부 Agent Pipeline과 실행 이벤트를 확인한 다음, 독립 Provider를 선택해 동일한 결과를 평가합니다."
    )
    columns = st.columns(2, gap="medium")
    for column, item in zip(columns, MANUAL_JUDGE_PROVIDERS):
        provider = item["provider"]
        selected = provider == selected_provider
        option = options.get(provider, {})
        independence = judge_independence_preview(provider, item["model"])
        with column:
            st.button(
                f"Judge Provider {item['number']}\n\n{item['label']} · {item['model']}\n\n"
                + ("✓ 현재 선택" if selected else "카드를 클릭하여 선택"),
                key=f"{key_prefix}_judge_select_{provider}",
                width="stretch",
                on_click=_select_manual_judge,
                args=(state_key, provider),
                help=f"{item['label']} {item['model']}을 독립 평가 Provider로 사용합니다.",
            )
            credential_text = "API 자격 증명 설정됨" if option.get("credential_configured") else "API 자격 증명 미설정"
            st.caption(f"{credential_text} · 예상 독립성 {independence['grade']}")

    selected = next(item for item in MANUAL_JUDGE_PROVIDERS if item["provider"] == selected_provider)
    credential_configured = bool(options.get(selected_provider, {}).get("credential_configured"))
    if fault_only:
        st.info(
            "격리 장애 Case는 개선안이 없어 선택한 Provider를 호출하지 않고 Judge 결과를 NOT_RUN으로 기록합니다.",
            icon=":material/info:",
        )
    elif not credential_configured:
        st.error(
            f"{selected['label']} API 자격 증명이 설정되지 않아 실행할 수 없습니다.",
            icon=":material/key_off:",
        )
    return {
        "enabled": not fault_only,
        "provider": selected_provider,
        "model": selected["model"],
        "timeout_seconds": 90,
        "max_retries": 2,
        "credential_configured": credential_configured or fault_only,
    }


def _validity_config_controls(key_prefix: str) -> dict:
    options = validity_provider_options()
    provider = st.selectbox(
        "자동 평가 Provider",
        [item["provider"] for item in options],
        format_func=lambda value: next(item["label"] for item in options if item["provider"] == value),
        key=f"{key_prefix}_validity_provider",
    )
    selected = next(item for item in options if item["provider"] == provider)
    model = st.text_input(
        "자동 평가 모델",
        value=selected["default_model"],
        key=f"{key_prefix}_validity_model_{provider}",
    )
    if selected["credential_configured"]:
        st.caption("자격 증명 설정됨 · 독립 Judge 결과와 별도로 개선안 실행 타당성을 평가합니다.")
    else:
        st.error(f"{selected['label']} API 자격 증명이 설정되지 않았습니다.")
    return {
        "provider": provider,
        "model": model,
        "credential_configured": selected["credential_configured"],
    }


def _keyword_text(values) -> str:
    safe = [escape(str(value)) for value in (values or [])[:6] if str(value).strip()]
    return ", ".join(safe) if safe else "-"


def _parse_json_mapping(value) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_pipeline_trace_summary(value) -> dict:
    values = {}
    flags = []
    for item in str(value or "").split(";"):
        token = item.strip()
        if not token:
            continue
        if "=" in token:
            key, raw_value = token.split("=", 1)
            values[key.strip()] = raw_value.strip()
        else:
            flags.append(token)
    return {"values": values, "flags": flags}


def _pipeline_trace_event_rows(trace: dict) -> list[dict]:
    operation_labels = {
        "ParseQuestion": "질문 의도 해석",
        "IntentDataTransfer": "분석 요청·결과 전달",
        "Retrieve": "관련 VOC 검색",
        "VOCDataTransfer": "검색 결과 전달",
        "Evaluate": "요약 후보 평가",
        "ReviewSummary": "요약 품질 검토",
        "ReviewPolicy": "개선안 품질 검토",
        "Refine": "요약 보완",
        "RefinePolicy": "개선안 보완",
        "Improve": "개선안 생성",
        "RunPolicyPipeline": "개선안 생성·검토",
    }
    status_labels = {"success": "성공", "failure": "실패", "started": "시작"}
    completed_events = [
        event
        for event in (trace.get("events", []) if isinstance(trace, dict) else [])
        if isinstance(event, dict) and event.get("status") in {"success", "failure"}
    ]
    rows = []
    for index, event in enumerate(completed_events, start=1):
        error_text = str(event.get("error") or "").strip()
        error = error_text.splitlines()[0] if error_text else ""
        clues = event.get("output_keywords") or event.get("keywords") or []
        clue_text = ", ".join(str(item) for item in clues[:6])
        if event.get("item_count") is not None:
            clue_text = f"VOC {event['item_count']}건 전달" + (f" · {clue_text}" if clue_text else "")
        if error:
            clue_text = error[:160]
        rows.append({
            "순서": index,
            "Agent 연결": f"{event.get('source', '-')} → {event.get('target', '-')}",
            "처리 내용": operation_labels.get(event.get("operation"), event.get("operation", "-")),
            "결과": status_labels.get(event.get("status"), event.get("status", "-")),
            "처리시간(ms)": round(float(event.get("duration_ms") or 0), 2),
            "판단 단서": clue_text or "-",
        })
    return rows


TRACE_FLOW_EXPLANATIONS = {
    "ParseQuestion": (
        "start",
        "질문 해석",
        "Agent 1이 사용자 질문을 의도·검색 조건·수행 작업으로 구조화합니다.",
    ),
    "IntentDataTransfer": (
        "handoff",
        "분석 이관",
        "Agent 1이 해석한 의도를 조정 역할의 Agent 3에 전달해 전체 Pipeline을 시작합니다.",
    ),
    "Retrieve": (
        "lookup",
        "근거 조회",
        "Agent 3이 답변과 요약의 근거가 되는 VOC 원문을 확보하기 위해 Agent 2를 호출합니다.",
    ),
    "VOCDataTransfer": (
        "return",
        "검색 결과 반환",
        "Agent 2가 검색한 VOC 데이터와 건수를 이후 단계를 조정하는 Agent 3에 반환합니다.",
    ),
    "Evaluate": (
        "selection",
        "후보 평가",
        "Agent 3이 생성한 후보 중 가장 적합한 결과를 선택하기 위해 Agent 4의 평가를 요청합니다.",
    ),
    "ReviewSummary": (
        "review",
        "요약 검토",
        "선택된 요약의 누락·왜곡·보완 필요 여부를 확인하기 위해 Agent 5가 검토합니다.",
    ),
    "ImprovePolicy": (
        "generation",
        "개선안 생성",
        "검토된 요약을 실행 가능한 정책 개선안으로 바꾸기 위해 Agent 6을 호출합니다.",
    ),
    "ReviewPolicy": (
        "feedback",
        "개선안 재검토",
        "Agent 6이 만든 개선안을 확정하기 전에 품질과 실행 가능성을 확인하기 위해 Agent 5로 되돌아갑니다.",
    ),
    "RefinePolicy": (
        "rework",
        "수정 요청 반영",
        "Agent 5가 개선안에 수정이 필요하다고 판단해 전달한 보완 의견을 Agent 6이 반영합니다.",
    ),
    "Improve": (
        "generation",
        "개선안 생성",
        "검토 결과를 실행 가능한 개선안으로 전환하기 위해 개선 Agent를 호출합니다.",
    ),
    "Refine": (
        "rework",
        "요약 보완",
        "Critic이 요청한 수정 사항을 반영하기 위해 요약 생성 단계를 다시 수행합니다.",
    ),
    "RunPolicyPipeline": (
        "handoff",
        "정책 Pipeline 실행",
        "검토된 요약을 기준으로 정책 개선과 재검토 흐름을 실행합니다.",
    ),
}


def _trace_agent_number(agent_name: str) -> int | None:
    return next(
        (
            index
            for index, (name, _, _) in enumerate(AGENT_PIPELINE, start=1)
            if name == agent_name
        ),
        None,
    )


def _trace_flow_explanation(
    event: dict,
    previous_event: dict | None = None,
) -> dict:
    operation = str(event.get("operation") or "작업")
    status = str(event.get("status") or "")
    current_number = _trace_agent_number(str(event.get("target") or ""))
    previous_number = _trace_agent_number(
        str((previous_event or {}).get("target") or "")
    )
    if previous_number and current_number:
        transition = f"Agent {previous_number} → Agent {current_number}"
    elif current_number:
        transition = f"시작 → Agent {current_number}"
    else:
        transition = "Agent 흐름"

    if status == "failure":
        error_text = str(event.get("error") or "").strip()
        short_error = error_text.splitlines()[0][:140] if error_text else ""
        return {
            "kind": "failure",
            "label": "호출 실패",
            "transition": transition,
            "reason": short_error
            or f"{operation} 처리 중 오류가 발생해 다음 단계로 진행하지 못했습니다.",
            "inferred": False,
        }

    configured = TRACE_FLOW_EXPLANATIONS.get(operation)
    if configured:
        kind, label, reason = configured
        return {
            "kind": kind,
            "label": label,
            "transition": transition,
            "reason": reason,
            "inferred": False,
        }

    if previous_number and current_number and current_number < previous_number:
        label = "이전 단계 재호출"
        direction_reason = f"{operation} 처리를 위해 앞 단계 Agent를 다시 호출했습니다."
    elif (
        previous_number
        and current_number
        and current_number > previous_number + 1
    ):
        label = "분기 호출"
        direction_reason = (
            f"{operation} 처리에 중간 단계가 필요하지 않아 해당 Agent로 바로 분기했습니다."
        )
    elif previous_number == current_number and current_number:
        label = "동일 단계 재처리"
        direction_reason = f"{operation} 결과를 보완하기 위해 같은 Agent가 다시 처리했습니다."
    else:
        label = "다음 단계 호출"
        direction_reason = f"{operation} 처리를 위해 다음 Agent를 호출했습니다."
    return {
        "kind": "inferred",
        "label": label,
        "transition": transition,
        "reason": (
            f"{direction_reason} Trace에 상세 분기 사유가 없어 작업 유형과 이동 방향을 기준으로 표시했습니다."
        ),
        "inferred": True,
    }


def _trace_reason(event: dict) -> str:
    """기존 호출부 호환용으로 작업 자체의 설명만 반환합니다."""
    return _trace_flow_explanation(event)["reason"]


def _trace_event_display_statuses(events: list[dict], *, running: bool) -> list[str]:
    """원본 started 이벤트가 후속 단계 진행 뒤에도 '진행'으로 남지 않게 표시 상태를 보정합니다."""
    display_statuses: list[str] = []
    for index, event in enumerate(events):
        status = str(event.get("status") or "unknown")
        if status != "started":
            display_statuses.append(status)
            continue

        signature = (event.get("source"), event.get("target"), event.get("operation"))
        later_events = events[index + 1 :]
        has_matching_terminal = any(
            (later.get("source"), later.get("target"), later.get("operation")) == signature
            and later.get("status") in {"success", "failure"}
            for later in later_events
        )
        # 같은 작업의 종료 로그가 있거나 다음 단계가 시작됐다면 이 started 기록은 이미 지난 단계입니다.
        display_statuses.append(
            "completed" if has_matching_terminal or bool(later_events) else ("started" if running else "ended")
        )
    return display_statuses


def _trace_display_events(events: list[dict]) -> list[dict]:
    """started/success 한 쌍을 하나의 단계 카드로 합쳐 상태 중복을 제거합니다."""
    display_events: list[dict] = []
    pending: dict[tuple, list[int]] = {}
    for event in events:
        item = dict(event)
        signature = (item.get("source"), item.get("target"), item.get("operation"))
        status = item.get("status")
        if status == "started":
            pending.setdefault(signature, []).append(len(display_events))
            display_events.append(item)
            continue
        if status in {"success", "failure"} and pending.get(signature):
            started_index = pending[signature].pop(0)
            if not pending[signature]:
                pending.pop(signature)
            started_event = display_events[started_index]
            item["started_at"] = started_event.get("timestamp", "")
            if not item.get("input_keywords"):
                item["input_keywords"] = started_event.get("input_keywords", [])
            display_events[started_index] = item
            continue
        display_events.append(item)
    return display_events


def _pipeline_run_summary(snapshot: dict, *, running: bool) -> dict:
    events = _trace_display_events(snapshot.get("events", []))
    result = st.session_state.get("goal_testcase_result") or {}
    started_at = st.session_state.get("goal_testcase_started_at", "")
    completed_at = st.session_state.get("goal_testcase_completed_at", "")

    execution = result.get("execution", {}) if isinstance(result, dict) else {}
    result_payload = execution.get("result", {}) if isinstance(execution, dict) else {}
    execution_ok = bool(execution.get("ok"))
    if result.get("mode") == "voc":
        execution_ok = execution_ok and bool(result_payload.get("ok"))

    failures = sum(event.get("status") == "failure" for event in events)
    successes = sum(event.get("status") == "success" for event in events)
    active_event = next(
        (event for event in reversed(events) if event.get("status") == "started"),
        {},
    )
    active_agent_name = str(active_event.get("target") or "")
    active_agent_number = next(
        (
            index
            for index, (name, _, _) in enumerate(AGENT_PIPELINE, start=1)
            if name == active_agent_name
        ),
        None,
    )
    if running:
        state = "preparing" if not events else "running"
        if not events:
            label = "테스트 수행 준비"
        elif active_agent_number:
            label = f"Agent {active_agent_number} · {active_agent_name} 수행 중"
        else:
            label = "Pipeline 결과 저장 중"
    elif result:
        state = "completed" if execution_ok else "failed"
        label = "수행 완료" if execution_ok else "수행 실패"
    elif failures:
        state, label = "failed", "최근 수행 실패"
    elif events and events[-1].get("operation") == "IntentDataTransfer" and events[-1].get("status") == "success":
        state, label = "completed", "최근 수행 완료"
    elif events:
        state, label = "recorded", "최근 수행 기록"
    else:
        state, label = "waiting", "수행 대기"

    duration_seconds = 0.0
    try:
        start = datetime.fromisoformat(started_at) if started_at else None
        end = datetime.fromisoformat(completed_at) if completed_at else datetime.now().astimezone()
        if start:
            duration_seconds = max(0.0, (end - start).total_seconds())
    except (TypeError, ValueError):
        pass
    if not duration_seconds and events:
        try:
            first = datetime.fromisoformat(str(events[0].get("started_at") or events[0].get("timestamp")))
            last = datetime.fromisoformat(str(events[-1].get("timestamp")))
            duration_seconds = max(0.0, (last - first).total_seconds())
        except (TypeError, ValueError):
            pass

    return {
        "state": state,
        "label": label,
        "case_id": result.get("case", {}).get("case_id") or st.session_state.get("goal_testcase_running_case_id", "-"),
        "steps": len(events),
        "successes": successes,
        "failures": failures,
        "duration_seconds": duration_seconds,
        "active_agent_number": active_agent_number,
        "active_agent_name": active_agent_name,
    }


def _render_agent_pipeline(snapshot: dict, running: bool):
    events = snapshot.get("events", [])
    agent_snapshot = st.session_state.get("goal_testcase_agent_snapshot")
    if not isinstance(agent_snapshot, dict):
        agent_snapshot = {"agents": []}
    agent_statuses = {agent["name"]: agent for agent in agent_snapshot.get("agents", [])}
    operation_states = {}
    for index, event in enumerate(events):
        key = (event.get("source"), event.get("target"), event.get("operation"))
        operation_states[key] = (index, event)
    active_events = [item for item in operation_states.values() if item[1].get("status") == "started"]
    current_agent = max(active_events, default=(-1, {}), key=lambda item: item[0])[1].get("target")

    cards = []
    for agent_number, (name, role, port) in enumerate(AGENT_PIPELINE, start=1):
        agent_status = agent_statuses.get(name, {})
        is_enabled = agent_status.get("healthy", True)
        related = [event for event in events if event.get("target") == name]
        failures = [event for event in related if event.get("status") == "failure"]
        successes = [event for event in related if event.get("status") == "success"]
        if not is_enabled:
            state, label = "disabled", "비활성"
        elif failures and (not successes or failures[-1].get("timestamp", "") >= successes[-1].get("timestamp", "")):
            state, label = "error", "오류"
        elif running and current_agent == name:
            state, label = "active", "작업 중"
        elif successes:
            state, label = "done", "완료"
        else:
            state, label = "waiting", "대기"
        last_in = next((event for event in reversed(related) if event.get("input_keywords")), {})
        last_out = next((event for event in reversed(related) if event.get("output_keywords")), {})
        duration = last_out.get("duration_ms") or (successes[-1].get("duration_ms") if successes else 0)
        status_detail = escape(str(agent_status.get("status", "점검 중" if running else "미확인")))
        cards.append(f"""
          <div class="agent-card {state}">
            <div class="agent-head"><span class="agent-icon">{agent_number}</span><span><b>{name}</b><small>{role} · {port}</small></span><em>{label}</em></div>
            <div class="io in"><b>IN</b><span>{_keyword_text(last_in.get('input_keywords'))}</span></div>
            <div class="io out"><b>OUT</b><span>{_keyword_text(last_out.get('output_keywords'))}</span></div>
            <div class="agent-meta">상태 {status_detail} · 처리시간 {float(duration or 0):,.0f} ms</div>
          </div>""")

    trace_id = escape(snapshot.get("trace_id") or "아직 실행 Trace 없음")
    status_text = "테스트 실행 중 · 2초마다 상태 확인" if running else "최근 수행 Agent Pipeline"
    st.html(f"""
    <style>
      .pipeline-wrap{{border:1px solid #d8e3f0;border-radius:16px;padding:16px;background:linear-gradient(180deg,#f8fbff,#fff);margin:4px 0 18px}}
      .pipeline-title{{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;color:#17355f;font:600 13px 'Segoe UI','Malgun Gothic',sans-serif}}
      .pipeline-grid{{display:grid;grid-template-columns:repeat(6,minmax(170px,1fr));gap:24px;overflow-x:auto;padding:4px}}
      .agent-card{{position:relative;min-width:170px;border:2px solid #d6deea;border-radius:13px;background:#fff;padding:12px;box-shadow:0 4px 12px rgba(26,56,96,.07)}}
      .agent-card:not(:last-child):after{{content:'→';position:absolute;right:-22px;top:47%;color:#4470aa;font-size:22px;font-weight:800}}
      .agent-card.active{{border-color:#1b6fd1;box-shadow:0 0 0 4px rgba(27,111,209,.12),0 8px 20px rgba(27,111,209,.18);animation:pulse 1.4s infinite}}
      .agent-card.done{{border-color:#36a269;background:#f7fff9}} .agent-card.error{{border-color:#dc4c4c;background:#fff8f8}}
      .agent-card.disabled{{border-color:#b8bec7;background:#eceff2;box-shadow:none;filter:grayscale(1);opacity:.72}}
      .agent-card.disabled:not(:last-child):after{{color:#aeb4bd}}
      .agent-head{{display:flex;gap:8px;align-items:center;font:13px 'Segoe UI','Malgun Gothic',sans-serif;color:#172b48}}
      .agent-head small{{display:block;color:#75849a;font-size:10px;margin-top:2px}} .agent-head em{{margin-left:auto;font-style:normal;font-size:10px;padding:3px 7px;border-radius:10px;background:#edf2f8}}
      .active .agent-head em{{background:#1b6fd1;color:#fff}} .done .agent-head em{{background:#daf4e3;color:#16713d}} .error .agent-head em{{background:#fde0e0;color:#a62525}}
      .disabled .agent-head{{color:#59616c}} .disabled .agent-head em{{background:#7a828d;color:#fff}}
      .agent-icon{{display:grid;place-items:center;width:30px;height:30px;border-radius:9px;background:#173f75;color:#fff;font-weight:800;font-size:10px}}
      .io{{display:grid;grid-template-columns:30px 1fr;gap:5px;margin-top:10px;border-radius:8px;padding:7px;font:10px 'Segoe UI','Malgun Gothic',sans-serif;line-height:1.35}}
      .io b{{color:#fff;text-align:center;border-radius:5px;padding:2px}} .io span{{color:#465871;overflow-wrap:anywhere}}
      .io.in{{background:#eef5ff}} .io.in b{{background:#2f6eb5}} .io.out{{background:#eefaf2}} .io.out b{{background:#32935b}}
      .disabled .agent-icon,.disabled .io b{{background:#858c95}} .disabled .io{{background:#dde1e5}} .disabled .io span{{color:#737a84}}
      .agent-meta{{text-align:right;color:#8794a8;font-size:9px;margin-top:7px}}
      @keyframes pulse{{50%{{transform:translateY(-2px)}}}} @media(max-width:900px){{.pipeline-grid{{grid-template-columns:repeat(6,180px)}}}}
    </style>
    <div class="pipeline-wrap"><div class="pipeline-title"><span>{status_text}</span><span>Trace · {trace_id}</span></div><div class="pipeline-grid">{''.join(cards)}</div></div>
    """)


def _render_agent_pipeline_v2(
    snapshot: dict,
    running: bool,
    preparation: dict | None = None,
):
    source_events = (
        snapshot.get("events", [])
        if isinstance(snapshot.get("events", []), list)
        else []
    )
    raw_event_count = len(source_events)
    raw_events = [
        event
        if isinstance(event, dict)
        else {
            "operation": "형식 미확인 원본 로그",
            "status": "unknown",
        }
        for event in source_events
    ]
    events = _trace_display_events(raw_events)
    agent_numbers = {name: index for index, (name, _, _) in enumerate(AGENT_PIPELINE, start=1)}
    display_statuses = _trace_event_display_statuses(events, running=running)
    run_summary = _pipeline_run_summary(snapshot, running=running)

    status_labels = {
        "started": "진행",
        "completed": "완료",
        "ended": "종료",
        "success": "성공",
        "failure": "실패",
    }
    raw_status_labels = {
        "started": "시작",
        "success": "성공",
        "failure": "실패",
    }

    def build_trace_history(
        event_items: list[dict],
        statuses: list[str],
        *,
        raw: bool = False,
    ) -> str:
        trace_rows = []
        for event_index, (event, display_status) in enumerate(
            zip(event_items, statuses),
            start=1,
        ):
            source = escape(str(event.get("source") or "-"))
            target = escape(str(event.get("target") or "-"))
            target_number = agent_numbers.get(event.get("target"), "-")
            operation = escape(str(event.get("operation") or "작업"))
            status = str(display_status or "unknown")
            status_class = status if status in status_labels else "unknown"
            status_label = (
                raw_status_labels.get(status, escape(status))
                if raw
                else status_labels.get(status, "기록")
            )
            timestamp = str(event.get("timestamp") or "-")
            time_text = escape(timestamp[11:19] if len(timestamp) >= 19 else timestamp)
            duration = float(event.get("duration_ms") or 0)
            duration_text = f"{duration:,.0f} ms" if duration else "-"
            previous_event = event_items[event_index - 2] if event_index > 1 else None
            flow = _trace_flow_explanation(event, previous_event)
            flow_kind = escape(str(flow["kind"]))
            flow_label = escape(str(flow["label"]))
            transition = escape(str(flow["transition"]))
            reason = escape(str(flow["reason"]))
            inferred_badge = " · 추정" if flow.get("inferred") else ""
            reason_text = (
                f"<b>{transition} · {flow_label}{inferred_badge}</b>"
                f"<span>{reason}</span>"
            )
            reason_class = f"flow2-reason flow2-{flow_kind}"
            trace_rows.append(f"""
          <div class="flow2-trace-row {status_class}">
            <span class="flow2-seq">#{event_index:02d}</span>
            <span class="flow2-agent-no">Agent {target_number}</span>
            <span class="flow2-time">{time_text}</span>
            <span class="flow2-route"><b>{source}</b><i>→</i><b>{target}</b><small>{operation}</small></span>
            <em>{status_label}</em>
            <span class="flow2-duration">{duration_text}</span>
            <span class="{reason_class}">{reason_text}</span>
          </div>""")
        return "".join(trace_rows)

    trace_history = build_trace_history(events, display_statuses)
    raw_trace_history = build_trace_history(
        raw_events,
        [str(event.get("status") or "unknown") for event in raw_events],
        raw=True,
    )
    if not raw_trace_history:
        raw_trace_history = (
            '<div class="flow2-trace-empty">아직 기록된 원본 로그가 없습니다.</div>'
        )
    has_run_context = bool(
        events
        or st.session_state.get("goal_testcase_started_at")
        or st.session_state.get("goal_testcase_result")
    )
    if not preparation:
        preparation = _new_manual_preparation_progress()
        if events or not running:
            preparation["status"] = "COMPLETED"
            for step in preparation["steps"]:
                step["status"] = "success"
        else:
            preparation["steps"][0]["status"] = "active"
    preparation_status = preparation.get("status", "RUNNING")
    preparation_state = {
        "COMPLETED": "completed",
        "ERROR": "failed",
    }.get(preparation_status, "active")
    preparation_label = {
        "COMPLETED": "성공",
        "ERROR": "실패",
    }.get(preparation_status, "진행 중")
    preparation_icon = {
        "COMPLETED": "✓",
        "ERROR": "!",
    }.get(preparation_status, "●")
    step_status_labels = {
        "waiting": "대기",
        "active": "진행",
        "success": "완료",
        "failure": "실패",
    }
    preparation_steps = list(preparation.get("steps", []))
    completed_preparation_steps = sum(
        step.get("status") == "success"
        for step in preparation_steps
    )
    preparation_progress_text = (
        "준비 완료"
        if preparation_status == "COMPLETED"
        else f"{completed_preparation_steps}/5 완료 · 순서대로 처리 중"
    )
    current_preparation_step = next(
        (
            str(step.get("label") or "-")
            for step in preparation_steps
            if step.get("status") in {"active", "failure"}
        ),
        "Agent Pipeline 호출 준비 완료"
        if preparation_status == "COMPLETED"
        else "다음 준비 단계 확인 중",
    )
    preparation_summary_card = (
        f"""
      <article class="flow2-preparation {preparation_state} flow2-preparation-summary">
        <div class="flow2-preparation-head">
          <span class="flow2-preparation-icon">{preparation_icon}</span>
          <span><strong>테스트 수행 준비</strong><small>Agent 이벤트 생성 전 선행 작업</small></span>
          <em>{preparation_label}</em>
        </div>
        <div class="flow2-preparation-progress">{preparation_progress_text}</div>
        <div class="flow2-preparation-current">
          <b>{'완료 결과' if preparation_status == 'COMPLETED' else '현재 단계'}</b>
          <span>{escape(current_preparation_step)}</span>
        </div>
      </article>"""
        if has_run_context
        else ""
    )

    def build_preparation_step_card(group: list[dict]) -> str:
        statuses = [str(step.get("status") or "waiting") for step in group]
        if "failure" in statuses:
            group_state, group_label, group_icon = "failed", "실패", "!"
        elif "active" in statuses:
            group_state, group_label, group_icon = "active", "진행", "●"
        elif statuses and all(status == "success" for status in statuses):
            group_state, group_label, group_icon = "completed", "완료", "✓"
        else:
            group_state, group_label, group_icon = "waiting", "대기", "○"
        first_number = int(group[0].get("number") or 1)
        last_number = int(group[-1].get("number") or first_number)
        group_rows = "".join(
            (
                f"<li class='{escape(str(step.get('status', 'waiting')))}'>"
                f"<span>{int(step.get('number') or index)}</span>"
                f"<b>{escape(str(step.get('label') or '-'))}</b>"
                f"<em>{step_status_labels.get(step.get('status'), '대기')}</em></li>"
            )
            for index, step in enumerate(group, start=first_number)
        )
        completed_in_group = sum(status == "success" for status in statuses)
        return f"""
      <article class="flow2-preparation {group_state} flow2-preparation-step">
        <div class="flow2-preparation-head">
          <span class="flow2-preparation-icon">{group_icon}</span>
          <span><strong>준비 단계 {first_number}–{last_number}</strong><small>{completed_in_group}/{len(group)}단계 완료</small></span>
          <em>{group_label}</em>
        </div>
        <ol>{group_rows}</ol>
      </article>"""

    preparation_step_cards = (
        "".join(
            build_preparation_step_card(group)
            for group in (preparation_steps[:3], preparation_steps[3:])
            if group
        )
        if has_run_context
        else ""
    )
    preparation_cards = preparation_summary_card + preparation_step_cards
    duration_text = (
        f"{run_summary['duration_seconds']:.1f}초"
        if run_summary["duration_seconds"]
        else "측정 중"
    )
    summary_card = f"""
      <article class="flow2-run-summary {run_summary['state']}">
        <span class="flow2-summary-icon">{'✓' if run_summary['state'] == 'completed' else '!' if run_summary['state'] == 'failed' else '●'}</span>
        <strong>{escape(run_summary['label'])}</strong>
        <small>Case {escape(str(run_summary['case_id']))}</small>
        <dl>
          <div><dt>총 스텝</dt><dd>{run_summary['steps']}단계</dd></div>
          <div><dt>성공</dt><dd>{run_summary['successes']}건</dd></div>
          <div><dt>실패</dt><dd>{run_summary['failures']}건</dd></div>
          <div><dt>수행시간</dt><dd>{duration_text}</dd></div>
        </dl>
      </article>""" if has_run_context else ""

    trace_id = escape(snapshot.get("trace_id") or "아직 실행 Trace 없음")
    st.html(f"""
    <style>
      .flow2-wrap{{border:1px solid #d8e3f0;border-radius:16px;padding:16px;background:#fff;margin:4px 0 18px}}
      .flow2-trace{{font-family:'Segoe UI','Malgun Gothic',sans-serif}}
      .flow2-trace + .flow2-trace{{margin-top:14px;padding-top:14px;border-top:1px solid #e3e9f1}}
      .flow2-trace-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;color:#334d70;font-size:11px;font-weight:700}}
      .flow2-trace-head span:last-child{{color:#7a889b;font-size:9px;font-weight:500}}
      .flow2-raw-summary{{display:grid;grid-template-columns:1fr auto auto;gap:10px;align-items:center;color:#334d70;font-size:11px;font-weight:700;cursor:pointer;list-style:none}}
      .flow2-raw-summary::-webkit-details-marker{{display:none}}
      .flow2-raw-summary span:nth-child(2){{color:#7a889b;font-size:9px;font-weight:500}}
      .flow2-raw-summary:after{{content:'펼치기 ＋';min-width:58px;padding:4px 8px;border:1px solid #c9d8e8;border-radius:8px;background:#f3f7fb;color:#42688f;font-size:9px;text-align:center}}
      .flow2-raw-trace[open] .flow2-raw-summary:after{{content:'접기 −'}}
      .flow2-raw-content{{margin-top:8px}}
      .flow2-raw-guide{{margin:-2px 0 7px;color:#7a889b;font-size:8px}}
      .flow2-legend{{display:flex;flex-wrap:wrap;gap:5px;margin:0 0 7px}} .flow2-legend span{{padding:3px 7px;border-radius:10px;background:#eef5fd;color:#355b87;font-size:8px}}
      .flow2-legend .return{{background:#edf9f2;color:#17643b}} .flow2-legend .feedback{{background:#fff8e8;color:#8a540c}} .flow2-legend .failure{{background:#fff0f0;color:#982d2d}} .flow2-legend .inferred{{background:#f7f2fb;color:#654186}}
      .flow2-trace-list{{overflow-x:auto;padding:10px;border:1px solid #e1e7ef;border-radius:10px;background:#f9fbfd;direction:rtl}}
      .flow2-trace-track{{display:flex;align-items:flex-start;gap:28px;width:max-content;min-width:100%;direction:ltr}}
      .flow2-trace-row{{position:relative;display:grid;grid-template-columns:38px 56px 1fr 42px;grid-template-areas:'seq agent time status' 'route route route duration' 'reason reason reason reason';gap:8px;align-items:center;width:280px;min-width:280px;height:{MANUAL_EVENT_CARD_HEIGHT}px;box-sizing:border-box;padding:10px;border:1px solid #dfe6ef;border-radius:10px;background:#fff;box-shadow:0 3px 9px rgba(30,59,96,.06);color:#52637a;font-size:9px}}
      .flow2-trace-row:not(:last-child):after{{content:'→';position:absolute;right:-22px;top:46%;color:#4b75a9;font-size:19px;font-weight:800}}
      .flow2-trace-row:hover{{border-color:#9db7d5;background:#f7fbff}}
      .flow2-seq{{grid-area:seq;color:#95a1b1;font-family:Consolas,monospace}} .flow2-time{{grid-area:time;color:#6f7f93;font-family:Consolas,monospace}}
      .flow2-agent-no{{display:inline-grid;place-items:center;border-radius:8px;background:#173f75;color:#fff;padding:3px 4px;font-weight:800}}
      .flow2-agent-no{{grid-area:agent}} .flow2-route{{grid-area:route;display:grid;grid-template-columns:auto 14px auto 1fr;align-items:center;gap:3px;color:#263d5d}}
      .flow2-route i{{font-style:normal;color:#4b75a9;text-align:center}} .flow2-route small{{color:#7f8da0;margin-left:5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
      .flow2-trace-row em{{grid-area:status;font-style:normal;text-align:center;border-radius:8px;padding:3px 4px;background:#e8eef5;color:#52637a}}
      .flow2-trace-row.started em{{background:#dfeeff;color:#175b9d}} .flow2-trace-row.completed em,.flow2-trace-row.success em{{background:#ddf4e6;color:#247147}} .flow2-trace-row.ended em{{background:#eef1f4;color:#687687}} .flow2-trace-row.failure em{{background:#fde3e3;color:#a52d2d}}
      .flow2-trace-row.failure{{background:#fff8f8}} .flow2-duration{{grid-area:duration;text-align:right;color:#6e7c8e;font-family:Consolas,monospace}}
      .flow2-reason{{grid-area:reason;display:grid;gap:3px;min-height:38px;padding:6px 7px;border-left:3px solid #4c7fba;border-radius:6px;background:#eef5fd;color:#355b87;line-height:1.35}}
      .flow2-reason b{{font-size:9px}} .flow2-reason span{{font-size:8px;color:#60748d}}
      .flow2-return{{border-left-color:#2f9660;background:#edf9f2;color:#17643b}} .flow2-feedback,.flow2-rework{{border-left-color:#b7791f;background:#fff8e8;color:#8a540c}}
      .flow2-failure{{border-left-color:#c84646;background:#fff0f0;color:#982d2d}} .flow2-inferred{{border-left-color:#8b67b1;background:#f7f2fb;color:#654186}}
      .flow2-failure span{{color:#a84a4a}} .flow2-feedback span,.flow2-rework span{{color:#8d6a32}} .flow2-inferred span{{color:#766383}}
      .flow2-trace-empty{{padding:18px;text-align:center;color:#8996a7;font-size:10px}}
      .flow2-preparation{{position:relative;width:280px;min-width:280px;height:{MANUAL_EVENT_CARD_HEIGHT}px;box-sizing:border-box;padding:10px;border:1px solid #9db7d5;border-radius:10px;background:#f4f8fd;box-shadow:0 3px 9px rgba(30,59,96,.06);color:#1c4f82}}
      .flow2-preparation:after{{content:'→';position:absolute;right:-22px;top:46%;color:#4b75a9;font-size:19px;font-weight:800}}
      .flow2-preparation-head{{display:grid;grid-template-columns:32px 1fr auto;gap:8px;align-items:center}}
      .flow2-preparation-icon{{display:grid;place-items:center;width:30px;height:30px;border-radius:9px;background:#2f75b5;color:#fff;font-size:13px;font-weight:800}}
      .flow2-preparation-head strong{{display:block;font-size:12px}} .flow2-preparation-head small{{display:block;margin-top:2px;color:#71869d;font-size:8px}}
      .flow2-preparation-head em{{font-style:normal;border-radius:8px;padding:3px 6px;background:#dcecff;color:#175b9d;font-size:9px;white-space:nowrap}}
      .flow2-preparation-progress{{margin-top:7px;padding:5px 7px;border-radius:7px;background:rgba(255,255,255,.72);font-size:9px;font-weight:700}}
      .flow2-preparation-current{{display:grid;gap:3px;margin-top:8px;padding:8px;border-left:3px solid #4c7fba;border-radius:6px;background:#eef5fd}}
      .flow2-preparation-current b{{font-size:9px}} .flow2-preparation-current span{{color:#60748d;font-size:8px}}
      .flow2-preparation ol{{display:grid;gap:3px;margin:8px 0 0;padding:0;list-style:none}}
      .flow2-preparation li{{display:grid;grid-template-columns:19px 1fr 30px;gap:6px;align-items:center;min-height:19px;padding:2px 6px;border-radius:6px;background:rgba(255,255,255,.72);font-size:9px;color:#98a3b1}}
      .flow2-preparation li span{{display:grid;place-items:center;width:16px;height:16px;border-radius:50%;background:#dceaff;color:#285f99;font:700 8px Consolas,monospace}}
      .flow2-preparation li b{{font-weight:600}} .flow2-preparation li em{{font-style:normal;text-align:right;font-size:8px}}
      .flow2-preparation li.active{{color:#175b9d;background:#e8f3ff}} .flow2-preparation li.active span{{background:#2f75b5;color:#fff}}
      .flow2-preparation li.success{{color:#247147;background:#edf9f2}} .flow2-preparation li.success span{{background:#2f9660;color:#fff}}
      .flow2-preparation li.failure{{color:#a52d2d;background:#fff0f0}} .flow2-preparation li.failure span{{background:#c84646;color:#fff}}
      .flow2-preparation-step.active{{animation:flow2-preparation-pulse 1.5s ease-in-out infinite}}
      .flow2-preparation.completed{{border-color:#2f9660;background:#edf9f2;color:#17643b;box-shadow:0 4px 12px rgba(47,150,96,.12)}}
      .flow2-preparation.completed .flow2-preparation-icon{{background:#2f9660}} .flow2-preparation.completed .flow2-preparation-head em{{background:#d9f1e3;color:#247147}}
      .flow2-preparation.completed li span{{background:#d9f1e3;color:#247147}}
      .flow2-preparation.failed{{border-color:#c84646;background:#fff0f0;color:#982d2d;animation:none}} .flow2-preparation.failed .flow2-preparation-icon{{background:#c84646}} .flow2-preparation.failed .flow2-preparation-head em{{background:#fde3e3;color:#a52d2d}}
      .flow2-preparation.waiting{{border-color:#d8e0e9;background:#f7f8fa;color:#69798d;box-shadow:none}}
      .flow2-preparation.waiting .flow2-preparation-icon{{background:#9aa8b7}} .flow2-preparation.waiting .flow2-preparation-head em{{background:#e9edf1;color:#69798d}}
      .flow2-run-summary{{position:relative;display:grid;grid-template-columns:34px 1fr;grid-template-areas:'icon title' 'icon case' 'stats stats';gap:4px 9px;width:280px;min-width:280px;height:{MANUAL_EVENT_CARD_HEIGHT}px;box-sizing:border-box;padding:12px;border:2px solid #7da8d1;border-radius:12px;background:#edf6ff;color:#174f85;box-shadow:0 6px 16px rgba(23,79,133,.15)}}
      .flow2-run-summary .flow2-summary-icon{{grid-area:icon;display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#2f75b5;color:#fff;font-size:16px;font-weight:800}}
      .flow2-run-summary strong{{grid-area:title;font-size:13px}} .flow2-run-summary small{{grid-area:case;color:#58728f;font-size:9px}}
      .flow2-run-summary dl{{grid-area:stats;display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin:10px 0 0}}
      .flow2-run-summary dl div{{padding:6px 4px;border-radius:7px;background:rgba(255,255,255,.66);text-align:center}} .flow2-run-summary dt{{font-size:8px;color:#71859c}} .flow2-run-summary dd{{margin:2px 0 0;font-size:10px;font-weight:700}}
      .flow2-run-summary.completed{{border-color:#2f9660;background:#eaf8ef;color:#17643b}} .flow2-run-summary.completed .flow2-summary-icon{{background:#2f9660}}
      .flow2-run-summary.failed{{border-color:#c84646;background:#fff0f0;color:#982d2d}} .flow2-run-summary.failed .flow2-summary-icon{{background:#c84646}}
      .flow2-run-summary.waiting,.flow2-run-summary.recorded{{border-color:#aeb9c5;background:#f1f3f5;color:#5c6978;box-shadow:none}} .flow2-run-summary.waiting .flow2-summary-icon,.flow2-run-summary.recorded .flow2-summary-icon{{background:#7f8a96}}
      @keyframes flow2-preparation-pulse{{50%{{transform:translateY(-2px);box-shadow:0 0 0 4px rgba(47,117,181,.10),0 7px 16px rgba(35,91,148,.18)}}}}
    </style>
    <div class="flow2-wrap">
      <div class="flow2-trace">
        <div class="flow2-trace-head"><span>{'실시간 실행 이벤트(Agent 호출)' if running else '최근 수행 이벤트(Agent 호출)'} · 왼쪽에서 오른쪽 시간순</span><span>Trace · {trace_id} · Agent 호출 {len(events)}건</span></div>
        <div class="flow2-legend"><span>분석·조회·평가</span><span class="return">결과 반환</span><span class="feedback">재검토·보완</span><span class="failure">호출 실패</span><span class="inferred">Trace 사유 미기록·추정</span></div>
        <div class="flow2-trace-list"><div class="flow2-trace-track">{preparation_cards}{trace_history}{summary_card}</div></div>
      </div>
      <details class="flow2-trace flow2-raw-trace">
        <summary class="flow2-raw-summary"><span>{'실시간 실행 이벤트(원본 로그)' if running else '최근 수행 이벤트(원본 로그)'} · 왼쪽에서 오른쪽 기록순</span><span>Trace · {trace_id} · 원본 로그 {raw_event_count}건 · 전체 표시</span></summary>
        <div class="flow2-raw-content">
          <div class="flow2-raw-guide">Trace에 저장된 started·success·failure 로그를 병합하거나 상태를 보정하지 않고 그대로 표시합니다.</div>
          <div class="flow2-trace-list"><div class="flow2-trace-track" data-event-count="{raw_event_count}">{raw_trace_history}</div></div>
        </div>
      </details>
    </div>
    """)


def _render_agent_pipeline_comparison(
    snapshot: dict,
    running: bool,
    preparation: dict | None = None,
):
    _render_agent_pipeline(snapshot, running)
    _render_agent_pipeline_v2(snapshot, running, preparation)


@st.fragment(run_every="2s")
def _live_testcase_pipeline():
    job_id = st.session_state.get("goal_testcase_job_id")
    started_at = st.session_state.get("goal_testcase_started_at", "")
    if not job_id:
        return
    job = background_job_snapshot(job_id)
    if not job:
        st.session_state.pop("goal_testcase_job_id", None)
        st.session_state.goal_testcase_result = {
            "case": {"case_id": st.session_state.get("goal_testcase_running_case_id", "-")},
            "mode": "voc",
            "execution": {"result": {"ok": False, "error": "백그라운드 작업 상태를 찾을 수 없습니다."}},
        }
        st.rerun()
    trace_id = st.session_state.get("goal_testcase_trace_id", "")
    trace = pipeline_trace_events(started_at, trace_id)
    if trace.get("trace_id") and not trace_id:
        st.session_state.goal_testcase_trace_id = trace["trace_id"]
    preparation = job.get("progress", {}).get("preparation")
    _render_agent_pipeline_comparison(
        trace,
        running=job.get("status") == "RUNNING",
        preparation=preparation,
    )
    if job.get("done"):
        if job.get("status") == "COMPLETED":
            completed = job.get("result") or {}
            st.session_state.goal_testcase_result = completed["testcase_result"]
            st.session_state.goal_testcase_agent_snapshot = completed["agent_snapshot"]
        else:
            st.session_state.goal_testcase_result = {
                "case": {"case_id": st.session_state.get("goal_testcase_running_case_id", "-")},
                "mode": "voc",
                "execution": {"result": {"ok": False, "error": job.get("error", "백그라운드 실행 실패")}},
            }
        st.session_state.goal_testcase_preparation = preparation
        st.session_state.goal_testcase_completed_at = datetime.now().astimezone().isoformat()
        st.session_state.pop("goal_testcase_job_id", None)
        discard_background_job(job_id)
        _load_goal_monitor_snapshot.clear()
        st.rerun()


@st.fragment(run_every="2s")
def _live_manual_judge():
    job_id = st.session_state.get("goal_judge_job_id")
    if not job_id:
        return
    job = background_job_snapshot(job_id)
    if not job:
        st.session_state.pop("goal_judge_job_id", None)
        st.session_state.goal_judge_error = "백그라운드 Judge 작업 상태를 찾을 수 없습니다."
        st.rerun()
    if job.get("status") == "RUNNING":
        st.info("선택한 독립 LLM이 저장된 Pipeline 개선안을 평가하고 있습니다.", icon=":material/hourglass_top:")
        return
    if job.get("status") == "COMPLETED":
        reevaluated = job.get("result") or {}
        testcase_result = deepcopy(st.session_state.get("goal_testcase_result") or {})
        testcase_result["judge_result"] = reevaluated.get("judge_result", {})
        testcase_result["evidence_status"] = next(
            (
                item.get("status", testcase_result.get("evidence_status", "-"))
                for item in reevaluated.get("summary", {}).get("case_results", [])
                if item.get("case_id") == reevaluated.get("case_id")
            ),
            testcase_result.get("evidence_status", "-"),
        )
        st.session_state.goal_testcase_result = testcase_result
        st.session_state.pop("goal_judge_error", None)
    else:
        st.session_state.goal_judge_error = job.get("error", "독립 LLM 평가 실패")
    st.session_state.pop("goal_judge_job_id", None)
    st.session_state.pop("goal_judge_running_case_id", None)
    discard_background_job(job_id)
    _load_voc_history_rows.clear()
    st.rerun()


@st.cache_data(ttl=5, max_entries=1, show_spinner=False)
def _load_goal_monitor_snapshot():
    return agent_status_snapshot(), a2a_trace_snapshot()


@st.cache_data(ttl=5, max_entries=1, show_spinner=False)
def _load_agent_management_snapshot():
    return agent_status_snapshot()


def _title(title, description):
    st.markdown(f"## {title}")
    st.caption(description)


def _show_command_result(*, show_success: bool = True):
    result = st.session_state.get("voc_command_result")
    if not result:
        return
    if result.get("ok"):
        if not show_success:
            st.session_state.pop("voc_command_result", None)
            return
        st.success(f"실행 성공 · {result.get('duration_seconds', 0)}초")
    else:
        st.error(f"실행 실패 · 종료 코드 {result.get('return_code')}")
    st.code(result.get("output", "출력 없음"), language="text")


def _run_and_store(callback, *args):
    with st.spinner("VOC 품질진단 작업을 수행하고 있습니다..."):
        st.session_state.voc_command_result = callback(*args)


def _agent_control_progress_message(action: str, agent_name: str | None = None) -> str:
    action_labels = {
        "start": "기동",
        "restart": "재기동",
        "stop": "중지",
    }
    if action not in action_labels:
        raise ValueError(f"허용되지 않은 Agent 제어 작업: {action}")
    target = f"{agent_name} Agent" if agent_name else "Interpreter 등 6개 Agent"
    return f"{target} 프로세스를 {action_labels[action]}하고 있습니다..."


def _run_agent_control_and_refresh(
    action: str,
    agent_name: str | None = None,
    display_name: str | None = None,
):
    try:
        with st.spinner(_agent_control_progress_message(action, display_name or agent_name)):
            result = run_agent_action(action, agent_name)
    except Exception as exc:
        result = {
            "ok": False,
            "return_code": -1,
            "output": f"{type(exc).__name__}: {exc}",
        }
    st.session_state["voc_command_result"] = result
    _load_agent_management_snapshot.clear()
    _load_goal_monitor_snapshot.clear()
    st.rerun()


@st.cache_data(ttl=5, max_entries=1, show_spinner=False)
def _load_voc_dashboard_snapshot():
    return {
        "runtime": runtime_health(),
        "agents": agent_status_snapshot(),
        "testcases": test_case_summary(),
        "runs": list_voc_run_history(),
        "defects": list_voc_defects(),
        "a2a": a2a_trace_snapshot(),
    }


def _dashboard_timestamp(value: str) -> str:
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _dashboard_date_range(value, today: date) -> tuple[date, date]:
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return value[0], value[1]
    if isinstance(value, date):
        return value, value
    return today - timedelta(days=6), today


def _dashboard_in_period(value: str, start_date: date, end_date: date) -> bool:
    try:
        observed = datetime.fromisoformat(value).date()
    except (TypeError, ValueError):
        return False
    return start_date <= observed <= end_date


def _dashboard_status_card(icon: str, label: str, value: str, detail: str, tone: str) -> str:
    return (
        f"<article class='vqd-status-card {tone}'>"
        f"<span class='vqd-status-icon'>{_dashboard_svg_icon(icon)}</span>"
        f"<span class='vqd-status-label'>{escape(label)}</span>"
        f"<strong>{escape(value)}</strong>"
        f"<small>{escape(detail)}</small>"
        "</article>"
    )


def _dashboard_a2a_status_panel(a2a: dict) -> str:
    definitions = {
        "PASS": "최근 완전 Trace에서 필수 Agent 연결이 모두 성공하고 실패 이벤트가 없습니다.",
        "FAIL": "최근 Trace에 Agent 간 호출 또는 데이터 전달 실패가 기록됐습니다.",
        "NOT_VERIFIED": "최근 확인 구간에 전체 필수 연결을 통과한 완전 Trace가 없습니다.",
    }
    decision = str(a2a.get("decision") or "NOT_VERIFIED").upper()
    if decision not in definitions:
        decision = "NOT_VERIFIED"
    tone = {"PASS": "pass", "FAIL": "fail", "NOT_VERIFIED": "not-verified"}[decision]
    options = "".join(
        (
            f"<span class='vqd-connection-option {'active ' + tone if status == decision else 'inactive'}' "
            f"aria-current='{'true' if status == decision else 'false'}' "
            f"title='{escape(description, quote=True)}'>{status}</span>"
        )
        for status, description in definitions.items()
    )
    reason = str(a2a.get("reason") or definitions[decision])
    recent_minutes = int(a2a.get("recent_minutes") or 30)
    return (
        f"<section class='vqd-connection-panel {tone}'>"
        f"<span class='vqd-connection-icon'>{_dashboard_svg_icon('trace')}</span>"
        "<div class='vqd-connection-heading'><b>최근 연결 판정</b><small>A2A Trace</small></div>"
        f"<div class='vqd-connection-options' role='list' aria-label='연결 판정 상태'>{options}</div>"
        f"<p>{escape(reason)} <small>· 최근 {recent_minutes}분 기준</small></p>"
        "</section>"
    )


def _dashboard_agent_cards(agents: dict) -> str:
    cards = []
    for item in agents.get("agents", []):
        name = str(item.get("name") or "Agent")
        role = next((role for agent, role, _port in AGENT_PIPELINE if agent == name), "역할 정보 없음")
        healthy = bool(item.get("healthy"))
        status = "정상" if healthy else str(item.get("status") or "STOPPED")
        cards.append(
            f"<article class='vqd-agent-card {'good' if healthy else 'bad'}'>"
            f"<span class='vqd-agent-icon'>{_dashboard_agent_svg_icon(name)}</span>"
            f"<div><b>{escape(name)}</b><small>{escape(role)}</small></div>"
            f"<span class='vqd-agent-state'>{escape(status)}</span>"
            f"<em>:{int(item.get('port') or 0)} · PID {escape(str(item.get('pid') or '-'))}</em>"
            "</article>"
        )
    return f"<div class='vqd-agent-grid'>{''.join(cards)}</div>"


def _dashboard_agent_svg_icon(name: str) -> str:
    paths = {
        "Interpreter": "<path d='M4 5h16v11H8l-4 4z'/><path d='M8 9h8m-8 3h5'/>",
        "Retriever": "<circle cx='10' cy='10' r='6'/><path d='m15 15 5 5'/>",
        "Summarizer": "<path d='M6 3h9l4 4v14H6z'/><path d='M15 3v5h5M9 12h7m-7 4h7'/>",
        "Evaluator": "<path d='M5 4h14v16H5z'/><path d='m8 10 2 2 5-5m-7 9h8'/>",
        "Critic": "<path d='M12 3 4 6v6c0 5 3.4 8.3 8 10 4.6-1.7 8-5 8-10V6z'/><path d='M12 8v5m0 3h.01'/>",
        "Improver": "<path d='m4 17 5-5 4 3 7-8'/><path d='M15 7h5v5'/>",
    }
    path = paths.get(name, "<circle cx='12' cy='12' r='8'/><path d='M8 12h8'/>")
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + path
        + "</svg>"
    )


def _agent_management_card_header(agent: dict) -> str:
    name = str(agent.get("name") or "Agent")
    role = next((role for agent_name, role, _port in AGENT_PIPELINE if agent_name == name), "역할 정보 없음")
    state_class = "good" if agent.get("healthy") else "bad"
    return (
        f"<div class='vqa-agent-head {state_class}'>"
        f"<span class='vqa-agent-icon'>{_dashboard_agent_svg_icon(name)}</span>"
        f"<span><b>{escape(name)}</b><small>{escape(role)}</small></span>"
        "</div>"
    )


def _build_voc_run_status_chart(runs: list[dict]):
    status_order = list(VOC_RUN_STATUS_COLORS)
    rows = [
        {
            "Run": _dashboard_timestamp(item.get("started_at", "")),
            "판정": status,
            "Case 수": int(item.get("counts", {}).get(status, 0)),
        }
        for item in reversed(runs[:12])
        for status in status_order
    ]
    frame = pd.DataFrame(rows)
    return (
        alt.Chart(frame)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("Run:N", title=None, sort=None, axis=alt.Axis(labelAngle=-35)),
            y=alt.Y("sum(Case 수):Q", title="Case 수", scale=alt.Scale(zero=True)),
            color=alt.Color(
                "판정:N",
                title=None,
                scale=alt.Scale(domain=status_order, range=list(VOC_RUN_STATUS_COLORS.values())),
                legend=alt.Legend(
                    orient="bottom",
                    direction="horizontal",
                    columns=len(status_order),
                    gridAlign="all",
                    columnPadding=18,
                    labelLimit=110,
                ),
            ),
            order=alt.Order("판정:N", sort="ascending"),
            tooltip=["Run:N", "판정:N", alt.Tooltip("Case 수:Q", format=",d")],
        )
        .properties(height=270)
    )


def _build_voc_run_history_chart(runs: list[dict]):
    rows = []
    for item in reversed(runs[:12]):
        counts = item.get("counts", {})
        total = max(sum(int(counts.get(status, 0)) for status in VOC_RUN_STATUS_COLORS), 1)
        values = {
            "PASS율": int(counts.get("PASS", 0)) / total * 100,
            "검토율": (int(counts.get("REVIEW_REQUIRED", 0)) + int(counts.get("NOT_RUN", 0))) / total * 100,
            "실패·오류율": (int(counts.get("FAIL", 0)) + int(counts.get("ERROR", 0))) / total * 100,
        }
        for metric, value in values.items():
            rows.append({
                "수행 시각": _dashboard_timestamp(item.get("started_at", "")),
                "지표": metric,
                "비율": round(value, 1),
                "Run ID": item.get("run_id", "-"),
            })
    frame = pd.DataFrame(rows)
    return (
        alt.Chart(frame)
        .mark_line(interpolate="monotone", point=alt.OverlayMarkDef(size=65), strokeWidth=3)
        .encode(
            x=alt.X("수행 시각:N", title=None, sort=None, axis=alt.Axis(labelAngle=-35)),
            y=alt.Y("비율:Q", title="비율 (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color(
                "지표:N",
                title=None,
                scale=alt.Scale(domain=list(VOC_HISTORY_COLORS), range=list(VOC_HISTORY_COLORS.values())),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["수행 시각:N", "Run ID:N", "지표:N", alt.Tooltip("비율:Q", format=".1f")],
        )
        .properties(height=245)
    )


def _dashboard_svg_icon(name: str) -> str:
    paths = {
        "runtime": "<path d='M4 5h16v11H4z'/><path d='M8 20h8m-4-4v4'/>",
        "agents": "<circle cx='8' cy='8' r='3'/><circle cx='17' cy='9' r='2.5'/><path d='M3 20c0-4 2-6 5-6s5 2 5 6m1-5c3 0 5 2 5 5'/>",
        "quality": "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 6-7'/>",
        "judge": "<path d='M12 3v18M6 6h12M4 9l-2 5h8L8 9m8 0-2 5h8l-2-5'/>",
        "defect": "<path d='M12 3 2.8 20h18.4L12 3Z'/><path d='M12 9v5m0 3h.01'/>",
        "trace": "<circle cx='6' cy='6' r='2'/><circle cx='18' cy='18' r='2'/><path d='M8 6h4a4 4 0 0 1 4 4v6M6 8v8a2 2 0 0 0 2 2h8'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + paths[name]
        + "</svg>"
    )


def _render_voc_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        .vqd-status-row{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin:2px 0 10px;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif}
        .vqd-status-card{height:96px;border:1px solid #c8d9ee;border-top:4px solid #7b8797;border-radius:8px;background:linear-gradient(145deg,#fff,#f8fbff);display:grid;grid-template-columns:38px 1fr;grid-template-rows:auto auto 1fr;column-gap:10px;padding:10px 12px;box-sizing:border-box;box-shadow:0 3px 10px rgba(22,78,128,.05);min-width:0}
        .vqd-status-icon{grid-row:1/4;width:36px;align-self:center;color:#7b8797}.vqd-status-icon svg{width:100%;height:auto}.vqd-status-label{font-size:11px;font-weight:700;color:#40536d}.vqd-status-card strong{font-size:21px;line-height:1.15;color:#073b72;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.vqd-status-card small{font-size:9px;color:#728095;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;align-self:end}
        .vqd-status-card.good{border-top-color:#299049}.vqd-status-card.good .vqd-status-icon,.vqd-status-card.good strong{color:#299049}
        .vqd-status-card.warn{border-top-color:#b36a08}.vqd-status-card.warn .vqd-status-icon,.vqd-status-card.warn strong{color:#b36a08}
        .vqd-status-card.bad{border-top-color:#d83f36}.vqd-status-card.bad .vqd-status-icon,.vqd-status-card.bad strong{color:#d83f36}
        .vqd-connection-panel{display:grid;grid-template-columns:38px 135px auto 1fr;align-items:center;gap:12px;min-height:64px;margin:0 0 12px;padding:9px 12px;border:1px solid #c8d9ee;border-left:4px solid #7b8797;border-radius:8px;background:linear-gradient(90deg,#f8fbff,#fff);box-sizing:border-box;font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;box-shadow:0 3px 10px rgba(22,78,128,.04)}
        .vqd-connection-panel.pass{border-left-color:#299049}.vqd-connection-panel.fail{border-left-color:#d83f36}.vqd-connection-panel.not-verified{border-left-color:#b36a08}
        .vqd-connection-icon{width:34px;color:#7b8797;display:flex}.vqd-connection-panel.pass .vqd-connection-icon{color:#299049}.vqd-connection-panel.fail .vqd-connection-icon{color:#d83f36}.vqd-connection-panel.not-verified .vqd-connection-icon{color:#b36a08}.vqd-connection-icon svg{width:100%;height:auto}
        .vqd-connection-heading b{display:block;font-size:12px;color:#173f68}.vqd-connection-heading small{display:block;font-size:9px;color:#718096;margin-top:2px}
        .vqd-connection-options{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.vqd-connection-option{display:inline-flex;align-items:center;justify-content:center;height:28px;padding:0 10px;border-radius:6px;font-size:10px;font-weight:800;box-sizing:border-box}
        .vqd-connection-option.inactive{color:#9aa5b1;background:#f1f3f5;border:1px solid #d8dee5;filter:grayscale(1)}.vqd-connection-option.active.pass{color:#176b35;background:#eaf7ef;border:1px solid #8dcba2}.vqd-connection-option.active.fail{color:#b42318;background:#fff0ee;border:1px solid #efaaa4}.vqd-connection-option.active.not-verified{color:#92550a;background:#fff7e6;border:1px solid #e8c47b}
        .vqd-connection-panel p{margin:0;font-size:11px;line-height:1.45;color:#40536d}.vqd-connection-panel p small{color:#718096;white-space:nowrap}
        .vqd-agent-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.vqd-agent-card{display:grid;grid-template-columns:34px 1fr auto;grid-template-rows:auto auto;gap:2px 9px;align-items:center;min-height:72px;padding:9px 10px;border:1px solid #d4e1ef;border-left:4px solid #7b8797;border-radius:7px;background:linear-gradient(145deg,#fff,#f8fbff);box-sizing:border-box}.vqd-agent-card.good{border-left-color:#299049}.vqd-agent-card.bad{border-left-color:#d83f36}.vqd-agent-icon{grid-row:1/3;width:31px;color:#7b8797;display:flex}.vqd-agent-card.good .vqd-agent-icon{color:#299049}.vqd-agent-card.bad .vqd-agent-icon{color:#d83f36}.vqd-agent-icon svg{width:100%;height:auto}.vqd-agent-card b{display:block;font-size:11px;color:#173f68}.vqd-agent-card small{display:block;font-size:9px;color:#718096}.vqd-agent-state{font-size:10px;font-weight:800;color:#7b8797}.vqd-agent-card.good .vqd-agent-state{color:#299049}.vqd-agent-card.bad .vqd-agent-state{color:#d83f36}.vqd-agent-card em{grid-column:2/4;font-size:9px;font-style:normal;color:#8795a8}
        div[data-testid="stForm"]{margin-bottom:0!important}div[data-testid="stForm"] [data-testid="stWidgetLabel"] p{font-size:10px!important;color:#40536d!important}div[data-testid="stForm"] [data-testid="stVerticalBlock"]{gap:.15rem!important}
        div[data-testid="stHeadingWithActionElements"] h1{font-size:29px!important;color:#0c3768!important;letter-spacing:-1px!important}div[data-testid="stHeadingWithActionElements"] h3{font-size:17px!important;color:#173f68!important}
        @media(max-width:1100px){.vqd-status-row{grid-template-columns:repeat(3,1fr)}.vqd-connection-panel{grid-template-columns:38px 130px 1fr}.vqd-connection-panel p{grid-column:2/4}}
        @media(max-width:720px){.vqd-status-row{grid-template-columns:repeat(2,1fr)}.vqd-connection-panel{grid-template-columns:34px 1fr}.vqd-connection-options,.vqd-connection-panel p{grid-column:1/3}.vqd-connection-panel p small{white-space:normal}.vqd-agent-grid{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard():
    _render_voc_dashboard_styles()
    today = date.today()
    if not st.session_state.get("voc_dashboard_header_rendered"):
        with st.container(border=True, key="voc_dashboard_inline_filter_panel"):
            with st.form("voc_dashboard_inline_filters", border=False):
                filter_columns = st.columns([2.2, 0.9, 0.95], vertical_alignment="bottom")
                with filter_columns[0]:
                    inline_range = st.date_input(
                        "기간",
                        value=st.session_state.get(
                            "voc_dashboard_filter_range",
                            (today - timedelta(days=6), today),
                        ),
                        max_value=today,
                        key="voc_dashboard_filter_range",
                    )
                with filter_columns[1]:
                    inline_submitted = st.form_submit_button(
                        "조회",
                        icon=":material/search:",
                        type="primary",
                        width="stretch",
                    )
                with filter_columns[2]:
                    inline_refresh_requested = st.form_submit_button(
                        "새로고침",
                        icon=":material/refresh:",
                        width="stretch",
                    )
            st.session_state["voc_dashboard_filter_submitted"] = bool(inline_submitted)
            st.session_state["voc_dashboard_filter_refresh_requested"] = bool(inline_refresh_requested)
    selected_range = st.session_state.get(
        "voc_dashboard_filter_range",
        (today - timedelta(days=6), today),
    )
    submitted = bool(st.session_state.get("voc_dashboard_filter_submitted", False))
    refresh_requested = bool(st.session_state.get("voc_dashboard_filter_refresh_requested", False))

    if submitted or refresh_requested:
        _load_voc_dashboard_snapshot.clear()

    start_date, end_date = _dashboard_date_range(selected_range, today)
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    snapshot = _load_voc_dashboard_snapshot()
    runtime = snapshot["runtime"]
    agents = snapshot["agents"]
    runs = [
        item for item in snapshot["runs"]
        if _dashboard_in_period(item.get("started_at", ""), start_date, end_date)
    ]
    defects = [
        item for item in snapshot["defects"]
        if _dashboard_in_period(item.get("created_at", ""), start_date, end_date)
    ]
    a2a = snapshot["a2a"]
    latest = runs[0] if runs else {}
    latest_counts = latest.get("counts", {})
    latest_judge_counts = latest.get("judge_counts", {})
    open_defects = [item for item in defects if item.get("status") != "CLOSED"]
    important_defects = [
        item for item in open_defects if item.get("severity") in {"HIGH", "CRITICAL"}
    ]

    runtime_ok = runtime.get("ok") and runtime.get("env_configured")
    quality_failures = int(latest_counts.get("FAIL", 0)) + int(latest_counts.get("ERROR", 0))
    quality_reviews = int(latest_counts.get("REVIEW_REQUIRED", 0)) + int(latest_counts.get("NOT_RUN", 0))
    judge_failures = int(latest_judge_counts.get("FAIL", 0)) + int(latest_judge_counts.get("ERROR", 0))
    judge_reviews = int(latest_judge_counts.get("REVIEW_REQUIRED", 0)) + int(latest_judge_counts.get("NOT_RUN", 0))
    cards = [
        _dashboard_status_card(
            "runtime", "실행 환경", "정상" if runtime_ok else "확인 필요",
            "필수 파일 · 환경 설정", "good" if runtime_ok else "bad",
        ),
        _dashboard_status_card(
            "agents", "Agent 가동", f"{agents.get('running', 0)} / {agents.get('total', 6)}",
            "전체 정상" if agents.get("all_running") else "중지 Agent 있음",
            "good" if agents.get("all_running") else "bad" if not agents.get("running") else "warn",
        ),
        _dashboard_status_card(
            "quality", "최신 Run 품질", "이력 없음" if not latest else f"PASS {latest_counts.get('PASS', 0)}",
            f"검토 {quality_reviews} · 실패/오류 {quality_failures}" if latest else "선택 기간 기준",
            "neutral" if not latest else "bad" if quality_failures else "warn" if quality_reviews else "good",
        ),
        _dashboard_status_card(
            "judge", "독립 Judge", "미사용" if not latest or not latest.get("judge_enabled") else f"PASS {latest_judge_counts.get('PASS', 0)}",
            f"검토 {judge_reviews} · 실패/오류 {judge_failures}" if latest.get("judge_enabled") else "최신 Run 기준",
            "neutral" if not latest or not latest.get("judge_enabled") else "bad" if judge_failures else "warn" if judge_reviews else "good",
        ),
        _dashboard_status_card(
            "defect", "기간 미종결 결함", str(len(open_defects)),
            f"High/Critical {len(important_defects)}건",
            "bad" if important_defects else "warn" if open_defects else "good",
        ),
    ]
    st.markdown(f"<div class='vqd-status-row'>{''.join(cards)}</div>", unsafe_allow_html=True)
    st.markdown(_dashboard_a2a_status_panel(a2a), unsafe_allow_html=True)

    overview_columns = st.columns(2, gap="medium")
    with overview_columns[0].container(border=True, height=VOC_OVERVIEW_PANEL_HEIGHT):
        chart_heading = st.columns([1.05, 0.95], vertical_alignment="center")
        with chart_heading[0]:
            st.markdown("#### 기간 Run 판정 추이")
        with chart_heading[1]:
            if runs:
                st.caption(
                    f"{start_date.isoformat()} ~ {end_date.isoformat()} · Run {len(runs)}건",
                    text_alignment="right",
                )
        if runs:
            st.altair_chart(_build_voc_run_status_chart(runs), theme=None)
        else:
            st.info("선택 기간에 저장된 Run이 없습니다.")

    with overview_columns[1].container(border=True, height=VOC_OVERVIEW_PANEL_HEIGHT):
        st.markdown("#### Agent 운영 상태")
        if not agents.get("agents"):
            st.info("Agent 상태를 조회할 수 없습니다.")
        else:
            st.markdown(_dashboard_agent_cards(agents), unsafe_allow_html=True)

    detail_columns = st.columns(2, gap="medium")
    with detail_columns[0].container(border=True):
        history_heading = st.columns([1.05, 0.95], vertical_alignment="center")
        with history_heading[0]:
            st.markdown("#### 기간 수행 이력")
        with history_heading[1]:
            if runs:
                st.caption(
                    "Run별 PASS·검토·실패/오류 비율 · 최근 12건",
                    text_alignment="right",
                )
        if not runs:
            st.info("선택 기간에 수행 이력이 없습니다.")
        else:
            st.altair_chart(_build_voc_run_history_chart(runs), theme=None)

    with detail_columns[1].container(border=True):
        st.markdown("#### 기간 미종결 결함·후보")
        run_lookup = {item.get("run_id"): item for item in snapshot["runs"]}
        defect_rows = pd.DataFrame([
            {
                "제목": item.get("title", "-"),
                "수행": _dashboard_timestamp(
                    run_lookup.get((item.get("related_run_ids") or [None])[0], {}).get("started_at", "")
                ),
                "Run": (item.get("related_run_ids") or ["-"])[0],
                "등록": _dashboard_timestamp(item.get("created_at", "")),
                "심각도": item.get("severity", "-"),
                "상태": _defect_status_label(item.get("status", "")),
            }
            for item in open_defects[:8]
        ])
        if defect_rows.empty:
            st.success("선택 기간에 생성된 미종결 결함이 없습니다.")
        else:
            st.dataframe(defect_rows, hide_index=True, width="stretch")

    st.caption(
        "기간 필터는 Run 시작일과 결함 생성일에 적용되며, 실행 환경·Agent·A2A는 현재 상태를 표시합니다. "
        "최종 품질 승인은 품질 보고서와 최종 인수·시연의 게이트 판정을 함께 확인하세요."
    )


def render_agents():
    health = runtime_health()
    if not health["env_configured"]:
        st.warning("Agent 실행에 필요한 `.env`가 없습니다. 환경 파일을 초기화한 뒤 API 키를 입력하세요.")

    st.markdown(
        """
        <style>
        .vqa-agent-head{display:flex;align-items:center;gap:7px;min-height:39px;margin:-2px 0 5px}
        .vqa-agent-icon{display:flex;flex:0 0 29px;width:29px;color:#7b8797}
        .vqa-agent-head.good .vqa-agent-icon{color:#299049}
        .vqa-agent-head.bad .vqa-agent-icon{color:#d83f36}
        .vqa-agent-icon svg{width:100%;height:auto}
        .vqa-agent-head b{display:block;color:#173f68;font-size:11px;line-height:1.2}
        .vqa-agent-head small{display:block;margin-top:2px;color:#718096;font-size:8px;line-height:1.15}
        div[class*="st-key-stop_agent_"] button{
            background:#d83f36!important;border-color:#d83f36!important;color:#fff!important;
        }
        div[class*="st-key-start_agent_"] button{
            background:#155a96!important;border-color:#155a96!important;color:#fff!important;
        }
        div[class*="st-key-cleanup_agent_"] button{
            background:#b36a08!important;border-color:#b36a08!important;color:#fff!important;
        }
        div[class*="st-key-stop_agent_"] button p,
        div[class*="st-key-start_agent_"] button p,
        div[class*="st-key-cleanup_agent_"] button p{
            color:#fff!important;font-weight:800!important;white-space:nowrap!important;
        }
        div[class*="st-key-agent_control_header_"] [data-testid="column"]:nth-child(2) button{
            min-height:30px!important;padding:4px 8px!important;font-size:12px!important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        confirmed = st.checkbox("Agent 프로세스 상태 변경")
        with st.container(horizontal=True):
            if st.button("전체 시작", disabled=not confirmed, width="stretch", icon=":material/play_arrow:"):
                _run_agent_control_and_refresh("start")
            if st.button("전체 재시작", disabled=not confirmed, width="stretch", icon=":material/restart_alt:"):
                _run_agent_control_and_refresh("restart")
            if st.button("전체 중지", disabled=not confirmed, width="stretch", icon=":material/stop:"):
                _run_agent_control_and_refresh("stop")
    _show_command_result(show_success=False)

    snapshot = _load_agent_management_snapshot()
    stop_impacts = {
        "interpreter": "질문 의도와 검색 조건을 해석할 수 없어 VOC Pipeline을 시작할 수 없습니다.",
        "retriever": "관련 VOC 근거를 검색할 수 없어 요약과 개선안 생성을 진행할 수 없습니다.",
        "summarizer": "요약 후보 생성과 전체 Agent 조정이 중단되어 최종 응답을 만들 수 없습니다.",
        "evaluator": "요약 후보를 비교·선정할 수 없어 최종 요약을 결정할 수 없습니다.",
        "critic": "요약과 개선안의 품질 검토가 누락되어 보완된 결과를 확정할 수 없습니다.",
        "improver": "정책 개선안을 생성·보완할 수 없어 최종 개선안 산출이 실패합니다.",
    }
    agent_columns = st.columns(6, gap="small")
    for index, agent in enumerate(snapshot["agents"]):
        with agent_columns[index].container(border=True):
            with st.container(
                horizontal=True,
                horizontal_alignment="distribute",
                vertical_alignment="center",
                key=f"agent_control_header_{agent['key']}",
            ):
                st.markdown(_agent_management_card_header(agent), unsafe_allow_html=True)
                if agent["status"] == "RUNNING":
                    if st.button(
                        "중지",
                        key=f"stop_agent_{agent['key']}",
                        icon=":material/stop_circle:",
                        width="content",
                    ):
                        _confirm_agent_action(agent, "stop")
                elif agent["status"] in {"STOPPED", "UNKNOWN"}:
                    if st.button(
                        "시작",
                        key=f"start_agent_{agent['key']}",
                        icon=":material/play_circle:",
                        width="content",
                    ):
                        _confirm_agent_action(agent, "start")
                elif agent["status"] == "STARTING/FAILED":
                    if st.button(
                        "정리",
                        key=f"cleanup_agent_{agent['key']}",
                        icon=":material/cleaning_services:",
                        width="content",
                    ):
                        _confirm_agent_action(agent, "stop")
                else:
                    st.button(
                        "제어 불가",
                        key=f"unmanaged_agent_{agent['key']}",
                        disabled=True,
                        width="content",
                    )
            _status_badge(
                agent["status"],
                "PASS" if agent["healthy"] else "FAIL",
                f"TCP {agent['port']} · PID {agent['pid']}",
            )
            st.caption(f"포트 {agent['port']} · PID {agent['pid']}")
            started_at = str(agent.get("started_at") or "").strip()
            if agent["status"] == "RUNNING" and started_at:
                try:
                    started_at = datetime.fromisoformat(started_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
                st.caption(f"기동 시간 · {started_at}")
            elif agent["status"] == "RUNNING":
                st.caption("기동 시간 · 확인 불가")
            else:
                st.caption("기동 시간 · -")
            if agent["status"] == "STOPPED":
                st.markdown(f":red-badge[중지 영향] {stop_impacts[agent['key']]}")

            test_result_key = f"agent_quick_test_result_{agent['key']}"
            if st.button(
                "간편 테스트",
                key=f"quick_test_agent_{agent['key']}",
                icon=":material/network_check:",
                disabled=agent["status"] != "RUNNING",
                width="stretch",
            ):
                with st.spinner(f"{agent['name']} Agent를 실제 호출하고 있습니다..."):
                    st.session_state[test_result_key] = test_agent_rpc(
                        agent["name"],
                        int(agent["port"]),
                        timeout=12.0,
                    )

            with st.container(height=124, border=False):
                test_result = st.session_state.get(test_result_key)
                if not test_result:
                    st.caption("RUNNING 상태에서 간편 테스트로 실제 RPC 응답을 확인할 수 있습니다.")
                elif test_result.get("ok"):
                    st.success(
                        f"{test_result.get('rpc', '-')} 호출 성공 · "
                        f"{test_result.get('duration_seconds', '-')}초"
                    )
                    st.caption(f"IN: {test_result.get('input', '-')}")
                    st.caption(f"OUT: {test_result.get('summary', '-')}")
                else:
                    st.error(
                        f"호출 실패 · {test_result.get('duration_seconds', '-')}초"
                    )
                    st.caption(test_result.get("summary", "-"))


def _status_badge(label: str, decision: str, help_text: str = ""):
    settings = {
        "PASS": ("green", ":material/check_circle:"),
        "FAIL": ("red", ":material/error:"),
        "NOT_VERIFIED": ("orange", ":material/pending:"),
    }
    color, icon = settings.get(decision, ("gray", ":material/help:"))
    st.badge(label, color=color, icon=icon, help=help_text or None)


@st.dialog("Agent 상태 변경 확인")
def _confirm_agent_action(agent: dict, action: str):
    action_label = "시작" if action == "start" else "중지"
    st.markdown(f"**{agent['name']} Agent를 {action_label}하시겠습니까?**")
    st.caption(f"대상: {agent['name']} · TCP {agent['port']} · 현재 상태 {agent['status']}")
    if action == "stop":
        st.warning(
            "이 Agent를 중지하면 해당 Agent를 사용하는 VOC 테스트가 실패할 수 있습니다. "
            "장애 시연 후 다시 시작하세요.",
            icon=":material/warning:",
        )
    else:
        st.info("시작하려면 런타임 `.env`에 필요한 API 키가 설정돼 있어야 합니다.", icon=":material/info:")

    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("취소", key=f"cancel_{action}_{agent['key']}"):
            st.rerun()
        if st.button(
            f"{action_label} 실행",
            key=f"confirm_{action}_{agent['key']}",
            type="primary",
        ):
            _run_agent_control_and_refresh(action, agent["key"], agent["name"])


def _set_goal_testcase_selection(selected_case_id: str):
    previous_case_id = st.session_state.get("goal_testcase_selected_case_id")
    if previous_case_id == selected_case_id:
        return
    st.session_state["goal_testcase_selected_case_id"] = selected_case_id
    st.session_state.pop("goal_testcase_result", None)
    if not st.session_state.get("goal_testcase_job_id"):
        st.session_state.pop("goal_testcase_started_at", None)
        st.session_state.pop("goal_testcase_completed_at", None)
        st.session_state.pop("goal_testcase_agent_snapshot", None)


def _table_selected_row_index(
    table_state: dict | None,
    row_count: int,
) -> int | None:
    table_state = table_state or {}
    selection = table_state.get("selection", {}) if hasattr(table_state, "get") else {}
    selected_rows = selection.get("rows", []) if hasattr(selection, "get") else []
    selected_cells = selection.get("cells", []) if hasattr(selection, "get") else []

    selected_row = None
    if selected_cells and isinstance(selected_cells[-1], (list, tuple)) and selected_cells[-1]:
        selected_row = selected_cells[-1][0]
    elif selected_rows:
        selected_row = selected_rows[0]

    if not isinstance(selected_row, int) or not 0 <= selected_row < row_count:
        return None
    return selected_row


def _promote_table_cell_to_row_selection(
    table_key: str,
    row_count: int,
) -> int | None:
    table_state = st.session_state.get(table_key, {})
    selected_row = _table_selected_row_index(table_state, row_count)
    if selected_row is None:
        return None
    selection = table_state.get("selection", {}) if hasattr(table_state, "get") else {}
    selected_cells = selection.get("cells", []) if hasattr(selection, "get") else []
    if selected_cells:
        st.session_state[table_key] = {
            "selection": {"rows": [selected_row], "columns": [], "cells": []}
        }
    return selected_row


def _remember_goal_testcase_selection(table_key: str, page_case_ids: list[str]):
    selected_row = _promote_table_cell_to_row_selection(
        table_key,
        len(page_case_ids),
    )
    if selected_row is not None:
        selected_case_id = page_case_ids[selected_row]
        previous_case_id = st.session_state.get("goal_testcase_selected_case_id")
        _set_goal_testcase_selection(selected_case_id)
        if previous_case_id and previous_case_id != selected_case_id:
            st.session_state["goal_testcase_selection_changed"] = True


def _remember_catalog_case_selection(table_key: str, case_ids: list[str]):
    selected_row = _promote_table_cell_to_row_selection(
        table_key,
        len(case_ids),
    )
    if selected_row is not None:
        st.session_state["voc_testcase_selected_case_id"] = case_ids[selected_row]


def _render_goal_judge_result(selected_case_id: str):
    test_execution = st.session_state.get("goal_testcase_result")
    executed_case_id = (test_execution or {}).get("case", {}).get("case_id")
    if not test_execution or executed_case_id != selected_case_id:
        return
    judge_result = test_execution.get("judge_result", {})
    if not judge_result or judge_result.get("decision") == "NOT_RUN":
        return

    with st.container(border=True, key="goal_manual_judge_result"):
        st.markdown("#### 독립 LLM 평가/판정 결과")
        st.caption(
            f"{judge_result.get('provider', '-')} · {judge_result.get('model', '-')} · "
            f"Rubric {judge_result.get('rubric_version', '-')}"
        )
        metrics = st.columns(4)
        metrics[0].metric("판정", judge_result.get("decision", "NOT_RUN"))
        metrics[1].metric(
            "총점",
            f"{judge_result['total_score']}점" if judge_result.get("total_score") is not None else "-",
        )
        metrics[2].metric("독립성", judge_result.get("independence_grade", "-"))
        metrics[3].metric(
            "수행 시간",
            f"{float(judge_result.get('duration_seconds') or 0):g}초",
        )

        if judge_result.get("error"):
            st.error(judge_result["error"])
        elif judge_result.get("decision") == "NOT_RUN":
            st.warning(judge_result.get("message", "독립 LLM 평가가 실행되지 않았습니다."))
        elif judge_result.get("independence_hold"):
            st.warning(
                f"점수 기준 판정은 {judge_result.get('rubric_decision')}이지만 "
                f"{judge_result.get('independence_hold_reason')}"
            )

        dimension_rows = []
        for dimension, detail in judge_result.get("dimension_scores", {}).items():
            if isinstance(detail, dict):
                dimension_rows.append(
                    {
                        "평가 차원": dimension,
                        "점수": detail.get("score", detail.get("points", "-")),
                        "판정 근거": detail.get("reason", "-"),
                    }
                )
            else:
                dimension_rows.append({"평가 차원": dimension, "점수": detail, "판정 근거": "-"})
        if dimension_rows:
            st.dataframe(pd.DataFrame(dimension_rows), hide_index=True, width="stretch")

        details = st.columns(3, gap="medium")
        for column, title, values in (
            (details[0], "확인 근거", judge_result.get("evidence", [])),
            (details[1], "잔여 위험", judge_result.get("risks", [])),
            (details[2], "보완 권고", judge_result.get("recommendations", [])),
        ):
            with column.container(border=True, height=145):
                st.markdown(f"**{title}**")
                if values:
                    for value in values:
                        st.write(f"- {value}")
                else:
                    st.caption("표시할 내용 없음")


def _render_goal_testcase_result(selected_case_id: str):
    test_execution = st.session_state.get("goal_testcase_result")
    executed_case_id = (test_execution or {}).get("case", {}).get("case_id")
    if not test_execution or executed_case_id != selected_case_id:
        return

    executed_case = test_execution.get("case", {})
    result_title = (
        executed_case.get("question")
        or executed_case.get("name")
        or executed_case.get("case_id")
        or "-"
    )
    st.markdown(f"#### {result_title}")
    if test_execution.get("run_id"):
        st.caption(
            f"Run ID: {test_execution['run_id']} · 증적 상태: "
            f"{test_execution.get('evidence_status', '-')} · 저장 위치: "
            f"reports/voc_quality_runs/{test_execution['run_id']}"
        )
    if test_execution.get("mode") == "fault":
        execution = test_execution.get("execution", {})
        if execution.get("ok"):
            st.success(f"격리 장애 시험 {test_execution.get('fault_id')} 통과")
        else:
            st.error(f"격리 장애 시험 {test_execution.get('fault_id')} 실패")
        st.code(execution.get("output", "출력 없음"), language="text")
        return

    payload = test_execution.get("execution", {})
    result = payload.get("result", {})
    if result.get("ok"):
        st.success(result.get("message", "VOC 테스트 실행 완료"))
    else:
        st.warning(result.get("message") or result.get("error") or "VOC 테스트 결과가 없습니다.")
    result_columns = st.columns(2, gap="medium")
    with result_columns[0].container(border=True):
        st.markdown("**요약**")
        st.write(result.get("summary", "-") or "-")
    with result_columns[1].container(border=True):
        st.markdown("**정책 개선안**")
        st.write(result.get("policy", "-") or "-")
    with st.expander("판정 근거 및 Agent Trace", icon=":material/account_tree:"):
        intent = _parse_json_mapping(result.get("intent_json"))
        evaluator = _parse_json_mapping(result.get("eval_json"))
        critic = _parse_json_mapping(result.get("summary_critic_json"))
        trace_summary = _parse_pipeline_trace_summary(result.get("trace"))
        trace = test_execution.get("trace") if isinstance(test_execution.get("trace"), dict) else {}
        trace_rows = _pipeline_trace_event_rows(trace)
        trace_values = trace_summary["values"]
        trace_flags = set(trace_summary["flags"])
        trace_id = trace.get("trace_id") or trace_values.get("audit_trace_id") or "-"
        failed_rows = [row for row in trace_rows if row["결과"] == "실패"]
        successful_rows = [row for row in trace_rows if row["결과"] == "성공"]

        st.info(
            "이 정보는 질문 해석, VOC 검색, 후보 평가, Critic 보완 및 Agent 연결 상태를 보여주는 "
            "판정 근거입니다. 다만 이 Trace만으로 최종 PASS를 확정하지 않으며, 독립 LLM Judge·품질 규칙·사람 검토와 함께 판단합니다.",
            icon=":material/fact_check:",
        )
        if not result.get("ok"):
            st.error(
                "판단: 파이프라인이 완료되지 않아 결과 품질을 평가할 수 없습니다. 아래 실패 단계와 오류를 장애 원인 근거로 확인하세요."
            )
        elif failed_rows:
            st.warning(
                f"판단: 결과는 생성됐지만 Agent 연결 실패 {len(failed_rows)}건이 있어 품질 판정을 보류하고 추가 검토해야 합니다."
            )
        elif trace_rows:
            st.success(
                "판단: 질문 해석부터 결과 생성까지의 실행 이력이 확인됩니다. 아래 평가점수와 Critic 보완 내용을 최종 결과의 타당성 검토에 활용할 수 있습니다."
            )
        else:
            st.warning(
                "판단: 요약 Trace만 있어 처리 흐름은 확인할 수 있지만 Agent별 성공·실패 증적은 제한적입니다. 최종 판정에는 저장된 Run 증적을 함께 확인하세요."
            )

        task_labels = {"summary": "VOC 요약", "policy": "정책 개선안", "both": "VOC 요약 + 정책 개선안"}
        winner = trace_values.get("winner")
        numeric_scores = {
            str(key): float(value)
            for key, value in evaluator.items()
            if isinstance(value, (int, float))
        }
        if not winner and numeric_scores:
            winner = max(numeric_scores, key=numeric_scores.get)
        retrieved = trace_values.get("retrieved", "-")
        critic_status = (
            "보완 반영"
            if critic.get("need_refine") and "summary_refined" in trace_flags
            else "보완 요청"
            if critic.get("need_refine")
            else "원안 유지"
            if critic
            else "평가 없음"
        )
        with st.container(horizontal=True):
            st.metric("실행 결과", "완료" if result.get("ok") else "실패", border=True)
            st.metric("검색 VOC", f"{retrieved}건" if str(retrieved).isdigit() else retrieved, border=True)
            st.metric(
                "선택 후보",
                f"{winner} · {numeric_scores[winner]:.1f}점" if winner in numeric_scores else winner or "-",
                border=True,
            )
            st.metric("Critic 검토", critic_status, border=True)

        st.markdown("##### 1. 질문 해석과 검색 범위")
        filters = [str(value) for value in intent.get("filters", []) if str(value).strip()]
        st.write(f"- 수행 목적: **{task_labels.get(intent.get('task'), intent.get('task') or '확인 불가')}**")
        st.write(f"- 검색 키워드: **{', '.join(filters) if filters else '확인 불가'}**")
        st.write(f"- 최대 검색 범위: **{intent.get('max_items', '-')}건**")
        st.caption("질문 의도와 검색 키워드는 최종 답변이 사용자의 VOC와 관련 있는지 판단하는 근거입니다.")

        st.markdown("##### 2. 요약 후보 평가와 선택 근거")
        if numeric_scores:
            score_rows = pd.DataFrame([
                {
                    "후보": candidate,
                    "평가점수": score,
                    "선택 여부": "최종 선택" if candidate == winner else "비선택",
                }
                for candidate, score in sorted(numeric_scores.items(), key=lambda item: item[1], reverse=True)
            ])
            st.table(score_rows)
            st.caption("Evaluator 점수는 후보 간 상대 비교 근거이며, 점수 자체가 최종 품질 PASS를 의미하지는 않습니다.")
        else:
            st.warning("Evaluator 후보 점수가 없어 선택 근거를 확인할 수 없습니다.")

        st.markdown("##### 3. Critic 검토와 반영 결과")
        edits = [str(value) for value in critic.get("edits", []) if str(value).strip()]
        if critic:
            st.write(f"- 보완 필요 판단: **{'예' if critic.get('need_refine') else '아니오'}**")
            st.write(f"- 추가 VOC 표본 권고: **{'예' if critic.get('ask_more_samples') else '아니오'}**")
            st.write(f"- 실제 요약 보완: **{'반영됨' if 'summary_refined' in trace_flags else '반영 기록 없음'}**")
            st.write(f"- 실제 개선안 보완: **{'반영됨' if 'policy_refined' in trace_flags else '반영 기록 없음'}**")
            if edits:
                st.markdown("**주요 보완 의견**")
                for edit in edits:
                    st.write(f"- {edit}")
        else:
            st.warning("Critic 검토 결과가 없어 요약·개선안의 보완 여부를 확인할 수 없습니다.")

        st.markdown("##### 4. Agent 실행 이력")
        st.caption(
            f"Trace ID: {trace_id} · 완료 연결 {len(trace_rows)}건 · 성공 {len(successful_rows)}건 · 실패 {len(failed_rows)}건"
        )
        if trace_rows:
            st.dataframe(
                pd.DataFrame(trace_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "순서": st.column_config.NumberColumn(width="small"),
                    "Agent 연결": st.column_config.TextColumn(width="medium"),
                    "처리 내용": st.column_config.TextColumn(width="medium"),
                    "결과": st.column_config.TextColumn(width="small"),
                    "처리시간(ms)": st.column_config.NumberColumn(format="%.2f", width="small"),
                    "판단 단서": st.column_config.TextColumn(width="large"),
                },
            )
        else:
            completed_steps = {
                "summary_refined": "Critic 의견을 반영해 요약 보완",
                "policy_refined": "Critic 의견을 반영해 개선안 보완",
                "policy_received": "최종 개선안 수신",
            }
            for flag in trace_summary["flags"]:
                st.write(f"- {completed_steps.get(flag, flag)}")
        if result.get("error"):
            st.error(f"실행 오류: {result['error']}")
    st.caption(
        "기존 Reports/VOC와 Run 단위 증적에 함께 저장됩니다. "
        "Trace는 판정 근거이며 최종 판정은 독립 Judge·품질 규칙·사람 검토와 함께 확인합니다."
    )


@st.fragment
def _goal_testcase_selector():
    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        gap="small",
        key="goal_testcase_compact_header",
    ):
        st.markdown("### Test Case 선택 실행")
    cases = load_test_cases().get("cases", [])
    if not cases:
        st.warning("test_cases.json에 실행할 테스트케이스가 없습니다.")
        return

    agent_snapshot = _load_agent_management_snapshot()
    page_size = 4
    total_pages = max(1, (len(cases) + page_size - 1) // page_size)
    page = st.session_state.get("goal_testcase_page", 1)
    start = (page - 1) * page_size
    page_cases = cases[start:start + page_size]
    page_case_ids = [case["case_id"] for case in page_cases]
    remembered_case_id = st.session_state.get("goal_testcase_selected_case_id")
    default_index = page_case_ids.index(remembered_case_id) if remembered_case_id in page_case_ids else 0
    rows = pd.DataFrame([
        {
            "ID": case.get("case_id", "-"),
            "분류": case.get("category", "-"),
            "질문": case.get("question", "-"),
        }
        for case in page_cases
    ])
    table_key = f"goal_testcase_table_{page}"

    table_column, detail_column = st.columns([1.75, 1], gap="medium")
    with table_column:
        selection = st.dataframe(
            rows,
            hide_index=True,
            width="stretch",
            height=245,
            row_height=48,
            key=table_key,
            on_select=partial(_remember_goal_testcase_selection, table_key, page_case_ids),
            selection_mode=["single-row-required", "single-cell"],
            selection_default={"selection": {"rows": [default_index]}},
            column_config={
                "ID": st.column_config.TextColumn("ID", width="small", pinned=True),
                "분류": st.column_config.TextColumn("분류", width="medium"),
                "질문": st.column_config.TextColumn("질문", width="large"),
            },
        )
        with st.container(horizontal_alignment="right"):
            selected_page = st.pagination(
                num_pages=total_pages,
                key="goal_testcase_page",
                persist_state="session",
            )
        if selected_page != page:
            st.rerun(scope="fragment")

    selected_rows = selection.selection.rows
    selected_index = selected_rows[0] if selected_rows else default_index
    selected_index = min(max(selected_index, 0), len(page_cases) - 1)
    selected_case = page_cases[selected_index]
    selected_case_id = selected_case["case_id"]
    _set_goal_testcase_selection(selected_case_id)
    is_fault_case = selected_case.get("category") == "fault_condition"
    test_running = bool(st.session_state.get("goal_testcase_job_id"))

    with detail_column.container(border=True):
        st.markdown(f"**선택: {selected_case.get('case_id')}**")
        st.write(selected_case.get("question", "-"))
        st.caption(
            f"기대 의도: {selected_case.get('expected_intent', '-')}  \n"
            f"기대 작업: {selected_case.get('expected_task', '-')}"
        )
        with st.expander("판정 기준", icon=":material/rule:"):
            st.markdown(
                f"필수 출력: {', '.join(selected_case.get('required_output', [])) or '-'}  \n"
                f"금지 출력: {', '.join(selected_case.get('prohibited_output', [])) or '-'}"
            )
        st.button(
            "Agent Pipeline ??",
            icon=":material/play_arrow:",
            type="primary",
            disabled=test_running or bool(st.session_state.get("goal_judge_job_id")),
            width="stretch",
            key=f"goal_execute_{selected_case_id}",
            on_click=_start_goal_testcase_pipeline,
            args=(selected_case_id,),
        )
        if is_fault_case:
            st.info(
                "이 케이스는 운영 Agent를 변경하지 않는 격리 장애 시험으로 실행합니다: "
                + " / ".join(selected_case.get("setup", [])),
                icon=":material/health_and_safety:",
            )
        elif not agent_snapshot["all_running"]:
            st.warning(
                "일부 Agent가 중지돼 있습니다. 장애 증상 확인을 위해 실행은 허용하며, "
                "장시간 대기를 막기 위해 20초 제한을 적용합니다."
            )

    if st.session_state.pop("goal_testcase_selection_changed", False):
        st.rerun(scope="app")


def _selected_goal_testcase() -> dict | None:
    selected_case_id = st.session_state.get("goal_testcase_selected_case_id")
    return next(
        (
            case
            for case in load_test_cases().get("cases", [])
            if case.get("case_id") == selected_case_id
        ),
        None,
    )


def _ensure_goal_testcase_selection() -> dict | None:
    cases = load_test_cases().get("cases", [])
    if not cases:
        return None
    selected_case_id = st.session_state.get("goal_testcase_selected_case_id")
    selected_case = next(
        (case for case in cases if case.get("case_id") == selected_case_id),
        None,
    )
    if selected_case is None:
        selected_case = cases[0]
        _set_goal_testcase_selection(selected_case["case_id"])
    return selected_case


def _start_goal_testcase_pipeline(selected_case_id: str):
    st.session_state.goal_testcase_started_at = datetime.now().astimezone().isoformat()
    st.session_state.goal_testcase_running_case_id = selected_case_id
    st.session_state.pop("goal_testcase_agent_snapshot", None)
    st.session_state.pop("goal_testcase_result", None)
    st.session_state.pop("goal_testcase_completed_at", None)
    st.session_state.pop("goal_testcase_preparation", None)
    st.session_state.pop("goal_testcase_trace_id", None)
    st.session_state.pop("goal_judge_error", None)
    st.session_state.goal_testcase_job_id = start_background_job(
        "manual-pipeline",
        selected_case_id,
        _execute_goal_testcase,
        selected_case_id,
        progress={"preparation": _new_manual_preparation_progress()},
    )


def _render_goal_execution_step(selected_case: dict):
    selected_case_id = selected_case["case_id"]
    test_running = bool(st.session_state.get("goal_testcase_job_id"))
    with st.container(border=True):
        st.markdown("#### 1단계 · Agent Pipeline 실행")
        st.caption(
            f"{selected_case_id} · 내부 Agent Pipeline만 먼저 수행합니다. 완료 후 독립 LLM 평가는 선택적으로 실행할 수 있습니다."
        )
        st.button(
            "Agent Pipeline 실행",
            icon=":material/play_arrow:",
            type="primary",
            disabled=test_running or bool(st.session_state.get("goal_judge_job_id")),
            width="stretch",
            key=f"goal_execute_{selected_case_id}",
            on_click=_start_goal_testcase_pipeline,
            args=(selected_case_id,),
        )


def _render_goal_judge_step(selected_case: dict):
    selected_case_id = selected_case["case_id"]
    test_execution = st.session_state.get("goal_testcase_result") or {}
    if test_execution.get("case", {}).get("case_id") != selected_case_id:
        return

    is_fault_case = selected_case.get("category") == "fault_condition"
    execution = test_execution.get("execution", {})
    pipeline_ok = bool(execution.get("ok"))
    if test_execution.get("mode") == "voc":
        pipeline_ok = pipeline_ok and bool(execution.get("result", {}).get("ok"))

    st.markdown("### 2단계 · 독립 LLM 평가 (선택)")
    st.caption("1단계에서 생성·저장한 동일한 개선안을 다시 생성하지 않고, 선택한 외부 Provider가 독립적으로 평가합니다.")
    if is_fault_case:
        st.info("격리 장애 Test Case는 개선안이 없어 독립 LLM 평가 대상이 아닙니다.", icon=":material/info:")
        return
    if not pipeline_ok:
        st.warning("Agent Pipeline이 정상 완료되지 않아 독립 LLM 평가를 시작할 수 없습니다.", icon=":material/block:")
        return

    judge_config = _manual_judge_config_controls(f"goal_{selected_case_id}")
    judge_running = bool(st.session_state.get("goal_judge_job_id"))
    with st.container(border=True):
        st.markdown("#### 선택한 Provider로 추가 평가")
        st.caption("필요한 경우에만 실행하세요. 실행하지 않아도 1단계 Pipeline 수행 결과는 그대로 보존됩니다.")
        if st.button(
            "독립 LLM 평가 실행",
            icon=":material/fact_check:",
            type="primary",
            disabled=judge_running or not judge_config["credential_configured"],
            width="stretch",
            key=f"goal_judge_execute_{selected_case_id}",
        ):
            st.session_state.pop("goal_judge_error", None)
            st.session_state.goal_judge_running_case_id = selected_case_id
            st.session_state.goal_judge_job_id = start_background_job(
                "manual-judge",
                f"{test_execution['run_id']}:{selected_case_id}",
                _execute_goal_judge,
                test_execution["run_id"],
                selected_case_id,
                judge_config,
            )
            st.rerun()
        if st.session_state.get("goal_judge_error"):
            st.error(st.session_state["goal_judge_error"], icon=":material/error:")


def render_goal_monitor():
    _ensure_goal_testcase_selection()
    _goal_testcase_selector()

    selected_case = _selected_goal_testcase()

    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
        gap="small",
        key="goal_pipeline_compact_header",
    ):
        st.markdown("### 실시간 Agent Pipeline")
    active_job_id = st.session_state.get("goal_testcase_job_id")
    if active_job_id:
        _live_testcase_pipeline()
    else:
        _render_agent_pipeline_comparison(
            pipeline_trace_events(
                st.session_state.get("goal_testcase_started_at", ""),
                st.session_state.get("goal_testcase_trace_id", ""),
            ),
            running=False,
            preparation=st.session_state.get("goal_testcase_preparation"),
        )

    if st.session_state.get("goal_judge_job_id"):
        _live_manual_judge()

    if selected_case:
        selected_case_id = selected_case["case_id"]
        _render_goal_testcase_result(selected_case_id)
        _render_goal_judge_step(selected_case)
        _render_goal_judge_result(selected_case_id)


@st.cache_data(ttl=5, max_entries=20, show_spinner=False)
def _load_batch_preflight(case_ids: tuple[str, ...]):
    return batch_preflight(list(case_ids))


def _launch_batch(
    case_ids: list[str],
    *,
    parent_run_id: str = "",
    judge_config: dict | None = None,
):
    run = start_batch_run(
        case_ids,
        timeout_seconds=180,
        max_retries=2,
        parent_run_id=parent_run_id,
        judge_config=judge_config,
    )
    run_id = run["run_id"]
    st.session_state.voc_batch_run_id = run_id
    st.session_state.voc_batch_case_ids = case_ids
    st.session_state.voc_batch_dialog_run_id = run_id
    st.session_state[f"voc_batch_initial_estimate_{run_id}"] = max(
        int(run.get("estimated_total_seconds") or 0),
        5,
    )
    st.session_state.voc_batch_future = _batch_executor().submit(
        execute_batch_run,
        run_id,
        case_ids,
        timeout_seconds=run["timeout_seconds"],
        max_retries=run["max_retries"],
        judge_config=run["judge_config"],
    )


def _parse_batch_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _format_batch_duration(seconds: float) -> str:
    total_seconds = max(int(round(float(seconds or 0))), 0)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {minutes}분"
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"


def _batch_timing(progress: dict, *, now: datetime | None = None) -> dict:
    started_at = _parse_batch_timestamp(progress.get("started_at", ""))
    finished_at = _parse_batch_timestamp(progress.get("finished_at", ""))
    now = now or datetime.now().astimezone()
    end_at = finished_at or now
    elapsed = max((end_at - started_at).total_seconds(), 0.0) if started_at else 0.0
    total = max(int(progress.get("total") or 0), 1)
    completed = max(int(progress.get("completed") or 0), 0)
    persisted_estimate = float(progress.get("estimated_total_seconds") or 0)
    initial_estimate = float(
        st.session_state.get(
            f"voc_batch_initial_estimate_{progress.get('run_id', '')}",
            persisted_estimate
            or total * (75 if progress.get("judge_config", {}).get("enabled") else 45),
        )
    )
    if completed > 0 and progress.get("status") == "RUNNING":
        observed_estimate = elapsed / completed * total
        estimated_total = max(elapsed, observed_estimate)
    elif progress.get("status") == "RUNNING":
        estimated_total = max(initial_estimate, elapsed)
    else:
        estimated_total = elapsed
    return {
        "elapsed_seconds": elapsed,
        "estimated_total_seconds": estimated_total,
        "remaining_seconds": max(estimated_total - elapsed, 0.0),
    }


def _batch_progress_fraction(
    progress: dict,
    timing: dict,
    *,
    now: datetime | None = None,
) -> float:
    status = progress.get("status")
    if status != "RUNNING":
        return 1.0
    runtime = progress.get("runtime_progress", {})
    phase = runtime.get("phase", "")
    total = max(int(progress.get("total") or 0), 1)
    completed = max(int(progress.get("completed") or 0), 0)
    now = now or datetime.now().astimezone()
    if phase == "PREFLIGHT":
        return 0.02
    if phase == "PREPARING":
        phase_started = _parse_batch_timestamp(runtime.get("phase_started_at", ""))
        phase_elapsed = max((now - phase_started).total_seconds(), 0.0) if phase_started else 0.0
        return min(0.02 + phase_elapsed / 15 * 0.03, 0.05)
    if phase == "FINALIZING":
        return 0.98
    if phase == "RUNNING":
        case_started = _parse_batch_timestamp(runtime.get("current_case_started_at", ""))
        case_elapsed = max((now - case_started).total_seconds(), 0.0) if case_started else 0.0
        case_estimate = max((timing["estimated_total_seconds"] - 15) / total, 1.0)
        current_fraction = min(case_elapsed / case_estimate, 0.9)
        case_progress = min((completed + current_fraction) / total, 1.0)
        return min(0.05 + case_progress * 0.90, 0.95)
    return min(completed / total, 0.99)


def _render_batch_stage_flow(progress: dict):
    runtime = progress.get("runtime_progress", {})
    phase = runtime.get("phase", "")
    stages = (
        ("PREFLIGHT", "사전 점검", "환경·Agent·대상 검증"),
        ("PREPARING", "처리 준비", "Run·카탈로그 준비"),
        ("RUNNING", "TC 수행", "Pipeline·Judge 실행"),
        ("FINALIZING", "결과 정리", "증적·집계 저장"),
    )
    phase_index = next((index for index, stage in enumerate(stages) if stage[0] == phase), -1)
    if progress.get("status") != "RUNNING":
        phase_index = len(stages)
    cards = []
    for index, (_, label, description) in enumerate(stages):
        state = "done" if index < phase_index else "active" if index == phase_index else "waiting"
        icon = "✓" if state == "done" else str(index + 1)
        cards.append(
            f'<div class="vqb-stage {state}"><b>{icon}</b><span><strong>{label}</strong><small>{description}</small></span></div>'
        )
    st.html(
        """
        <style>
        .vqb-stage-flow{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin:4px 0 12px}
        .vqb-stage{display:flex;align-items:center;gap:9px;padding:10px 11px;border:1px solid #d4dde7;border-radius:11px;background:#f2f4f6;color:#87919d}
        .vqb-stage>b{display:grid;place-items:center;min-width:27px;height:27px;border-radius:50%;background:#aeb6bf;color:#fff;font-size:11px}
        .vqb-stage span{display:block}.vqb-stage strong{display:block;font-size:12px}.vqb-stage small{display:block;font-size:9px;margin-top:2px}
        .vqb-stage.done{background:#f3f8fd;border-color:#b9cee2;color:#315b82}.vqb-stage.done>b{background:#2e6d9f}
        .vqb-stage.active{background:#edf6ff;border:2px solid #1767a5;color:#124b79;box-shadow:0 4px 13px rgba(23,103,165,.13)}
        .vqb-stage.active>b{background:#1767a5;animation:vqb-pulse 1.2s infinite}
        @keyframes vqb-pulse{50%{box-shadow:0 0 0 6px rgba(23,103,165,.14)}}
        @media(max-width:800px){.vqb-stage-flow{grid-template-columns:repeat(2,1fr)}}
        </style>
        <div class="vqb-stage-flow">"""
        + "".join(cards)
        + "</div>"
    )


def _render_batch_progress_styles():
    st.markdown(
        """
        <style>
        div[data-testid="stDialog"] div[data-testid="stProgress"] [role="progressbar"] {
            height: 24px !important;
            border-radius: 12px !important;
        }
        div[data-testid="stDialog"] div[data-testid="stProgress"] [role="progressbar"] > div {
            height: 100% !important;
            border-radius: 12px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_batch_progress_content(
    run_id: str,
    progress: dict,
    timing: dict | None = None,
):
    total = max(int(progress.get("total") or 0), 1)
    completed = int(progress.get("completed") or 0)
    timing = timing or _batch_timing(progress)
    progress_fraction = _batch_progress_fraction(progress, timing)
    runtime = progress.get("runtime_progress", {})
    phase_label = runtime.get("phase_label") or (
        "수행 완료" if progress.get("status") != "RUNNING" else "실행 상태 확인 중"
    )
    phase_message = runtime.get("message", "Run 진행 정보를 불러오고 있습니다.")
    if progress.get("status") == "RUNNING":
        st.info(f"**{phase_label}** · {phase_message}", icon=":material/pending:")
    st.progress(
        progress_fraction,
        text=(
            f"**전체 예상 진행률 {progress_fraction * 100:.0f}% · "
            f"완료 {completed} / {total}건**"
        ),
    )

    counts = progress.get("counts", {})
    with st.container(horizontal=True):
        st.metric("검토 필요", counts.get("REVIEW_REQUIRED", 0))
        st.metric("실패", counts.get("FAIL", 0))
        st.metric("오류", counts.get("ERROR", 0))
        st.metric("미실행", counts.get("NOT_RUN", 0))
    if progress.get("judge_config", {}).get("enabled"):
        judge_counts = progress.get("judge_counts", {})
        with st.container(horizontal=True):
            st.metric("Judge 통과", judge_counts.get("PASS", 0))
            st.metric("Judge 검토", judge_counts.get("REVIEW_REQUIRED", 0))
            st.metric("Judge 실패", judge_counts.get("FAIL", 0))
            st.metric("Judge 오류", judge_counts.get("ERROR", 0))

    rows = pd.DataFrame(progress.get("case_results", []))
    if not rows.empty:
        visible = [
            column for column in
            [
                "case_id", "status", "mode", "attempt_count", "judge_status",
                "judge_score", "judge_independence_grade", "message", "finished_at",
            ]
            if column in rows.columns
        ]
        st.dataframe(rows[visible], hide_index=True, width="stretch")

    status = progress.get("status")
    if status == "RUNNING":
        st.caption(f"Run ID: {run_id}")
        if progress.get("stop_requested"):
            st.warning("현재 Case가 끝난 뒤 나머지를 NOT_RUN으로 기록하고 중지합니다.")
        elif st.button("실행 중지", icon=":material/stop_circle:", key=f"stop_{run_id}"):
            request_batch_stop(run_id)
            st.rerun(scope="fragment")
        return

    st.session_state.pop("voc_batch_future", None)
    if status == "COMPLETED":
        st.success(f"일괄 실행이 완료되었습니다. · Run ID: {run_id}")
    elif status == "INTERRUPTED":
        st.warning(f"중지 요청에 따라 실행을 종료했습니다. · Run ID: {run_id}")
    else:
        st.error(f"일괄 실행 엔진 오류로 종료되었습니다. · Run ID: {run_id}")
    st.caption(f"증적 위치: {progress.get('run_dir', '-')}")

    retry_ids = [
        item.get("case_id") for item in progress.get("case_results", [])
        if item.get("status") in {"FAIL", "ERROR"}
    ]
    if retry_ids and st.button(
        f"실패·오류 {len(retry_ids)}건 재실행",
        icon=":material/replay:",
        key=f"retry_{run_id}",
    ):
        _launch_batch(
            retry_ids,
            parent_run_id=run_id,
            judge_config=progress.get("judge_config"),
        )
        st.rerun()


@st.fragment(run_every="1s")
def _live_batch_progress():
    run_id = st.session_state.get("voc_batch_run_id")
    if not run_id:
        return
    _render_batch_progress_content(run_id, get_batch_run_progress(run_id))


def _open_batch_progress_dialog(run_id: str):
    if run_id:
        st.session_state.voc_batch_dialog_run_id = str(run_id)
        st.rerun(scope="app")


def _close_batch_progress_dialog():
    st.session_state.pop("voc_batch_dialog_run_id", None)


@st.dialog(
    "일괄 TC 수행 진행 상황",
    width="large",
    icon=":material/pending_actions:",
    on_dismiss=_close_batch_progress_dialog,
)
def _render_batch_progress_dialog(run_id: str):
    _render_batch_progress_dialog_body(run_id)


@st.fragment(run_every="1s")
def _render_batch_progress_dialog_body(run_id: str):
    progress = get_batch_run_progress(run_id)
    timing = _batch_timing(progress)
    _render_batch_progress_styles()

    status = progress.get("status", "ERROR")
    header = st.columns([1.0, 1.15, 1.25, 1.15, 0.7], vertical_alignment="center")
    header[0].metric("상태", status)
    progress_fraction = _batch_progress_fraction(progress, timing)
    header[1].metric("예상 진행률", f"{progress_fraction * 100:.0f}%")
    header[2].metric("예상 소요시간", f"약 {_format_batch_duration(timing['estimated_total_seconds'])}")
    header[3].metric("예상 남은 시간", _format_batch_duration(timing["remaining_seconds"]))
    if header[4].button(
        ":material/close: 닫기",
        key=f"voc_batch_dialog_close_{run_id}",
        width="stretch",
        help="팝업만 닫으며 일괄 수행은 백그라운드에서 계속됩니다.",
    ):
        _close_batch_progress_dialog()
        st.rerun(scope="app")

    st.caption(
        f"경과 시간 {_format_batch_duration(timing['elapsed_seconds'])} · "
        "예상 시간은 완료된 Case의 평균 처리시간으로 실시간 보정됩니다."
    )
    _render_batch_stage_flow(progress)
    _render_batch_progress_content(run_id, progress, timing)


def render_batch_execution():
    st.markdown("### 실행 대상 선택")
    st.caption(
        "기본은 순차 실행입니다. 실행 결과와 재시도 내역은 Case별 증적으로 즉시 저장됩니다."
    )
    catalog = load_quality_test_catalog()
    cases = catalog.get("cases", [])
    groups = catalog.get("groups", {})
    if not cases:
        st.warning("quality_test_catalog.json에 실행할 Case가 없습니다.")
        return

    all_mode_label = f"전체 실행 대상 {len(cases)}건"
    mode = st.segmented_control(
        "선택 방식",
        [all_mode_label, "그룹 선택", "개별 선택"],
        default=all_mode_label,
        key="voc_batch_selection_mode",
    )
    selected_ids: list[str] = []
    if mode == all_mode_label:
        selected_ids = [item["case_id"] for item in cases]
    elif mode == "그룹 선택":
        selected_groups = st.multiselect(
            "그룹",
            options=list(groups),
            format_func=lambda key: f"{groups[key].get('label', key)} ({groups[key].get('expected_count', 0)}건)",
            key="voc_batch_groups",
        )
        selected_ids = [item["case_id"] for item in cases if item.get("group") in selected_groups]
    else:
        case_options = [item["case_id"] for item in cases]
        labels = {item["case_id"]: item for item in cases}
        selected_ids = st.multiselect(
            "테스트케이스",
            options=case_options,
            format_func=lambda case_id: f"{case_id} · {labels[case_id].get('name', '-')}",
            key="voc_batch_cases",
        )

    selected_rows = pd.DataFrame(
        [
            {
                "Case ID": item.get("case_id"),
                "그룹": groups.get(item.get("group"), {}).get("label", item.get("group")),
                "이름": item.get("name"),
                "구현 상태": item.get("implementation_status"),
            }
            for item in cases if item.get("case_id") in selected_ids
        ]
    )
    if not selected_rows.empty:
        st.dataframe(selected_rows, hide_index=True, width="stretch", height=280)

    if not selected_ids:
        st.info("실행할 그룹 또는 Case를 선택하세요.")
        return

    judge_config = _judge_config_controls(
        "voc_batch",
        fault_only=all(case_id.startswith("FT-") for case_id in selected_ids),
    )

    preflight = _load_batch_preflight(tuple(selected_ids))
    with st.container(border=True):
        st.markdown("#### 사전 점검")
        with st.container(horizontal=True):
            st.metric("선택", preflight["selected_count"])
            st.metric("실행 가능", preflight["implemented_count"])
            st.metric("후속 구현", preflight["pending_count"])
            st.metric("Agent", f"{preflight['agents'].get('running', 0)}/6")
        for warning in preflight.get("warnings", []):
            st.warning(warning)
        for blocker in preflight.get("blockers", []):
            st.error(blocker)

    active_run_id = st.session_state.get("voc_batch_run_id")
    active = False
    if active_run_id:
        active = get_batch_run_progress(active_run_id).get("status") == "RUNNING"
    if active:
        run_button_label = "진행 화면 열기"
    elif mode == all_mode_label:
        run_button_label = f"전체 실행 대상 {len(selected_ids)}건 일괄 실행"
    else:
        run_button_label = f"선택 {len(selected_ids)}건 일괄 실행"
    if st.button(
        run_button_label,
        icon=":material/open_in_new:" if active else ":material/play_arrow:",
        type="primary",
        disabled=not active and not preflight.get("ok"),
    ):
        if active:
            _open_batch_progress_dialog(active_run_id)
        else:
            _launch_batch(selected_ids, judge_config=judge_config)
            st.rerun()

    if active_run_id:
        if active:
            st.caption(
                f"백그라운드 실행 중 · Run ID: {active_run_id} · "
                "팝업을 닫거나 다른 페이지로 이동해도 수행은 계속됩니다."
            )

    dialog_run_id = st.session_state.get("voc_batch_dialog_run_id")
    if dialog_run_id:
        _render_batch_progress_dialog(dialog_run_id)


@st.cache_data(ttl=3, max_entries=1, show_spinner=False)
def _load_voc_history_rows():
    return list_voc_run_history()


@st.dialog("수행 이력 삭제 확인")
def _confirm_delete_voc_runs(run_ids: list[str]):
    st.warning("선택한 Run 폴더와 중앙 index 항목을 함께 삭제합니다. 이 작업은 되돌릴 수 없습니다.")
    st.code("\n".join(run_ids), language="text")
    if st.button("선택 Run 영구 삭제", type="primary", icon=":material/delete_forever:"):
        result = delete_voc_run_history(run_ids)
        _load_voc_history_rows.clear()
        st.session_state.voc_history_delete_result = result
        st.rerun()


def _render_voc_run_detail(run_id: str):
    detail = load_voc_run_history_detail(run_id)
    manifest = detail.get("manifest", {})
    summary = detail.get("summary", {})
    integrity = detail.get("integrity", {})
    st.markdown(f"### 실행 상세 · {run_id}")
    with st.container(horizontal=True):
        st.metric("유형", manifest.get("run_type", "-"), border=True)
        st.metric("상태", manifest.get("status", "-"), border=True)
        st.metric("대상", summary.get("total", 0), border=True)
        st.metric("Judge", "사용" if manifest.get("judge_enabled") else "미사용", border=True)
        st.metric("타당성", summary.get("validity_state", "DRAFT"), border=True)

    if integrity.get("ok"):
        st.success("Run 폴더·index·Case 증적의 무결성이 일치합니다.")
    else:
        for error in integrity.get("errors", []):
            st.error(error)
    for warning in integrity.get("warnings", []):
        st.warning(warning)

    safe_manifest = {
        key: manifest.get(key)
        for key in (
            "run_id", "run_type", "status", "started_at", "finished_at", "suite_id",
            "catalog_version", "selected_case_ids", "rubric_versions", "judge_enabled",
            "run_metadata",
        )
        if key in manifest
    }
    view = st.segmented_control(
        "상세 구분",
        ["Case 결과", "실행 정보", "Case 증적"],
        default="Case 결과",
        key=f"voc_history_detail_view_{run_id}",
    )
    case_results = summary.get("case_results", [])
    if view == "Case 결과":
        rows = pd.DataFrame(case_results)
        if rows.empty:
            st.info("아직 저장된 Case 결과가 없습니다.")
        else:
            visible = [
                column for column in
                [
                    "case_id", "status", "mode", "attempt_count", "judge_status",
                    "judge_score", "judge_independence_grade", "message", "started_at", "finished_at",
                    "validity_status", "validity_score", "approval_state", "formal_approval",
                ]
                if column in rows.columns
            ]
            st.dataframe(rows[visible], hide_index=True, width="stretch")
    elif view == "실행 정보":
        st.json(safe_manifest)
    else:
        completed_case_ids = [item.get("case_id") for item in case_results if item.get("case_id")]
        if not completed_case_ids:
            st.info("조회할 Case 증적이 없습니다.")
        else:
            selected_case_id = st.selectbox(
                "Case ID",
                completed_case_ids,
                key=f"voc_history_case_{run_id}",
            )
            artifacts = load_voc_case_history_detail(run_id, selected_case_id)
            artifact_names = [
                name for name in
                ("pipeline_result", "trace", "rule_result", "judge_result", "validity_result")
                if name in artifacts
            ]
            if artifact_names:
                artifact_name = st.selectbox(
                    "증적 파일",
                    artifact_names,
                    key=f"voc_history_artifact_{run_id}",
                )
                st.json(artifacts[artifact_name])
            else:
                st.warning("Case 증적 JSON을 읽을 수 없습니다.")
            pipeline = artifacts.get("pipeline_result", {})
            execution = pipeline.get("execution", {})
            result = execution.get("result", {}) if isinstance(execution, dict) else {}
            if pipeline.get("mode") == "voc" and execution.get("ok") and result.get("ok"):
                st.markdown("#### 동일 결과 Judge 재평가")
                reevaluation_config = _judge_config_controls(
                    f"history_{run_id}_{selected_case_id}"
                )
                if st.button(
                    "저장된 Pipeline 결과 재평가",
                    icon=":material/replay:",
                    disabled=not reevaluation_config.get("enabled"),
                    key=f"reevaluate_{run_id}_{selected_case_id}",
                ):
                    with st.spinner("독립 LLM Judge가 저장된 동일 결과를 재평가하고 있습니다..."):
                        reevaluated = reevaluate_voc_run_case(
                            run_id,
                            selected_case_id,
                            reevaluation_config,
                        )
                    st.session_state.voc_judge_reevaluation_result = reevaluated
                    _load_voc_history_rows.clear()
                    st.rerun()

    evidence = download_voc_run_evidence(run_id)
    st.download_button(
        "Run 전체 증적 ZIP 다운로드",
        data=evidence,
        file_name=f"{run_id}.zip",
        mime="application/zip",
        icon=":material/download:",
        key=f"download_{run_id}",
    )


def _render_retest_comparison(history: list[dict]):
    st.markdown("### 재시험 전후 비교")
    st.caption(
        "임의 A/B 평가가 아니라 원본 Run과 연결된 RETEST Run의 Case 상태 변화를 비교합니다. "
        "Catalog·TC·Rubric 버전이 다르면 비교를 차단합니다."
    )
    completed = [item for item in history if item.get("status") != "RUNNING"]
    retests = [item for item in completed if item.get("run_type") == "RETEST"]
    if not retests:
        st.info("비교 가능한 RETEST Run이 아직 없습니다. 실패·오류 재실행 후 사용할 수 있습니다.")
        return
    baseline_id = st.selectbox(
        "원본 Run",
        [item["run_id"] for item in completed],
        key="voc_history_baseline_run",
    )
    candidate_id = st.selectbox(
        "재시험 Run",
        [item["run_id"] for item in retests],
        key="voc_history_retest_run",
    )
    comparison = compare_voc_runs(baseline_id, candidate_id)
    if not comparison["compatible"]:
        st.error(
            "재시험 전후 비교 조건이 일치하지 않습니다: "
            + ", ".join(comparison["compatibility_differences"])
        )
        return
    st.success("동일 Catalog·TC·Rubric과 부모 Run 연결이 확인됐습니다.")
    st.dataframe(pd.DataFrame(comparison["count_comparison"]), hide_index=True, width="stretch")
    changed = [item for item in comparison["case_comparison"] if item["changed"]]
    st.markdown(f"#### 상태 변경 Case · {len(changed)}건")
    st.dataframe(pd.DataFrame(changed or comparison["case_comparison"]), hide_index=True, width="stretch")


def render_voc_history():
    st.markdown("### 실행 이력 조회")
    history = _load_voc_history_rows()
    delete_result = st.session_state.pop("voc_history_delete_result", None)
    if delete_result:
        st.success(f"{delete_result['deleted_count']}개 Run을 삭제했습니다.")
    reevaluation_result = st.session_state.pop("voc_judge_reevaluation_result", None)
    if reevaluation_result:
        judge = reevaluation_result.get("judge_result", {})
        st.success(
            f"{reevaluation_result['case_id']} Judge 재평가 완료 · "
            f"{judge.get('decision', 'ERROR')} · {judge.get('total_score', '-')}점"
        )
    if not history:
        st.info("저장된 VOC 실행 이력이 없습니다.")
        return

    started_dates = [
        datetime.fromisoformat(item["started_at"]).date()
        for item in history if item.get("started_at")
    ]
    min_date, max_date = min(started_dates), max(started_dates)
    with st.container(border=True):
        date_range = st.date_input(
            "실행 기간",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            key="voc_history_date_range",
        )
        with st.container(horizontal=True):
            statuses = st.multiselect(
                "Run 상태",
                sorted({item.get("status", "") for item in history}),
                key="voc_history_status_filter",
            )
            run_types = st.multiselect(
                "실행 유형",
                sorted({item.get("run_type", "") for item in history}),
                key="voc_history_type_filter",
            )
            judge_filter = st.selectbox(
                "Judge",
                ["전체", "사용", "미사용"],
                key="voc_history_judge_filter",
            )
            case_query = st.text_input(
                "Case ID",
                placeholder="예: TC-01",
                key="voc_history_case_filter",
            )

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range
    filtered = []
    for item in history:
        started_date = datetime.fromisoformat(item["started_at"]).date() if item.get("started_at") else min_date
        if not (start_date <= started_date <= end_date):
            continue
        if statuses and item.get("status") not in statuses:
            continue
        if run_types and item.get("run_type") not in run_types:
            continue
        if judge_filter != "전체" and item.get("judge_status") != judge_filter:
            continue
        if case_query and case_query.strip().upper() not in {
            str(case_id).upper() for case_id in item.get("selected_case_ids", [])
        }:
            continue
        filtered.append(item)

    with st.container(horizontal=True):
        st.metric("전체 Run", len(history), border=True)
        st.metric("조회 Run", len(filtered), border=True)
        st.metric("실행 중", sum(item.get("status") == "RUNNING" for item in filtered), border=True)
        st.metric("무결성 오류", sum(bool(item.get("integrity_error")) for item in filtered), border=True)
    if not filtered:
        st.info("필터 조건에 맞는 Run이 없습니다.")
        return

    table_rows = pd.DataFrame(
        [
            {
                "Run ID": item.get("run_id"),
                "실행 시각": item.get("started_at"),
                "유형": item.get("run_type"),
                "상태": item.get("status"),
                "대상": item.get("selected_count", 0),
                "완료": item.get("completed_count", 0),
                "진행률": item.get("completion_rate", 0.0),
                "PASS": item.get("counts", {}).get("PASS", 0),
                "FAIL": item.get("counts", {}).get("FAIL", 0),
                "ERROR": item.get("counts", {}).get("ERROR", 0),
                "검토 필요": item.get("counts", {}).get("REVIEW_REQUIRED", 0),
                "Judge": item.get("judge_status"),
                "Judge 통과": item.get("judge_counts", {}).get("PASS", 0),
                "Judge 오류": item.get("judge_counts", {}).get("ERROR", 0),
                "타당성": item.get("validity_state", "DRAFT"),
                "배포 판정": item.get("deployment_decision"),
            }
            for item in filtered
        ]
    )
    event = st.dataframe(
        table_rows,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        key="voc_history_table",
        column_config={
            "Run ID": st.column_config.TextColumn(pinned=True),
            "진행률": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
        },
    )
    selected_indices = event.selection.rows
    selected_items = [filtered[index] for index in selected_indices if index < len(filtered)]
    with st.container(horizontal=True):
        if st.button(
            "선택 Run 삭제",
            icon=":material/delete:",
            disabled=not selected_items or any(item.get("status") == "RUNNING" for item in selected_items),
        ):
            _confirm_delete_voc_runs([item["run_id"] for item in selected_items])
        if st.button("이력 새로고침", icon=":material/refresh:"):
            _load_voc_history_rows.clear()
            st.rerun()

    if selected_items:
        _render_voc_run_detail(selected_items[0]["run_id"])
    else:
        st.caption("상세 조회 또는 삭제할 Run 행을 선택하세요. 여러 행을 선택하면 일괄 삭제할 수 있습니다.")

    if st.toggle("재시험 전후 비교 보기", key="voc_history_show_retest"):
        _render_retest_comparison(history)


@st.cache_data(ttl=3, max_entries=1, show_spinner=False)
def _load_validity_candidates():
    return list_improvement_validity_candidates()


def _validity_candidate_key(candidate: dict) -> str:
    return f"{candidate.get('run_id', '')}::{candidate.get('case_id', '')}"


def _validity_candidate_rows(candidates: list[dict], selected_key: str = "") -> pd.DataFrame:
    rows = []
    for candidate in candidates:
        validity_status = candidate.get("validity_status", "NOT_RUN")
        rows.append(
            {
                "선택": "●" if _validity_candidate_key(candidate) == selected_key else "",
                "수행 일시": _dashboard_timestamp(candidate.get("started_at", "")),
                "Run ID": candidate.get("run_id", "-"),
                "Case ID": candidate.get("case_id", "-"),
                "유형": candidate.get("run_type", "-"),
                "질문": candidate.get("question", "-") or "-",
                "Judge": candidate.get("judge_status", "NOT_RUN"),
                "Judge 점수": candidate.get("judge_score"),
                "타당성": validity_status,
                "타당성 점수": candidate.get("validity_score"),
                "승인 단계": candidate.get("workflow_state", "DRAFT"),
                "정식 승인": "승인" if candidate.get("formal_approval") else "미승인",
            }
        )
    return pd.DataFrame(rows)


def _filter_validity_candidates(
    candidates: list[dict],
    *,
    query: str,
    status_filter: str,
) -> list[dict]:
    query = str(query or "").strip().lower()
    filtered = []
    for candidate in candidates:
        if query and query not in " ".join(
            str(candidate.get(key, ""))
            for key in ("run_id", "case_id", "question", "run_type")
        ).lower():
            continue
        validity_status = candidate.get("validity_status", "NOT_RUN")
        if status_filter == "평가 전" and validity_status != "NOT_RUN":
            continue
        if status_filter == "평가 완료" and validity_status == "NOT_RUN":
            continue
        if status_filter == "정식 승인" and not candidate.get("formal_approval"):
            continue
        filtered.append(candidate)
    return filtered


def _select_validity_candidate(candidate: dict):
    st.session_state.voc_validity_selected_key = _validity_candidate_key(candidate)


@st.dialog(
    "타당성 검증 대상 상세",
    width="large",
    icon=":material/fact_check:",
)
def _render_validity_candidate_dialog(candidate: dict):
    artifacts = load_voc_case_history_detail(candidate["run_id"], candidate["case_id"])
    execution = artifacts.get("pipeline_result", {}).get("execution", {})
    result = execution.get("result", {}) if isinstance(execution, dict) else {}
    judge = artifacts.get("judge_result", {})
    validity = artifacts.get("validity_result", {})

    st.caption(
        f"{candidate.get('run_type', '-')} · {candidate['run_id']} · "
        f"{_dashboard_timestamp(candidate.get('started_at', ''))}"
    )
    with st.container(horizontal=True):
        st.metric("Case", candidate["case_id"], border=True)
        st.metric("Judge", judge.get("decision", candidate.get("judge_status", "NOT_RUN")), border=True)
        st.metric("타당성", validity.get("decision", candidate.get("validity_status", "NOT_RUN")), border=True)
        st.metric("승인 단계", validity.get("workflow_state", candidate.get("workflow_state", "DRAFT")), border=True)

    st.markdown("#### :material/help: 검증 질문")
    st.write(candidate.get("question") or execution.get("question") or "-")

    answer_columns = st.columns(2, gap="medium")
    with answer_columns[0].container(border=True, height="stretch"):
        st.markdown("#### :material/summarize: Pipeline 요약")
        st.write(result.get("summary", "-") or "-")
    with answer_columns[1].container(border=True, height="stretch"):
        st.markdown("#### :material/lightbulb: 최종 개선안")
        st.write(result.get("policy", "-") or "-")

    score_columns = st.columns(2, gap="medium")
    with score_columns[0].container(border=True, height="stretch"):
        st.markdown("#### 독립 Judge 판정")
        st.metric("Judge 점수", f"{judge.get('total_score', '-')}점")
        st.caption(
            f"Provider {judge.get('provider', '-')} · 모델 {judge.get('model', '-')} · "
            f"독립성 {judge.get('independence_grade', '-')}"
        )
    with score_columns[1].container(border=True, height="stretch"):
        st.markdown("#### 타당성 평가 상태")
        st.metric(
            "타당성 점수",
            f"{validity.get('total_score', candidate.get('validity_score', '-'))}점",
        )
        st.caption(
            f"판정 {validity.get('decision', candidate.get('validity_status', 'NOT_RUN'))} · "
            f"정식 승인 {'완료' if candidate.get('formal_approval') else '미완료'}"
        )

    dimension_scores = validity.get("dimension_scores", {})
    if dimension_scores:
        with st.expander("타당성 평가 근거", icon=":material/analytics:"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "평가 항목": dimension,
                            "점수": detail.get("score"),
                            "배점": detail.get("max_points"),
                            "판정 근거": detail.get("reason", "-"),
                        }
                        for dimension, detail in dimension_scores.items()
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            for recommendation in validity.get("recommendations", []):
                st.write(f"- {recommendation}")

    trace = artifacts.get("trace", {}) if isinstance(artifacts.get("trace"), dict) else {}
    trace_events = trace.get("events", []) if isinstance(trace.get("events"), list) else []
    with st.expander("실행·판정 증적", icon=":material/account_tree:"):
        st.caption(f"Trace ID: {trace.get('trace_id', '-')} · 이벤트 {len(trace_events)}건")
        if trace_events:
            trace_rows = pd.DataFrame(trace_events)
            visible = [
                column for column in ("source", "target", "status", "duration_ms", "message")
                if column in trace_rows.columns
            ]
            st.dataframe(trace_rows[visible], hide_index=True, width="stretch")
        else:
            st.info("표시할 Agent Trace 이벤트가 없습니다.")

    if st.button(
        "이 대상으로 검증 진행",
        type="primary",
        icon=":material/check_circle:",
        width="stretch",
        key=f"validity_confirm_{candidate['run_id']}_{candidate['case_id']}",
    ):
        _select_validity_candidate(candidate)
        st.session_state.voc_validity_dialog_opened_key = _validity_candidate_key(candidate)
        st.rerun()


def _render_validity_result(result: dict):
    if not result:
        st.info("아직 자동 타당성 평가가 없습니다.")
        return
    with st.container(horizontal=True):
        st.metric("자동 판정", result.get("decision", "NOT_RUN"), border=True)
        st.metric("타당성 점수", result.get("total_score", "-"), border=True)
        st.metric("승인 상태", result.get("workflow_state", "DRAFT"), border=True)
        st.metric("정식 승인", "승인" if result.get("formal_approval") else "미승인", border=True)
    if result.get("error"):
        st.error(result["error"])
    holds = result.get("immediate_hold_rules_triggered", [])
    if holds:
        st.error("즉시 승인 보류: " + ", ".join(holds))
    scores = [
        {
            "평가 항목": key,
            "점수": value.get("score"),
            "배점": value.get("max_points"),
            "판정 사유": value.get("reason"),
        }
        for key, value in result.get("dimension_scores", {}).items()
    ]
    if scores:
        st.dataframe(pd.DataFrame(scores), hide_index=True, width="stretch")
    if result.get("recommendations"):
        st.markdown("#### 보완 권고")
        for recommendation in result["recommendations"]:
            st.write(f"- {recommendation}")
    reviews = result.get("human_reviews", [])
    if reviews:
        st.markdown("#### 사람 검토 감사 이력")
        st.dataframe(pd.DataFrame(reviews), hide_index=True, width="stretch")


def _render_human_validity_review(run_id: str, case_id: str, result: dict):
    state = result.get("workflow_state", "DRAFT")
    if result.get("decision") != "AI_PASS" or result.get("immediate_hold_rules_triggered"):
        st.warning("AI_PASS이고 즉시 보류 규칙이 없어야 QA 검토를 시작할 수 있습니다.")
        return
    if state == "AI_REVIEWED":
        role, heading = "QA", "QA 검토"
    elif state == "QA_REVIEWED":
        role, heading = "BUSINESS", "업무 담당자 승인"
    elif state == "BUSINESS_APPROVED":
        st.success("QA와 업무 담당자 승인이 모두 완료되어 정식 운영 승인 상태입니다.")
        return
    else:
        st.info(f"현재 상태({state})에서는 추가 승인을 진행할 수 없습니다.")
        return

    st.markdown(f"### {heading}")
    st.info(
        "시연에서는 한 사람이 QA와 업무 담당자 역할을 모두 수행할 수 있습니다. "
        "다만 같은 이름을 사용하더라도 QA 검토와 업무 승인은 서로 다른 단계·시각·의견으로 각각 기록됩니다."
    )
    with st.form(f"validity_review_{run_id}_{case_id}_{role}"):
        reviewer = st.text_input("검토자 이름 또는 ID", max_chars=100)
        decision_label = st.segmented_control(
            "검토 결정",
            ("승인", "보완 요구", "반려"),
            default="승인",
        )
        comment = st.text_area("검토 의견", max_chars=1000, height=100)
        submitted = st.form_submit_button(
            "검토 결과 저장",
            type="primary",
            icon=":material/approval:",
        )
    if submitted:
        decision = {"승인": "APPROVE", "보완 요구": "REVISION_REQUIRED", "반려": "REJECTED"}[
            decision_label
        ]
        review_voc_improvement_validity(
            run_id,
            case_id,
            reviewer_role=role,
            reviewer_name_or_id=reviewer,
            decision=decision,
            comment=comment,
        )
        _load_validity_candidates.clear()
        _load_voc_history_rows.clear()
        st.session_state.voc_validity_notice = f"{heading} 결과를 저장했습니다."
        st.rerun()


def _render_improvement_ab(candidates: list[dict], baseline: dict, artifacts: dict):
    st.markdown("## 기존·개선 답변 A/B 비교")
    st.caption(
        "현재 선택한 결과를 A로 고정합니다. A에서 실행한 연결 재시험만 B 후보로 표시하므로 "
        "두 Run을 직접 맞춰 고를 필요가 없습니다."
    )
    with st.container(border=True):
        st.markdown("#### 사용 순서")
        st.write("1. 위에서 기준 Run·Case를 선택합니다.")
        st.write("2. 아래 버튼으로 같은 TC의 연결 재시험을 실행합니다.")
        st.write("3. 재시험 완료 후 B 결과에 독립 Judge와 타당성 평가를 수행합니다.")
        st.write("4. B 후보를 선택하면 원본 A를 자동으로 찾아 점수와 답변을 비교합니다.")
        st.caption("재시험은 실제 Agent·LLM을 호출하므로 수행 시간과 API 비용이 발생합니다.")

    active_run_id = st.session_state.get("voc_batch_run_id")
    active = bool(active_run_id and get_batch_run_progress(active_run_id).get("status") == "RUNNING")
    judge = artifacts.get("judge_result", {})
    judge_config = {
        "enabled": True,
        "provider": judge.get("provider", "anthropic"),
        "model": judge.get("model", "claude-opus-4-6"),
    }
    with st.container(horizontal=True):
        if st.button(
            "현재 Case 연결 재시험 실행",
            icon=":material/replay:",
            disabled=active,
            key=f"validity_linked_retest_{baseline['run_id']}_{baseline['case_id']}",
        ):
            _launch_batch(
                [baseline["case_id"]],
                parent_run_id=baseline["run_id"],
                judge_config=judge_config,
            )
            st.rerun()
        if st.button("B 후보 새로고침", icon=":material/refresh:", key="validity_ab_refresh"):
            _load_validity_candidates.clear()
            _load_voc_history_rows.clear()
            st.rerun()
    if active_run_id:
        _live_batch_progress()

    retests = [
        item for item in candidates
        if item.get("run_type") == "RETEST"
        and item.get("parent_run_id") == baseline["run_id"]
        and item.get("case_id") == baseline["case_id"]
    ]
    if not retests:
        st.info("현재 선택한 A와 연결된 완료 RETEST가 없습니다. 위 버튼으로 B 후보를 먼저 생성하세요.")
        return
    labels = [
        f"{item['run_id']} · Judge {item['judge_status']} · 타당성 {item['validity_status']}"
        for item in retests
    ]
    candidate_label = st.selectbox("B · 연결 재시험", labels, key="validity_ab_candidate")
    candidate = retests[labels.index(candidate_label)]
    comparison = compare_voc_improvement_answers(
        baseline["run_id"], candidate["run_id"], baseline["case_id"]
    )
    if not comparison["compatible"]:
        st.error("동일 조건 A/B 비교 불가: " + ", ".join(comparison["compatibility_differences"]))
        return
    st.success("동일 질문·TC·Catalog·Rubric과 RETEST 부모 연결이 확인됐습니다.")
    before, after = st.columns(2)
    with before:
        st.markdown("### A · 기존 답변")
        st.write(comparison["baseline"]["policy"] or "-")
        st.caption(
            f"Judge {comparison['baseline']['judge_score']} · "
            f"타당성 {comparison['baseline']['validity_score']} · "
            f"{comparison['baseline']['workflow_state']}"
        )
    with after:
        st.markdown("### B · 개선 답변")
        st.write(comparison["candidate"]["policy"] or "-")
        st.caption(
            f"Judge {comparison['candidate']['judge_score']} · "
            f"타당성 {comparison['candidate']['validity_score']} · "
            f"{comparison['candidate']['workflow_state']}"
        )
    with st.container(horizontal=True):
        judge_delta = comparison["score_deltas"]["judge_score"]
        validity_delta = comparison["score_deltas"]["validity_score"]
        st.metric("Judge 점수 변화", "-" if judge_delta is None else judge_delta)
        st.metric("타당성 점수 변화", "-" if validity_delta is None else validity_delta)


def render_improvement_validity():
    notice = st.session_state.pop("voc_validity_notice", None)
    if notice:
        st.success(notice)
    st.markdown("## 검증 대상 선택")
    st.caption("성공한 VOC Pipeline 결과를 자동 채점한 뒤 QA와 업무 담당자가 순서대로 검토합니다.")
    candidates = _load_validity_candidates()
    if not candidates:
        st.info("타당성을 검증할 수 있는 완료 VOC Case가 없습니다.")
        return

    approval_ready = [
        item for item in candidates
        if item.get("validity_status") == "AI_PASS" and item.get("workflow_state") == "AI_REVIEWED"
    ]
    not_evaluated = sum(item.get("validity_status") == "NOT_RUN" for item in candidates)
    formally_approved = sum(bool(item.get("formal_approval")) for item in candidates)
    with st.container(horizontal=True):
        st.metric("전체 대상", len(candidates), border=True)
        st.metric("평가 전", not_evaluated, border=True)
        st.metric("QA 검토 가능", len(approval_ready), border=True)
        st.metric("정식 승인", formally_approved, border=True)

    with st.container(border=True):
        filter_columns = st.columns([1.8, 1.2], gap="medium", vertical_alignment="bottom")
        with filter_columns[0]:
            query = st.text_input(
                "대상 검색",
                placeholder="Run ID, Case ID, 질문 또는 수행 유형 검색",
                key="voc_validity_candidate_query",
                icon=":material/search:",
            )
        with filter_columns[1]:
            status_filter = st.segmented_control(
                "평가 상태",
                ("전체", "평가 전", "평가 완료", "정식 승인"),
                default="전체",
                key="voc_validity_candidate_status",
                width="stretch",
            )

    filtered = _filter_validity_candidates(
        candidates,
        query=query,
        status_filter=status_filter or "전체",
    )
    if not filtered:
        st.info("현재 검색·상태 조건에 맞는 검증 대상이 없습니다.")
        return

    selected_key = st.session_state.get("voc_validity_selected_key", "")
    if not any(_validity_candidate_key(item) == selected_key for item in filtered):
        selected_key = _validity_candidate_key(filtered[0])
        st.session_state.voc_validity_selected_key = selected_key

    status_counts = pd.DataFrame(
        [
            {"평가 상태": status, "대상 수": count}
            for status, count in pd.Series(
                [item.get("validity_status", "NOT_RUN") for item in filtered]
            ).value_counts().items()
        ]
    )
    list_column, chart_column = st.columns([4.2, 1.15], gap="medium", vertical_alignment="top")
    with list_column:
        st.markdown("#### 검증 대상 목록")
        st.caption("행을 선택하면 테스트 수행 상세 형식의 팝업이 열리고 해당 Case가 검증 대상으로 지정됩니다.")
        candidate_frame = _validity_candidate_rows(filtered, selected_key)
        event = st.dataframe(
            candidate_frame,
            hide_index=True,
            width="stretch",
            height=min(465, 76 + len(candidate_frame) * 38),
            on_select="rerun",
            selection_mode="single-row",
            key="voc_validity_candidate_table",
            column_config={
                "선택": st.column_config.TextColumn("", width="small", pinned=True),
                "수행 일시": st.column_config.TextColumn(width="medium"),
                "Run ID": st.column_config.TextColumn(width="large", pinned=True),
                "Case ID": st.column_config.TextColumn(width="small"),
                "유형": st.column_config.TextColumn(width="small"),
                "질문": st.column_config.TextColumn(width="large"),
                "Judge": st.column_config.TextColumn(width="small"),
                "Judge 점수": st.column_config.ProgressColumn(
                    width="small", min_value=0, max_value=100, format="%g점"
                ),
                "타당성": st.column_config.TextColumn(width="small"),
                "타당성 점수": st.column_config.ProgressColumn(
                    width="small", min_value=0, max_value=100, format="%g점"
                ),
                "승인 단계": st.column_config.TextColumn(width="medium"),
                "정식 승인": st.column_config.TextColumn(width="small"),
            },
        )
    with chart_column.container(border=True):
        st.markdown("#### 상태 분포")
        st.bar_chart(
            status_counts,
            x="평가 상태",
            y="대상 수",
            horizontal=True,
            color="#2F75B5",
            height=max(190, 55 + len(status_counts) * 42),
        )

    selected_rows = event.selection.rows
    if selected_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(filtered):
            clicked = filtered[selected_index]
            clicked_key = _validity_candidate_key(clicked)
            _select_validity_candidate(clicked)
            if st.session_state.get("voc_validity_dialog_opened_key") != clicked_key:
                st.session_state.voc_validity_dialog_opened_key = clicked_key
                _render_validity_candidate_dialog(clicked)

    selected = next(
        item for item in candidates
        if _validity_candidate_key(item) == st.session_state.voc_validity_selected_key
    )
    artifacts = load_voc_case_history_detail(selected["run_id"], selected["case_id"])
    execution = artifacts.get("pipeline_result", {}).get("execution", {})
    with st.container(border=True):
        selected_heading, selected_status = st.columns([2.2, 1], vertical_alignment="center")
        with selected_heading:
            st.markdown(f"#### 선택 대상 · {selected['case_id']}")
            st.caption(f"{selected['run_id']} · {selected.get('question') or execution.get('question') or '-'}")
        with selected_status:
            st.markdown(
                f":blue-badge[Judge {selected.get('judge_status', 'NOT_RUN')}] "
                f":blue-badge[타당성 {selected.get('validity_status', 'NOT_RUN')}]",
                text_alignment="right",
            )

    with st.container(border=True):
        st.markdown("#### 자동 평가 설정")
        config = _validity_config_controls(f"{selected['run_id']}_{selected['case_id']}")
        if st.button(
            "선택 대상 자동 타당성 평가 실행",
            type="primary",
            icon=":material/fact_check:",
            disabled=not config["credential_configured"],
            width="stretch",
        ):
            with st.spinner("개선안의 근거·실행 가능성·담당·일정·KPI·위험을 평가하고 있습니다..."):
                evaluate_voc_improvement_validity(
                    selected["run_id"], selected["case_id"], config
                )
            _load_validity_candidates.clear()
            _load_voc_history_rows.clear()
            st.session_state.voc_validity_notice = "자동 타당성 평가를 저장했습니다."
            st.rerun()

    validity = artifacts.get("validity_result", {})
    st.markdown("## 타당성 평가 및 승인")
    _render_validity_result(validity)
    if validity.get("recommendations"):
        st.caption(
            "보완 권고는 AI가 제시한 검토 후보이며 확정 결함이나 업무 지시가 아닙니다. "
            "현재는 사용자 분석이 끝날 때까지 미확정으로 유지합니다."
        )
    if validity:
        _render_human_validity_review(selected["run_id"], selected["case_id"], validity)
    if st.toggle("동일 조건 A/B 비교 보기", key="validity_show_ab"):
        _render_improvement_ab(candidates, selected, artifacts)

def _build_testcase_group_chart(group_rows: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(group_rows)
        .mark_bar(color="#2F6FB0", cornerRadiusEnd=5, size=18)
        .encode(
            y=alt.Y(
                "검증 영역:N",
                title=None,
                sort="-x",
                axis=alt.Axis(
                    domain=False,
                    ticks=False,
                    labelColor="#425b76",
                    labelLimit=150,
                    labelPadding=8,
                ),
            ),
            x=alt.X(
                "Case 수:Q",
                title=None,
                axis=alt.Axis(
                    domain=False,
                    gridColor="#e6eef6",
                    format="d",
                    tickCount=5,
                ),
            ),
            tooltip=[
                alt.Tooltip("검증 영역:N", title="검증 영역"),
                alt.Tooltip("Case 수:Q", title="Case 수", format="d"),
            ],
        )
        .properties(height=120)
        .configure_view(strokeWidth=0)
    )


def render_testcases():
    payload = load_test_cases()
    catalog = load_quality_test_catalog()
    cases = catalog.get("cases", [])
    groups = catalog.get("groups", {})
    testcase_details = {
        item.get("case_id"): item for item in payload.get("cases", [])
    }

    if not cases:
        st.warning("통합 테스트 카탈로그에 등록된 Case가 없습니다.")
        return

    implemented_count = sum(
        item.get("implementation_status") == "IMPLEMENTED" for item in cases
    )
    defined_count = len(cases) - implemented_count
    voc_count = sum(item.get("group") == "voc_functional" for item in cases)
    additional_count = len(cases) - voc_count

    group_rows = pd.DataFrame(
        [
            {
                "검증 영역": group.get("label", group_key),
                "Case 수": sum(item.get("group") == group_key for item in cases),
            }
            for group_key, group in groups.items()
        ]
    )
    st.html(
        """
        <style>
        .st-key-voc_testcase_metrics [data-testid="stMetric"]{
            height:86px!important;min-height:86px!important;padding:7px 9px!important;
        }
        .st-key-voc_testcase_metrics [data-testid="stMetricLabel"] p{
            font-size:.72rem!important;line-height:1.2!important;
        }
        .st-key-voc_testcase_metrics [data-testid="stMetricValue"]{
            font-size:1.25rem!important;line-height:1.25!important;
        }
        .st-key-voc_testcase_metrics [data-testid="stMetricDelta"]{
            font-size:.66rem!important;
        }
        .st-key-voc_testcase_metrics>div[data-testid="stVerticalBlock"]{
            gap:.45rem!important;
        }
        .st-key-voc_testcase_search>div[data-testid="stVerticalBlock"],
        .st-key-voc_testcase_browser>div[data-testid="stVerticalBlock"],
        .st-key-voc_testcase_detail>div[data-testid="stVerticalBlock"]{
            gap:.55rem!important;
        }
        .st-key-voc_testcase_browser [data-testid="stDataFrame"]{
            margin-top:.1rem;
        }
        .st-key-voc_testcase_detail [data-testid="stTabs"] button{
            min-height:34px!important;
        }
        </style>
        """
    )
    overview_columns = st.columns(
        [1.6, 1],
        gap="small",
        vertical_alignment="top",
    )
    with overview_columns[0].container(
        border=True,
            height=190,
        key="voc_testcase_metrics",
    ):
        st.markdown("#### :material/target: 실행 대상 요약")
        with st.container(horizontal=True, horizontal_alignment="right"):
            st.download_button(
                "TC Download",
                data=json.dumps(catalog, ensure_ascii=False, indent=2),
                file_name="quality_test_catalog.json",
                mime="application/json",
                icon=":material/download:",
                type="primary",
                width="content",
                key="voc_testcase_catalog_download",
            )
            with st.popover(
                "TC Upload",
                icon=":material/upload_file:",
                width="content",
            ):
                uploaded_catalog = st.file_uploader(
                    "통합 테스트케이스 JSON",
                    type=["json"],
                    key="voc_testcase_catalog_upload",
                )
                if uploaded_catalog is not None:
                    try:
                        uploaded_payload = json.loads(
                            uploaded_catalog.getvalue().decode("utf-8-sig")
                        )
                        upload_errors = validate_quality_test_catalog(uploaded_payload)
                    except Exception as exc:
                        uploaded_payload = None
                        upload_errors = [f"JSON 파일을 해석할 수 없습니다: {exc}"]
                    if upload_errors:
                        for error in upload_errors:
                            st.error(error)
                    elif st.button(
                        "검증 완료 · 적용",
                        type="primary",
                        key="voc_testcase_catalog_apply_upload",
                    ):
                        result = save_quality_test_catalog(uploaded_payload, source="json_upload")
                        st.success(
                            f"통합 테스트케이스 {result.get('total_cases', 0)}건을 저장했습니다."
                        )
                        st.rerun()
        metric_row = st.columns(4, gap="small")
        metric_row[0].metric("전체 실행 대상", f"{len(cases)}건", border=True)
        metric_row[1].metric("VOC 질문형", f"{voc_count}건", border=True)
        metric_row[2].metric("추가 검증 Case", f"{additional_count}건", border=True)
        metric_row[3].metric(
            "구현 상태",
            f"{implemented_count}건 완료",
            delta=f"{defined_count}건 후속 구현",
            delta_color="off",
            border=True,
    )
    with overview_columns[1].container(
        border=True,
            height=190,
        key="voc_testcase_group_chart",
    ):
        st.markdown("#### :material/bar_chart: 검증 영역별 Case 구성")
        st.altair_chart(_build_testcase_group_chart(group_rows))

    browser_columns = st.columns([0.5, 1.1, 1], gap="small", vertical_alignment="top")
    with browser_columns[0].container(
        border=True,
        height=380,
        key="voc_testcase_search",
    ):
        st.markdown("#### :material/search: Case 탐색")
        search_text = st.text_input(
            "검색",
            placeholder="ID·이름·판정 기준",
            key="voc_testcase_catalog_search",
        ).strip().lower()
        group_filter = st.selectbox(
            "검증 영역",
            options=["전체", *groups.keys()],
            format_func=lambda key: (
                "전체" if key == "전체" else groups[key].get("label", key)
            ),
            key="voc_testcase_catalog_group",
        )
        status_filter = st.selectbox(
            "구현 상태",
            options=["전체", "IMPLEMENTED", "DEFINED"],
            format_func=lambda value: {
                "전체": "전체",
                "IMPLEMENTED": "실행 구현 완료",
                "DEFINED": "정의됨 · 후속 구현",
            }[value],
            key="voc_testcase_catalog_status",
        )

    status_labels = {
        "IMPLEMENTED": "실행 구현 완료",
        "DEFINED": "정의됨 · 후속 구현",
    }
    rows = []
    visible_cases = []
    for case in cases:
        group_key = case.get("group", "")
        status = case.get("implementation_status", "")
        searchable = " ".join(
            str(case.get(key, ""))
            for key in ("case_id", "name", "acceptance", "source_ref")
        ).lower()
        if group_filter != "전체" and group_key != group_filter:
            continue
        if status_filter != "전체" and status != status_filter:
            continue
        if search_text and search_text not in searchable:
            continue
        visible_cases.append(case)
        rows.append(
            {
                "Case ID": case.get("case_id"),
                "검증 영역": groups.get(group_key, {}).get("label", group_key),
                "이름": case.get("name"),
                "구현 상태": status_labels.get(status, status or "-"),
            }
        )

    with browser_columns[1].container(
        border=True,
        height=380,
        key="voc_testcase_browser",
    ):
        st.markdown("#### :material/list_alt: Case 목록")
        st.caption(f"검색 결과 {len(rows)}건 · 행을 선택하면 우측에서 상세 확인")
        visible_case_ids = [case.get("case_id", "") for case in visible_cases]
        table_key = "voc_testcase_catalog_table"
        remembered_case_id = st.session_state.get("voc_testcase_selected_case_id")
        default_index = (
            visible_case_ids.index(remembered_case_id)
            if remembered_case_id in visible_case_ids
            else 0
        )
        event = st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
            height=270,
            on_select=(
                partial(
                    _remember_catalog_case_selection,
                    table_key,
                    visible_case_ids,
                )
                if visible_case_ids
                else "rerun"
            ),
            selection_mode=(
                ["single-row-required", "single-cell"]
                if visible_case_ids
                else "single-row"
            ),
            selection_default=(
                {"selection": {"rows": [default_index]}}
                if visible_case_ids
                else None
            ),
            key=table_key,
            column_config={
                "Case ID": st.column_config.TextColumn(width=82, pinned=True),
                "검증 영역": st.column_config.TextColumn(width=110),
                "이름": st.column_config.TextColumn(width=150),
                "구현 상태": st.column_config.TextColumn(width=130),
            },
        )

    selected_rows = event.selection.rows if event else []
    if not selected_rows and visible_cases:
        selected_rows = [default_index]
    with browser_columns[2].container(
        border=True,
        height=380,
        key="voc_testcase_detail",
    ):
        st.markdown("#### :material/description: Case 상세")
        if not selected_rows:
            st.caption("목록에서 Case ID를 선택하세요.")
            st.markdown(
                """
                :blue-badge[선택한 Case의 검증 기준]

                선택 후 이 영역에서 등록 원본, 판정 기준과 VOC 입출력 조건을 간단히 확인할 수 있습니다.
                """
            )
        else:
            selected = visible_cases[selected_rows[0]]
            detail = testcase_details.get(selected.get("case_id"), {})
            group_label = groups.get(selected.get("group"), {}).get(
                "label", selected.get("group", "-")
            )
            status_label = status_labels.get(
                selected.get("implementation_status"), "-"
            )
            status_badge = (
                "green"
                if selected.get("implementation_status") == "IMPLEMENTED"
                else "orange"
            )
            st.markdown(
                f"**{selected.get('case_id')}** · {selected.get('name', '-')}"
            )
            st.markdown(
                f":blue-badge[{group_label}] "
                f":{status_badge}-badge[{status_label}]"
            )
            criteria_tab, conditions_tab = st.tabs(["판정 기준", "VOC 조건"])
            with criteria_tab:
                st.caption(f"등록 원본 · {selected.get('source_ref', '-')}")
                st.write(selected.get("acceptance", "-") or "-")
            with conditions_tab:
                if not detail:
                    st.caption("이 Case에는 별도의 VOC 질문 조건이 없습니다.")
                else:
                    st.markdown("**질문**")
                    st.write(detail.get("question", "-") or "-")
                    st.caption(f"예상 의도 · {detail.get('expected_intent', '-')}")
                    with st.expander(
                        "필수·금지 출력 조건",
                        icon=":material/rule:",
                    ):
                        output_columns = st.columns(2, gap="small")
                        with output_columns[0]:
                            st.markdown("**필수 출력**")
                            st.write(
                                "\n".join(
                                    f"- {item}"
                                    for item in detail.get("required_output", [])
                                )
                                or "-"
                            )
                        with output_columns[1]:
                            st.markdown("**금지 출력**")
                            st.write(
                                "\n".join(
                                    f"- {item}"
                                    for item in detail.get("prohibited_output", [])
                                )
                                or "-"
                            )


def render_analysis():
    with st.container(border=True):
        st.info("통합 런타임 Agent(6101~6106)가 RUNNING이어야 합니다.", icon=":material/hub:")
        question = st.text_area(
            "VOC 질문",
            placeholder="예: 모바일 앱에서 보험 갱신이 되지 않는 불만을 요약하고 개선안을 제안해 주세요.",
            height=120,
        )
        save_report = st.checkbox(
            "질문과 결과를 Reports/VOC에 저장합니다.",
            value=False,
            help="질문에 개인정보나 민감정보가 있으면 선택하지 마세요.",
        )
        if st.button("VOC 분석 실행", type="primary", icon=":material/analytics:", width="stretch"):
            with st.spinner("6개 Agent가 VOC를 처리하고 있습니다. 최대 3분 정도 걸릴 수 있습니다..."):
                st.session_state.voc_analysis_result = run_voc_analysis(question, save_report)

    payload = st.session_state.get("voc_analysis_result")
    if not payload:
        return
    result = payload.get("result", {})
    if result.get("ok"):
        st.success(result.get("message", "VOC 분석 완료"))
    else:
        st.warning(result.get("message") or result.get("error") or "VOC 분석 결과가 없습니다.")
    result_columns = st.columns(2, gap="medium")
    with result_columns[0].container(border=True, height="stretch"):
        st.markdown("### :material/summarize: 요약")
        st.write(result.get("summary", "-") or "-")
    with result_columns[1].container(border=True, height="stretch"):
        st.markdown("### :material/lightbulb: 정책 개선안")
        st.write(result.get("policy", "-") or "-")
    with st.expander("의도·평가·비평·Trace", icon=":material/account_tree:"):
        st.json({
            "intent_json": result.get("intent_json", "{}"),
            "eval_json": result.get("eval_json", "{}"),
            "summary_critic_json": result.get("summary_critic_json", "{}"),
            "trace": result.get("trace", ""),
            "error": result.get("error", ""),
        })
    if payload.get("reports"):
        st.caption(f"저장된 Report: {payload['reports']}")


def _rubric_rows(items: dict) -> list[dict]:
    rows = []
    for key, value in items.items():
        row = {
            "ID": key,
            "평가 항목": value.get("label"),
            "배점": value.get("max_points"),
            "세부 기준": ", ".join(
                f"{name} {score}" for name, score in value.get("criteria", {}).items()
            ),
        }
        if "pass_floor" in value:
            row["PASS 하한"] = value.get("pass_floor")
        rows.append(row)
    return rows


def _render_rules(title: str, rules: list[str]):
    st.markdown(f"### {title}")
    for rule in rules:
        st.markdown(f"- `{rule}`")


def _render_internal_pipeline_rubric():
    rubric = load_system_rubric()
    st.caption(
        "6개 Agent 80점 + Agent 연계 10점 + 장애·로그 5점 + 성능 5점으로 "
        "Pipeline 내부 실행 품질을 평가합니다."
    )
    st.dataframe(pd.DataFrame(_rubric_rows(rubric.get("categories", {}))), hide_index=True)
    st.markdown("### 배포 판정")
    st.dataframe(pd.DataFrame(rubric.get("deployment_decisions", [])), hide_index=True)
    _render_rules("점수와 무관한 즉시 배포 보류", rubric.get("immediate_deployment_hold", []))
    st.info(
        "현재는 평가 기준 정의 단계입니다. case별 점수·Run ID·Trace·Rubric 버전 저장은 "
        "Step 2~4 실행 이력에서 연결합니다."
    )


def _render_independent_judge_rubric():
    rubric = load_independent_judge_rubric()
    st.caption(
        f"{rubric.get('title')} · 기본 Provider: {rubric.get('default_provider')} "
        f"(실행 시 변경 가능) · Rubric {rubric.get('version')} · "
        "Evaluator·Critic과 분리된 외부 판정입니다."
    )
    st.dataframe(pd.DataFrame(_rubric_rows(rubric.get("dimensions", {}))), hide_index=True)
    st.markdown("### Judge 판정")
    st.dataframe(pd.DataFrame(rubric.get("decisions", [])), hide_index=True)
    _render_rules("점수와 무관한 즉시 FAIL", rubric.get("immediate_fail_rules", []))
    st.markdown("### 품질 점수와 분리하는 실행 상태")
    st.dataframe(
        pd.DataFrame(
            [
                {"상태": status, "의미": description}
                for status, description in rubric.get("non_quality_statuses", {}).items()
            ]
        ),
        hide_index=True,
    )
    st.info(
        "기준은 Step 1에서 등록했습니다. 실제 LLM Judge 호출, 모델 독립성 등급, case별 판정과 "
        "비용·시간 증적은 Step 5에서 구현합니다."
    )


def _render_improvement_validity_rubric():
    rubric = load_improvement_validity_rubric()
    st.caption(
        f"{rubric.get('title')} · Rubric {rubric.get('version')} · "
        "최종 개선안의 근거·실행 가능성과 사람 승인을 검증합니다."
    )
    st.dataframe(pd.DataFrame(_rubric_rows(rubric.get("dimensions", {}))), hide_index=True)
    st.markdown("### AI 자동 판정")
    st.dataframe(pd.DataFrame(rubric.get("automatic_decisions", [])), hide_index=True)
    st.markdown("### 승인 흐름")
    st.write(" → ".join(rubric.get("workflow_states", [])))
    st.warning(rubric.get("formal_approval_rule", ""))
    _render_rules("즉시 승인 보류", rubric.get("immediate_hold_rules", []))
    st.info(
        "기준은 Step 1에서 등록했습니다. VOC·Trace 연결, QA 검토, 업무 담당자 승인과 변경 이력은 "
        "Step 6에서 구현합니다."
    )


def _plain_editor_value(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    if hasattr(value, "item"):
        value = value.item()
    return value


def _score_value(value):
    number = float(_plain_editor_value(value))
    return int(number) if number.is_integer() else number


def _rubric_editor_rows(payload: dict, items_key: str) -> tuple[list[dict], list[dict]]:
    items = payload.get(items_key, {})
    include_pass_floor = any("pass_floor" in item for item in items.values())
    item_rows = []
    criterion_rows = []
    for item_id, item in items.items():
        row = {
            "ID": item_id,
            "평가 항목": item.get("label", ""),
            "배점": item.get("max_points", 0),
        }
        if include_pass_floor:
            row["PASS 하한"] = item.get("pass_floor")
        item_rows.append(row)
        for criterion_id, points in item.get("criteria", {}).items():
            criterion_rows.append(
                {
                    "평가 항목 ID": item_id,
                    "세부 기준 ID": criterion_id,
                    "점수": points,
                }
            )
    return item_rows, criterion_rows


def _build_edited_rubric(
    payload: dict,
    spec: dict,
    *,
    version: str,
    title: str | None,
    item_rows: list[dict],
    criterion_rows: list[dict],
    decision_rows: list[dict],
    hold_rules_text: str,
    default_provider: str | None = None,
) -> dict:
    edited = deepcopy(payload)
    edited["version"] = version.strip()
    if title is not None:
        edited["title"] = title.strip()
    if default_provider is not None:
        edited["default_provider"] = default_provider.strip()

    items = edited[spec["items_key"]]
    for row in item_rows:
        item = items[str(row["ID"])]
        item["label"] = str(row["평가 항목"]).strip()
        item["max_points"] = _score_value(row["배점"])
        if "PASS 하한" in row:
            item["pass_floor"] = _score_value(row["PASS 하한"])
    for row in criterion_rows:
        item_id = str(row["평가 항목 ID"])
        criterion_id = str(row["세부 기준 ID"])
        items[item_id]["criteria"][criterion_id] = _score_value(row["점수"])

    edited_decisions = []
    for row in decision_rows:
        edited_decisions.append(
            {
                key: _plain_editor_value(value)
                for key, value in row.items()
                if _plain_editor_value(value) is not None
            }
        )
    edited[spec["decisions_key"]] = edited_decisions
    edited[spec["hold_rules_key"]] = [
        line.strip() for line in hold_rules_text.splitlines() if line.strip()
    ]
    return edited


def _show_rubric_save_result(rubric_type: str, result: dict, saved_payload: dict):
    if not result.get("ok"):
        for error in result.get("errors", ["품질 평가 기준을 저장하지 못했습니다."]):
            st.error(error)
        return False
    if result.get("changed", True):
        saved_signature = _rubric_signature(saved_payload)
        st.session_state[f"voc_rubric_last_save_message_{rubric_type}"] = "변경완료"
        st.session_state[f"voc_rubric_last_saved_signature_{rubric_type}"] = saved_signature
        st.session_state[f"rubric_edit_{rubric_type}_draft"] = deepcopy(saved_payload)
        st.session_state[f"rubric_edit_{rubric_type}_source"] = saved_signature
    else:
        st.session_state[f"voc_rubric_last_save_message_{rubric_type}"] = "변경없음"
    return True


def _rubric_signature(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _rubric_save_state_pill(label: str, *, tone: str) -> str:
    colors = {
        "red": ("#b42318", "#fff1f0", "#f2b8b5"),
        "gray": ("#617083", "#f3f6fa", "#d8e1eb"),
    }
    color, background, border = colors.get(tone, colors["gray"])
    return (
        "<div style=\""
        "display:inline-flex;align-items:center;justify-content:center;"
        "height:27px;min-width:74px;padding:0 10px;border-radius:999px;"
        f"border:1px solid {border};background:{background};color:{color};"
        "font-size:12px;font-weight:800;line-height:1;white-space:nowrap;"
        "box-sizing:border-box;max-width:100%;overflow:hidden;text-overflow:ellipsis;"
        f"\">{escape(label)}</div>"
    )


def _highlight_rubric_version_input(rubric_type: str) -> None:
    widget_class = f"st-key-rubric_edit_{rubric_type}_widget_version"
    st.markdown(
        f"""
        <style>
        .{widget_class} input {{
            border-color:#d83f36!important;
            box-shadow:0 0 0 2px rgba(216,63,54,.14)!important;
            background:#fffafa!important;
        }}
        .{widget_class} label p {{
            color:#b42318!important;
            font-weight:800!important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _ordered_decision_rows(decisions: list[dict], spec: dict) -> list[dict]:
    """Return decision bands from the highest score to the lowest score."""
    min_key = spec["decision_min_key"]
    return sorted(
        (deepcopy(row) for row in decisions),
        key=lambda row: float(row.get(min_key, 0)),
        reverse=True,
    )


def _link_decision_ranges(
    decisions: list[dict],
    spec: dict,
    boundary_index: int,
    boundary_score: float,
) -> list[dict]:
    """Move one boundary and keep adjoining decision bands contiguous."""
    min_key = spec["decision_min_key"]
    max_key = spec["decision_max_key"]
    ordered = _ordered_decision_rows(decisions, spec)
    boundaries = [float(row[min_key]) for row in ordered[:-1]]
    boundaries[boundary_index] = round(float(boundary_score), 2)

    for index, row in enumerate(ordered):
        minimum = boundaries[index] if index < len(boundaries) else 0.0
        maximum = 100.0 if index == 0 else round(boundaries[index - 1] - 0.01, 2)
        row[min_key] = _score_value(minimum)
        row[max_key] = _score_value(maximum)
    return ordered


def _decision_display_frame(decisions: list[dict], spec: dict) -> pd.DataFrame:
    """Build the preview table with the user-facing decision first."""
    rows = []
    for row in _ordered_decision_rows(decisions, spec):
        rows.append({"decision": row.get("decision", ""), **{k: v for k, v in row.items() if k != "decision"}})
    return pd.DataFrame(rows)


def _rubric_draft(payload: dict, rubric_type: str) -> dict:
    draft_key = f"rubric_edit_{rubric_type}_draft"
    source_key = f"rubric_edit_{rubric_type}_source"
    source = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if st.session_state.get(source_key) != source:
        widget_prefix = f"rubric_edit_{rubric_type}_widget_"
        for key in list(st.session_state):
            if str(key).startswith(widget_prefix):
                del st.session_state[key]
        st.session_state[draft_key] = deepcopy(payload)
        st.session_state[source_key] = source
    return st.session_state[draft_key]


def _rubric_item_total(item: dict) -> float:
    return sum(float(value) for value in item.get("criteria", {}).values())


def _rubric_total(items: dict) -> float:
    return sum(_rubric_item_total(item) for item in items.values())


def _rubric_criterion_range(
    items: dict,
    item_id: str,
    criterion_id: str,
    *,
    total_budget: int = 100,
) -> tuple[int, int]:
    """Return a score range that cannot push the full rubric over its budget."""
    current_score = float(items[item_id].get("criteria", {}).get(criterion_id, 0))
    other_scores = _rubric_total(items) - current_score
    maximum = max(0, int(round(total_budget - other_scores)))
    return 0, maximum


def _render_rubric_transfer_tools(
    draft: dict,
    rubric_type: str,
    spec: dict,
    download_container=None,
    upload_container=None,
):
    if download_container is None or upload_container is None:
        download_container, upload_container = st.columns(2, gap="small")
    with download_container:
        st.download_button(
            "JSON D/L",
            data=(json.dumps(draft, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            file_name=Path(spec["relative_path"]).name,
            mime="application/json",
            icon=":material/download:",
            key=f"rubric_download_{rubric_type}",
            width="stretch",
        )
    with upload_container, st.popover(
            "JSON Up",
            icon=":material/upload_file:",
            key=f"rubric_upload_popover_{rubric_type}",
            width="stretch",
        ):
        uploaded = st.file_uploader(
            "Rubric JSON 파일",
            type=["json"],
            max_upload_size=1,
            key=f"rubric_upload_{rubric_type}",
            help="현재 선택한 평가 단계와 같은 구조의 JSON만 적용할 수 있습니다.",
        )
        if uploaded is None:
            st.caption("업로드한 파일은 검증을 통과한 뒤에만 저장됩니다.")
            return
        try:
            uploaded_payload = json.loads(uploaded.getvalue().decode("utf-8-sig"))
            upload_errors = validate_quality_rubric(rubric_type, uploaded_payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            uploaded_payload = None
            upload_errors = [f"JSON 파일을 해석할 수 없습니다: {exc}"]
        if upload_errors:
            for error in upload_errors:
                st.error(error)
            return
        st.success("업로드 파일 검증을 통과했습니다.")
        if st.button(
            "업로드 기준 적용",
            type="primary",
            icon=":material/check:",
            key=f"rubric_apply_upload_{rubric_type}",
            width="stretch",
        ):
            result = save_quality_rubric(rubric_type, uploaded_payload, source="json_upload")
            saved = _show_rubric_save_result(rubric_type, result, uploaded_payload)
            if saved:
                draft.clear()
                draft.update(deepcopy(uploaded_payload))
                st.rerun()


RUBRIC_CRITERION_KO_LABELS = {
    "intent": "의도 파악",
    "keywords": "핵심어 추출",
    "search_conditions": "검색 조건",
    "defaults_and_format": "기본값·형식",
    "recall": "검색 재현율",
    "precision": "검색 정밀도",
    "source_preservation": "출처 보존",
    "limit_and_error_handling": "제한·오류 처리",
    "factual_consistency": "사실 일관성",
    "coverage": "핵심 내용 포함",
    "deduplication_and_conciseness": "중복 제거·간결성",
    "format_and_readability": "형식·가독성",
    "criteria_consistency": "평가 기준 일관성",
    "winner_correctness": "우수안 판정 정확성",
    "evidence_validity": "근거 타당성",
    "format_and_repeatability": "형식·반복 가능성",
    "defect_detection": "결함 탐지",
    "risk_detection": "위험 탐지",
    "edit_actionability": "수정 실행 가능성",
    "false_positive_control": "오탐 통제",
    "voc_grounding": "VOC 근거 반영",
    "specificity": "구체성",
    "feasibility": "실행 가능성",
    "measurability": "측정 가능성",
    "priority": "우선순위",
    "trace_completeness": "Trace 완전성",
    "data_transfer_integrity": "데이터 전달 무결성",
    "upstream_result_usage": "이전 단계 결과 활용",
    "no_duplicate_calls": "중복 호출 방지",
    "explicit_failure_response": "명확한 실패 응답",
    "traceable_error_log": "추적 가능한 오류 로그",
    "recovery_and_cleanup": "복구·정리",
    "end_to_end_response_time": "전체 응답시간",
    "timeout_compliance": "타임아웃 준수",
    "per_agent_timing_visibility": "Agent별 소요시간 표시",
    "complaint_type_and_cause": "불만 유형·원인 정확성",
    "impact_consistency": "영향 일관성",
    "policy_statement_correctness": "정책 설명 정확성",
    "question_relevance": "질문 관련성",
    "voc_source_traceability": "VOC 출처 추적성",
    "no_unsupported_claim": "근거 없는 주장 방지",
    "source_meaning_preservation": "원문 의미 보존",
    "uncertainty_disclosure": "불확실성 명시",
    "required_issue_coverage": "필수 이슈 포함",
    "cause_impact_action_coverage": "원인·영향·조치 포함",
    "compound_complaint_coverage": "복합 불만 포함",
    "no_critical_omission": "핵심 누락 방지",
    "action_detail": "조치 상세성",
    "owner_and_priority": "담당·우선순위",
    "measurable_kpi": "측정 가능한 KPI",
    "clear_language": "명확한 표현",
    "no_sensitive_data_exposure": "민감정보 노출 방지",
    "no_fabricated_guarantee": "허위 보장 방지",
    "failure_transparency": "실패 투명성",
    "safe_escalation": "안전한 상향 보고",
    "complaint_to_root_cause": "불만-근본원인 연결",
    "root_cause_to_action": "근본원인-조치 연결",
    "expected_customer_impact": "예상 고객 영향",
    "voc_id_reference": "VOC ID 참조",
    "trace_and_agent_reference": "Trace·Agent 참조",
    "no_unsupported_evidence": "근거 없는 증적 방지",
    "process_feasibility": "업무 절차 실행 가능성",
    "technical_feasibility": "기술 실행 가능성",
    "resource_and_dependency_awareness": "자원·의존성 고려",
    "responsible_owner": "담당자 명확성",
    "target_schedule": "목표 일정",
    "customer_and_operational_risk": "고객·운영 위험",
    "privacy_and_security": "개인정보·보안",
    "compliance_and_escalation": "규제 준수·상향 보고",
}


RUBRIC_ITEM_PANEL_HEIGHT = 460
RUBRIC_CRITERIA_PANEL_MIN_HEIGHT = 430
RUBRIC_WEIGHT_CHART_HEIGHT = 112
RUBRIC_DETAIL_DIALOG_WIDTH = "medium"
RUBRIC_DETAIL_NAV_STYLE = """
<style>
[class*="st-key-rubric_detail_previous_"] button,
[class*="st-key-rubric_detail_next_"] button {
    background: #F2F6FB;
    border: 1px solid #B9CBE0;
    color: #345F8A;
    box-shadow: none;
    font-weight: 600;
}
[class*="st-key-rubric_detail_previous_"] button:hover,
[class*="st-key-rubric_detail_next_"] button:hover {
    background: #E8F0F8;
    border-color: #8EADCC;
    color: #244F78;
}
[class*="st-key-rubric_detail_previous_"] button:focus,
[class*="st-key-rubric_detail_next_"] button:focus {
    border-color: #789DC2;
    box-shadow: 0 0 0 0.12rem rgba(72, 116, 158, 0.16);
}
[class*="st-key-rubric_criteria_panel_"] {
    min-height: %dpx;
    overflow: visible;
}
</style>
""" % RUBRIC_CRITERIA_PANEL_MIN_HEIGHT


def _rubric_criterion_label(criterion_id: str) -> str:
    korean = RUBRIC_CRITERION_KO_LABELS.get(
        criterion_id,
        criterion_id.replace("_", " ").title(),
    )
    return f"{korean} ({criterion_id})"


def _build_rubric_weight_chart(item_label: str, item_total: float) -> alt.LayerChart:
    selected_score = max(0.0, min(float(item_total), 100.0))
    chart_rows = pd.DataFrame(
        [
            {
                "구분": item_label,
                "배점": selected_score,
                "색상": "선택 평가 항목",
                "순서": 1,
            },
            {
                "구분": "나머지 평가 항목",
                "배점": 100.0 - selected_score,
                "색상": "나머지 평가 항목",
                "순서": 2,
            },
        ]
    )
    arc = (
        alt.Chart(chart_rows)
        .mark_arc(innerRadius=34, outerRadius=50, cornerRadius=4)
        .encode(
            theta=alt.Theta("배점:Q", stack=True),
            color=alt.Color(
                "색상:N",
                scale=alt.Scale(
                    domain=["선택 평가 항목", "나머지 평가 항목"],
                    range=["#1769AA", "#E3EAF2"],
                ),
                legend=None,
            ),
            order=alt.Order("순서:O"),
            tooltip=[
                alt.Tooltip("구분:N"),
                alt.Tooltip("배점:Q", format=".0f", title="배점"),
            ],
        )
    )
    score_text = (
        alt.Chart(pd.DataFrame([{"text": f"{selected_score:g}점"}]))
        .mark_text(fontSize=18, fontWeight=700, color="#0B4F91", dy=-6)
        .encode(text="text:N")
    )
    total_text = (
        alt.Chart(pd.DataFrame([{"text": "전체 100점 중"}]))
        .mark_text(fontSize=10, color="#66788A", dy=13)
        .encode(text="text:N")
    )
    return (arc + score_text + total_text).properties(height=RUBRIC_WEIGHT_CHART_HEIGHT)


def _selected_rubric_item_id(
    item_ids: list[str],
    selection_state: dict | None,
    fallback: str,
) -> str:
    selected_row = _table_selected_row_index(selection_state, len(item_ids))
    if selected_row is not None:
        return item_ids[selected_row]
    return fallback


def _sync_rubric_item_selection(
    table_key: str,
    selected_key: str,
    item_ids: list[str],
):
    suppress_key = f"{selected_key}_suppress_detail_dialog_once"
    if st.session_state.pop(suppress_key, False):
        return
    selected_row = _promote_table_cell_to_row_selection(
        table_key,
        len(item_ids),
    )
    if selected_row is not None:
        selected_id = item_ids[selected_row]
        st.session_state[selected_key] = selected_id
        st.session_state[f"{selected_key}_detail_dialog_request"] = selected_id


def _navigate_rubric_detail_dialog(
    rubric_type: str,
    item_ids: list[str],
    item_id: str,
):
    """팝업 항목만 이동하고 목록은 선택 항목 상태로 다음 전체 렌더에서 맞춥니다."""
    if item_id not in item_ids:
        return
    selected_key = f"rubric_edit_{rubric_type}_selected_item"
    dialog_key = f"{selected_key}_detail_dialog_item"
    opened_key = f"{dialog_key}_opened"
    st.session_state[selected_key] = item_id
    st.session_state[dialog_key] = item_id
    st.session_state[opened_key] = True


def _clear_rubric_detail_dialog_state(rubric_type: str):
    selected_key = f"rubric_edit_{rubric_type}_selected_item"
    dialog_key = f"{selected_key}_detail_dialog_item"
    st.session_state.pop(f"{selected_key}_detail_dialog_request", None)
    st.session_state.pop(dialog_key, None)
    st.session_state.pop(f"{dialog_key}_opened", None)


def _dismiss_rubric_detail_dialog():
    for rubric_type in QUALITY_RUBRIC_SPECS:
        _clear_rubric_detail_dialog_state(rubric_type)


def _complete_rubric_detail_dialog(rubric_type: str):
    selected_key = f"rubric_edit_{rubric_type}_selected_item"
    dialog_key = f"{selected_key}_detail_dialog_item"
    st.session_state.pop(f"{selected_key}_detail_dialog_request", None)
    st.session_state.pop(dialog_key, None)
    # Dialog 조각 rerun이 먼저 발생하므로 전체 앱 rerun을 유도할 표식을 남깁니다.
    st.session_state[f"{dialog_key}_opened"] = True


@st.dialog(
    "세부 배점 설정",
    width=RUBRIC_DETAIL_DIALOG_WIDTH,
    icon=":material/tune:",
    on_dismiss=_dismiss_rubric_detail_dialog,
)
def _rubric_item_detail_dialog(
    draft: dict,
    rubric_type: str,
    spec: dict,
    selected_id: str,
):
    items = draft.get(spec["items_key"], {})
    item_ids = list(items)
    selected_key = f"rubric_edit_{rubric_type}_selected_item"
    dialog_key = f"{selected_key}_detail_dialog_item"
    opened_key = f"{dialog_key}_opened"
    if st.session_state.get(dialog_key) not in items:
        if st.session_state.get(opened_key):
            st.session_state.pop(opened_key, None)
            st.rerun(scope="app")
        st.session_state[dialog_key] = selected_id
        st.session_state[opened_key] = True
    selected_id = st.session_state[dialog_key]
    if selected_id not in items or not item_ids:
        st.warning("선택한 평가 항목을 찾을 수 없습니다.")
        return
    selected_index = item_ids.index(selected_id)
    previous_id = item_ids[(selected_index - 1) % len(item_ids)]
    next_id = item_ids[(selected_index + 1) % len(item_ids)]
    item = items[selected_id]
    prefix = f"rubric_edit_{rubric_type}_widget_{selected_id}"
    other_item_total = _rubric_total(items) - _rubric_item_total(item)
    item_budget = max(0, int(round(100 - other_item_total)))
    item_total = _rubric_item_total(item)
    st.html(RUBRIC_DETAIL_NAV_STYLE)
    previous_col, title_col, chart_col, next_col = st.columns(
        [1.35, 4.6, 2.4, 1.35],
        gap="small",
        vertical_alignment="center",
    )
    with previous_col:
        st.button(
            "< 이전",
            type="secondary",
            key=f"rubric_detail_previous_{rubric_type}_{selected_id}",
            help=f"이전 · {items[previous_id].get('label', previous_id)}",
            on_click=_navigate_rubric_detail_dialog,
            args=(rubric_type, item_ids, previous_id),
            width="stretch",
        )
    with title_col:
        st.markdown(f"#### {item.get('label', selected_id)}")
        st.caption(
            f"{selected_index + 1} / {len(item_ids)} · "
            f"세부 배점 입력 가능 범위 0~{item_budget}점"
        )
    with chart_col:
        chart_slot = st.empty()
    with next_col:
        st.button(
            "다음 >",
            type="secondary",
            key=f"rubric_detail_next_{rubric_type}_{selected_id}",
            help=f"다음 · {items[next_id].get('label', next_id)}",
            on_click=_navigate_rubric_detail_dialog,
            args=(rubric_type, item_ids, next_id),
            width="stretch",
        )

    with st.container(
        border=False,
        key=f"rubric_criteria_panel_{rubric_type}_{selected_id}",
    ):
        for criterion_id, points in list(item.get("criteria", {}).items()):
            minimum, maximum = _rubric_criterion_range(
                items,
                selected_id,
                criterion_id,
            )
            score = st.slider(
                _rubric_criterion_label(criterion_id),
                min_value=minimum,
                max_value=maximum,
                value=max(minimum, min(int(round(float(points))), maximum)),
                step=1,
                format="%d점",
                key=f"{prefix}_criterion_{criterion_id}",
                help=(
                    f"전체 평가 기준 100점 예산을 초과하지 않도록 이 세부 배점은 "
                    f"{minimum}~{maximum}점 범위에서 입력할 수 있습니다."
                ),
            )
            if score != points:
                item["criteria"][criterion_id] = score
                item["max_points"] = _score_value(_rubric_item_total(item))
                if "pass_floor" in item and float(item["pass_floor"]) > float(item["max_points"]):
                    item["pass_floor"] = item["max_points"]

        item_total = _rubric_item_total(item)
        item["max_points"] = _score_value(item_total)
        if "pass_floor" in item:
            pass_floor = st.slider(
                "PASS 하한",
                min_value=1,
                max_value=max(1, int(round(item_total))),
                value=max(1, min(int(round(float(item.get("pass_floor", 1)))), int(round(item_total)))),
                step=1,
                format="%d점",
                key=f"{prefix}_pass_floor",
                help="평가 항목 배점을 넘지 않는 범위에서 설정합니다.",
            )
            item["pass_floor"] = pass_floor

    chart_slot.altair_chart(
        _build_rubric_weight_chart(
            str(item.get("label", selected_id)),
            item_total,
        )
    )

    with st.container(horizontal=True, horizontal_alignment="right"):
        st.button(
            "설정 완료",
            type="primary",
            icon=":material/check:",
            key=f"rubric_detail_done_{rubric_type}_{selected_id}",
            on_click=_complete_rubric_detail_dialog,
            args=(rubric_type,),
        )


def _render_rubric_items(draft: dict, rubric_type: str, spec: dict):
    items = draft.get(spec["items_key"], {})
    item_ids = list(items)
    selected_key = f"rubric_edit_{rubric_type}_selected_item"
    if st.session_state.get(selected_key) not in items:
        st.session_state[selected_key] = item_ids[0]
    selected_id = st.session_state[selected_key]

    with st.container(
        border=True,
        height=RUBRIC_ITEM_PANEL_HEIGHT,
        key=f"rubric_item_list_{rubric_type}",
    ):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
        ):
            st.markdown("### 항목별 배점 설정")
            _render_rubric_total_summary(draft, spec)
        item_frame = pd.DataFrame(
            [
                {
                    "ID": item_id,
                    "평가 항목": item.get("label", ""),
                    "배점": _score_value(_rubric_item_total(item)),
                }
                for item_id, item in items.items()
            ]
        )
        default_row = item_ids.index(selected_id)
        table_key = f"rubric_edit_{rubric_type}_widget_item_table"
        st.dataframe(
            item_frame,
            hide_index=True,
            on_select=partial(
                _sync_rubric_item_selection,
                table_key,
                selected_key,
                item_ids,
            ),
            selection_mode=["single-row-required", "single-cell"],
            selection_default={"selection": {"rows": [default_row]}},
            key=table_key,
            column_config={
                "ID": None,
                "배점": st.column_config.ProgressColumn(
                    "배점",
                    min_value=0,
                    max_value=100,
                    format="%g점",
                ),
            },
            height=min(430, 38 + len(item_frame) * 35),
        )
    request_key = f"{selected_key}_detail_dialog_request"
    dialog_key = f"{selected_key}_detail_dialog_item"
    opened_key = f"{dialog_key}_opened"
    if st.session_state.pop(f"{selected_key}_suppress_detail_dialog_once", False):
        st.session_state.pop(request_key, None)
    requested_item = st.session_state.pop(request_key, None)
    if requested_item in items:
        st.session_state[dialog_key] = requested_item
        st.session_state[opened_key] = True
    elif dialog_key not in st.session_state:
        st.session_state.pop(opened_key, None)
    dialog_item = st.session_state.get(dialog_key)
    if dialog_item in items:
        _rubric_item_detail_dialog(
            draft,
            rubric_type,
            spec,
            dialog_item,
        )


def _render_rubric_total_summary(draft: dict, spec: dict):
    total = _rubric_total(draft.get(spec["items_key"], {}))
    complete = abs(total - 100.0) < 0.001
    if complete:
        first_line = f"{total:g} / 100점 배점 구성 완료"
        second_line = "저장 가능한 배점 구성입니다."
        accent = "#155a96"
        background = "#f3f8fd"
        border = "#b9cee2"
    else:
        first_line = f"{total:g} / 100점 배점 조정 필요"
        second_line = f"100점까지 {100 - total:+g}점 조정이 필요합니다."
        accent = "#b42318"
        background = "#fff7f6"
        border = "#f2b8b5"
    st.markdown(
        f"""
        <div style="
            display:flex;flex-direction:column;align-items:flex-end;justify-content:center;gap:3px;
            min-width:190px;max-width:260px;padding:5px 9px;border:1px solid {border};
            border-radius:10px;background:{background};box-sizing:border-box;line-height:1.2;
        ">
            <div style="display:block;font-size:12px;font-weight:850;color:{accent};white-space:nowrap;">
                {escape(first_line)}
            </div>
            <div style="display:block;font-size:10px;font-weight:700;color:{accent};opacity:.82;white-space:nowrap;">
                {escape(second_line)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.dialog(
    "판정 구간 미리보기",
    width="large",
    icon=":material/table_view:",
)
def _rubric_decision_preview_dialog(draft: dict, spec: dict):
    decision_frame = _decision_display_frame(
        draft.get(spec["decisions_key"], []),
        spec,
    )
    ordered_columns = [
        "decision",
        spec["decision_min_key"],
        spec["decision_max_key"],
        *[
            column
            for column in decision_frame.columns
            if column
            not in {
                "decision",
                spec["decision_min_key"],
                spec["decision_max_key"],
            }
        ],
    ]
    st.dataframe(
        decision_frame,
        hide_index=True,
        column_order=ordered_columns,
        column_config={
            "decision": st.column_config.TextColumn("decision", pinned=True),
        },
    )


def _render_decision_gauges(draft: dict, rubric_type: str, spec: dict):
    decisions_key = spec["decisions_key"]
    min_key = spec["decision_min_key"]
    ordered = _ordered_decision_rows(draft.get(decisions_key, []), spec)

    with st.container(
        border=True,
        height=RUBRIC_ITEM_PANEL_HEIGHT,
        key=f"rubric_decision_section_{rubric_type}",
    ):
        st.markdown("### 판정 구간")
        st.caption("시작 점수를 조정하면 맞닿은 상·하위 판정의 최소·최대 점수가 함께 변경됩니다.")
        for index, row in enumerate(ordered[:-1]):
            lower_bound = round(float(ordered[index + 1][min_key]) + 0.01, 2)
            upper_bound = 100.0 if index == 0 else round(float(ordered[index - 1][min_key]) - 0.01, 2)
            boundary = st.slider(
                f"{row.get('decision', '-')} 시작 점수",
                min_value=lower_bound,
                max_value=upper_bound,
                value=float(row[min_key]),
                step=0.01,
                format="%.2f점",
                key=f"rubric_edit_{rubric_type}_widget_decision_{index}",
            )
            if abs(boundary - float(row[min_key])) > 0.001:
                draft[decisions_key] = _link_decision_ranges(
                    ordered,
                    spec,
                    index,
                    boundary,
                )
                st.rerun()

        if st.button(
            "판정 구간 미리보기",
            icon=":material/visibility:",
            key=f"rubric_decision_preview_{rubric_type}",
            width="stretch",
        ):
            _rubric_decision_preview_dialog(draft, spec)

        with st.expander("즉시 FAIL·보류 규칙", icon=":material/warning:"):
            hold_rules_text = st.text_area(
                "한 줄에 한 규칙",
                value="\n".join(draft.get(spec["hold_rules_key"], [])),
                height=140,
                key=f"rubric_edit_{rubric_type}_widget_hold_rules",
            )
            draft[spec["hold_rules_key"]] = [
                line.strip()
                for line in hold_rules_text.splitlines()
                if line.strip()
            ]


def _render_rubric_management(stage: str):
    rubric_type = RUBRIC_STAGE_TYPES[stage]
    spec = QUALITY_RUBRIC_SPECS[rubric_type]
    payload = load_quality_rubric(rubric_type)
    draft = _rubric_draft(payload, rubric_type)

    version_col, title_col, provider_col, action_col = st.columns(
        [1.0, 1.8, 1.4, 2.6],
        gap="small",
        vertical_alignment="bottom",
    )
    with version_col:
        version_widget_key = f"rubric_edit_{rubric_type}_widget_version"
        previous_version_key = f"{version_widget_key}_previous"
        version = st.text_input(
            "Rubric 버전",
            value=str(draft.get("version", "")),
            key=version_widget_key,
            help="기준 내용을 변경해 저장할 때는 이전과 다른 버전을 입력해야 합니다.",
        )
        previous_version = st.session_state.get(previous_version_key)
        if previous_version is not None and str(previous_version) != str(version):
            selected_key = f"rubric_edit_{rubric_type}_selected_item"
            st.session_state[f"{selected_key}_suppress_detail_dialog_once"] = True
            st.session_state.pop(f"{selected_key}_detail_dialog_request", None)
        st.session_state[previous_version_key] = str(version)
        draft["version"] = version.strip()
        original_version = str(payload.get("version", "")).strip()
    with title_col:
        default_titles = {
            "internal_pipeline": "내부 Pipeline 품질 평가 기준",
            "independent_judge": "독립 LLM Judge 100점 평가 기준",
            "improvement_validity": "최종 개선안 타당성 100점 검증 기준",
        }
        title = st.text_input(
            "기준명",
            value=str(draft.get("title") or default_titles[rubric_type]),
            key=f"rubric_edit_{rubric_type}_widget_title",
        )
        draft["title"] = title.strip()
    with provider_col:
        if rubric_type == "independent_judge":
            current_provider = str(draft.get("default_provider") or "anthropic")
            provider_options = list(
                dict.fromkeys(
                    [current_provider, "anthropic", "openai", "google", "azure_openai"]
                )
            )
            draft["default_provider"] = st.selectbox(
                "기본 Judge Provider",
                provider_options,
                index=provider_options.index(current_provider),
                accept_new_options=True,
                key=f"rubric_edit_{rubric_type}_widget_provider",
            )
        else:
            st.selectbox(
                "기본 Judge Provider",
                ["해당 없음"],
                disabled=True,
                key=f"rubric_edit_{rubric_type}_widget_provider",
            )
    with action_col:
        download_col, upload_col, spacer_col, save_col = st.columns(
            [1.0, 1.0, 0.35, 1.45],
            gap="small",
            vertical_alignment="bottom",
        )
        _render_rubric_transfer_tools(
            draft,
            rubric_type,
            spec,
            download_container=download_col,
            upload_container=upload_col,
        )
        with spacer_col:
            st.empty()
        header_validation_errors = validate_quality_rubric(
            rubric_type,
            draft,
        )
        draft_signature = _rubric_signature(draft)
        payload_signature = _rubric_signature(payload)
        saved_signature = st.session_state.get(
            f"voc_rubric_last_saved_signature_{rubric_type}"
        )
        has_rubric_changes = draft_signature != payload_signature
        needs_version_change = has_rubric_changes and draft.get("version", "") == original_version
        if needs_version_change:
            _highlight_rubric_version_input(rubric_type)
        save_button_help = (
            "Rubric 버전을 변경해야 저장할 수 있습니다."
            if needs_version_change
            else "변경된 평가 기준을 저장합니다."
        )
        with save_col:
            if needs_version_change:
                st.markdown(_rubric_save_state_pill("변경발생", tone="red"), unsafe_allow_html=True)
            elif has_rubric_changes:
                st.markdown(_rubric_save_state_pill("변경발생", tone="red"), unsafe_allow_html=True)
            elif (
                st.session_state.get(f"voc_rubric_last_save_message_{rubric_type}") == "변경완료"
                and saved_signature == draft_signature
            ):
                st.markdown(_rubric_save_state_pill("변경완료", tone="gray"), unsafe_allow_html=True)
            else:
                st.markdown(_rubric_save_state_pill("변경없음", tone="gray"), unsafe_allow_html=True)
            if st.button(
                "평가 기준 저장",
                type="primary",
                icon=":material/save:",
                key=f"rubric_edit_{rubric_type}_save",
                width="stretch",
                help=save_button_help,
                disabled=bool(header_validation_errors) or not has_rubric_changes or needs_version_change,
            ):
                saved_payload = deepcopy(draft)
                saved = _show_rubric_save_result(
                    rubric_type,
                    save_quality_rubric(
                        rubric_type,
                        saved_payload,
                        source="screen_editor",
                    ),
                    saved_payload,
                )
                if saved:
                    st.rerun()

    score_col, decision_col = st.columns(
        2,
        gap="small",
        vertical_alignment="top",
    )
    with score_col:
        _render_rubric_items(draft, rubric_type, spec)
    with decision_col:
        _render_decision_gauges(draft, rubric_type, spec)

    validation_errors = validate_quality_rubric(rubric_type, draft)
    if validation_errors:
        with st.expander(f"저장 전 확인 필요 · {len(validation_errors)}건", icon=":material/error:"):
            for error in validation_errors:
                st.markdown(f"- {error}")


def render_rubric():
    stage = st.segmented_control(
        "수정할 평가 단계",
        RUBRIC_STAGE_OPTIONS,
        default=RUBRIC_STAGE_OPTIONS[0],
        key="voc_quality_rubric_stage",
        label_visibility="collapsed",
        on_change=_dismiss_rubric_detail_dialog,
    )
    selected_stage = stage or RUBRIC_STAGE_OPTIONS[0]
    _render_rubric_management(selected_stage)


@st.cache_data(ttl=3, max_entries=1, show_spinner=False)
def _load_voc_defect_rows():
    return list_voc_defects()


def _clear_voc_defect_caches():
    _load_voc_defect_rows.clear()
    _load_voc_history_rows.clear()


def _defect_status_label(status: str) -> str:
    return {
        "OPEN": "접수",
        "ANALYZED": "분석 완료",
        "FIXED": "조치 완료",
        "RETESTED": "재시험 완료",
        "CLOSED": "종료",
    }.get(status, status or "-")


def _render_defect_create():
    st.markdown("### 신규 결함 등록")
    st.caption("미확인 이슈는 PENDING으로 등록하고 원본 Run·Case·Trace 확인 후 CONFIRMED로 전환합니다.")
    history = [row for row in _load_voc_history_rows() if row.get("status") != "RUNNING"]
    run_options = [""] + [row["run_id"] for row in history]
    selected_run_id = st.selectbox(
        "원본 Run ID (선택)",
        run_options,
        format_func=lambda value: value or "연결하지 않음",
        key="defect_create_run",
    )
    selected_cases = []
    if selected_run_id:
        selected_row = next(row for row in history if row["run_id"] == selected_run_id)
        selected_cases = st.multiselect(
            "관련 Case ID", selected_row.get("selected_case_ids", []), key="defect_create_cases"
        )

    with st.form("voc_defect_create_form", border=True):
        title = st.text_input("결함 제목")
        columns = st.columns(3)
        severity = columns[0].selectbox("심각도", ["CRITICAL", "HIGH", "MEDIUM", "LOW"], index=1)
        category = columns[1].selectbox(
            "결함 분류",
            ["INTERFACE_BRANCH", "API_RATE_LIMIT", "AGENT_FAILURE", "DATA", "PERFORMANCE", "OTHER"],
        )
        evidence_status = columns[2].selectbox("증적 상태", ["PENDING", "CONFIRMED"])
        description = st.text_area("현상 및 재현 정보", height=120)
        trace_text = st.text_input("관련 Trace ID", help="여러 건은 쉼표로 구분합니다.")
        metadata_columns = st.columns(3)
        actor = metadata_columns[0].text_input("등록자", value="QA")
        candidate_key = metadata_columns[1].text_input("후보 결함 키 (선택)")
        jira_key = metadata_columns[2].text_input("Jira Key (선택)")
        submitted = st.form_submit_button("결함 등록", type="primary", icon=":material/add_circle:")

    if submitted:
        try:
            defect = create_voc_defect(
                title=title,
                severity=severity,
                category=category,
                description=description,
                actor=actor,
                evidence_status=evidence_status,
                related_run_ids=[selected_run_id] if selected_run_id else [],
                related_case_ids=selected_cases,
                related_trace_ids=[value.strip() for value in trace_text.split(",") if value.strip()],
                candidate_key=candidate_key,
                jira_key=jira_key,
            )
        except Exception as exc:
            st.error(f"결함을 등록하지 못했습니다: {exc}")
        else:
            _clear_voc_defect_caches()
            st.session_state.voc_selected_defect_id = defect["defect_id"]
            st.success(f"결함을 등록했습니다: {defect['defect_id']}")


def _eligible_retest_runs(defect: dict) -> list[str]:
    originals = set(defect.get("related_run_ids", []))
    eligible = []
    for row in _load_voc_history_rows():
        if row.get("run_type") != "RETEST" or row.get("status") == "RUNNING":
            continue
        try:
            detail = load_voc_run_history_detail(row["run_id"])
        except Exception:
            continue
        parent = detail.get("manifest", {}).get("run_metadata", {}).get("parent_run_id")
        if parent in originals:
            eligible.append(row["run_id"])
    return eligible


def _change_defect_status(defect_id: str, target: str, actor: str, comment: str, fields: dict):
    try:
        transition_voc_defect(
            defect_id, target_status=target, actor=actor, comment=comment, fields=fields
        )
    except Exception as exc:
        st.error(f"상태를 변경하지 못했습니다: {exc}")
        return
    _clear_voc_defect_caches()
    st.success(f"결함 상태를 {_defect_status_label(target)}로 변경했습니다.")
    st.rerun()


def _render_isolated_fault_tests():
    st.markdown("### 격리 장애시험")
    st.caption("운영 Agent와 실제 키를 변경하지 않는 격리 모드로 6개 장애를 재현합니다.")
    scenarios = [
        ("FT-01", "Retriever 종료"), ("FT-02", "포트 충돌"), ("FT-03", "CSV 파일 누락"),
        ("FT-04", "API 키 오류"), ("FT-05", "응답 지연"), ("FT-06", "빈 검색 결과"),
    ]
    st.dataframe(pd.DataFrame(scenarios, columns=["ID", "장애 상황"]), hide_index=True, width="stretch")
    if st.button("장애 진단 6종 실행", type="primary"):
        _run_and_store(run_diagnostics, "fault")
    _show_command_result()
    reports = list_reports("장애 진단 Fault")
    latest = next((item for item in reports if item["name"] == "latest.md"), None)
    if latest:
        st.markdown(read_report(latest["path"]))


def _render_defect_transition(defect: dict):
    defect_id = defect["defect_id"]
    status = defect.get("status")
    st.markdown("#### 다음 상태 처리")

    if status == "OPEN":
        with st.form(f"analyze_{defect_id}", border=True):
            root_cause = st.text_area("원인 분석")
            impact = st.text_area("영향 범위")
            evidence_status = st.selectbox(
                "증적 상태", ["PENDING", "CONFIRMED"],
                index=0 if defect.get("evidence_status") == "PENDING" else 1,
            )
            actor = st.text_input("처리자", value="QA")
            comment = st.text_input("처리 의견", value="원인 및 영향 분석 완료")
            submitted = st.form_submit_button("분석 완료 처리", type="primary")
        if submitted:
            _change_defect_status(
                defect_id, "ANALYZED", actor, comment,
                {"root_cause": root_cause, "impact": impact, "evidence_status": evidence_status},
            )
        return

    if status == "ANALYZED":
        with st.form(f"fix_{defect_id}", border=True):
            corrective_action = st.text_area("조치 내용")
            columns = st.columns(2)
            owner = columns[0].text_input("담당자", value="QA")
            due_date = columns[1].date_input("조치 기한")
            actor = st.text_input("처리자", value="QA")
            comment = st.text_input("처리 의견", value="조치 반영 완료")
            submitted = st.form_submit_button("조치 완료 처리", type="primary")
        if submitted:
            _change_defect_status(
                defect_id, "FIXED", actor, comment,
                {"corrective_action": corrective_action, "owner": owner, "due_date": due_date.isoformat()},
            )
        return

    if status == "FIXED":
        related_cases = defect.get("related_case_ids", [])
        original_runs = []
        for run_id in defect.get("related_run_ids", []):
            try:
                detail = load_voc_run_history_detail(run_id)
            except Exception:
                continue
            if detail.get("manifest", {}).get("run_type") != "RETEST":
                original_runs.append(run_id)

        if original_runs and related_cases:
            st.info("원본 Run과 동일한 Case로 연결된 RETEST를 실행한 뒤 PASS 결과를 선택하세요.")
            parent_run_id = st.selectbox(
                "재시험 기준 원본 Run", original_runs, key=f"retest_parent_{defect_id}"
            )
            active_run_id = st.session_state.get("voc_batch_run_id")
            is_running = bool(
                active_run_id
                and get_batch_run_progress(active_run_id).get("status") == "RUNNING"
            )
            if st.button(
                f"관련 Case {len(related_cases)}건 재시험 시작",
                type="primary", icon=":material/replay:", disabled=is_running,
                key=f"start_retest_{defect_id}",
            ):
                _launch_batch(
                    related_cases, parent_run_id=parent_run_id, judge_config={"enabled": False}
                )
                st.rerun()
            if active_run_id:
                _live_batch_progress()
        else:
            st.warning("재시험을 만들려면 결함에 원본 Run과 관련 Case가 모두 연결되어 있어야 합니다.")

        retest_runs = _eligible_retest_runs(defect)
        if not retest_runs:
            st.caption("연결 가능한 완료 RETEST가 없습니다. 재시험을 먼저 실행하세요.")
            return
        with st.form(f"retested_{defect_id}", border=True):
            retest_run_id = st.selectbox("PASS 재시험 Run", retest_runs)
            actor = st.text_input("처리자", value="QA")
            comment = st.text_input("처리 의견", value="연결 재시험 결과 확인")
            submitted = st.form_submit_button("재시험 완료 처리", type="primary")
        if submitted:
            _change_defect_status(
                defect_id, "RETESTED", actor, comment, {"retest_run_id": retest_run_id}
            )
        return

    if status == "RETESTED":
        with st.form(f"close_{defect_id}", border=True):
            closure_comment = st.text_area("종료 근거")
            actor = st.text_input("처리자", value="QA")
            comment = st.text_input("처리 의견", value="PASS 재시험 증적 확인 후 종료")
            submitted = st.form_submit_button("결함 종료", type="primary")
        if submitted:
            _change_defect_status(
                defect_id, "CLOSED", actor, comment, {"closure_comment": closure_comment}
            )
        return

    st.success("PASS 재시험 증적을 근거로 종료된 결함입니다.")


def _render_defect_list():
    defects = _load_voc_defect_rows()
    if not defects:
        st.info("등록된 결함이 없습니다. 신규 등록에서 첫 결함을 등록하세요.")
        return

    columns = st.columns(4)
    columns[0].metric("전체", len(defects))
    columns[1].metric("미종료", sum(item.get("status") != "CLOSED" for item in defects))
    columns[2].metric(
        "미종료 중요 결함",
        sum(item.get("status") != "CLOSED" and item.get("severity") in {"CRITICAL", "HIGH"} for item in defects),
    )
    columns[3].metric("종료", sum(item.get("status") == "CLOSED" for item in defects))

    filters = st.columns(2)
    status_filter = filters[0].multiselect(
        "상태", ["OPEN", "ANALYZED", "FIXED", "RETESTED", "CLOSED"]
    )
    severity_filter = filters[1].multiselect(
        "심각도", ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    )
    filtered = [
        item for item in defects
        if (not status_filter or item.get("status") in status_filter)
        and (not severity_filter or item.get("severity") in severity_filter)
    ]
    rows = pd.DataFrame([
        {
            "결함 ID": item.get("defect_id"), "제목": item.get("title"),
            "심각도": item.get("severity"), "상태": _defect_status_label(item.get("status")),
            "증적": item.get("evidence_status"), "담당자": item.get("owner") or "-",
            "갱신 시각": item.get("updated_at"),
        }
        for item in filtered
    ])
    st.dataframe(rows, hide_index=True, width="stretch")
    if not filtered:
        st.info("선택한 조건에 해당하는 결함이 없습니다.")
        return

    ids = [item["defect_id"] for item in filtered]
    remembered = st.session_state.get("voc_selected_defect_id")
    selected_id = st.selectbox(
        "상세 조회 결함", ids, index=ids.index(remembered) if remembered in ids else 0,
        format_func=lambda value: f"{value} · {next(item['title'] for item in filtered if item['defect_id'] == value)}",
    )
    st.session_state.voc_selected_defect_id = selected_id
    defect = load_voc_defect(selected_id)

    st.markdown(f"### {defect['title']}")
    with st.container(border=True):
        detail_columns = st.columns(4)
        detail_columns[0].metric("상태", _defect_status_label(defect.get("status")))
        detail_columns[1].metric("심각도", defect.get("severity", "-"))
        detail_columns[2].metric("증적", defect.get("evidence_status", "-"))
        detail_columns[3].metric("담당자", defect.get("owner") or "미지정")
        st.write(defect.get("description") or "-")
        st.caption(
            f"Run: {', '.join(defect.get('related_run_ids', [])) or '-'}  |  "
            f"Case: {', '.join(defect.get('related_case_ids', [])) or '-'}  |  "
            f"Trace: {', '.join(defect.get('related_trace_ids', [])) or '-'}"
        )
        if defect.get("jira_key"):
            st.caption(f"Jira: {defect['jira_key']}")

    tabs = st.tabs(["원인·조치", "처리 이력", "재시험 증적"])
    with tabs[0]:
        st.write({
            "원인": defect.get("root_cause") or "미분석",
            "영향": defect.get("impact") or "미분석",
            "조치": defect.get("corrective_action") or "미조치",
            "조치 기한": defect.get("due_date") or "-",
            "종료 근거": defect.get("closure_comment") or "-",
        })
    with tabs[1]:
        st.dataframe(pd.DataFrame(defect.get("history", [])), hide_index=True, width="stretch")
    with tabs[2]:
        evidence = defect.get("retest_evidence", [])
        st.json(evidence) if evidence else st.info("등록된 재시험 증적이 없습니다.")
    _render_defect_transition(defect)


def render_fault():
    mode = st.segmented_control(
        "관리 구분", ["결함 목록", "신규 등록", "격리 장애시험"],
        default="결함 목록", key="voc_defect_mode",
    )
    if mode == "신규 등록":
        _render_defect_create()
    elif mode == "격리 장애시험":
        _render_isolated_fault_tests()
    else:
        _render_defect_list()


def render_a2a():
    summary = audit_summary()
    cols = st.columns(4)
    cols[0].metric("Trace", summary["traces"], border=True)
    cols[1].metric("이벤트", summary["events"], border=True)
    cols[2].metric("성공", summary["success"], border=True)
    cols[3].metric("실패", summary["failure"], border=True)
    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center"):
        st.caption(f"원시 감사 로그: {summary['path']}")
        create_report = st.button(
            "A2A Report 생성",
            type="primary",
            icon=":material/description:",
        )
    if create_report:
        _run_and_store(run_diagnostics, "a2a")
    _show_command_result()
    reports = list_reports("Agent 연결 A2A")
    latest = next((item for item in reports if item["name"] == "latest.md"), None)
    if latest:
        st.markdown(read_report(latest["path"]))
    elif not summary["exists"]:
        st.info("아직 Trace가 없습니다. 실제 VOC 요청을 처리한 뒤 Report를 생성하세요.")


def _render_legacy_reports():
    st.markdown("### 기존 진단 보고서")
    st.caption("Summary·Validation·Fault·A2A 결과를 구분하여 조회하고 다운로드합니다.")
    category = st.selectbox("Report 분류", list(REPORT_CATEGORIES))
    reports = list_reports(category)
    if not reports:
        st.info("이 분류의 Report가 없습니다. 해당 진단을 먼저 실행하세요.")
        return
    labels = [f"{item['name']} · {datetime.fromtimestamp(item['modified']).strftime('%Y-%m-%d %H:%M:%S')}" for item in reports]
    selected_label = st.selectbox("Report 파일", labels)
    selected = reports[labels.index(selected_label)]
    content = read_report(selected["path"])
    st.download_button(
        "Report 다운로드",
        data=content.encode("utf-8"),
        file_name=selected["name"],
        mime="application/json" if selected["name"].endswith(".json") else "text/markdown",
    )
    if selected["name"].endswith(".json"):
        try:
            st.json(content)
        except Exception:
            st.code(content, language="json")
    else:
        st.markdown(content)


@st.cache_data(ttl=3, max_entries=20, show_spinner=False)
def _load_voc_quality_report_model(run_id: str, baseline_run_id: str):
    return build_voc_quality_report(run_id, baseline_run_id)


def _render_quality_report_preview(model: dict):
    run = model["run"]
    counts = run["counts"]
    if model["release_decision"] == "FORMAL_APPROVED":
        st.success("모든 정식 품질 승인 조건을 충족했습니다.", icon=":material/verified:")
    else:
        st.warning(
            "현재 보고서는 증적 초안입니다. 미검증 수치와 미충족 승인 조건을 성공으로 표시하지 않습니다.",
            icon=":material/release_alert:",
        )

    with st.container(horizontal=True):
        st.metric("보고서 상태", model["report_state"], border=True)
        st.metric("최종 판정", model["release_decision"], border=True)
        st.metric("선택 Case", run["selected_count"], border=True)
        st.metric("증적 무결성", "PASS" if model["integrity"]["ok"] else "FAIL", border=True)

    st.markdown("### 3단계 품질평가 요약")
    stage_columns = st.columns(3)
    with stage_columns[0].container(border=True, height="stretch"):
        st.markdown("**1단계 · VOC 분석 및 개선안**")
        st.metric("대표 산출물 확인", len(model["evaluation"]["voc_examples"]))
        st.caption("VOC 요약과 정책 개선안의 생성 여부를 Case 증적에서 확인합니다.")
    with stage_columns[1].container(border=True, height="stretch"):
        st.markdown("**2단계 · 내부 Agent 품질**")
        st.metric("Trace Case", model["evaluation"]["trace_cases"])
        st.caption(f"저장된 Agent Trace 이벤트 {model['evaluation']['trace_events']}건")
    with stage_columns[2].container(border=True, height="stretch"):
        st.markdown("**3단계 · 독립 LLM Judge**")
        st.metric("Judge 평가 Case", model["evaluation"]["judge_evaluated"])
        st.caption(str(model["evaluation"]["judge_counts"]) or "평가 결과 없음")

    st.markdown("### 전체 테스트 정량 분석")
    status_rows = pd.DataFrame([
        {"상태": status, "건수": counts[status]}
        for status in ("PASS", "FAIL", "ERROR", "REVIEW_REQUIRED", "NOT_RUN")
    ])
    chart_column, table_column = st.columns([1, 1.4])
    with chart_column.container(border=True, height="stretch"):
        st.bar_chart(status_rows, x="상태", y="건수")
    with table_column.container(border=True, height="stretch"):
        coverage = pd.DataFrame(model["coverage"]).rename(columns={
            "group": "점검 범위", "expected": "기대", "selected": "선택",
            "PASS": "통과", "FAIL": "실패", "ERROR": "오류",
            "REVIEW_REQUIRED": "검토 필요", "NOT_RUN": "미실행",
        })
        visible = ["점검 범위", "선택", "기대", "통과", "실패", "오류", "검토 필요", "미실행"]
        st.dataframe(coverage[visible], hide_index=True, width="stretch")

    st.markdown("### 테스트 추이와 수치 대조")
    claim = model["claims"]
    if claim["improvement_verified"]:
        st.success(f"{claim['claim_text']} 수치가 동일 조건 Run 증적으로 확인됐습니다.")
    else:
        st.error(f"{claim['claim_text']} 수치는 아직 증명되지 않았습니다.")
        st.write("기준선: " + (" / ".join(claim["baseline"]["errors"]) or "검증 완료"))
        st.write("최종: " + (" / ".join(claim["final"]["errors"]) or "검증 완료"))

    defect_column, risk_column = st.columns(2)
    with defect_column.container(border=True, height="stretch"):
        st.markdown("**결함 상태**")
        defect_rows = pd.DataFrame(model["defects"])
        if defect_rows.empty:
            st.info("등록된 결함이 없습니다.")
        else:
            st.dataframe(
                defect_rows[["defect_id", "title", "severity", "status", "evidence_status"]],
                hide_index=True, width="stretch",
            )
    with risk_column.container(border=True, height="stretch"):
        st.markdown("**잔여 위험과 운영 권고**")
        risk_rows = pd.DataFrame(model["risks"])
        if risk_rows.empty:
            st.success("현재 산식에서 식별된 잔여 위험이 없습니다.")
        else:
            st.dataframe(risk_rows, hide_index=True, width="stretch")

    with st.expander("Evaluator·Critic·독립 Judge 역할과 산식", icon=":material/calculate:"):
        st.dataframe(pd.DataFrame(model["roles"]), hide_index=True, width="stretch")
        st.json(model["formula"])


def _render_voc_quality_report():
    st.markdown("### 수행 이력 기반 품질 보고서")
    st.caption("선택 Run의 저장 증적과 중앙 이력을 자동 대조해 TXT·JUnit XML·HTML을 동일 데이터로 생성합니다.")
    history = [row for row in _load_voc_history_rows() if row.get("status") != "RUNNING"]
    if not history:
        st.info("보고서를 생성할 완료 Run이 없습니다.")
        return
    run_ids = [row["run_id"] for row in history]
    full_suite = [row["run_id"] for row in history if row.get("selected_count") == 35]
    default_id = full_suite[0] if full_suite else run_ids[0]
    selected_run_id = st.selectbox(
        "보고 대상 Run", run_ids, index=run_ids.index(default_id),
        format_func=lambda value: f"{value} · {next(row['selected_count'] for row in history if row['run_id'] == value)}건",
        key="voc_report_run_id",
    )
    baseline_options = [""] + [value for value in full_suite if value != selected_run_id]
    baseline_run_id = st.selectbox(
        "33 통과 / 2 실패 기준선 Run (선택)", baseline_options,
        format_func=lambda value: value or "연결하지 않음 · 현재 기준선 증적 없음",
        key="voc_report_baseline_run_id",
        help="동일 35개 Case·Catalog·TC hash·Rubric과 결함 링크가 확인되는 Run만 유효합니다.",
    )
    st.info(
        "사용자 제공 최종 보고서 양식은 아직 전달되지 않아 기본 증적 템플릿을 사용합니다. 양식을 받으면 같은 report model에 적용할 수 있습니다.",
        icon=":material/article:",
    )
    model = _load_voc_quality_report_model(selected_run_id, baseline_run_id)
    _render_quality_report_preview(model)

    if st.button(
        "TXT·XML·HTML 증적 생성", type="primary", icon=":material/description:",
        key=f"generate_voc_report_{selected_run_id}_{baseline_run_id}",
    ):
        with st.spinner("수행 이력과 증적 수치를 다시 대조하고 있습니다..."):
            st.session_state.voc_generated_quality_report = generate_voc_quality_report(
                selected_run_id, baseline_run_id
            )
        st.success("세 형식의 증적을 같은 report model에서 생성했습니다.")

    generated = st.session_state.get("voc_generated_quality_report")
    if (
        not generated
        or generated.get("model", {}).get("run", {}).get("run_id") != selected_run_id
        or generated.get("manifest", {}).get("baseline_run_id", "") != baseline_run_id
    ):
        return
    st.caption(f"저장 위치: {Path(generated['paths']['txt']).parent}")
    with st.container(horizontal=True):
        st.download_button(
            "TXT 다운로드", generated["contents"]["txt"], file_name="result.txt",
            mime="text/plain", icon=":material/download:",
        )
        st.download_button(
            "JUnit XML 다운로드", generated["contents"]["xml"], file_name="junit.xml",
            mime="application/xml", icon=":material/download:",
        )
        st.download_button(
            "HTML 다운로드", generated["contents"]["html"], file_name="report.html",
            mime="text/html", icon=":material/download:",
        )


def render_reports():
    mode = st.segmented_control(
        "보고서 구분", ["품질 증적 보고서", "기존 진단 보고서"],
        default="품질 증적 보고서", key="voc_report_mode",
    )
    if mode == "기존 진단 보고서":
        _render_legacy_reports()
    else:
        _render_voc_quality_report()


def render_guide():
    with st.container(border=True):
        guide_name = st.segmented_control(
            "가이드 구분",
            ["사용자 가이드", "품질진단 실행", "이식 가이드", "이식 체크리스트"],
            default="사용자 가이드",
            key="voc_user_guide_type",
            width="stretch",
        )
    with st.container(border=True):
        st.markdown(load_guide(guide_name))


def render_acceptance():
    history = [
        row for row in _load_voc_history_rows()
        if row.get("status") == "COMPLETED" and row.get("selected_count") == 35
    ]
    if not history:
        st.warning("최종 인수 판정에 사용할 완료된 35건 Run이 없습니다.")
        return

    run_ids = [row["run_id"] for row in history]
    default_id = latest_voc_full_run_id()
    if default_id not in run_ids:
        default_id = run_ids[0]
    run_id = st.selectbox(
        "최종 인수 대상 Run",
        run_ids,
        index=run_ids.index(default_id),
        key="voc_acceptance_run_id",
        help="완료된 35건 Run의 저장 증적만 최종 품질 게이트에 사용합니다.",
    )
    baseline_ids = [value for value in run_ids if value != run_id]
    baseline_run_id = st.selectbox(
        "33 통과 / 2 실패 기준선 Run (선택)",
        [""] + baseline_ids,
        format_func=lambda value: value or "연결하지 않음",
        key="voc_acceptance_baseline_run_id",
    )
    with st.spinner("Run·Case·Judge·타당성·결함·회귀 증적을 대조하고 있습니다..."):
        snapshot = build_voc_acceptance_snapshot(run_id, baseline_run_id)

    if snapshot["decision"] == "READY_FOR_UAT":
        st.success("모든 자동 품질 게이트를 통과했습니다. 사용자 UAT와 최종 서명이 남았습니다.")
    else:
        st.error("현재 최종 판정은 HOLD입니다. 미충족 게이트를 보완하기 전 정식 배포할 수 없습니다.")

    with st.container(horizontal=True):
        st.metric("인수 판정", snapshot["decision"], border=True)
        st.metric("품질 게이트", f"{snapshot['gate_summary']['pass']}/{snapshot['gate_summary']['total']}", border=True)
        st.metric("HOLD", snapshot["gate_summary"]["hold"], border=True)
        st.metric("사용자 서명", snapshot["user_signoff"], border=True)

    st.markdown("### 최종 품질 게이트")
    st.dataframe(
        pd.DataFrame(snapshot["gates"]).rename(columns={
            "label": "완료 조건", "status": "상태", "evidence": "증적", "gate_id": "ID",
        })[["상태", "완료 조건", "증적"]],
        hide_index=True,
        width="stretch",
    )

    st.markdown("### 핵심 업무 흐름 인수 범위")
    st.dataframe(
        pd.DataFrame(snapshot["workflow_coverage"]).rename(columns={
            "workflow": "업무 흐름", "status": "상태", "evidence": "증적",
        }),
        hide_index=True,
        width="stretch",
    )

    quantitative = snapshot["quantitative"]
    with st.container(horizontal=True):
        st.metric("Pipeline 통과", quantitative["case_counts"].get("PASS", 0), border=True)
        st.metric("Judge 평가", sum(quantitative["judge_counts"].values()), border=True)
        st.metric("타당성 평가", sum(quantitative["validity_counts"].values()), border=True)
        st.metric("비통과율", f"{quantitative['failure_rate_percent']}%", border=True)
    st.caption(
        "비용은 현재 저장 증적에 공통 필드가 없어 확인 불가로 표시합니다. "
        "응답시간은 수행 이력의 Run·Case 시작/종료 시각으로 확인합니다."
    )

    peer_column, professor_column = st.columns(2)
    with peer_column.container(border=True, height="stretch"):
        st.markdown("**동료평가 80점 증적 준비**")
        st.dataframe(
            pd.DataFrame(snapshot["evaluation_checklist"]["peer_80"]),
            hide_index=True,
            width="stretch",
        )
    with professor_column.container(border=True, height="stretch"):
        st.markdown("**교수평가 20점 증적 준비**")
        st.dataframe(
            pd.DataFrame(snapshot["evaluation_checklist"]["professor_20"]),
            hide_index=True,
            width="stretch",
        )
    st.caption(snapshot["evaluation_checklist"]["notice"])

    st.markdown("### 잔여 위험과 운영 권고")
    if snapshot["remaining_risks"]:
        st.dataframe(pd.DataFrame(snapshot["remaining_risks"]), hide_index=True, width="stretch")
    else:
        st.success("저장 증적 기준으로 식별된 잔여 위험이 없습니다.")

    st.markdown("### 시연 순서")
    st.write(" → ".join(snapshot["presentation_flow"]))
    st.info(
        "자동 판정은 사용자 최종 승인을 대신하지 않습니다. 시연·UAT 후 잔여 위험 수용 여부와 배포 가능 여부를 승인해야 합니다.",
        icon=":material/approval:",
    )

    if st.button(
        "Step 10 인수 증적 생성",
        type="primary",
        icon=":material/fact_check:",
        key=f"generate_voc_acceptance_{run_id}_{baseline_run_id}",
    ):
        st.session_state.voc_acceptance_evidence = generate_voc_acceptance_evidence(snapshot)
        st.success("JSON·Markdown 인수 증적을 Run evidence 경로에 저장했습니다.")
    generated = st.session_state.get("voc_acceptance_evidence")
    if generated and generated.get("snapshot", {}).get("run_id") == run_id:
        st.caption(f"저장 위치: {Path(generated['paths']['json']).parent}")
        with st.container(horizontal=True):
            st.download_button(
                "인수 JSON 다운로드", generated["contents"]["json"],
                file_name="step10_acceptance.json", mime="application/json",
                icon=":material/download:",
            )
            st.download_button(
                "인수 Markdown 다운로드", generated["contents"]["markdown"],
                file_name="step10_acceptance.md", mime="text/markdown",
                icon=":material/download:",
            )


ROUTES = {
    "Dashboard": render_dashboard,
    "수동 TC 수행": render_goal_monitor,
    "일괄 TC 수행": render_batch_execution,
    "수행 이력": render_voc_history,
    "개선안 타당성 검증": render_improvement_validity,
    "Agent 관리": render_agents,
    "VOC 분석": render_analysis,
    "테스트케이스": render_testcases,
    "품질 평가 기준": render_rubric,
    "장애·결함 관리": render_fault,
    "A2A Trace": render_a2a,
    "품질 보고서": render_reports,
    "사용자 가이드": render_guide,
    "최종 인수·시연": render_acceptance,
}


def render_voc_quality_view(sub_menu):
    renderer = ROUTES.get(sub_menu)
    if not renderer:
        return False
    try:
        _render_voc_design_system()
        _render_voc_page_header(sub_menu)
        with st.container(key="voc_page_content"):
            renderer()
    except Exception as exc:
        st.error(f"VOC 품질진단 화면을 불러오지 못했습니다: {type(exc).__name__}: {exc}")
    return True
