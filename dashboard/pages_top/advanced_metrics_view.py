import pandas as pd
import streamlit as st

from quality_metrics import (
    build_cost_tracking,
    build_coverage_gap,
    build_hallucination,
    build_pii_scan,
    build_redteam,
    build_regression,
    build_search_quality,
    build_summary,
    load_evaluation_results,
)


def render_advanced_metrics_page():
    df, source_path = load_evaluation_results()
    render_advanced_metrics_for_dataframe(df, f"분석 데이터: {source_path}" if source_path else "")


def render_advanced_metrics_for_dataframe(df, source_label=""):
    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">고도화 지표</div>
            <p class="section-desc">실행 결과를 기반으로 검색품질, 레드티밍, 회귀, 커버리지, PII, 비용, 환각 위험을 확인합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if df.empty:
        st.warning("분석할 실행 결과 데이터가 없어 고도화 지표를 계산할 수 없습니다.")
        return

    if source_label:
        st.caption(source_label)
    summary = build_summary(df)
    metric_cols = st.columns(6)
    metric_cols[0].metric("총 케이스", f"{summary['total_count']}건")
    metric_cols[1].metric("PASS 비율", f"{summary['pass_rate']}%")
    metric_cols[2].metric("검색품질", f"{summary['avg_quality']}/100")
    metric_cols[3].metric("레드티밍 위험", f"{summary['redteam_risk_count']}건")
    metric_cols[4].metric("PII 의심", f"{summary['pii_count']}건")
    metric_cols[5].metric("환각 의심", f"{summary['hallucination_count']}건")

    tab_search, tab_safety, tab_regression, tab_cost = st.tabs(
        ["검색품질", "레드티밍/PII/환각검증", "회귀 테스트/커버리지 갭", "비용추적"]
    )

    with tab_search:
        render_search_quality(df)

    with tab_safety:
        render_safety_metrics(df)

    with tab_regression:
        render_regression_and_coverage(df)

    with tab_cost:
        render_cost_metrics(df)


def render_search_quality(df):
    search_quality = build_search_quality(df)
    st.markdown("#### 검색품질")
    st.dataframe(
        search_quality[
            ["case_id", "category", "user_question", "expected_keyword", "search_quality_score", "status"]
        ],
        hide_index=True,
        use_container_width=True,
    )
    category_quality = (
        search_quality.groupby("category", as_index=False)["search_quality_score"].mean()
        if not search_quality.empty
        else pd.DataFrame()
    )
    if not category_quality.empty:
        st.bar_chart(category_quality, x="category", y="search_quality_score")


def render_safety_metrics(df):
    redteam = build_redteam(df)
    pii = build_pii_scan(df)
    hallucination = build_hallucination(df)

    st.markdown("#### 레드티밍")
    if redteam.empty:
        st.info("레드티밍 대상 케이스가 없습니다.")
    else:
        st.dataframe(redteam, hide_index=True, use_container_width=True)

    st.markdown("#### PII 검사")
    if pii.empty:
        st.success("PII 의심 응답이 발견되지 않았습니다.")
    else:
        st.dataframe(pii, hide_index=True, use_container_width=True)

    st.markdown("#### 환각검증")
    if hallucination.empty:
        st.success("환각 의심 케이스가 발견되지 않았습니다.")
    else:
        st.dataframe(
            hallucination[
                ["case_id", "category", "risk", "accuracy", "groundedness", "expected_keyword", "response", "reason"]
            ],
            hide_index=True,
            use_container_width=True,
        )


def render_regression_and_coverage(df):
    regression, previous_path = build_regression(df)
    st.markdown("#### 회귀 테스트")
    if previous_path is None:
        st.info("비교할 과거 실행 이력이 없습니다. reports/history/<timestamp>/evaluation_result.csv 파일이 있으면 비교합니다.")
    elif regression.empty:
        st.success(f"회귀 의심 케이스가 없습니다. 비교 기준: {previous_path}")
    else:
        st.warning(f"회귀 의심 {len(regression)}건이 발견되었습니다. 비교 기준: {previous_path}")
        st.dataframe(regression, hide_index=True, use_container_width=True)

    st.markdown("#### 커버리지 갭")
    coverage = build_coverage_gap(df)
    col_category, col_type = st.columns(2)
    with col_category:
        st.markdown("**카테고리별 케이스 수**")
        if not coverage["category_counts"].empty:
            st.bar_chart(coverage["category_counts"], x="category", y="case_count")
    with col_type:
        st.markdown("**테스트 유형별 분포**")
        if not coverage["type_counts"].empty:
            st.bar_chart(coverage["type_counts"], x="test_type", y="case_count")

    if coverage["uncovered_categories"]:
        st.warning(
            "보강 권장 카테고리: "
            + ", ".join(map(str, coverage["uncovered_categories"]))
            + f" / 권장 추가 케이스 {coverage['recommended_case_count']}건"
        )
    else:
        st.success("카테고리별 최소 커버리지를 충족했습니다.")


def render_cost_metrics(df):
    cost = build_cost_tracking(df)
    if cost.empty:
        st.info("비용추적 데이터가 없습니다.")
        return

    total_cost = float(cost["estimated_cost_usd"].sum())
    avg_cost = total_cost / len(cost) if len(cost) else 0
    metric_cols = st.columns(3)
    metric_cols[0].metric("총 추정 비용", f"${total_cost:.4f}")
    metric_cols[1].metric("케이스당 평균", f"${avg_cost:.4f}")
    metric_cols[2].metric("대상 케이스", f"{len(cost)}건")

    st.dataframe(cost, hide_index=True, use_container_width=True)
    if "model" in cost.columns:
        model_cost = cost.groupby("model", as_index=False)["estimated_cost_usd"].sum()
        st.bar_chart(model_cost, x="model", y="estimated_cost_usd")
