from datetime import datetime

import pandas as pd
import streamlit as st

from components.performance_design import (
    render_icon_cards,
    render_page_hero,
    render_performance_design_styles,
    render_section_header,
)
from services.k6_service import (
    K6RunSettings,
    get_active_k6_run,
    get_k6_version,
    is_k6_available,
    load_k6_run,
    load_recent_runs,
    start_k6_test_background,
    stop_k6_test,
)


def render_k6_runner_page():
    render_performance_design_styles()
    render_page_hero(
        "gauge",
        "k6 성능 테스트 실행",
        "부하 조건과 판정 기준을 설정하고 백그라운드 테스트 진행 상황과 결과 이력을 관리합니다.",
    )

    available = is_k6_available()
    version = get_cached_k6_version()
    if available:
        st.success(f"k6 실행 가능: {version or 'version 확인됨'}")
    else:
        st.warning("k6 실행 파일을 찾을 수 없습니다. k6 설치 후 터미널을 새로 열고 다시 실행해주세요.")

    settings = render_settings_form()
    render_expected_duration(settings)
    active_run = get_active_k6_run()

    run_col, hint_col = st.columns([0.28, 0.72])
    with run_col:
        run_clicked = st.button(
            ":material/open_in_new: 수행 화면 열기" if active_run else "k6 백그라운드 실행",
            type="primary",
            width="stretch",
            disabled=not available and not active_run,
        )
    with hint_col:
        if active_run:
            st.caption(f"실행 중: {active_run.get('run_id', '-')} · 다른 페이지로 이동해도 계속 수행됩니다.")
        else:
            st.caption("실행 이력은 reports/k6_runs에 저장되고 최신 결과는 reports/k6_summary.json으로 갱신됩니다.")

    if run_clicked:
        if active_run:
            open_k6_execution_dialog(active_run.get("run_id"))
        else:
            start_background_run(settings)

    render_background_run_status()

    dialog_run_id = st.session_state.get("k6_execution_dialog_run_id")
    if dialog_run_id:
        render_k6_execution_dialog(dialog_run_id)


@st.cache_data(ttl=60, max_entries=1, show_spinner=False)
def get_cached_k6_version():
    return get_k6_version()


def render_settings_form():
    render_section_header("settings", "실행 설정", "대상, 부하, 수행 시간과 PASS/FAIL 판정 기준")
    target_url = st.text_input(
        "대상 URL",
        value=st.session_state.get("k6_target_url", "http://localhost:8000/health"),
        help="예: http://localhost:8000/health 또는 http://localhost:8000/ask?question=...",
    )
    st.session_state.k6_target_url = target_url

    load_col, time_col, threshold_col = st.columns(3)
    with load_col:
        vus = st.slider("동시 사용자 수", min_value=1, max_value=200, value=20, step=1)
        think_time = st.slider("요청 간 대기시간(초)", min_value=0.0, max_value=5.0, value=1.0, step=0.1)
    with time_col:
        duration_seconds = st.slider("총 테스트 시간(초)", min_value=10, max_value=600, value=60, step=10)
        ramp_up_seconds = st.slider("Ramp-up 시간(초)", min_value=0, max_value=300, value=10, step=5)
    with threshold_col:
        p95_threshold_ms = st.slider("p95 응답시간 기준(ms)", min_value=100, max_value=30000, value=3000, step=100)
        failure_rate_threshold_pct = st.slider("실패율 기준(%)", min_value=0.0, max_value=50.0, value=1.0, step=0.1)
        checks_threshold_pct = st.slider("체크 성공률 기준(%)", min_value=50.0, max_value=100.0, value=95.0, step=0.5)

    return K6RunSettings(
        target_url=target_url.strip(),
        vus=vus,
        duration_seconds=duration_seconds,
        ramp_up_seconds=min(ramp_up_seconds, max(duration_seconds - 1, 0)),
        p95_threshold_ms=p95_threshold_ms,
        failure_rate_threshold_pct=failure_rate_threshold_pct,
        checks_threshold_pct=checks_threshold_pct,
        think_time_seconds=think_time,
    )


def start_background_run(settings):
    try:
        result = start_k6_test_background(settings)
    except ValueError as exc:
        st.error(str(exc))
        return

    if result.get("ok"):
        st.session_state.k6_execution_dialog_run_id = result.get("run_id")
        st.success(f"k6 백그라운드 테스트를 시작했습니다. Run ID: {result.get('run_id', '-')}")
        st.rerun()
    else:
        st.error(result.get("error") or "k6 백그라운드 실행을 시작하지 못했습니다.")


