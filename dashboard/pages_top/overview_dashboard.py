from datetime import date, timedelta
from html import escape

import altair as alt
import streamlit as st

from services.overview_dashboard import build_overview
from services.qa_observer_client import (
    QAObserverClientError,
    fetch_dashboard_bundle,
    fetch_filter_options,
    observer_base_url,
)


PRIMARY_PANEL_COLUMNS = (1, 1, 1)
PRIMARY_CHART_HEIGHT = 220
TEST_RESULT_COLORS = {
    "Pass": "#155A96",
    "Fail": "#5599D2",
    "Error": "#A9CAE7",
}
KPI_TOOLTIPS = {
    "전체 품질점수": (
        "의미: 평가가 완료된 정확성·근거성·유용성·안전성 등 품질 항목의 종합 수준\n"
        "산정: evaluated=true인 1~5점 항목의 평균 × 20\n"
        "기준: 정상 90점 이상 · 주의 80점 이상 90점 미만 · 위험 80점 미만"
    ),
    "테스트 통과율": (
        "의미: 선택 기간에 완료된 전체 테스트 중 Pass한 테스트의 비율\n"
        "산정: Pass 건수 ÷ 전체 테스트 건수 × 100\n"
        "기준: 정상 95% 이상 · 주의 85% 이상 95% 미만 · 위험 85% 미만"
    ),
    "p95 응답시간": (
        "의미: API 요청의 95%가 이 시간 이내에 완료되었음을 나타내는 지연시간\n"
        "산정: 완료된 API 요청 duration_ms의 95백분위수\n"
        "기준: 정상 5초 이하 · 주의 5초 초과 8초 이하 · 위험 8초 초과"
    ),
    "오류율": (
        "의미: 전체 API 요청 중 서버 오류 또는 타임아웃이 발생한 비율\n"
        "산정: HTTP 5xx 또는 timeout 요청 수 ÷ 전체 API 요청 수 × 100\n"
        "기준: 정상 1% 이하 · 주의 1% 초과 2% 이하 · 위험 2% 초과"
    ),
    "안전성 위반": (
        "의미: 안전성 정책 위반으로 탐지된 이벤트 수\n"
        "산정: safety.violation.detected 이벤트 건수\n"
        "기준: 정상 0건 · 위험 1건 이상(즉시 확인 필요)"
    ),
    "LLM 토큰 / API 비용": (
        "의미: 선택 기간의 LLM 사용량과 가격 산정이 가능한 호출의 누적 비용\n"
        "산정: LLM 호출 total_tokens 합계 및 원화 환산 비용 합계\n"
        "기준: 일 예산 사용률 정상 80% 미만 · 주의 80% 이상 · 위험 100% 이상"
    ),
}


@st.cache_data(ttl=60, max_entries=4, show_spinner=False)
def _load_filter_options(base_url):
    return fetch_filter_options(base_url)


@st.cache_data(ttl=15, max_entries=64, show_spinner=False)
def _load_dashboard_bundle(date_from, date_to, environment, service, provider, model, base_url):
    return fetch_dashboard_bundle(
        date_from,
        date_to,
        environment=environment,
        service=service,
        provider=provider,
        model=model,
        base_url=base_url,
    )


def render_overview_dashboard_page():
    _render_page_styles()

    base_url = observer_base_url()
    try:
        options = _load_filter_options(base_url)
        options_error = None
    except QAObserverClientError as exc:
        options = {"environments": [], "services": [], "providers": [], "models": []}
        options_error = str(exc)

    today = date.today()
    heading, controls = st.columns([1.12, 3.88], vertical_alignment="bottom")
    with heading:
        st.title("AI QA 모니터링 대시보드")
        st.caption("응답 품질 · 테스트 · 성능 · 안전성 · RAG 검색 품질")
    with controls:
        with st.form("qa_overview_filters", border=False):
            filters = st.columns([1.55, 0.75, 1.05, 0.9, 1.2, 0.58], vertical_alignment="bottom")
            with filters[0]:
                selected_range = st.date_input(
                    "기간",
                    value=(today - timedelta(days=6), today),
                    max_value=today,
                    key="qa_overview_date_range",
                )
            with filters[1]:
                environment = st.selectbox("환경", ["전체", *options["environments"]], key="qa_overview_environment")
            with filters[2]:
                service = st.selectbox("서비스", ["전체", *options["services"]], key="qa_overview_service")
            with filters[3]:
                provider = st.selectbox("공급자", ["전체", *options["providers"]], key="qa_overview_provider")
            with filters[4]:
                model = st.selectbox("모델", ["전체", *options["models"]], key="qa_overview_model")
            with filters[5]:
                submitted = st.form_submit_button(
                    "조회",
                    icon=":material/search:",
                    type="primary",
                    width="stretch",
                )

    if submitted:
        _load_dashboard_bundle.clear()

    start_date, end_date = _normalize_date_range(selected_range, today)
    _render_live_dashboard(
        start_date,
        end_date,
        _optional(environment),
        _optional(service),
        _optional(provider),
        _optional(model),
        base_url,
        options_error,
    )
    return True


