import html
import json
import importlib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import altair as alt
import httpx
import pandas as pd
import streamlit as st

from components.performance_design import (
    render_page_hero,
    render_performance_design_styles,
    render_section_header,
)
from core.paths import PROJECT_DIR, REPORTS_DIR


if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import GRAFANA_DASHBOARD_URL, GRAFANA_URL, K6_SUMMARY_FILE, PROMETHEUS_URL  # noqa: E402


PROMETHEUS_TIMEOUT_SECONDS = 0.5
DETAIL_HTTP_TIMEOUT_SECONDS = 1.5
DETAIL_LOG_TAIL_LINES = 120
OPS_SNAPSHOT_CACHE_TTL_SECONDS = 5
FASTAPI_URL = "http://localhost:8000"
CHROMA_URL = os.getenv("CHROMA_URL", "http://localhost:8001").rstrip("/")
DEFAULT_OPS_REFRESH_MODE = "수동"
NETWORK_HISTORY_MAX_SAMPLES = 60
NETWORK_SAMPLE_INTERVAL_SECONDS = 5
NETWORK_PANEL_COLUMN_RATIO = (1.7, 0.8)
NETWORK_PORT_GRID_COLUMNS = 1
NETWORK_SERIES_COLORS = {
    "Inbound Mbps": "#2563EB",
    "Outbound Mbps": "#14B8A6",
}


def render_ops_monitoring_page():
    render_ops_design_styles()
    st.markdown(
        """
        <div class="ops-hero">
            <div class="ops-hero-icon">__ICON__</div>
            <div><div class="ops-hero-title">운영 모니터링</div>
            <p>서비스 상태 · 실시간 네트워크 · FastAPI 요청 · 성능 테스트 결과를 한 화면에서 확인합니다.</p></div>
        </div>
        """.replace("__ICON__", _ops_svg_icon("monitor")),
        unsafe_allow_html=True,
    )
    refresh_settings = render_refresh_control()

    run_every = f"{refresh_settings['seconds']}s" if refresh_settings["mode"] == "auto" else None
    st.fragment(render_ops_monitoring_snapshot, run_every=run_every)()


def render_ops_monitoring_snapshot():
    with st.spinner("운영 지표를 불러오는 중입니다...", show_time=True):
        snapshot = collect_ops_snapshot()

    render_major_feature_status(snapshot)
    render_live_network_performance()
    render_top_pages(snapshot)
    render_golden_signals(snapshot)
    render_request_dashboard(snapshot)
    render_traffic_and_errors(snapshot)
    render_duration_distribution(snapshot)
    render_k6_summary(snapshot)


