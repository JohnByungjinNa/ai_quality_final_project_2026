import streamlit as st
from dataclasses import replace

from components.test_execution_dialog import open_test_execution_dialog
from quality_criteria import (
    criteria_summary,
    get_quality_criteria,
    validate_quality_criteria,
)
from testcase.helpers import build_upload_table_rows, extract_test_cases_from_uploads


def render_quality_criteria_settings():
    labels = {
        "초기": "initial",
        "중기": "mid",
        "고도화": "advanced",
        "사용자 정의": "custom",
    }
    with st.expander("품질 판정 기준 설정", expanded=True):
        selected_label = st.selectbox(
            "운영 단계",
            list(labels),
            index=1,
            help="운영 성숙도에 맞는 프리셋을 선택하거나 사용자 정의 기준을 입력하세요.",
        )
        preset_key = labels[selected_label]
        base = get_quality_criteria("mid" if preset_key == "custom" else preset_key)

        if preset_key != "custom":
            criteria = base
            st.info(criteria_summary(criteria))
            st.caption(
                f"REVIEW {criteria.review_min_score}점 이상 · 안전성 {criteria.safety_critical_min}점 미만 강제 FAIL · "
                f"조건부 배포 규칙/API {criteria.conditional_rule_pass_rate_min:g}%/"
                f"{criteria.conditional_api_pass_rate_min:g}% 이상"
            )
        else:
            score_cols = st.columns(3)
            pass_min_score = score_cols[0].number_input(
                "PASS 최저점", min_value=2, max_value=5, value=base.pass_min_score, step=1
            )
            review_min_score = score_cols[1].number_input(
                "REVIEW 최저점", min_value=1, max_value=4, value=base.review_min_score, step=1
            )
            safety_critical_min = score_cols[2].number_input(
                "안전성 강제 FAIL 하한", min_value=1, max_value=5, value=base.safety_critical_min, step=1,
                help="안전성 점수가 이 값보다 낮으면 다른 점수와 관계없이 FAIL입니다.",
            )

            gate_cols = st.columns(3)
            rule_rate = gate_cols[0].number_input(
                "규칙 합격률 (%)", min_value=0.0, max_value=100.0, value=base.rule_pass_rate_min, step=1.0
            )
            api_rate = gate_cols[1].number_input(
                "API 합격률 (%)", min_value=0.0, max_value=100.0, value=base.api_pass_rate_min, step=1.0
            )
            safety_avg = gate_cols[2].number_input(
                "평균 안전성", min_value=0.0, max_value=5.0, value=base.safety_avg_min, step=0.1
            )

            st.markdown("##### 조건부 배포 기준")
            conditional_cols = st.columns(3)
            conditional_rule_rate = conditional_cols[0].number_input(
                "조건부 규칙 합격률 (%)", min_value=0.0, max_value=100.0,
                value=base.conditional_rule_pass_rate_min, step=1.0
            )
            conditional_api_rate = conditional_cols[1].number_input(
                "조건부 API 합격률 (%)", min_value=0.0, max_value=100.0,
                value=base.conditional_api_pass_rate_min, step=1.0
            )
            conditional_safety = conditional_cols[2].number_input(
                "조건부 평균 안전성", min_value=0.0, max_value=5.0,
                value=base.conditional_safety_avg_min, step=0.1
            )

            require_rule = st.checkbox(
                "최종 케이스 합격에 규칙 기반 PASS 필수",
                value=base.require_rule_pass_for_overall,
                help="선택하면 규칙 기반과 API 기반 평가를 모두 통과한 케이스만 최종 합격으로 집계합니다.",
            )
            criteria = replace(
                base,
                stage="custom",
                stage_label="사용자 정의",
                pass_min_score=int(pass_min_score),
                review_min_score=int(review_min_score),
                safety_critical_min=int(safety_critical_min),
                rule_pass_rate_min=float(rule_rate),
                api_pass_rate_min=float(api_rate),
                safety_avg_min=float(safety_avg),
                conditional_rule_pass_rate_min=float(conditional_rule_rate),
                conditional_api_pass_rate_min=float(conditional_api_rate),
                conditional_safety_avg_min=float(conditional_safety),
                require_rule_pass_for_overall=require_rule,
            )

        errors = validate_quality_criteria(criteria)
        for error in errors:
            st.error(error)
        return criteria, errors

def render_testcase_execution_page():
    st.markdown(
        """
        <div class="section-card">
            <p class="section-desc">업로드된 테스트케이스 파일 중 실행 대상을 선택하고 테스트를 수행합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.testcase_uploads:
        st.warning("실행할 테스트케이스가 없습니다. 먼저 테스트케이스 파일을 업로드해 주세요.")
        return

    st.markdown("#### 실행 대상 선택")
    target_list = build_upload_table_rows(include_selection=True)
    edited_targets = st.data_editor(
        target_list.drop(columns=["_id"]),
        key="testcase_execution_target_table",
        hide_index=True,
        width="stretch",
        disabled=["NO", "파일명", "형식", "테스트케이스 수", "컬럼 수", "업로드일시", "상태"],
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", help="실행할 테스트케이스를 선택하세요."),
            "NO": st.column_config.NumberColumn("NO", width="small"),
            "파일명": st.column_config.TextColumn("파일명", width="large"),
            "형식": st.column_config.TextColumn("형식", width="small"),
            "테스트케이스 수": st.column_config.NumberColumn("테스트케이스 수", width="medium"),
            "컬럼 수": st.column_config.NumberColumn("컬럼 수", width="small"),
            "업로드일시": st.column_config.TextColumn("업로드일시", width="medium"),
            "상태": st.column_config.TextColumn("상태", width="small"),
        },
    )

    selected_ids = [
        target_list.iloc[index]["_id"]
        for index, selected in enumerate(edited_targets["선택"].tolist())
        if selected
    ]
    selected_items = [
        item for item in st.session_state.testcase_uploads if item["id"] in selected_ids
    ]

    executable_cases = extract_test_cases_from_uploads(selected_items)
    summary_cols = st.columns(3)
    summary_cols[0].metric("선택 파일", f"{len(selected_items)}개")
    summary_cols[1].metric("실행 테스트케이스", f"{len(executable_cases)}건")
    summary_cols[2].metric("실행 방식", "규칙/API 병행 평가")

    quality_criteria, criteria_errors = render_quality_criteria_settings()

    run_clicked = st.button(
        "테스트케이스 실행",
        type="primary",
        width="content",
        disabled=not selected_items or bool(criteria_errors),
    )

    if run_clicked:
        if not executable_cases:
            st.error("선택한 파일에서 user_question 또는 질문 컬럼을 가진 테스트케이스를 찾을 수 없습니다.")
            return

        open_test_execution_dialog(selected_items, executable_cases, quality_criteria)
        return
