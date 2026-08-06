from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from services.observability_service import (
    ObservabilityError,
    grafana_url,
    instant_query,
    prometheus_url,
    range_query,
    readiness_snapshot,
    tempo_url,
)


GRAFANA_DASHBOARDS = {
    "SLO·Error Budget": ("ai-qa-slo", "AI QA Executive & SLO"),
    "Agent Pipeline": ("ai-qa-agent-pipeline", "Agent Pipeline Drilldown"),
    "Drift·FinOps": ("ai-qa-audit-finops", "Audit, Drift & FinOps"),
}


@st.cache_data(ttl=15, max_entries=32, show_spinner=False)
def _snapshot(base_url):
    return readiness_snapshot(base_url)


@st.cache_data(ttl=15, max_entries=32, show_spinner=False)
def _instant(expression, base_url):
    return instant_query(expression, base_url)


@st.cache_data(ttl=30, max_entries=32, show_spinner=False)
def _range(expression, hours, base_url):
    return range_query(expression, hours=hours, base_url=base_url)


def render_observability_page(sub_menu):
    st.title("AI QA 관측성 센터")
    st.caption("기존 업무 화면과 분리된 Prometheus·Grafana·Blackbox·Tempo 운영 화면입니다.")
    _render_links(sub_menu)
    if sub_menu == "SLO·Error Budget":
        _render_slo()
    elif sub_menu == "Agent Pipeline":
        _render_agents()
    elif sub_menu == "Drift·FinOps":
        _render_drift_finops()
    elif sub_menu == "관측 인프라":
        _render_infrastructure()
    else:
        return False
    return True


def _render_links(sub_menu):
    with st.container(horizontal=True, gap="small"):
        dashboard = GRAFANA_DASHBOARDS.get(sub_menu)
        if dashboard:
            st.link_button(
                "Grafana 상세 열기",
                f"{grafana_url()}/d/{dashboard[0]}",
                icon=":material/open_in_new:",
            )
        st.link_button("Prometheus 열기", prometheus_url(), icon=":material/monitoring:")
        st.link_button("Tempo 열기", tempo_url(), icon=":material/account_tree:")


@st.fragment(run_every="30s")
def _render_slo():
    try:
        values = _snapshot(prometheus_url())
    except ObservabilityError as exc:
        st.warning(f"Prometheus 연결 후 실측값이 표시됩니다. {exc}", icon=":material/cloud_off:")
        values = {}
    with st.container(horizontal=True):
        st.metric("API 가용성", _percent(values.get("api_availability")), border=True)
        st.metric("5초 이내 응답", _percent(values.get("api_latency")), border=True)
        st.metric("테스트 통과", _percent(values.get("test_pass")), border=True)
        st.metric("품질 PASS", _percent(values.get("quality_pass")), border=True)
    st.subheader("남은 Error Budget")
    for label, key in (("API", "budget_api"), ("테스트", "budget_test"), ("품질", "budget_quality")):
        value = values.get(key)
        st.write(f"**{label}** · {_percent(value)}")
        st.progress(max(0.0, min(float(value or 0), 1.0)))
    _trend_panel(
        "SLI 추이",
        "qa:sli_api_availability:ratio_5m",
        unit_multiplier=100,
        value_name="가용성(%)",
    )


@st.fragment(run_every="20s")
def _render_agents():
    try:
        values = _snapshot(prometheus_url())
        rows = _instant(
            "sum by (source,target,operation,status) (voc_agent_rpc_calls_total)",
            prometheus_url(),
        )
    except ObservabilityError as exc:
        st.warning(f"A2A 수집기가 시작되면 Agent 지표가 표시됩니다. {exc}", icon=":material/cloud_off:")
        values, rows = {}, []
    with st.container(horizontal=True):
        st.metric("Agent 실패율", _percent(values.get("agent_failure")), border=True)
        st.metric("A2A 수집 상태", "정상" if rows else "데이터 대기", border=True)
        st.metric("관측 구간", f"{len(rows)}개", border=True)
    table = []
    for row in rows:
        metric = row.get("metric") or {}
        value = row.get("value") or [None, 0]
        table.append({
            "출발 Agent": metric.get("source"),
            "도착 Agent": metric.get("target"),
            "작업": metric.get("operation"),
            "상태": metric.get("status"),
            "호출 수": int(float(value[1])),
        })
    if table:
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    else:
        st.info("Agent Pipeline을 한 번 실행하면 기존 A2A 감사 로그에서 자동 집계됩니다.")
    _trend_panel("Agent RPC p95", "qa:agent_rpc_duration_seconds:p95_5m", value_name="p95(초)")