def render_ops_design_styles():
    st.markdown(
        """
        <style>
        .ops-hero,.ops-section-head,.ops-metric-grid,.ops-status-row,.ops-signal-grid,.net-status-row{
            font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif;color:#15243b
        }
        .ops-hero{display:flex;align-items:center;gap:15px;border:1px solid #c8d9ee;border-left:5px solid #155a96;
            border-radius:9px;background:linear-gradient(110deg,#f5faff,#fff);padding:14px 17px;margin:3px 0 13px;
            box-shadow:0 4px 14px rgba(22,78,128,.06);box-sizing:border-box;width:100%}
        .ops-hero-icon{width:46px;min-width:46px;color:#155a96}.ops-hero-icon svg{width:100%;height:auto}
        .ops-hero-title{font-size:21px;font-weight:850;color:#073b72;letter-spacing:-.4px}.ops-hero p{margin:3px 0 0;color:#53657c;font-size:12px}
        .ops-section-head{display:flex;align-items:center;gap:10px;margin:21px 0 9px;padding-bottom:8px;border-bottom:1px solid #dbe6f2;width:100%}
        .ops-section-icon{display:flex;width:30px;height:30px;min-width:30px;padding:5px;border-radius:8px;color:#155a96;background:#eaf3fb;box-sizing:border-box}
        .ops-section-icon svg{width:100%;height:auto}.ops-section-copy{min-width:0}.ops-section-title{font-size:16px;font-weight:850;color:#173f68;line-height:1.2}
        .ops-section-desc{font-size:10px;color:#718096;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .ops-metric-grid{display:grid;grid-template-columns:repeat(var(--ops-cols,6),minmax(0,1fr));gap:10px;margin:2px 0 12px;width:100%}
        .ops-metric{height:88px;border:1px solid #c8d9ee;border-radius:8px;background:linear-gradient(145deg,#fff,#f8fbff);display:flex;align-items:center;gap:9px;padding:10px 11px;box-sizing:border-box;min-width:0;box-shadow:0 3px 10px rgba(22,78,128,.05)}
        .ops-metric-icon{display:flex;width:32px;min-width:32px;color:#155a96}.ops-metric-icon svg{width:100%;height:auto}.ops-metric-copy{min-width:0}
        .ops-metric-label{display:block;color:#40536d;font-size:10px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .ops-metric strong{display:block;color:#073b72;font-size:20px;line-height:1.14;margin:4px 0 2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .ops-metric small{display:block;color:#728095;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
        .ops-metric.good .ops-metric-icon,.ops-metric.good strong{color:#299049}.ops-metric.warn .ops-metric-icon,.ops-metric.warn strong{color:#b36a08}.ops-metric.bad .ops-metric-icon,.ops-metric.bad strong{color:#d83f36}
        .ops-signal-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;width:100%;margin-bottom:12px}
        .ops-signal{border:1px solid #cbdbea;border-radius:8px;background:#fff;display:grid;grid-template-columns:34px 1fr auto;align-items:center;gap:9px;padding:11px;min-height:72px;box-sizing:border-box}
        .ops-signal-icon{display:flex;width:32px;color:#155a96}.ops-signal-icon svg{width:100%;height:auto}.ops-signal span{display:block;font-size:10px;color:#53657c}.ops-signal strong{display:block;font-size:17px;color:#073b72;margin-top:3px}.ops-signal em{font-style:normal;font-size:10px;font-weight:800;padding:3px 7px;border-radius:999px;background:#eef2f7;color:#64748b;white-space:nowrap}
        .ops-signal.good em{background:#dcfce7;color:#15803d}.ops-signal.warn em{background:#fef3c7;color:#b45309}.ops-signal.bad em{background:#fee2e2;color:#b91c1c}
        @media(max-width:1100px){.ops-metric-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.ops-signal-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ops-status-row{grid-template-columns:repeat(3,minmax(0,1fr))!important}}
        @media(max-width:720px){.ops-hero{align-items:flex-start}.ops-metric-grid,.ops-signal-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ops-status-row{grid-template-columns:repeat(2,minmax(0,1fr))!important}.ops-section-desc{white-space:normal}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_ops_section_header(icon, title, description):
    st.markdown(
        f"<div class='ops-section-head'><span class='ops-section-icon'>{_ops_svg_icon(icon)}</span>"
        f"<div class='ops-section-copy'><div class='ops-section-title'>{html.escape(title)}</div>"
        f"<div class='ops-section-desc'>{html.escape(description)}</div></div></div>",
        unsafe_allow_html=True,
    )


def _render_ops_metric_grid(cards, columns=6):
    card_html = "".join(
        f"<article class='ops-metric {html.escape(tone)}'><span class='ops-metric-icon'>{_ops_svg_icon(icon)}</span>"
        f"<div class='ops-metric-copy'><span class='ops-metric-label'>{html.escape(str(label))}</span>"
        f"<strong>{html.escape(str(value))}</strong><small>{html.escape(str(detail or ''))}</small></div></article>"
        for icon, label, value, detail, tone in cards
    )
    st.markdown(
        f"<div class='ops-metric-grid' style='--ops-cols:{int(columns)}'>{card_html}</div>",
        unsafe_allow_html=True,
    )


def _ops_svg_icon(name):
    paths = {
        "monitor": "<rect x='3' y='4' width='18' height='13' rx='2'/><path d='M8 21h8m-4-4v4M7 12l3-3 3 2 4-4'/>",
        "services": "<rect x='3' y='4' width='7' height='6' rx='1'/><rect x='14' y='4' width='7' height='6' rx='1'/><rect x='8.5' y='15' width='7' height='6' rx='1'/><path d='M6.5 10v2h11v-2m-5.5 2v3'/>",
        "network": "<circle cx='5' cy='12' r='2'/><circle cx='19' cy='6' r='2'/><circle cx='19' cy='18' r='2'/><path d='m7 11 10-4m-10 6 10 4'/>",
        "ranking": "<path d='M4 20V10m6 10V4m6 16v-7m4 7H2'/>",
        "pulse": "<path d='M3 12h4l2-6 4 12 2-6h6'/>",
        "request": "<path d='M4 7h13m-4-4 4 4-4 4M20 17H7m4-4-4 4 4 4'/>",
        "check": "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 6-7'/>",
        "warning": "<path d='M12 3 2.8 20h18.4L12 3Z'/><path d='M12 9v5m0 3h.01'/>",
        "timer": "<circle cx='12' cy='13' r='8'/><path d='M9 2h6m-3 3v8l4 2'/>",
        "traffic": "<path d='M4 18V9m5 9V5m5 13v-7m5 7V3'/>",
        "gauge": "<path d='M4 18a8 8 0 1 1 16 0'/><path d='m12 18 5-7M7 18h10'/>",
        "percent": "<path d='m7 17 10-10'/><circle cx='7' cy='7' r='2'/><circle cx='17' cy='17' r='2'/>",
        "database": "<ellipse cx='12' cy='5' rx='8' ry='3'/><path d='M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6'/>",
        "grafana": "<circle cx='12' cy='12' r='8'/><path d='M12 4v4l3 2 3-1M7 18l3-4 4 2 3-4'/>",
        "prometheus": "<path d='M12 3c1 4-2 5-2 8 0 1.7 1 3 2 3s2-1.3 2-3c2 2 3 4 3 6a5 5 0 0 1-10 0c0-3 2-5 5-8'/><path d='M8 20h8'/>",
        "test": "<path d='M9 4h6l1 3h3v14H5V7h3l1-3Z'/><path d='m8 13 2 2 5-5m-7 8h8'/>",
        "metrics": "<path d='M3 13h4l2-6 4 11 2-6h6'/><path d='M4 4h16v16H4z'/>",
        "health": "<path d='M12 20S4 15.5 4 9.5A4.5 4.5 0 0 1 12 7a4.5 4.5 0 0 1 8 2.5C20 15.5 12 20 12 20Z'/><path d='M7 12h3l1-2 2 4 1-2h3'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        + paths[name]
        + "</svg>"
    )


@st.fragment(run_every=f"{NETWORK_SAMPLE_INTERVAL_SECONDS}s")
def render_live_network_performance():
    render_network_performance(collect_network_snapshot())


def render_refresh_control():
    if "ops_refresh_seconds" not in st.session_state:
        st.session_state.ops_refresh_seconds = 30
    else:
        st.session_state.ops_refresh_seconds = min(max(int(st.session_state.ops_refresh_seconds), 5), 180)
    if "ops_refresh_mode" not in st.session_state:
        st.session_state.ops_refresh_mode = DEFAULT_OPS_REFRESH_MODE

    control_cols = st.columns([0.28, 0.38, 0.34])
    with control_cols[0]:
        refresh_mode = st.radio(
            "새로고침 방식",
            ["자동", "수동"],
            horizontal=True,
            key="ops_refresh_mode",
        )

    refresh_seconds = int(st.session_state.get("ops_refresh_seconds", 30))
    with control_cols[1]:
        if refresh_mode == "자동":
            refresh_seconds = st.slider(
                "자동 새로고침(초)",
                min_value=5,
                max_value=180,
                step=5,
                key="ops_refresh_seconds",
                help="지정한 초마다 운영 모니터링 화면을 자동 갱신합니다.",
            )
        else:
            st.caption("자동 새로고침이 꺼져 있습니다.")

    with control_cols[2]:
        if refresh_mode == "자동":
            st.caption(f"현재 설정: {refresh_seconds}초마다 자동 갱신")
        elif st.button("수동 새로고침", width="stretch"):
            collect_ops_snapshot.clear()
            st.rerun()

    return {
        "mode": "auto" if refresh_mode == "자동" else "manual",
        "seconds": refresh_seconds,
    }

def render_ops_detail_page():
    render_performance_design_styles()
    render_page_hero(
        "database",
        "운영 세부데이터",
        "주요 서비스의 구성 정보, 실제 엔드포인트 응답과 최근 실행 로그를 상세하게 확인합니다.",
    )

    render_section_header("database", "상세 데이터 보기", "서비스 구성 · 제공 엔드포인트 · 최근 로그 중 확인할 영역")
    detail_view = st.segmented_control(
        "상세 데이터",
        ["서비스 정보", "제공 정보", "서비스 로그"],
        default="서비스 정보",
        width="stretch",
        key="ops_detail_view",
    )
    if detail_view == "서비스 정보":
        render_ops_service_information()
    elif detail_view == "제공 정보":
        render_ops_endpoint_details()
    else:
        render_ops_logs()


def render_ops_service_information():
    service_rows = pd.DataFrame(
        [
            {
                "서비스": "FastAPI",
                "주요 주소": FASTAPI_URL,
                "상태/정보": "/health, /metrics, /ask",
                "제공 정보": "헬스체크, Prometheus 메트릭, 질문 응답 API",
            },
            {
                "서비스": "Prometheus",
                "주요 주소": PROMETHEUS_URL,
                "상태/정보": "/-/ready, /api/v1/targets",
                "제공 정보": "수집 준비 상태, scrape 대상 상태, 시계열 지표",
            },
            {
                "서비스": "Grafana",
                "주요 주소": GRAFANA_DASHBOARD_URL or GRAFANA_URL,
                "상태/정보": "/api/health",
                "제공 정보": "대시보드 접속 및 Grafana 내부 상태",
            },
            {
                "서비스": "ChromaDB / 지식DB",
                "주요 주소": CHROMA_URL,
                "상태/정보": "업로드 파일과 검색 반영 상태 비교",
                "제공 정보": "지식파일 업로드 목록, 검색 반영 완료 여부",
            },
            {
                "서비스": "k6",
                "주요 주소": str(REPORTS_DIR / "k6_runs"),
                "상태/정보": "최근 실행 기록",
                "제공 정보": "성능 테스트 설정, 요청 수, 실패율, 응답시간 요약",
            },
        ]
    )
    render_section_header("services", "주요 서비스 정보", "운영 구성요소별 주소와 상태 확인 기준")
    st.dataframe(service_rows, hide_index=True, width="stretch")


def render_ops_endpoint_details():
    endpoints = [
        ("FastAPI", "/health", f"{FASTAPI_URL}/health", "애플리케이션 생존 상태"),
        ("FastAPI", "/metrics", f"{FASTAPI_URL}/metrics", "Prometheus 수집 메트릭"),
        ("FastAPI", "/ask", f"{FASTAPI_URL}/ask?question=health", "질문 응답 API 샘플"),
        ("Prometheus", "/-/ready", f"{PROMETHEUS_URL}/-/ready", "Prometheus 준비 상태"),
        ("Prometheus", "/api/v1/targets", f"{PROMETHEUS_URL}/api/v1/targets", "수집 대상 상세 상태"),
        ("Grafana", "/api/health", f"{GRAFANA_URL}/api/health", "Grafana 내부 상태"),
    ]
    details = [read_service_endpoint_detail(*endpoint) for endpoint in endpoints]

    rows = pd.DataFrame(
        [
            {
                "서비스": detail["service"],
                "엔드포인트": detail["endpoint"],
                "상태": detail["status"],
                "응답코드": detail["status_code"],
                "제공 정보": detail["summary"],
            }
            for detail in details
        ]
    )
    render_section_header("endpoint", "서비스 제공 정보", "실제 엔드포인트 응답 상태와 제공 데이터 요약")
    st.dataframe(rows, hide_index=True, width="stretch")

    for detail in details:
        with st.expander(f"{detail['service']} {detail['endpoint']} 응답 상세", expanded=False):
            st.caption(detail["url"])
            st.code(detail["preview"], language=detail["language"])


def render_ops_logs():
    render_section_header("logs", "서비스 로그", "FastAPI, Prometheus, Grafana와 k6의 최근 실행 기록")
    st.caption(f"최근 {DETAIL_LOG_TAIL_LINES}줄 기준으로 표시합니다.")
    log_sources = [
        ("FastAPI 로컬 로그", read_text_tail(REPORTS_DIR / "fastapi_service.log")),
        ("Prometheus 컨테이너 로그", read_docker_logs("ai-quality-prometheus")),
        ("Grafana 컨테이너 로그", read_docker_logs("ai-quality-grafana")),
        ("최근 k6 실행 기록", read_latest_k6_run_record()),
    ]

    for label, content in log_sources:
        with st.expander(label, expanded=False):
            st.code(content or "표시할 로그가 없습니다.", language="text")


def read_service_endpoint_detail(service, endpoint, url, description):
    try:
        response = get_http_client().get(normalize_request_url(url), timeout=DETAIL_HTTP_TIMEOUT_SECONDS)
        body = response.text.strip()
        preview, language = format_response_preview(response, body)
        return {
            "service": service,
            "endpoint": endpoint,
            "url": url,
            "status": "정상" if response.status_code < 400 else "비정상",
            "status_code": response.status_code,
            "summary": summarize_endpoint_body(endpoint, response, body) or description,
            "preview": preview,
            "language": language,
        }
    except Exception as exc:
        return {
            "service": service,
            "endpoint": endpoint,
            "url": url,
            "status": "비정상",
            "status_code": "-",
            "summary": "서비스 응답을 받을 수 없습니다.",
            "preview": f"{type(exc).__name__}: {exc}",
            "language": "text",
        }


def summarize_endpoint_body(endpoint, response, body):
    if response.status_code >= 400:
        return f"HTTP {response.status_code} 응답"

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if endpoint == "/metrics":
        metric_lines = [line for line in body.splitlines() if line and not line.startswith("#")]
        return f"메트릭 {len(metric_lines)}개 노출"

    if endpoint == "/api/v1/targets" and isinstance(payload, dict):
        active_targets = payload.get("data", {}).get("activeTargets", [])
        healthy_targets = sum(1 for target in active_targets if target.get("health") == "up")
        return f"수집 대상 {len(active_targets)}개, 정상 {healthy_targets}개"

    if isinstance(payload, dict):
        if "status" in payload:
            return f"상태: {payload.get('status')}"
        if "database" in payload:
            return f"DB: {payload.get('database')}, 버전: {payload.get('version', '-')}"

    return "응답 수신"


def format_response_preview(response, body, max_chars=6000):
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            body = json.dumps(response.json(), ensure_ascii=False, indent=2)
        except ValueError:
            pass
        language = "json"
    else:
        language = "text"

    if not body:
        body = "(빈 응답)"
    if len(body) > max_chars:
        body = f"{body[:max_chars]}\n... 생략 ..."
    return body, language


def read_text_tail(path, max_lines=DETAIL_LOG_TAIL_LINES):
    if not path.exists():
        return f"로그 파일이 없습니다: {path}"

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return f"로그 파일을 읽을 수 없습니다: {exc}"
    return "\n".join(lines[-max_lines:])


def read_docker_logs(container_name):
    result = run_detail_command(["docker", "logs", "--tail", str(DETAIL_LOG_TAIL_LINES), container_name], timeout=6)
    if result["ok"]:
        content = "\n".join(part for part in [result["stdout"], result["stderr"]] if part.strip())
        return content.strip() or "컨테이너 로그가 비어 있습니다."

    message = result["stderr"] or result["stdout"] or "Docker 명령을 실행할 수 없습니다."
    return f"Docker 로그 조회 실패: {message.strip()}"


def read_latest_k6_run_record():
    runs_dir = REPORTS_DIR / "k6_runs"
    if not runs_dir.exists():
        return f"k6 실행 기록 폴더가 없습니다: {runs_dir}"

    records = sorted(runs_dir.glob("*/run_record.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not records:
        return "k6 실행 기록이 없습니다."

    latest_record = records[0]
    try:
        payload = json.loads(latest_record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"최근 k6 기록을 읽을 수 없습니다: {exc}"

    summary = {
        "file": str(latest_record),
        "created_at": payload.get("created_at"),
        "settings": payload.get("settings"),
        "summary": payload.get("summary"),
        "exit_code": payload.get("exit_code"),
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def run_detail_command(command, timeout=6):
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc)}

    return {
        "ok": completed.returncode == 0,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@st.cache_data(ttl=OPS_SNAPSHOT_CACHE_TTL_SECONDS, max_entries=1, show_spinner=False)
def collect_ops_snapshot():
    prometheus = PrometheusClient(PROMETHEUS_URL)
    with ThreadPoolExecutor(max_workers=3) as executor:
        prometheus_future = executor.submit(prometheus.is_available)
        evaluation_future = executor.submit(load_evaluation_summary)
        k6_future = executor.submit(load_k6_summary)

        prometheus_alive = prometheus_future.result()
        evaluation = evaluation_future.result()
        k6_summary = k6_future.result()

    if prometheus_alive:
        with ThreadPoolExecutor(max_workers=2) as executor:
            prometheus_data_future = executor.submit(collect_prometheus_data, prometheus)
            feature_statuses_future = executor.submit(build_feature_statuses, True, evaluation)
            prometheus_data = prometheus_data_future.result()
            feature_statuses = feature_statuses_future.result()
    else:
        prometheus_data = empty_prometheus_data()
        feature_statuses = build_feature_statuses(False, evaluation)

    metrics = prometheus_data["metrics"]

    total_requests = metrics.get("total_requests")
    error_requests = metrics.get("error_requests")
    avg_latency = metrics.get("avg_latency")
    p95_latency = metrics.get("p95_latency")
    error_rate = calculate_rate(error_requests, total_requests)
    request_metrics_available = prometheus_alive and any(
        value is not None for value in (total_requests, error_requests, avg_latency, p95_latency)
    )

    return {
        "prometheus_alive": prometheus_alive,
        "prometheus_url": PROMETHEUS_URL,
        "grafana_url": GRAFANA_URL,
        "grafana_dashboard_url": GRAFANA_DASHBOARD_URL,
        "request_metrics_available": request_metrics_available,
        "request_metrics_source": {
            "name": "Prometheus → FastAPI /metrics",
            "window": "최근 5분",
            "scope": "/metrics를 제외한 FastAPI 전체 HTTP 요청",
        },
        "total_requests": total_requests,
        "success_requests": calculate_success_requests(total_requests, error_requests),
        "error_requests": error_requests,
        "error_rate": error_rate,
        "avg_latency": avg_latency,
        "p95_latency": p95_latency,
        "service_up": metrics.get("service_up"),
        "request_series": prometheus_data["request_series"],
        "error_series": prometheus_data["error_series"],
        "duration_series": prometheus_data["duration_series"],
        "evaluation": evaluation,
        "k6_summary": k6_summary,
        "duration_distribution": build_duration_distribution(avg_latency, p95_latency),
        "top_pages": prometheus_data["top_pages"] if prometheus_alive else build_top_pages_from_k6_runs(),
        "feature_statuses": feature_statuses,
    }


def collect_prometheus_data(prometheus):
    number_queries = {
        "total_requests": "sum(increase(http_requests_total[5m]))",
        "error_requests": 'sum(increase(http_requests_total{status=~"5..|4.."}[5m]))',
        "avg_latency": "rate(agent_response_seconds_sum[5m]) / rate(agent_response_seconds_count[5m])",
        "p95_latency": "histogram_quantile(0.95, sum(rate(agent_response_seconds_bucket[5m])) by (le))",
        "service_up": "up",
    }
    range_queries = {
        "request_series": "sum(increase(http_requests_total[1m]))",
        "error_series": 'sum(increase(http_requests_total{status=~"5..|4.."}[1m]))',
        "duration_series": "rate(agent_response_seconds_sum[1m]) / rate(agent_response_seconds_count[1m])",
    }
    top_pages_query = "topk(5, sum by (path) (increase(http_requests_total[30m])))"

    with ThreadPoolExecutor(max_workers=9) as executor:
        number_futures = {
            name: executor.submit(prometheus.query_number, query)
            for name, query in number_queries.items()
        }
        range_futures = {
            name: executor.submit(prometheus.query_range_series, query)
            for name, query in range_queries.items()
        }
        top_pages_future = executor.submit(prometheus.query_vector, top_pages_query)

        metrics = {name: future.result() for name, future in number_futures.items()}
        series = {name: future.result() for name, future in range_futures.items()}
        top_pages = build_top_pages_from_results(top_pages_future.result())

    return {"metrics": metrics, "top_pages": top_pages, **series}


def empty_prometheus_data():
    return {
        "metrics": {},
        "request_series": pd.DataFrame(),
        "error_series": pd.DataFrame(),
        "duration_series": pd.DataFrame(),
        "top_pages": pd.DataFrame(),
    }


def render_connection_status(snapshot):
    st.markdown("#### 연결 상태")
    cols = st.columns(3)
    prometheus_status = "연결됨" if snapshot["prometheus_alive"] else "연결 안 됨"
    cols[0].metric("Prometheus", prometheus_status, snapshot["prometheus_url"])
    cols[1].metric("Grafana", "URL 설정됨" if snapshot["grafana_url"] else "설정 없음", snapshot["grafana_url"] or "-")
    cols[2].metric("k6 결과", "로드됨" if snapshot["k6_summary"] else "파일 없음")

    if not snapshot["prometheus_alive"]:
        st.warning("Prometheus 연결 안 됨. 운영 요청 지표는 다른 테스트 결과로 대체하지 않고 데이터 없음으로 표시합니다.")


def render_monitoring_actions(snapshot):
    dashboard_url = snapshot["grafana_dashboard_url"] or snapshot["grafana_url"]
    st.caption("이 화면의 지표는 Streamlit이 Prometheus API를 직접 조회해 표시합니다. 최신 값은 화면을 새로고침하면 다시 조회됩니다.")
    action_cols = st.columns([1, 1, 4])
    with action_cols[0]:
        if st.button("현재 지표 새로고침", width="stretch"):
            collect_ops_snapshot.clear()
            st.rerun()
    with action_cols[1]:
        if dashboard_url:
            st.link_button("Grafana 열기", dashboard_url, width="stretch")
        else:
            st.button("Grafana 미설정", disabled=True, width="stretch")
    if not dashboard_url:
        st.info("Grafana URL이 설정되지 않았습니다. .env에 GRAFANA_URL 또는 GRAFANA_DASHBOARD_URL을 설정하세요.")


def render_major_feature_status(snapshot):
    statuses = snapshot.get("feature_statuses", [])
    if not statuses:
        return

    status_html = "\n".join(
        f"""
        <div class="ops-status-chip ops-status-{item['level']}">
            <span class="ops-status-service-icon">{_ops_svg_icon(_feature_status_icon(item['name']))}</span>
            <div class="ops-status-copy"><div class="ops-status-name">{html.escape(str(item['name']))}</div>
            <div class="ops-status-value"><span class="ops-status-dot"></span>{html.escape(str(item['status']))}</div></div>
        </div>
        """
        for item in statuses
    )
    st.markdown(
        f"""
        <style>
        .ops-status-row {{
            display: grid;
            grid-template-columns: repeat(var(--ops-status-cols, 6), minmax(0, 1fr));
            gap: 10px;
            margin: 4px 0 18px;
            width: 100%;
        }}
        .ops-status-chip {{
            border: 1px solid #d9e0ea;
            border-radius: 8px;
            padding: 11px 12px;
            background: #ffffff;
            min-height: 76px;
            display:flex;
            align-items:center;
            gap:10px;
            min-width:0;
            box-sizing:border-box;
            box-shadow:0 3px 10px rgba(22,78,128,.04);
        }}
        .ops-status-service-icon {{
            display:flex;
            width:34px;
            min-width:34px;
            color:#155a96;
        }}
        .ops-status-service-icon svg {{
            width:100%;
            height:auto;
        }}
        .ops-status-copy {{
            min-width:0;
        }}
        .ops-status-name {{
            color: #475569;
            font-size: 12px;
            font-weight: 700;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin-bottom: 6px;
        }}
        .ops-status-value {{
            font-size: 16px;
            font-weight: 800;
            line-height: 1.1;
            display:flex;
            align-items:center;
            gap:5px;
        }}
        .ops-status-dot {{
            width:7px;
            height:7px;
            border-radius:999px;
            background:currentColor;
        }}
        .ops-status-ok {{
            border-color: #bbf7d0;
            background: #f0fdf4;
        }}
        .ops-status-ok .ops-status-value {{
            color: #15803d;
        }}
        .ops-status-ok .ops-status-service-icon {{color:#299049;}}
        .ops-status-bad {{
            border-color: #fecaca;
            background: #fef2f2;
        }}
        .ops-status-bad .ops-status-value {{
            color: #b91c1c;
        }}
        .ops-status-bad .ops-status-service-icon {{color:#d83f36;}}
        .ops-status-warn {{
            border-color: #fde68a;
            background: #fffbeb;
        }}
        .ops-status-warn .ops-status-value {{
            color: #b45309;
        }}
        .ops-status-warn .ops-status-service-icon {{color:#b36a08;}}
        .ops-status-neutral {{
            border-color: #e2e8f0;
            background: #f8fafc;
        }}
        .ops-status-neutral .ops-status-value {{
            color: #64748b;
        }}
        .ops-status-neutral .ops-status-service-icon {{color:#7b8797;}}
        </style>
        <div class="ops-section-head"><span class="ops-section-icon">{_ops_svg_icon('services')}</span>
          <div class="ops-section-copy"><div class="ops-section-title">주요 기능 상태</div>
          <div class="ops-section-desc">핵심 서비스의 연결 및 실행 상태를 동일 기준으로 비교합니다.</div></div></div>
        <div class="ops-status-row" style="--ops-status-cols:{len(statuses)}">{status_html}</div>
        """,
        unsafe_allow_html=True,
    )


def render_network_performance(network):
    _render_ops_section_header("network", "네트워크 성능", "실시간 송수신 트래픽과 네트워크 어댑터 연결 상태")
    adapters = network.get("adapters", [])
    if not adapters:
        st.info("네트워크 인터페이스 상태를 읽을 수 없습니다. Windows PowerShell의 Get-NetAdapter 권한을 확인하세요.")
        return

    traffic_rates = update_network_traffic_history(network)
    chart_col, status_col = st.columns(NETWORK_PANEL_COLUMN_RATIO)
    with chart_col:
        st.caption(
            f"전체 실시간 트래픽: Inbound {traffic_rates['inbound_mbps']:.3f} Mbps / "
            f"Outbound {traffic_rates['outbound_mbps']:.3f} Mbps"
        )
        history = pd.DataFrame(st.session_state.get("ops_network_history", []))
        if len(history) >= 2:
            st.altair_chart(build_network_traffic_chart(history))
            st.caption(
                f"최근 {len(history)}개 샘플 · 운영체제 누적 송수신 바이트의 구간 차이로 Mbps를 계산합니다. "
                f"이 영역만 {NETWORK_SAMPLE_INTERVAL_SECONDS}초마다 독립적으로 갱신됩니다."
            )
        else:
            st.info(
                f"첫 번째 기준 샘플을 수집했습니다. 약 {NETWORK_SAMPLE_INTERVAL_SECONDS}초 후부터 "
                "트래픽 변화율이 자동으로 표시됩니다."
            )

    with status_col:
        status_html = "\n".join(
            f"""
            <div class="net-port net-{_adapter_level(adapter['status'])}">
                <span class="net-port-icon">{_ethernet_port_svg(_adapter_level(adapter['status']))}</span>
                <div class="net-port-copy"><div class="net-name">{html.escape(str(adapter['name']))}</div>
                <div class="net-port-meta"><strong>{_adapter_status_label(adapter['status'])}</strong><span>{html.escape(str(adapter.get('link_speed') or '-'))}</span></div></div>
            </div>
            """
            for adapter in adapters
        )
        st.markdown(
            f"""
            <style>
            .net-status-row {{
                display:grid;
                grid-template-columns: repeat({NETWORK_PORT_GRID_COLUMNS}, minmax(0, 1fr));
                column-gap:18px;
                row-gap:2px;
                width:100%;
            }}
            .net-port {{
                display:flex;
                align-items:center;
                gap:10px;
                padding:8px 2px;
                min-height:52px;
                border-bottom:1px solid #e4ebf3;
                box-sizing:border-box;
                min-width:0;
            }}
            .net-port-icon {{
                display:flex;
                width:38px;
                min-width:38px;
            }}
            .net-port-icon svg {{width:100%;height:auto;}}
            .net-port-copy {{min-width:0;flex:1;}}
            .net-port-meta {{display:flex;align-items:center;gap:7px;margin-top:4px;}}
            .net-port-meta strong {{font-size:13px;line-height:1;}}
            .net-port-meta span {{color:#718096;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
            .net-up .net-port-icon,.net-up .net-port-meta strong {{color:#15803d;}}
            .net-down .net-port-icon,.net-down .net-port-meta strong {{color:#b91c1c;}}
            .net-hang .net-port-icon,.net-hang .net-port-meta strong {{color:#b45309;}}
            @media(max-width:900px) {{
                .net-status-row {{grid-template-columns:1fr;}}
            }}
            .net-name {{
                color:#475569;
                font-size:12px;
                font-weight:700;
                white-space:nowrap;
                overflow:hidden;
                text-overflow:ellipsis;
            }}
            </style>
            <div class="net-status-row">{status_html}</div>
            """,
            unsafe_allow_html=True,
        )


def render_top_pages(snapshot):
    _render_ops_section_header("ranking", "주요 Top5 페이지 접속 및 사용", "최근 30분간 요청이 많은 FastAPI 경로 순위")
    top_pages = snapshot.get("top_pages", pd.DataFrame())
    if top_pages.empty:
        st.info("최근 페이지 접속 데이터를 찾지 못했습니다. FastAPI 요청 또는 k6 수행 후 표시됩니다.")
        return

    st.dataframe(top_pages, hide_index=True, width="stretch")


def render_golden_signals(snapshot):
    _render_ops_section_header("pulse", "Golden Signals", "지연시간 · 트래픽 · 오류 · 포화도를 한눈에 확인하는 운영 핵심 신호")
    latency_status = classify_latency(snapshot["p95_latency"])
    traffic_status = "정상" if snapshot["total_requests"] is not None else "데이터 없음"
    error_status = classify_error_rate(snapshot["error_rate"])
    saturation_status = "데이터 없음"

    signals = [
        ("timer", "Latency", format_seconds(snapshot["p95_latency"]), latency_status),
        ("traffic", "Traffic", format_request_count(snapshot["total_requests"], " req"), traffic_status),
        ("warning", "Errors", format_percentage(snapshot["error_rate"]), error_status),
        ("database", "Saturation", "추가 메트릭 필요", saturation_status),
    ]
    cards = "".join(
        f"<article class='ops-signal {_ops_status_tone(status)}'><span class='ops-signal-icon'>{_ops_svg_icon(icon)}</span>"
        f"<div><span>{html.escape(label)}</span><strong>{html.escape(value)}</strong></div><em>{html.escape(status)}</em></article>"
        for icon, label, value, status in signals
    )
    st.markdown(f"<div class='ops-signal-grid'>{cards}</div>", unsafe_allow_html=True)


def render_request_dashboard(snapshot):
    _render_ops_section_header("request", "FastAPI 운영 요청 / 오류율 / 응답시간", "Prometheus가 수집한 최근 5분 FastAPI 운영 요청")
    source = snapshot["request_metrics_source"]
    st.caption(
        f"출처: {source['name']} · 범위: {source['scope']}. "
        "k6가 FastAPI를 호출하면 해당 요청도 포함되지만, 최신 k6 결과나 테스트케이스 PASS/FAIL 이력을 표시하는 영역은 아닙니다."
    )
    if not snapshot["request_metrics_available"]:
        st.warning(
            "운영 요청 메트릭을 조회할 수 없습니다. Prometheus와 FastAPI /metrics 연결을 확인하세요. "
            "테스트케이스 평가 건수와 k6 결과를 섞어 대체 표시하지 않습니다."
        )
    request_cards = [
        ("request", "총 요청 수", format_request_count(snapshot["total_requests"]), "최근 5분", ""),
        ("check", "성공 요청 수", format_request_count(snapshot["success_requests"]), "2xx/3xx 요청", "good"),
        ("warning", "오류 요청 수", format_request_count(snapshot["error_requests"]), "4xx/5xx 요청", "bad" if snapshot["error_requests"] else ""),
        ("percent", "오류율", format_percentage(snapshot["error_rate"]), "오류 ÷ 전체 요청", "bad" if (snapshot["error_rate"] or 0) > 2 else ""),
        ("timer", "평균 응답시간", format_seconds(snapshot["avg_latency"]), "최근 5분 평균", ""),
        ("timer", "p95 응답시간", format_seconds(snapshot["p95_latency"]), "95% 요청 완료 기준", ""),
    ]
    _render_ops_metric_grid(request_cards, columns=6)

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.markdown("**시간대별 요청 수**")
        render_series_or_info(snapshot["request_series"], "request_rate")
    with chart_col2:
        st.markdown("**응답시간 추이**")
        render_series_or_info(snapshot["duration_series"], "duration_seconds")


def render_traffic_and_errors(snapshot):
    _render_ops_section_header("traffic", "트래픽 & 오류", "분당 요청량과 HTTP 오류 발생 추이")
    requests_per_minute = (
        snapshot["total_requests"] / 5 if snapshot["total_requests"] is not None else None
    )
    metric_col, chart_col = st.columns(2)
    with metric_col:
        row1, row2, row3 = st.container(), st.container(), st.container()
        row1.metric("분당 요청 수", f"{requests_per_minute:.1f}" if requests_per_minute is not None else "-")
        row2.metric("오류 수", format_request_count(snapshot["error_requests"]))
        row3.metric("서비스 Alive", "정상" if snapshot["service_up"] else "데이터 없음")

    error_series = snapshot["error_series"]
    with chart_col:
        if not error_series.empty:
            st.line_chart(error_series, x="time", y="error_rate", height=210)
        elif not snapshot["request_series"].empty and "time" in snapshot["request_series"].columns:
            zero_error_series = pd.DataFrame(
                {
                    "time": snapshot["request_series"]["time"],
                    "error_rate": 0,
                }
            )
            st.line_chart(zero_error_series, x="time", y="error_rate", height=210)
            st.caption("최근 수집 구간의 4xx/5xx 오류 시계열이 없어 0으로 표시합니다.")
        else:
            st.info("Prometheus 오류 시계열 데이터가 없습니다. HTTP 상태코드별 오류 분포와 Top N 메시지는 추가 로그가 필요합니다.")


def render_duration_distribution(snapshot):
    _render_ops_section_header("timer", "FastAPI 운영 응답시간 요약", "백분위별 응답시간 표와 분포 비교")
    distribution = snapshot["duration_distribution"]
    if distribution.empty:
        st.info("응답시간 분포 데이터가 없습니다.")
        return

    section_height = max(170, min(260, 42 + len(distribution) * 35))
    table_col, chart_col = st.columns(2)
    with table_col:
        st.dataframe(distribution, hide_index=True, width="stretch", height=section_height)
    with chart_col:
        st.bar_chart(distribution, x="percentile", y="seconds", height=section_height)


def render_k6_summary(snapshot):
    _render_ops_section_header("gauge", "k6 성능 테스트 결과", "가장 최근에 완료된 별도 부하 테스트 실행 요약")
    k6_summary = snapshot["k6_summary"]
    if not k6_summary:
        st.info(f"k6 결과 파일이 없습니다: {resolve_k6_summary_path()}")
        return

    run_id = k6_summary.get("run_id") or "-"
    created_at = k6_summary.get("created_at") or "-"
    target_url = k6_summary.get("target_url") or "-"
    st.caption(f"별도 k6 실행 결과 · Run ID: {run_id} · 수행 시각: {created_at} · 대상: {target_url}")

    failure_rate = k6_summary.get("failure_rate", 0)
    p95 = k6_summary.get("p95_duration_seconds", 0)
    decision = "PASS" if failure_rate <= 1 and p95 <= 2 else "REVIEW" if failure_rate <= 5 and p95 <= 5 else "FAIL"

    decision_tone = "good" if decision == "PASS" else "warn" if decision == "REVIEW" else "bad"
    k6_cards = [
        ("request", "총 요청 수", f"{k6_summary.get('total_requests', 0):.0f}", "완료된 HTTP 요청", ""),
        ("percent", "실패율", f"{failure_rate:.2f}%", "실패 요청 비율", "bad" if failure_rate > 5 else ""),
        ("timer", "평균 응답시간", format_seconds(k6_summary.get("avg_duration_seconds")), "요청 평균", ""),
        ("timer", "p95 응답시간", format_seconds(p95), "95% 요청 완료 기준", ""),
        ("traffic", "처리량", f"{k6_summary.get('throughput', 0):.2f}/s", "초당 요청", ""),
        ("services", "VUs", f"{k6_summary.get('vus', '-')}", "가상 사용자", ""),
        ("gauge", "판정", decision, "실패율 및 p95 기준", decision_tone),
        ("database", "Run ID", run_id, "최근 완료 실행", ""),
    ]
    _render_ops_metric_grid(k6_cards, columns=4)


def _ops_status_tone(status):
    if status in {"정상", "양호", "PASS"}:
        return "good"
    if status in {"주의", "REVIEW"}:
        return "warn"
    if status in {"위험", "비정상", "FAIL"}:
        return "bad"
    return ""


@st.cache_resource(show_spinner=False)
def get_http_client():
    return httpx.Client(
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
        headers={"User-Agent": "ai-quality-ops-monitor/1.0"},
        trust_env=False,
    )


class PrometheusClient:
    def __init__(self, base_url):
        self.base_url = normalize_request_url(base_url)
        self.client = get_http_client()

    def is_available(self):
        try:
            response = self.client.get(
                f"{self.base_url}/api/v1/query",
                params={"query": "up"},
                timeout=PROMETHEUS_TIMEOUT_SECONDS,
            )
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def query_number(self, query):
        try:
            response = self.client.get(
                f"{self.base_url}/api/v1/query",
                params={"query": query},
                timeout=PROMETHEUS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json().get("data", {}).get("result", [])
            if not result:
                return None
            return float(result[0]["value"][1])
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

    def query_vector(self, query):
        try:
            response = self.client.get(
                f"{self.base_url}/api/v1/query",
                params={"query": query},
                timeout=PROMETHEUS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("result", [])
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return []

    def query_range_series(self, query):
        try:
            end_time = time.time()
            start_time = end_time - 15 * 60
            response = self.client.get(
                f"{self.base_url}/api/v1/query_range",
                params={"query": query, "start": start_time, "end": end_time, "step": "30s"},
                timeout=PROMETHEUS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            result = response.json().get("data", {}).get("result", [])
            if not result:
                return pd.DataFrame()
            values = result[0].get("values", [])
            rows = [{"time": pd.to_datetime(item[0], unit="s"), query_label(query): float(item[1])} for item in values]
            return pd.DataFrame(rows)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return pd.DataFrame()


def load_evaluation_summary():
    csv_path = REPORTS_DIR / "evaluation_result.csv"
    if not csv_path.exists():
        return {"case_count": 0, "failed_count": 0}

    try:
        dataframe = pd.read_csv(csv_path)
    except (OSError, pd.errors.ParserError):
        return {"case_count": 0, "failed_count": 0}

    failed_count = 0
    if "rule_passed" in dataframe.columns:
        failed_count = int((dataframe["rule_passed"].astype(str).str.lower() != "true").sum())
    return {"case_count": len(dataframe), "failed_count": failed_count}


def load_k6_summary():
    summary_path = resolve_k6_summary_path()
    if summary_path.exists():
        try:
            with summary_path.open("r", encoding="utf-8") as file:
                return normalize_k6_summary(json.load(file))
        except (OSError, json.JSONDecodeError):
            return {}

    csv_path = REPORTS_DIR / "k6_result.csv"
    if csv_path.exists():
        try:
            dataframe = pd.read_csv(csv_path)
            return normalize_k6_csv(dataframe)
        except (OSError, pd.errors.ParserError):
            return {}
    return {}


def build_feature_statuses(prometheus_alive, evaluation):
    with ThreadPoolExecutor(max_workers=5) as executor:
        grafana_future = executor.submit(http_status, f"{GRAFANA_URL}/api/health")
        chroma_future = executor.submit(build_chroma_status)
        test_future = executor.submit(build_test_status, evaluation)
        fastapi_metrics_future = executor.submit(http_status, f"{FASTAPI_URL}/metrics")
        fastapi_health_future = executor.submit(http_status, f"{FASTAPI_URL}/health")

        grafana_status = grafana_future.result()
        chroma_status = chroma_future.result()
        test_status = test_future.result()
        fastapi_metrics = fastapi_metrics_future.result()
        fastapi_health = fastapi_health_future.result()

    return [
        build_status_item("Grafana", grafana_status),
        build_status_item("Prometheus", {"ok": prometheus_alive, "neutral": False}),
        chroma_status,
        test_status,
        build_status_item("FastAPI /metrics", fastapi_metrics),
        build_status_item("FastAPI /health", fastapi_health),
    ]


def build_status_item(name, status):
    if status.get("neutral"):
        return {"name": name, "status": status.get("label", "미구성"), "level": "neutral"}
    if status.get("ok"):
        return {"name": name, "status": "정상", "level": "ok"}
    return {"name": name, "status": "비정상", "level": "bad"}


def build_chroma_status():
    try:
        knowledge_base = importlib.import_module("knowledge_base")
        knowledge_base = importlib.reload(knowledge_base)
        uploaded_files = knowledge_base.list_uploaded_knowledge_files()
        indexed_files = knowledge_base.list_search_ready_files()

        if not uploaded_files and not indexed_files:
            return {"name": "ChromaDB", "status": "미구성", "level": "neutral"}
        if knowledge_base.is_index_current():
            return {"name": "ChromaDB", "status": "정상", "level": "ok"}
        return {"name": "ChromaDB", "status": "미반영", "level": "warn"}
    except Exception:
        return {"name": "ChromaDB", "status": "비정상", "level": "bad"}


def build_test_status(evaluation):
    if is_test_execution_available():
        return {"name": "Test수행", "status": "정상", "level": "ok"}
    return {"name": "Test수행", "status": "비정상", "level": "bad"}


def is_test_execution_available():
    tests_dir = PROJECT_DIR / "tests"
    has_test_files = tests_dir.exists() and any(tests_dir.glob("test_*.py"))
    has_registered_cases = has_testcase_source()
    try:
        import pytest  # noqa: F401

        pytest_available = True
    except Exception:
        pytest_available = False

    return has_test_files and has_registered_cases and pytest_available


def has_testcase_source():
    candidates = [
        PROJECT_DIR / "data" / "testcases" / "testcase_uploads.json",
        PROJECT_DIR / "data" / "test_cases.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list) and len(data) > 0:
            return True
    return False


def http_status(url):
    try:
        response = get_http_client().get(normalize_request_url(url), timeout=0.65)
        return {"ok": response.status_code < 400}
    except httpx.HTTPError:
        return {"ok": False}


def normalize_request_url(url):
    return str(url).replace("://localhost", "://127.0.0.1", 1)


def collect_network_snapshot():
    adapter_items = normalize_powershell_items(
        read_powershell_json(
            """
$adapters = Get-NetAdapter
$statsByName = @{}
Get-NetAdapterStatistics | ForEach-Object { $statsByName[$_.Name] = $_ }
$adapters | ForEach-Object {
    $stat = $statsByName[$_.Name]
    $received = 0
    $sent = 0
    if ($null -ne $stat) {
        $received = $stat.ReceivedBytes
        $sent = $stat.SentBytes
    }
    [PSCustomObject]@{
        Name = $_.Name
        Status = [string]$_.Status
        LinkSpeed = [string]$_.LinkSpeed
        ReceivedBytes = $received
        SentBytes = $sent
    }
} | ConvertTo-Json -Depth 4
"""
        )
    )

    rows = []
    total_received = 0
    total_sent = 0
    for adapter in adapter_items:
        name = str(adapter.get("Name", ""))
        received = int(adapter.get("ReceivedBytes", 0) or 0)
        sent = int(adapter.get("SentBytes", 0) or 0)
        total_received += received
        total_sent += sent
        rows.append(
            {
                "name": name,
                "status": str(adapter.get("Status", "")),
                "link_speed": str(adapter.get("LinkSpeed", "")),
                "received_bytes": received,
                "sent_bytes": sent,
            }
        )

    return {
        "adapters": rows,
        "total_received_bytes": total_received,
        "total_sent_bytes": total_sent,
        "sampled_at": time.time(),
    }


def update_network_traffic_history(network):
    sampled_at = network.get("sampled_at", time.time())
    received = int(network.get("total_received_bytes", 0) or 0)
    sent = int(network.get("total_sent_bytes", 0) or 0)
    previous = st.session_state.get("ops_network_last_sample")

    inbound_mbps = 0.0
    outbound_mbps = 0.0
    if previous:
        if sampled_at <= previous.get("sampled_at", 0):
            return {
                "inbound_mbps": float(previous.get("inbound_mbps", 0.0)),
                "outbound_mbps": float(previous.get("outbound_mbps", 0.0)),
            }
        elapsed = max(sampled_at - previous.get("sampled_at", sampled_at), 0.001)
        inbound_mbps = max((received - previous.get("received", received)) * 8 / elapsed / 1_000_000, 0.0)
        outbound_mbps = max((sent - previous.get("sent", sent)) * 8 / elapsed / 1_000_000, 0.0)

    st.session_state.ops_network_last_sample = {
        "sampled_at": sampled_at,
        "received": received,
        "sent": sent,
        "inbound_mbps": inbound_mbps,
        "outbound_mbps": outbound_mbps,
    }

    history = st.session_state.get("ops_network_history", [])
    history.append(
        {
            "time": datetime.fromtimestamp(sampled_at),
            "Inbound Mbps": round(inbound_mbps, 4),
            "Outbound Mbps": round(outbound_mbps, 4),
        }
    )
    st.session_state.ops_network_history = history[-NETWORK_HISTORY_MAX_SAMPLES:]
    return {"inbound_mbps": inbound_mbps, "outbound_mbps": outbound_mbps}


def build_network_traffic_chart(history):
    frame = history.copy()
    frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
    frame = frame.dropna(subset=["time"]).melt(
        id_vars="time",
        value_vars=list(NETWORK_SERIES_COLORS),
        var_name="방향",
        value_name="Mbps",
    )
    encoding = {
        "x": alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M:%S", labelAngle=0)),
        "y": alt.Y("Mbps:Q", title="처리량 (Mbps)", scale=alt.Scale(zero=True)),
        "color": alt.Color(
            "방향:N",
            title=None,
            scale=alt.Scale(
                domain=list(NETWORK_SERIES_COLORS),
                range=list(NETWORK_SERIES_COLORS.values()),
            ),
            legend=alt.Legend(orient="top"),
        ),
        "tooltip": [
            alt.Tooltip("time:T", title="수집 시각", format="%H:%M:%S"),
            alt.Tooltip("방향:N", title="방향"),
            alt.Tooltip("Mbps:Q", title="처리량", format=".3f"),
        ],
    }
    area = alt.Chart(frame).mark_area(
        interpolate="monotone",
        opacity=0.10,
    ).encode(**encoding)
    line = alt.Chart(frame).mark_line(
        interpolate="monotone",
        strokeWidth=3,
        strokeCap="round",
        strokeJoin="round",
    ).encode(**encoding)
    # Keep charts static so the mouse wheel always scrolls the page instead of
    # changing the chart scale.
    return (area + line).properties(height=310)


def read_powershell_json(command):
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    if completed.returncode != 0 or not completed.stdout.strip():
        return []

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []


def normalize_powershell_items(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _adapter_level(status):
    normalized = str(status).strip().lower()
    if normalized == "up":
        return "up"
    if normalized in {"down", "disconnected", "disabled", "not present", "lowerlayerdown"}:
        return "down"
    return "hang"


def _adapter_status_label(status):
    level = _adapter_level(status)
    return {"up": "Up", "down": "Down", "hang": "Hang"}[level]


def _feature_status_icon(name):
    normalized = str(name).lower()
    if "grafana" in normalized:
        return "grafana"
    if "prometheus" in normalized:
        return "prometheus"
    if "chroma" in normalized:
        return "database"
    if "test" in normalized:
        return "test"
    if "metrics" in normalized:
        return "metrics"
    if "health" in normalized:
        return "health"
    return "services"


def _ethernet_port_svg(level):
    status_marks = {
        "up": "<path d='m9 15 3-3 3 3'/><path d='M12 18v-6'/>",
        "down": "<path d='m9 12 3 3 3-3'/><path d='M12 9v6'/>",
        "hang": "<path d='M9 11h6l-6 5h6'/>",
    }
    return (
        "<svg viewBox='0 0 24 24' aria-hidden='true' fill='none' stroke='currentColor' "
        "stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'>"
        "<path d='M5 4h14v7l-3 3v6H8v-6l-3-3V4Z'/><path d='M8 4v4m3-4v4m3-4v4m3-4v4'/>"
        + status_marks[level]
        + "</svg>"
    )


def build_top_pages(prometheus):
    results = prometheus.query_vector("topk(5, sum by (path) (increase(http_requests_total[30m])))")
    return build_top_pages_from_results(results)


def build_top_pages_from_results(results):
    rows = []
    total = 0
    for item in results:
        try:
            value = float(item.get("value", [0, 0])[1])
        except (TypeError, ValueError, IndexError):
            value = 0
        path = item.get("metric", {}).get("path", "/")
        if value <= 0:
            continue
        total += value
        rows.append({"페이지": path, "접속 수": value, "최근 사용": "최근 30분", "데이터": "Prometheus"})

    return _format_top_pages(rows, total)


def build_top_pages_from_k6_runs():
    runs_dir = REPORTS_DIR / "k6_runs"
    if not runs_dir.exists():
        return pd.DataFrame()

    grouped = {}
    latest_time = {}
    for record_path in runs_dir.glob("*/run_record.json"):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        settings = record.get("settings") or {}
        summary = record.get("summary") or {}
        target_url = settings.get("target_url") or record.get("target_url") or ""
        path = _path_from_url(target_url)
        if not path:
            continue

        count = float(summary.get("total_requests", 0) or 0)
        grouped[path] = grouped.get(path, 0) + count
        latest_time[path] = max(str(record.get("created_at", "")), latest_time.get(path, ""))

    total = sum(grouped.values())
    rows = [
        {"페이지": path, "접속 수": count, "최근 사용": latest_time.get(path, "-"), "데이터": "k6 최근 수행"}
        for path, count in grouped.items()
        if count > 0
    ]
    return _format_top_pages(rows, total)


def _format_top_pages(rows, total):
    if not rows:
        return pd.DataFrame()

    top_rows = sorted(rows, key=lambda row: row["접속 수"], reverse=True)[:5]
    for row in top_rows:
        row["접속 수"] = int(row["접속 수"])
        row["사용 비율"] = f"{safe_rate(row['접속 수'], total):.1f}%" if total else "0.0%"
    return pd.DataFrame(top_rows)[["페이지", "접속 수", "사용 비율", "최근 사용", "데이터"]]


def _path_from_url(target_url):
    if not target_url:
        return ""
    parsed = urlparse(target_url)
    path = parsed.path or "/"
    return path


def normalize_k6_summary(summary):
    metrics = summary.get("metrics", summary)
    settings = summary.get("settings") or {}
    normalized = {
        "total_requests": metric_value(metrics, "http_reqs", "count"),
        "failure_rate": metric_value(metrics, "http_req_failed", "rate") * 100,
        "avg_duration_seconds": metric_value(metrics, "http_req_duration", "avg") / 1000,
        "p95_duration_seconds": metric_value(metrics, "http_req_duration", "p(95)") / 1000,
        "throughput": metric_value(metrics, "http_reqs", "rate"),
        "vus": metric_value(metrics, "vus_max", "value") or metric_value(metrics, "vus", "value"),
        "duration_seconds": metric_value(metrics, "iteration_duration", "avg") / 1000,
        "p50_duration_seconds": metric_value(metrics, "http_req_duration", "med") / 1000,
        "p90_duration_seconds": metric_value(metrics, "http_req_duration", "p(90)") / 1000,
        "p99_duration_seconds": metric_value(metrics, "http_req_duration", "p(99)") / 1000,
        "max_duration_seconds": metric_value(metrics, "http_req_duration", "max") / 1000,
        "run_id": summary.get("run_id"),
        "created_at": summary.get("created_at"),
        "target_url": settings.get("target_url"),
    }
    normalized.update(
        {
            key: value
            for key, value in (summary.get("normalized") or {}).items()
            if key in normalized and value is not None
        }
    )
    return normalized


def normalize_k6_csv(dataframe):
    if dataframe.empty:
        return {}
    duration_column = "http_req_duration" if "http_req_duration" in dataframe.columns else None
    durations = pd.to_numeric(dataframe[duration_column], errors="coerce").dropna() / 1000 if duration_column else pd.Series(dtype=float)
    failed = pd.to_numeric(dataframe.get("http_req_failed", pd.Series(dtype=float)), errors="coerce").fillna(0)
    return {
        "total_requests": len(dataframe),
        "failure_rate": float(failed.mean() * 100) if len(failed) else 0,
        "avg_duration_seconds": float(durations.mean()) if len(durations) else 0,
        "p95_duration_seconds": float(durations.quantile(0.95)) if len(durations) else 0,
        "throughput": 0,
        "vus": dataframe["vus"].max() if "vus" in dataframe.columns else "-",
    }


def resolve_k6_summary_path():
    path = Path(K6_SUMMARY_FILE)
    return path if path.is_absolute() else PROJECT_DIR / path


def metric_value(metrics, metric_name, key):
    value = metrics.get(metric_name, {})
    if isinstance(value, dict):
        return float(value.get(key, 0) or 0)
    return 0


def build_duration_distribution(avg_latency, p95_latency):
    rows = []
    percentile_values = {"avg": avg_latency, "p95": p95_latency}
    for percentile, seconds in percentile_values.items():
        if seconds is not None and seconds > 0:
            rows.append({"percentile": percentile, "seconds": round(float(seconds), 3)})
    return pd.DataFrame(rows)


def classify_error_rate(error_rate):
    if error_rate is None:
        return "데이터 없음"
    if error_rate < 1:
        return "정상"
    if error_rate < 5:
        return "주의"
    return "위험"


def classify_latency(seconds):
    if seconds is None or seconds <= 0:
        return "데이터 없음"
    if seconds >= 5:
        return "위험"
    if seconds >= 2:
        return "주의"
    return "정상"


def safe_rate(part, total):
    return float(part) / float(total) * 100 if total else 0


def calculate_rate(part, total):
    if part is None or total is None or total <= 0:
        return None
    return float(part) / float(total) * 100


def calculate_success_requests(total, errors):
    if total is None or errors is None:
        return None
    return max(float(total) - float(errors), 0)


def format_request_count(value, suffix=""):
    return f"{float(value):.0f}{suffix}" if value is not None else "-"


def format_percentage(value):
    return f"{float(value):.2f}%" if value is not None else "-"


def format_seconds(value):
    if value is None or value <= 0:
        return "-"
    return f"{float(value):.2f}s"


def render_series_or_info(dataframe, y_column):
    if dataframe.empty or y_column not in dataframe.columns:
        st.info("Prometheus 시계열 데이터가 없습니다.")
        return
    st.line_chart(dataframe, x="time", y=y_column)


def query_label(query):
    if "error" in query or "5.." in query:
        return "error_rate"
    if "response" in query or "duration" in query:
        return "duration_seconds"
    return "request_rate"
