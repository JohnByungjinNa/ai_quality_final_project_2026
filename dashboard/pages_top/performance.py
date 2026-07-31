from pages_top.k6_runner_view import render_k6_runner_page
from pages_top.ops_monitoring import render_ops_detail_page, render_ops_monitoring_page
from pages_top.service_management import render_service_management_page


def render_performance_page(sub_menu):
    if _matches_menu(sub_menu, "운영 모니터링"):
        render_ops_monitoring_page()
        return True

    if _matches_menu(sub_menu, "운영 세부데이터"):
        render_ops_detail_page()
        return True

    if _matches_menu(sub_menu, "서비스 관리") or _matches_menu(sub_menu, "Grafana 운영 대시보드"):
        render_service_management_page()
        return True

    if _matches_menu(sub_menu, "K6") or _matches_menu(sub_menu, "k6"):
        render_k6_performance_page()
        return True

    return False


def _matches_menu(sub_menu, keyword):
    return keyword.lower() in str(sub_menu).lower()


def render_k6_performance_page():
    render_k6_runner_page()
    return

    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">6단계 · k6 성능 테스트</div>
            <p class="section-desc">동시 사용자 부하를 걸어 응답시간과 오류율을 확인하고, 병목 위치를 추적합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### k6 주요 기능")
    flow_col, result_col = st.columns([1.05, 1])

    with flow_col:
        st.markdown("**k6 테스트 흐름**")
        st.code(
            """k6 가상 사용자
  |
  | 동시에 /ask 호출
  v
FastAPI
  |
  v
Service Agent
  |-- Rule 기반 응답
  |-- LLM API 호출
  v
응답시간·성공·실패 기록
  |
  v
k6 결과 요약
  |
  v
성능 보고서 및 배포 판단""",
            language="text",
        )

    with result_col:
        st.markdown("**예시 결과 분석**")
        k6_metrics = pd.DataFrame(
            [
                {"지표": "checks", "결과": "98.50% / 197 / 3"},
                {"지표": "http_req_duration", "결과": "avg=1.85s, p95=3.92s"},
                {"지표": "http_req_failed", "결과": "1.50%"},
                {"지표": "http_reqs", "결과": "200"},
                {"지표": "vus_max", "결과": "20"},
            ]
        )
        st.dataframe(k6_metrics, hide_index=True, width="stretch")

    metric_cols = st.columns(5)
    metric_cols[0].metric("checks", "98.50%", "197/200")
    metric_cols[1].metric("avg 응답시간", "1.85s")
    metric_cols[2].metric("p95 응답시간", "3.92s")
    metric_cols[3].metric("오류율", "1.50%")
    metric_cols[4].metric("동시 사용자", "20 VUs")

    st.markdown("#### k6 결과에서 가장 중요한 질문")
    st.dataframe(
        pd.DataFrame(
            {
                "점검 질문": [
                    "동시 사용자가 늘어날 때 응답시간은 얼마나 증가했는가?",
                    "p95 응답시간이 기준을 넘었는가?",
                    "오류율이 목표치 이하인가?",
                    "특정 요청에서만 실패가 집중되는가?",
                    "Rule 응답과 LLM 응답의 속도 차이는 얼마나 되는가?",
                    "실패했을 때 사용자에게 안전한 오류 안내가 나오는가?",
                ]
            }
        ),
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### 응답시간 추이 예시")
    st.line_chart(
        pd.DataFrame(
            {
                "avg_response_seconds": [1.2, 1.4, 1.7, 1.85, 2.1, 1.9, 1.8],
                "p95_response_seconds": [2.3, 2.8, 3.4, 3.92, 4.4, 4.1, 3.8],
            }
        )
    )


def render_prometheus_metrics_page():
    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">7단계 · Prometheus 지표 수집</div>
            <p class="section-desc">FastAPI 서비스의 운영 지표를 /metrics로 노출하고, Prometheus가 주기적으로 수집합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    left_col, right_col = st.columns([1.05, 1])
    with left_col:
        st.markdown("#### Prometheus란?")
        st.write(
            "서버, 컨테이너, 애플리케이션 상태와 성능 데이터를 주기적으로 수집하고 "
            "시계열 데이터베이스에 저장하는 오픈소스 모니터링 시스템입니다."
        )
        st.markdown(
            """
            - Pull 방식으로 지표 데이터를 가져옴
            - 자체 PromQL을 활용해 데이터를 분석하고 알림 조건을 만들 수 있음
            - k6 부하 결과와 운영 지표를 함께 보면 병목 판단이 쉬움
            """
        )

    with right_col:
        st.markdown("#### 수집 엔드포인트")
        st.code("/metrics", language="text")
        st.caption("/metrics는 FastAPI 서비스 내부의 운영 데이터를 숫자 형태로 보여주는 주소입니다.")
        st.code(
            """# 예시 지표
agent_response_seconds_count 200
agent_response_seconds_sum 370.0
agent_request_errors_total 3
process_cpu_seconds_total 12.4""",
            language="text",
        )

    st.markdown("#### k6와 Prometheus가 답해야 하는 질문")
    st.dataframe(
        pd.DataFrame(
            [
                {"도구": "k6", "핵심 질문": "20명이 동시에 접속하면 버틸 수 있는가?"},
                {"도구": "Prometheus", "핵심 질문": "현재 서비스가 정상인가? 오류가 늘고 있는가? 느려지고 있는가?"},
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("수집 상태", "정상")
    metric_cols[1].metric("스크랩 주기", "5s")
    metric_cols[2].metric("오류 카운터", "3")
    metric_cols[3].metric("최근 p95", "6.5s")


def render_grafana_dashboard_page():
    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">8단계 · Grafana 운영 대시보드</div>
            <p class="section-desc">Prometheus에 쌓인 지표를 실시간 패널로 시각화해 운영 상태를 확인합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.success("운영 대시보드가 정상적으로 실시간 모니터링 중입니다.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(label="평균 응답시간", value="1.8초", delta="-0.2초")
    m2.metric(label="p95 응답시간", value="6.5초", delta="+0.4초")
    m3.metric(label="오류율", value="1.5%", delta="+0.3%")
    m4.metric(label="서비스 가용률", value="99.9%", delta="정상")

    chart_col, query_col = st.columns([1.2, 1])
    with chart_col:
        st.markdown("#### 실시간 응답시간 패널")
        st.area_chart(
            pd.DataFrame(
                {
                    "avg_response_seconds": [1.4, 1.6, 1.7, 1.8, 1.9, 1.8, 1.7],
                    "p95_response_seconds": [4.8, 5.2, 5.8, 6.5, 6.2, 5.9, 5.6],
                }
            )
        )

    with query_col:
        st.markdown("#### p95 응답시간 패널 PromQL")
        st.code(
            """histogram_quantile(
  0.95,
  sum(rate(agent_response_seconds_bucket[5m])) by (le)
)""",
            language="text",
        )
        st.caption("최근 5분간 요청의 95%가 몇 초 안에 처리되었는지 확인합니다.")

    st.markdown("#### 운영 판단 기준")
    st.dataframe(
        pd.DataFrame(
            [
                {"항목": "평균 응답시간", "현재": "1.8초", "판단": "정상"},
                {"항목": "p95 응답시간", "현재": "6.5초", "판단": "주의"},
                {"항목": "오류율", "현재": "1.5%", "판단": "관찰 필요"},
                {"항목": "서비스 가용률", "현재": "99.9%", "판단": "정상"},
            ]
        ),
        hide_index=True,
        width="stretch",
    )