@st.fragment(run_every="30s")
def _render_drift_finops():
    try:
        values = _snapshot(prometheus_url())
    except ObservabilityError as exc:
        st.warning(f"품질·비용 이벤트 수집 후 실측값이 표시됩니다. {exc}", icon=":material/cloud_off:")
        values = {}
    with st.container(horizontal=True):
        st.metric("오늘 품질 점수", _number(values.get("quality_score"), "점"), border=True)
        st.metric("오늘 LLM 비용", _currency(values.get("llm_cost")), border=True)
        st.metric("품질 PASS당 비용", _currency(values.get("cost_per_pass")), border=True)
    quality, cost = st.columns(2)
    with quality.container(border=True):
        st.subheader("품질 Drift")
        _trend_panel("최근 24시간 품질", "qa:quality_score:today", hours=24, value_name="품질 점수")
    with cost.container(border=True):
        st.subheader("FinOps")
        _trend_panel("최근 24시간 비용", "qa:llm_cost_krw:today", hours=24, value_name="비용(KRW)")
    st.caption("표본이 없는 구간은 0으로 보정하지 않으며, 실제 이벤트가 수집된 경우에만 값을 표시합니다.")


@st.fragment(run_every="30s")
def _render_infrastructure():
    try:
        rows = _instant('probe_success{job="blackbox-http"}', prometheus_url())
        values = _snapshot(prometheus_url())
    except ObservabilityError as exc:
        st.warning(f"Docker 관측 스택을 시작하면 준비 상태가 표시됩니다. {exc}", icon=":material/cloud_off:")
        rows, values = [], {}
    ready = values.get("demo_ready")
    st.metric(
        "시연 준비 상태",
        "READY" if ready == 1 else ("BLOCKED" if ready == 0 else "데이터 대기"),
        border=True,
    )
    table = []
    for row in rows:
        metric = row.get("metric") or {}
        value = row.get("value") or [None, 0]
        table.append({
            "점검 대상": metric.get("instance"),
            "상태": "PASS" if float(value[1]) == 1 else "FAIL",
            "확인 시각": datetime.fromtimestamp(float(value[0])).astimezone(),
        })
    if table:
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch")
    else:
        st.info("Blackbox Exporter가 API·qa-observer·Dashboard·Grafana·Prometheus를 점검합니다.")
    with st.container(border=True):
        st.subheader("고급 분산 추적")
        st.write("Tempo OTLP 수신기와 Grafana 데이터소스가 준비되어 있습니다.")
        st.code("A2A_TEMPO_ENABLED=true\nOTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318")
        st.caption("기본값은 비활성화입니다. 활성화해도 추적 전송 실패가 Agent Pipeline을 중단하지 않습니다.")


def _trend_panel(title, expression, *, hours=6, unit_multiplier=1, value_name="값"):
    try:
        rows = _range(expression, hours, prometheus_url())
    except ObservabilityError:
        rows = []
    data = []
    for row in rows:
        label = (row.get("metric") or {}).get("__name__") or title
        for timestamp, value in row.get("values") or []:
            try:
                data.append({"시각": datetime.fromtimestamp(float(timestamp)), "지표": label, value_name: float(value) * unit_multiplier})
            except (TypeError, ValueError):
                continue
    st.markdown(f"**{title}**")
    if data:
        frame = pd.DataFrame(data)
        chart = frame.pivot_table(index="시각", columns="지표", values=value_name, aggfunc="last")
        st.line_chart(chart)
    else:
        st.caption("표시할 시계열 데이터가 없습니다.")


def _percent(value):
    return "데이터 없음" if value is None else f"{float(value) * 100:,.1f}%"


def _number(value, suffix=""):
    return "데이터 없음" if value is None else f"{float(value):,.1f}{suffix}"


def _currency(value):
    return "데이터 없음" if value is None else f"₩{float(value):,.0f}"