@st.fragment(run_every="2s")
def render_background_run_status():
    active = get_active_k6_run()
    if not active:
        records = load_recent_runs(limit=1)
        if records and records[0].get("status") in {"PASS", "FAIL", "ERROR", "STOPPED"}:
            render_section_header("check", "최근 완료 결과", "가장 최근에 종료된 k6 실행의 핵심 성능 지표")
            render_result_summary(records[0])
            render_run_log(records[0])
    render_recent_runs()


def render_run_log(result):
    stdout = result.get("stdout") or ""
    stderr = result.get("stderr") or ""
    if not stdout and not stderr:
        return
    with st.expander("실행 로그", expanded=result.get("status") in {"FAIL", "ERROR"}):
        if stdout:
            st.code(stdout, language="text")
        if stderr:
            st.code(stderr, language="text")


def render_result_summary(result):
    summary = result.get("summary") or {}
    if not summary:
        st.info("k6 요약 결과가 아직 생성되지 않았습니다.")
        return

    decision = decide_result(summary, result.get("settings", {}))
    render_icon_cards(
        [
            ("request", "총 요청", format_number(summary.get("total_requests")), "완료된 HTTP 요청", ""),
            ("warning", "실패율", f"{summary.get('failure_rate', 0):.2f}%", "실패 요청 비율", "bad" if summary.get("failure_rate", 0) else ""),
            ("duration", "평균 응답", format_seconds(summary.get("avg_duration_seconds")), "전체 요청 평균", ""),
            ("duration", "p95 응답", format_seconds(summary.get("p95_duration_seconds")), "95% 요청 완료 기준", ""),
            ("gauge", "처리량", f"{summary.get('throughput', 0):.2f}/s", "초당 요청 수", ""),
            ("check", "체크 성공률", f"{summary.get('checks_rate', 0):.2f}%", "응답 검증 성공", "good" if float(summary.get("checks_rate", 0) or 0) >= 95 else "warn"),
            ("check" if decision == "PASS" else "warning", "판정", decision, "설정 임계값 기준", "good" if decision == "PASS" else "bad"),
        ],
        columns=4,
    )

    rows = pd.DataFrame(
        [
            {"항목": "상태", "값": result.get("status", "-")},
            {"항목": "실행 ID", "값": result.get("run_id", "-")},
            {"항목": "결과 파일", "값": result.get("summary_path", "-")},
            {"항목": "대상 URL", "값": result.get("settings", {}).get("target_url", "-")},
        ]
    )
    st.dataframe(rows, hide_index=True, width="stretch")
    if st.button(
        ":material/open_in_new: 수행 화면 다시 열기",
        key=f"k6_reopen_dialog_{result.get('run_id')}",
    ):
        open_k6_execution_dialog(result.get("run_id"))


def render_expected_duration(settings):
    estimate = estimate_k6_duration(settings)
    st.info(
        f"예상 k6 수행 시간은 **약 {format_compact_duration(estimate['k6_seconds'])}**입니다. "
        f"({estimate['breakdown']}) 결과 집계·이력 저장까지 포함하면 "
        f"**약 {format_compact_duration(estimate['minimum_total_seconds'])}~"
        f"{format_compact_duration(estimate['maximum_total_seconds'])}**이 예상됩니다."
    )


def open_k6_execution_dialog(run_id):
    if run_id:
        st.session_state.k6_execution_dialog_run_id = str(run_id)
        st.rerun(scope="app")


def close_k6_execution_dialog():
    st.session_state.pop("k6_execution_dialog_run_id", None)


@st.dialog(
    "k6 성능 테스트 수행",
    width="large",
    icon=":material/speed:",
    on_dismiss=close_k6_execution_dialog,
)
def render_k6_execution_dialog(run_id):
    render_k6_execution_dialog_body(run_id)