@st.fragment(run_every="30s")
def _render_live_dashboard(
    start_date,
    end_date,
    environment,
    service,
    provider,
    model,
    base_url,
    options_error,
):
    try:
        bundle = _load_dashboard_bundle(
            start_date,
            end_date,
            environment,
            service,
            provider,
            model,
            base_url,
        )
        summary = bundle.get("summary", {})
        view = build_overview(
            summary,
            bundle.get("timeseries", {}).get("items", []),
            bundle.get("events", {}).get("items", []),
            bundle.get("health", {}),
            bundle.get("quality_events", {}).get("items", []),
            bundle.get("safety_events", {}).get("items", []),
        )
        load_error = None
    except QAObserverClientError as exc:
        summary = {"data_status": "no_data"}
        view = build_overview(summary, [], [], {})
        load_error = str(exc)

    _render_status(view["status"], summary, view["collection"], load_error or options_error, base_url)
    _render_safety_action(view["safety_incidents"])
    _render_kpis(summary, view)
    _render_primary_panels(view)
    _render_secondary_panels(view)
    _render_bottom_panels(view)


def _render_status(status, summary, collection, error, base_url):
    if error:
        st.warning(f"qa-observer 연결을 확인할 수 없습니다. 마지막 주소: {base_url}", icon=":material/cloud_off:")
        return
    colors = {"normal": "#299049", "warning": "#b36a08", "danger": "#d83f36", "no_data": "#7b8797"}
    freshness = ""
    if summary.get("latest_received_at_utc"):
        freshness = (
            f"마지막 수집 {escape(str(summary['latest_received_at_utc']))} · "
            f"신선도 {int(summary.get('freshness_seconds') or 0):,}초"
        )
    if collection.get("healthy"):
        interval = int(collection.get("interval_seconds") or 0)
        collector = f"수집기 정상 · {interval}초 주기"
        if summary.get("data_status") == "stale":
            freshness += " · 신규 이벤트 대기 중"
    else:
        collector = "수집기 상태 확인 필요"
        if collection.get("last_error_type"):
            collector += f" · {collection['last_error_type']}"
    status_col, refresh_col = st.columns([9.35, 0.65], vertical_alignment="center")
    with status_col:
        st.markdown(
            f"""
            <div class="aqd-status" style="--status-color:{colors[status['level']]}">
              <span class="aqd-status-icon">{_svg_icon('monitor')}</span>
              <b>{escape(status['label'])}</b><span>{escape(status['reason'])}</span>
              <small>{escape(collector)} · {freshness}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with refresh_col:
        if st.button("갱신", icon=":material/refresh:", key="qa_overview_refresh", help="수집기 상태와 집계 데이터를 다시 조회합니다.", width="stretch"):
            _load_filter_options.clear()
            _load_dashboard_bundle.clear()
            st.rerun()


def _render_safety_action(incidents):
    if incidents.empty:
        return
    latest = incidents.iloc[0]
    run_id = str(latest["Run ID"])
    case_id = str(latest["Case ID"])
    message_col, action_col = st.columns([8.35, 1.65], vertical_alignment="center")
    with message_col:
        st.markdown(
            f"<div class='aqd-safety-action'><b>{escape(str(latest['심각도']))} 안전성 위험 · {len(incidents):,}건</b>"
            f"<span>최근 위반 {escape(run_id)} · {escape(case_id)} · {escape(str(latest['탐지 기준']))}</span></div>",
            unsafe_allow_html=True,
        )
    with action_col:
        if st.button("위반 Case 확인", icon=":material/policy:", type="primary", width="stretch", key="qa_safety_detail"):
            _show_safety_dialog(incidents)


@st.dialog("안전성 위험 상세 및 조치", width="large")
def _show_safety_dialog(incidents):
    st.warning("High/Critical 안전성 평가를 확인하고 해당 테스트 결과와 프롬프트 정책을 검토하세요.", icon=":material/gpp_maybe:")
    st.dataframe(
        incidents,
        hide_index=True,
        width="stretch",
        column_config={
            "발생 시각(UTC)": st.column_config.DatetimeColumn("발생 시각(UTC)", format="MM-DD HH:mm:ss"),
            "Run ID": st.column_config.TextColumn("Run ID", pinned=True),
            "Case ID": st.column_config.TextColumn("Case ID", pinned=True),
        },
    )
    st.markdown("**빠른 조치 순서**  ① 실행 이력에서 실패 응답 확인 → ② 안전성 기준·프롬프트 검토 → ③ 수정 후 해당 Case 재실행")
    linked_incidents = incidents[(incidents["Run ID"] != "-") & (incidents["Case ID"] != "-")].to_dict("records")
    selected_incident = (
        st.selectbox(
            "확인할 위반 Case",
            linked_incidents,
            format_func=lambda row: f"{row['Case ID']} · {row['심각도']} · {row['탐지 기준']} · {row['Run ID']}",
            key="qa_safety_selected_incident",
        )
        if linked_incidents
        else None
    )
    if selected_incident:
        if st.button(
            "선택한 위반 Case의 수행 상세 열기",
            icon=":material/open_in_new:",
            type="primary",
            width="stretch",
            key="qa_safety_dialog_history",
        ):
            _open_test_history_from_dialog(selected_incident["Run ID"], selected_incident["Case ID"])


def _open_test_history(run_id, case_id=None):
    st.session_state.qa_safety_focus_run_id = run_id
    if case_id:
        st.session_state.qa_safety_focus_case_id = case_id
    st.session_state.current_menu = "테스트 관리"
    st.session_state.current_sub_menu = "테스트 수행 이력"


def _open_test_history_from_dialog(run_id, case_id=None):
    _open_test_history(run_id, case_id)
    # Dialog widgets rerun only the dialog fragment. A full-app rerun is
    # required for render_navigation() to apply the changed menu state.
    st.rerun(scope="app")


def _render_kpis(summary, view):
    trend = view["quality_trend"]
    quality_values = trend["품질점수"].tolist() if not trend.empty else None
    quality_delta = None
    if quality_values and len(quality_values) >= 2:
        quality_delta = f"이전 대비 {quality_values[-1] - quality_values[0]:+.1f}점"

    test_counts = view["test_distribution"].set_index("결과")["건수"].to_dict()
    traffic = view["traffic_trend"]
    api_errors = 0 if traffic.empty else int(traffic["서비스 오류 수"].sum())
    llm = view["llm_usage"]
    budget_rate = llm["budget_usage_rate"]
    if llm["cost_krw"] is None and llm["total_tokens"]:
        llm_value = f"{llm['total_tokens']:,}개"
        llm_detail = (
            f"입력 {llm['input_tokens']:,} · 출력 {llm['output_tokens']:,} · 비용 미산정"
        )
        llm_tone = "warn"
    else:
        llm_value = _currency(llm["cost_krw"])
        token_detail = "" if llm["total_tokens"] is None else f"토큰 {llm['total_tokens']:,}개 · "
        llm_detail = (
            f"{token_detail}예산 사용률 데이터 없음"
            if budget_rate is None
            else f"{token_detail}예산 {budget_rate:,.1f}% 사용"
        )
        llm_tone = ""

    cards = [
        ("star", "전체 품질점수", _number(summary.get("quality_score"), "점"), quality_delta, ""),
        (
            "check",
            "테스트 통과율",
            _number(summary.get("test_pass_rate"), "%"),
            f"Pass {test_counts.get('Pass', 0)} / Fail {test_counts.get('Fail', 0)}",
            "",
        ),
        ("timer", "p95 응답시간", _duration(summary.get("api_p95_duration_ms")), "목표 5초 이내", ""),
        ("warning", "오류율", _number(summary.get("api_error_rate"), "%"), f"API 오류 {api_errors}건", "bad" if (summary.get("api_error_rate") or 0) > 2 else ""),
        (
            "shield",
            "안전성 위반",
            _integer(summary.get("safety_violation_count"), "건"),
            "주의 필요" if (summary.get("safety_violation_count") or 0) else "감지 없음",
            "warn" if (summary.get("safety_violation_count") or 0) else "good",
        ),
        (
            "cost",
            "LLM 토큰 / API 비용",
            llm_value,
            llm_detail,
            llm_tone,
        ),
    ]
    card_html = "".join(
        _kpi_card_html(icon, label, value, detail, tone)
        for icon, label, value, detail, tone in cards
    )
    st.markdown(f'<div class="aqd-kpi-row">{card_html}</div>', unsafe_allow_html=True)


def _kpi_card_html(icon, label, value, detail, tone):
    current = f"현재 표시: {value}"
    if detail:
        current += f" · {detail}"
    tooltip = f"{KPI_TOOLTIPS[label]}\n{current}"
    escaped_tooltip = escape(tooltip, quote=True)
    return (
        f"<article class='aqd-kpi {tone}' tabindex='0' "
        f"data-tooltip='{escaped_tooltip}' aria-label='{escape(label, quote=True)}. {escaped_tooltip}'>"
        f"<div class='aqd-kpi-icon'>{_svg_icon(icon)}</div>"
        f"<div><span class='aqd-kpi-label'>{escape(label)}<i aria-hidden='true'>ⓘ</i></span>"
        f"<strong>{escape(value)}</strong><small>{escape(detail or '')}</small></div></article>"
    )


def _render_primary_panels(view):
    quality_panel, test_panel, status_panel = st.columns(PRIMARY_PANEL_COLUMNS)
    with quality_panel.container(border=True, height="stretch"):
        st.subheader("품질 점수 추이")
        _render_quality_trend(view["quality_trend"])
    with test_panel.container(border=True, height="stretch"):
        st.subheader("테스트 결과")
        _render_test_distribution(view["test_distribution"])
    with status_panel.container(border=True, height="stretch"):
        st.subheader("운영 상태")
        _render_operation_status(view["operation_status"])


def _render_secondary_panels(view):
    quality_panel, latency_panel, rag_panel = st.columns([1.25, 1, 1.45])
    with quality_panel.container(border=True, height="stretch"):
        st.subheader("품질 지표별 점수")
        _render_quality_indicators(view["quality_indicators"])
    with latency_panel.container(border=True, height="stretch"):
        latency_frame = view["latency_breakdown"]
        latency_heading = st.columns([1.05, 0.95], vertical_alignment="center", gap="small")
        with latency_heading[0]:
            st.subheader("응답시간 구성")
        with latency_heading[1]:
            if not latency_frame.empty:
                st.caption(
                    f"집계 단계 합계 {latency_frame['평균 시간(ms)'].sum() / 1000:,.2f}초",
                    text_alignment="right",
                )
        _render_latency_breakdown(latency_frame)
    with rag_panel.container(border=True, height="stretch"):
        st.subheader("RAG 검색 품질")
        _render_rag_quality(view["rag_quality"])


def _render_quality_trend(frame):
    if frame.empty:
        st.info("표시할 품질 평가 데이터가 없습니다.", icon=":material/info:")
        return
    st.altair_chart(_build_quality_trend_chart(frame))
    st.caption(f"최근 테스트 실행 {len(frame)}건 · 실행별 평가 지표 평균 × 20점")


def _build_quality_trend_chart(frame):
    return (
        alt.Chart(frame)
        .mark_line(
            interpolate="monotone",
            point=alt.OverlayMarkDef(size=65, filled=True),
            strokeWidth=3,
            color="#2563EB",
        )
        .encode(
            x=alt.X("실행:O", title="최근 테스트 실행"),
            y=alt.Y("품질점수:Q", title="점수", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                "Run ID:N",
                "테스트 케이스:Q",
                alt.Tooltip("품질점수:Q", format=".1f"),
            ],
        )
        .properties(height=PRIMARY_CHART_HEIGHT)
    )


def _render_test_distribution(frame):
    total = int(frame["건수"].sum()) if not frame.empty else 0
    if not total:
        st.info("표시할 테스트 결과가 없습니다.", icon=":material/info:")
        return
    display = frame[frame["건수"] > 0]
    chart = (
        alt.Chart(display)
        .mark_arc(innerRadius=62, outerRadius=98)
        .encode(
            theta=alt.Theta("건수:Q"),
            color=alt.Color(
                "결과:N",
                scale=alt.Scale(
                    domain=list(TEST_RESULT_COLORS),
                    range=list(TEST_RESULT_COLORS.values()),
                ),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=["결과:N", "건수:Q"],
        )
        .properties(height=PRIMARY_CHART_HEIGHT)
    )
    st.altair_chart(chart)
    st.caption(f"총 {total:,}건 · Pass {int(frame.loc[frame['결과'] == 'Pass', '건수'].sum()):,}건")


def _render_operation_status(items):
    labels = {"normal": ("정상", "green"), "warning": ("주의", "orange"), "danger": ("위험", "red"), "no_data": ("없음", "gray")}
    for item in items:
        label, color = labels[item["상태"]]
        with st.container(border=True, horizontal=True, vertical_alignment="center", gap="small"):
            st.markdown(f"**{item['영역']}**")
            st.caption(item["설명"])
            st.badge(label, color=color)


def _render_quality_indicators(frame):
    if frame.empty:
        st.info("표시할 품질 지표가 없습니다.", icon=":material/info:")
        return
    chart = (
        alt.Chart(frame)
        .mark_bar(color="#2563EB", cornerRadiusEnd=5)
        .encode(
            x=alt.X("점수:Q", scale=alt.Scale(domain=[0, 100]), title="점수"),
            y=alt.Y("품질 지표:N", sort="-x", title=None),
            tooltip=["품질 지표:N", alt.Tooltip("점수:Q", format=".1f")],
        )
        .properties(height=165)
    )
    st.altair_chart(chart)


def _render_latency_breakdown(frame):
    if frame.empty:
        st.info("표시할 단계별 응답시간이 없습니다.", icon=":material/info:")
        return
    display = frame.copy()
    display["구성"] = "평균 응답시간"
    chart = (
        alt.Chart(display)
        .mark_bar(size=42, cornerRadius=4)
        .encode(
            x=alt.X("평균 시간(ms):Q", title="밀리초"),
            y=alt.Y("구성:N", axis=None),
            color=alt.Color("단계:N", legend=alt.Legend(orient="bottom", columns=2)),
            tooltip=["단계:N", alt.Tooltip("평균 시간(ms):Q", format=",.0f")],
        )
        .properties(height=165)
    )
    st.altair_chart(chart)


def _render_rag_quality(rag):
    top_k_value = (
        _number(rag["top_k_hit_rate"], "%")
        if rag["top_k_evaluated_count"]
        else "평가 기준 없음"
    )
    metrics = [
        ("target", "검색 성공률", _number(rag["search_success_rate"], "%")),
        ("check", "Top-K 적중률", top_k_value),
        ("warning", "No Result 비율", _number(rag["no_result_rate"], "%")),
        ("timer", "평균 검색시간", _duration(rag["average_duration_ms"])),
    ]
    cards = "".join(
        f"<article><i>{_svg_icon(icon)}</i><span>{escape(label)}</span><strong>{escape(value)}</strong></article>"
        for icon, label, value in metrics
    )
    st.markdown(f'<div class="aqd-rag-grid">{cards}</div>', unsafe_allow_html=True)
    if not rag["top_k_evaluated_count"]:
        st.caption("정답 문서 기준이 수집되지 않아 Top-K 적중률을 계산하지 않았습니다.")


def _render_bottom_panels(view):
    issue_count = len(view["issues"])
    with st.expander(
        f"실패 테스트·결함 및 조치 상세 · {issue_count}건",
        expanded=False,
        icon=":material/assignment_late:",
    ):
        issues_panel, action_panel = st.columns([1.55, 1])
        with issues_panel.container(border=True, height="stretch"):
            st.markdown("#### 최근 실패 테스트 / 결함")
            if view["issues"].empty:
                st.success("선택 기간에 실패 또는 결함 이벤트가 없습니다.", icon=":material/check_circle:")
            else:
                st.dataframe(
                    view["issues"],
                    hide_index=True,
                    column_config={
                        "발생 시각(UTC)": st.column_config.DatetimeColumn("발생 시각(UTC)", format="MM-DD HH:mm:ss"),
                        "요약": st.column_config.TextColumn("요약", pinned=True),
                    },
                    height=220,
                )
        alert_column, recommendation_column = action_panel.columns(2)
        with alert_column.container(border=True, height="stretch"):
            st.markdown("#### 알림 및 액션")
            colors = {"normal": "green", "warning": "orange", "danger": "red"}
            icons = {"normal": ":material/check_circle:", "warning": ":material/warning:", "danger": ":material/error:"}
            for alert in view["alerts"]:
                st.badge(alert["message"], color=colors[alert["level"]], icon=icons[alert["level"]])
        with recommendation_column.container(border=True, height="stretch"):
            st.markdown("#### 추천 조치")
            for action in view["actions"]:
                st.write(f":material/check_circle: {action}")


def _render_page_styles():
    st.markdown(
        """
        <style>
        .aqd-status,.aqd-safety-action,.aqd-kpi-row,.aqd-rag-grid{font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#15243b}
        .aqd-status{display:grid;grid-template-columns:24px auto 1fr auto;align-items:center;gap:9px;border:1px solid #c8d9ee;border-left:4px solid var(--status-color);border-radius:7px;background:linear-gradient(90deg,#f8fbff,#fff);padding:8px 12px;margin:2px 0 9px;min-height:42px;box-sizing:border-box}
        .aqd-status-icon{width:22px;color:var(--status-color);display:flex}.aqd-status-icon svg{width:100%;height:auto}.aqd-status b{color:var(--status-color);font-size:12px}.aqd-status span{font-size:12px;color:#40536d}.aqd-status small{font-size:10px;color:#718096;white-space:nowrap}
        .aqd-safety-action{display:flex;align-items:center;gap:12px;min-height:39px;border:1px solid #f4b5af;border-left:4px solid #d83f36;border-radius:7px;background:#fff8f7;padding:7px 12px;box-sizing:border-box}.aqd-safety-action b{font-size:12px;color:#c42f28}.aqd-safety-action span{font-size:11px;color:#53657c;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
        .aqd-kpi-row{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;margin:0 0 10px}
        .aqd-kpi{height:91px;border:1px solid #c8d9ee;border-radius:7px;background:linear-gradient(145deg,#fff,#f8fbff);display:flex;align-items:center;gap:10px;padding:11px 12px;box-shadow:0 3px 10px rgba(22,78,128,.05);min-width:0;position:relative;cursor:help}
        .aqd-kpi-icon{width:36px;min-width:36px;color:#0e4a80}.aqd-kpi-icon svg{width:100%;height:auto}.aqd-kpi>div:last-child{min-width:0}.aqd-kpi span{display:block;color:#40536d;font-size:11px;font-weight:700}.aqd-kpi strong{display:block;color:#073b72;font-size:22px;line-height:1.12;margin:4px 0 2px;white-space:nowrap}.aqd-kpi small{display:block;color:#728095;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.aqd-kpi.good .aqd-kpi-icon,.aqd-kpi.good strong{color:#299049}.aqd-kpi.warn .aqd-kpi-icon,.aqd-kpi.warn strong{color:#b36a08}.aqd-kpi.bad .aqd-kpi-icon,.aqd-kpi.bad strong{color:#d83f36}
        .aqd-kpi-label i{display:inline;margin-left:4px;color:#718096;font-size:10px;font-style:normal}.aqd-kpi:focus-visible{outline:2px solid #2563eb;outline-offset:2px;z-index:31}.aqd-kpi:hover{z-index:30}
        .aqd-kpi::after{content:attr(data-tooltip);position:absolute;z-index:40;top:calc(100% + 8px);left:50%;transform:translateX(-50%);width:min(310px,calc(100vw - 32px));box-sizing:border-box;padding:11px 12px;border:1px solid #b8cbe1;border-radius:7px;background:#102a43;color:#f8fbff;box-shadow:0 8px 24px rgba(7,36,67,.22);font-size:11px;font-weight:400;line-height:1.55;white-space:pre-line;text-align:left;pointer-events:none;opacity:0;visibility:hidden;transition:opacity .12s ease}
        .aqd-kpi:hover::after,.aqd-kpi:focus-visible::after{opacity:1;visibility:visible}.aqd-kpi:first-child::after{left:0;transform:none}.aqd-kpi:last-child::after{left:auto;right:0;transform:none}
        .aqd-rag-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.aqd-rag-grid article{height:73px;border:1px solid #d4e1ef;border-radius:7px;background:linear-gradient(145deg,#fff,#f8fbff);display:grid;grid-template-columns:28px 1fr;grid-template-rows:auto 1fr;column-gap:8px;padding:9px 10px;box-sizing:border-box}.aqd-rag-grid i{grid-row:1/3;width:27px;color:#155a96;align-self:center}.aqd-rag-grid svg{width:100%;height:auto}.aqd-rag-grid span{font-size:10px;color:#40536d}.aqd-rag-grid strong{font-size:18px;color:#073b72;line-height:1.2;white-space:nowrap}
        div[data-testid="stForm"]{margin-bottom:0!important}div[data-testid="stForm"] [data-testid="stWidgetLabel"] p{font-size:10px!important;color:#40536d!important}div[data-testid="stForm"] [data-testid="stVerticalBlock"]{gap:.15rem!important}
        div[data-testid="stHeadingWithActionElements"] h1{font-size:29px!important;color:#0c3768!important;letter-spacing:-1px!important}div[data-testid="stHeadingWithActionElements"] h3{font-size:17px!important;color:#173f68!important}
        @media(max-width:1100px){.aqd-kpi-row{grid-template-columns:repeat(3,1fr)}.aqd-status{grid-template-columns:24px auto 1fr}.aqd-status small{grid-column:2/4}}
        @media(max-width:720px){.aqd-kpi-row{grid-template-columns:repeat(2,1fr)}.aqd-rag-grid{grid-template-columns:1fr}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _svg_icon(name):
    paths = {
        "star": "<path d='m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z'/>",
        "check": "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 6-7'/>",
        "timer": "<circle cx='12' cy='13' r='8'/><path d='M9 2h6m-3 3v8l4 2'/>",
        "warning": "<path d='M12 3 2.8 20h18.4L12 3Z'/><path d='M12 9v5m0 3h.01'/>",
        "shield": "<path d='M12 3 4 6v6c0 5 3.4 8.3 8 10 4.6-1.7 8-5 8-10V6l-8-3Z'/><path d='m8.5 12 2.2 2.2 4.8-5'/>",
        "cost": "<circle cx='12' cy='12' r='9'/><path d='M8 8.5h8M8 12h8m-6-6v12m4-12v12'/>",
        "monitor": "<path d='M4 18V9m5 9V5m5 13v-7m5 7V3'/>",
        "target": "<circle cx='11' cy='13' r='8'/><circle cx='11' cy='13' r='4'/><path d='m14 10 7-7m-4 0h4v4'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + paths[name]
        + "</svg>"
    )


def _normalize_date_range(value, today):
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return value[0], value[1]
    if isinstance(value, date):
        return value, value
    return today - timedelta(days=6), today


def _optional(value):
    return None if value in (None, "", "전체") else value


def _number(value, suffix):
    return "데이터 없음" if value is None else f"{float(value):,.1f}{suffix}"


def _integer(value, suffix):
    return "데이터 없음" if value is None else f"{int(value):,}{suffix}"


def _duration(value):
    return "데이터 없음" if value is None else f"{float(value) / 1000:,.2f}초"


def _currency(value):
    return "데이터 없음" if value is None else f"₩{float(value):,.0f}"