@st.fragment(run_every="2s")
def render_k6_execution_dialog_body(run_id):
    record = load_k6_run(run_id)
    if not record:
        st.error(f"실행 이력을 찾을 수 없습니다. Run ID: {run_id}")
        if st.button("닫기", key=f"k6_dialog_close_missing_{run_id}"):
            close_k6_execution_dialog()
            st.rerun(scope="app")
        return

    status = record.get("status", "STARTING")
    settings = record.get("settings") or {}
    estimate = estimate_k6_duration(settings)
    elapsed = elapsed_seconds(record.get("started_at") or record.get("created_at"))
    terminal = status in {"PASS", "FAIL", "ERROR", "STOPPED"}
    progress = 1.0 if terminal else min(elapsed / max(estimate["expected_total_seconds"], 1), 0.99)

    header_cols = st.columns([1.0, 1.25, 1.0, 1.3, 0.72], vertical_alignment="center")
    header_cols[0].metric("상태", status)
    header_cols[1].metric("Run ID", record.get("run_id", "-"))
    header_cols[2].metric("경과 시간", format_compact_duration(elapsed))
    header_cols[3].metric("예상 시간", estimate["expected_range_label"])
    if header_cols[4].button(
        ":material/close: 닫기",
        key=f"k6_dialog_close_{run_id}",
        width="stretch",
        help="팝업만 닫습니다. 백그라운드 테스트는 계속 수행됩니다.",
    ):
        close_k6_execution_dialog()
        st.rerun(scope="app")
    st.progress(progress, text=execution_progress_text(status))

    st.markdown("#### 프로세스별 수행 단계")
    render_execution_stage_selector(record)
    st.dataframe(
        pd.DataFrame(build_execution_stages(record)),
        hide_index=True,
        width="stretch",
        column_order=("단계", "프로세스", "상태", "내용"),
    )

    st.markdown("#### 테스트 실행 설정")
    st.dataframe(
        pd.DataFrame(build_settings_rows(settings, estimate)),
        hide_index=True,
        width="stretch",
        column_order=("설정", "값", "평가 기준/의미"),
    )
    st.caption(
        f"예상 구간: {estimate['breakdown']} · 결과 집계·이력 저장 포함 "
        f"{estimate['expected_range_label']}"
    )

    if not terminal:
        render_dialog_stop_control(record)

    if terminal:
        if status in {"PASS", "FAIL"} and record.get("summary"):
            st.markdown("#### 수행 결과")
            render_result_summary_metrics(record)
        elif status in {"ERROR", "STOPPED"}:
            st.warning(record.get("error") or f"테스트가 {status} 상태로 종료되었습니다.")

def render_dialog_stop_control(record):
    with st.container(border=True):
        st.caption("테스트 중지는 수행 팝업에서만 제어합니다. 중지된 실행은 STOPPED 이력으로 보존됩니다.")
        confirm_col, stop_col = st.columns([0.6, 0.4], vertical_alignment="center")
        confirm = confirm_col.checkbox(
            "실행 중지 확인",
            key=f"k6_dialog_stop_confirm_{record.get('run_id')}",
        )
        if stop_col.button(
            ":material/stop_circle: 테스트 중지",
            key=f"k6_dialog_stop_{record.get('run_id')}",
            disabled=not confirm,
            width="stretch",
        ):
            result = stop_k6_test(record.get("run_id"))
            if result.get("ok"):
                st.success("k6 테스트를 중지하고 STOPPED 이력을 저장했습니다.")
            else:
                st.error(result.get("error") or "k6 테스트를 중지하지 못했습니다.")
            st.rerun(scope="fragment")


def render_result_summary_metrics(record):
    summary = record.get("summary") or {}
    cols = st.columns(5)
    cols[0].metric("총 요청", format_number(summary.get("total_requests")))
    cols[1].metric("실패율", f"{summary.get('failure_rate', 0):.2f}%")
    cols[2].metric("p95 응답", format_seconds(summary.get("p95_duration_seconds")))
    cols[3].metric("처리량", f"{summary.get('throughput', 0):.2f}/s")
    cols[4].metric("판정", decide_result(summary, record.get("settings") or {}))


def estimate_k6_duration(settings):
    values = settings if isinstance(settings, dict) else vars(settings)
    duration = max(int(values.get("duration_seconds", 0) or 0), 0)
    ramp_up = min(max(int(values.get("ramp_up_seconds", 0) or 0), 0), max(duration - 1, 0))
    if ramp_up:
        stable = max(duration - ramp_up, 1)
        ramp_down = 5
        k6_seconds = ramp_up + stable + ramp_down
        breakdown = f"Ramp-up {ramp_up}초 + 유지 {stable}초 + 종료 {ramp_down}초"
    else:
        stable = duration
        ramp_down = 0
        k6_seconds = duration
        breakdown = f"고정 부하 {duration}초"

    minimum_total = k6_seconds + 2
    maximum_total = k6_seconds + 10
    return {
        "duration_seconds": duration,
        "ramp_up_seconds": ramp_up,
        "stable_seconds": stable,
        "ramp_down_seconds": ramp_down,
        "k6_seconds": k6_seconds,
        "minimum_total_seconds": minimum_total,
        "maximum_total_seconds": maximum_total,
        "expected_total_seconds": maximum_total,
        "expected_range_label": (
            f"{format_compact_duration(minimum_total)}~{format_compact_duration(maximum_total)}"
        ),
        "breakdown": breakdown,
    }


def build_execution_stages(record):
    status = record.get("status", "STARTING")
    states = {
        "STARTING": ("완료", "진행 중", "대기", "대기", "대기"),
        "RUNNING": ("완료", "완료", "진행 중", "대기", "대기"),
        "STOPPING": ("완료", "완료", "중지 처리 중", "대기", "대기"),
        "FINALIZING": ("완료", "완료", "완료", "진행 중", "대기"),
        "PASS": ("완료", "완료", "완료", "완료", "PASS"),
        "FAIL": ("완료", "완료", "완료", "완료", "FAIL"),
        "ERROR": ("완료", "완료", "오류", "미완료", "ERROR"),
        "STOPPED": ("완료", "완료", "중지", "완료", "STOPPED"),
    }.get(status, ("완료", "완료", status, "대기", "대기"))
    definitions = (
        ("1/5", "실행 설정 검증", "URL, 부하, 시간 및 판정 기준의 유효성을 확인합니다."),
        ("2/5", "백그라운드 worker 시작", "화면과 분리된 worker 프로세스를 기동합니다."),
        ("3/5", "k6 부하 테스트 수행", "설정한 동시 사용자와 구간에 따라 요청을 실행합니다."),
        ("4/5", "결과 집계 및 이력 저장", "요약 지표와 로그를 reports/k6_runs에 저장합니다."),
        ("5/5", "테스트 완료", "임계값 기준으로 PASS 또는 FAIL을 확정합니다."),
    )
    return [
        {"단계": step, "프로세스": name, "상태": state, "내용": description}
        for (step, name, description), state in zip(definitions, states)
    ]


def render_execution_stage_selector(record):
    stages = build_execution_stages(record)
    current_index = current_execution_stage_index(record.get("status", "STARTING"))
    options = [
        format_execution_stage_option(index, stage, current_index)
        for index, stage in enumerate(stages)
    ]
    current_stage = stages[current_index]

    st.segmented_control(
        "현재 수행 단계",
        options=options,
        default=options[current_index],
        disabled=True,
        width="stretch",
        key=f"k6_stage_selector_{record.get('run_id', 'unknown')}_{record.get('status', 'STARTING')}",
    )
    st.caption(
        f"현재 선택 단계: {current_stage['단계']} {current_stage['프로세스']} · "
        f"{current_stage['상태']}"
    )


def current_execution_stage_index(status):
    return {
        "STARTING": 1,
        "RUNNING": 2,
        "STOPPING": 2,
        "FINALIZING": 3,
        "PASS": 4,
        "FAIL": 4,
        "ERROR": 2,
        "STOPPED": 4,
    }.get(status, 0)


def format_execution_stage_option(index, stage, current_index):
    short_names = ("설정 검증", "worker 시작", "k6 수행", "결과 저장", "완료")
    state = stage.get("상태", "대기")
    if index < current_index and state == "완료":
        marker = "✓"
    elif index == current_index:
        marker = {
            "PASS": "✓",
            "FAIL": "×",
            "ERROR": "!",
            "STOPPED": "■",
            "중지": "■",
            "중지 처리 중": "■",
        }.get(state, "▶")
    else:
        marker = "○"
    return f"{marker} {index + 1} {short_names[index]}"


def build_settings_rows(settings, estimate=None):
    estimate = estimate or estimate_k6_duration(settings)
    return [
        {"설정": "대상 URL", "값": settings.get("target_url", "-"), "평가 기준/의미": "부하 요청을 보낼 HTTP 주소"},
        {"설정": "동시 사용자(VUs)", "값": settings.get("vus", "-"), "평가 기준/의미": "동시에 요청을 반복하는 가상 사용자 수"},
        {"설정": "총 테스트 시간", "값": f"{estimate['duration_seconds']}초", "평가 기준/의미": "Ramp-up과 목표 부하 유지 구간의 합"},
        {"설정": "Ramp-up", "값": f"{estimate['ramp_up_seconds']}초", "평가 기준/의미": "목표 동시 사용자까지 점진적으로 증가하는 시간"},
        {"설정": "요청 간 대기", "값": f"{settings.get('think_time_seconds', 0)}초", "평가 기준/의미": "가상 사용자별 요청 반복 사이의 대기시간"},
        {"설정": "p95 응답시간", "값": f"{settings.get('p95_threshold_ms', '-')}ms 이하", "평가 기준/의미": "전체 요청의 95%가 만족해야 하는 응답시간"},
        {"설정": "실패율", "값": f"{settings.get('failure_rate_threshold_pct', '-')}% 이하", "평가 기준/의미": "HTTP 요청 실패 비율의 허용 상한"},
        {"설정": "체크 성공률", "값": f"{settings.get('checks_threshold_pct', '-')}% 이상", "평가 기준/의미": "응답 상태·본문 검증 성공률의 허용 하한"},
    ]


def execution_progress_text(status):
    return {
        "STARTING": "백그라운드 worker를 시작하고 있습니다.",
        "RUNNING": "k6가 설정된 부하 테스트를 수행하고 있습니다.",
        "STOPPING": "k6 worker를 안전하게 중지하고 있습니다.",
        "PASS": "테스트와 결과 저장이 완료되었으며 기준을 통과했습니다.",
        "FAIL": "테스트와 결과 저장이 완료되었으며 일부 기준을 충족하지 못했습니다.",
        "ERROR": "테스트 수행 중 오류가 발생했습니다.",
        "STOPPED": "사용자 요청으로 테스트가 중지되었고 이력이 저장되었습니다.",
    }.get(status, f"현재 상태: {status}")


def format_compact_duration(value):
    seconds = max(int(round(float(value or 0))), 0)
    minutes, remainder = divmod(seconds, 60)
    if minutes and remainder:
        return f"{minutes}분 {remainder}초"
    if minutes:
        return f"{minutes}분"
    return f"{remainder}초"


def render_recent_runs():
    render_section_header("history", "최근 k6 수행이력", "최근 10개 백그라운드 실행의 설정과 판정 결과")
    records = load_recent_runs(limit=10)
    if not records:
        st.info("아직 k6 수행이력이 없습니다.")
        return

    rows = []
    for record in records:
        summary = record.get("summary") or {}
        settings = record.get("settings") or {}
        rows.append(
            {
                "실행시각": record.get("created_at", ""),
                "상태": record.get("status", "완료" if record.get("return_code") is not None else "-"),
                "대상 URL": settings.get("target_url", ""),
                "VUs": settings.get("vus", ""),
                "시간(초)": settings.get("duration_seconds", ""),
                "요청 수": int(summary.get("total_requests", 0) or 0),
                "실패율": f"{summary.get('failure_rate', 0):.2f}%",
                "p95": format_seconds(summary.get("p95_duration_seconds")),
                "판정": decide_history_result(record, summary, settings),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def decide_history_result(record, summary, settings):
    status = record.get("status")
    if status in {"STARTING", "RUNNING", "STOPPING", "ERROR", "STOPPED"}:
        return status
    return decide_result(summary, settings)


def elapsed_seconds(started_at):
    try:
        return max((datetime.now() - datetime.fromisoformat(started_at)).total_seconds(), 0)
    except (TypeError, ValueError):
        return 0


def decide_result(summary, settings):
    failure_rate = float(summary.get("failure_rate", 0) or 0)
    p95_seconds = float(summary.get("p95_duration_seconds", 0) or 0)
    checks_rate = float(summary.get("checks_rate", 0) or 0)
    p95_limit = float(settings.get("p95_threshold_ms", 3000) or 3000) / 1000
    failure_limit = float(settings.get("failure_rate_threshold_pct", 1.0) or 1.0)
    checks_limit = float(settings.get("checks_threshold_pct", 95.0) or 95.0)

    if failure_rate <= failure_limit and p95_seconds <= p95_limit and checks_rate >= checks_limit:
        return "PASS"
    return "FAIL"


def format_seconds(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if numeric <= 0:
        return "-"
    return f"{numeric:.2f}s"


def format_number(value):
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return "0"
