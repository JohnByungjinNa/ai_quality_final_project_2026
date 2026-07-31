import pandas as pd
import streamlit as st

from core.paths import JIRA_REGISTERED_ISSUES_FILE
from core.storage import load_json_file, save_json_file
from services.jira_client import (
    JiraConfigurationError,
    JiraIssueCreateError,
    create_issue_for_fail_case,
    missing_jira_settings,
)


FAIL_CASES = [
    {
        "case_id": "TC-003",
        "summary": "교육시간 안내 질문에서 320시간 기준 누락",
        "severity": "High",
        "status": "등록 대기",
        "owner": "QA",
    },
    {
        "case_id": "TC-006",
        "summary": "수료 기준 답변에서 최종 프로젝트 통과 조건 누락",
        "severity": "Medium",
        "status": "등록 대기",
        "owner": "Service Agent",
    },
    {
        "case_id": "TC-007",
        "summary": "조기 취업 예외 질문에서 80% 기준 표현 불일치",
        "severity": "Medium",
        "status": "등록 대기",
        "owner": "Rule Validator",
    },
]


def render_jira_page(sub_menu):
    if "jira_registered_issues" not in st.session_state:
        st.session_state.jira_registered_issues = load_json_file(JIRA_REGISTERED_ISSUES_FILE, [])
    registered_issue_by_case = {
        issue.get("case_id"): issue
        for issue in st.session_state.jira_registered_issues
        if issue.get("case_id")
    }
    table_cases = []
    for case in FAIL_CASES:
        issue = registered_issue_by_case.get(case["case_id"])
        table_cases.append(
            {
                **case,
                "status": f"등록 완료 ({issue['issue_key']})" if issue else case["status"],
                "register": issue is None,
            }
        )

    st.markdown(
        """
        <div class="section-card">
            <div class="section-title">9단계 · Jira 결함관리</div>
            <p class="section-desc">테스트에서 FAIL로 판정된 사례를 Jira 이슈로 등록하고 처리 상태를 추적합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(4)
    metric_cols[0].metric("FAIL 사례", f"{len(FAIL_CASES)}건")
    metric_cols[1].metric("등록 대기", "3건")
    metric_cols[2].metric("High 이상", "1건")
    metric_cols[3].metric("Jira 등록", f"{len(st.session_state.jira_registered_issues)}건")

    missing_settings = missing_jira_settings()
    if missing_settings:
        st.warning(f"Jira 자동등록 설정이 누락되었습니다: {', '.join(missing_settings)}")
    else:
        st.success("Jira 자동등록 설정이 확인되었습니다.")

    st.markdown("#### FAIL 사례 등록")
    selected_cases = st.data_editor(
        pd.DataFrame(table_cases),
        key="jira_fail_case_editor",
        hide_index=True,
        width="stretch",
        column_order=["register", "case_id", "severity", "summary", "owner", "status"],
        column_config={
            "register": st.column_config.CheckboxColumn("등록", help="Jira 이슈로 등록할 FAIL 사례를 선택합니다."),
            "case_id": st.column_config.TextColumn("Case ID", disabled=True),
            "severity": st.column_config.SelectboxColumn(
                "심각도",
                options=["Critical", "High", "Medium", "Low"],
            ),
            "summary": st.column_config.TextColumn("요약"),
            "owner": st.column_config.TextColumn("담당"),
            "status": st.column_config.TextColumn("상태", disabled=True),
        },
    )

    button_cols = st.columns([1, 1, 4])
    with button_cols[0]:
        register_clicked = st.button("Jira 등록", type="primary", width="stretch")
    with button_cols[1]:
        csv_bytes = selected_cases.drop(columns=["register"], errors="ignore").to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV 내보내기",
            data=csv_bytes,
            file_name="jira_fail_cases.csv",
            mime="text/csv",
            width="stretch",
        )

    if register_clicked:
        target_cases = (
            selected_cases[selected_cases["register"]].drop(columns=["register"]).to_dict("records")
            if "register" in selected_cases
            else []
        )
        if not target_cases:
            st.warning("Jira에 등록할 FAIL 사례를 선택해주세요.")
        else:
            created_issues = []
            failed_issues = []
            with st.spinner("선택된 FAIL 사례를 Jira에 등록하는 중입니다..."):
                for fail_case in target_cases:
                    try:
                        result = create_issue_for_fail_case(fail_case)
                        created_issues.append(
                            {
                                "case_id": fail_case.get("case_id", "-"),
                                "issue_key": result.get("key", "-"),
                                "issue_url": _build_issue_url(result),
                            }
                        )
                    except (JiraConfigurationError, JiraIssueCreateError) as exc:
                        failed_issues.append(
                            {
                                "case_id": fail_case.get("case_id", "-"),
                                "error": str(exc),
                            }
                        )

            if created_issues:
                existing_case_ids = {
                    issue.get("case_id")
                    for issue in st.session_state.jira_registered_issues
                }
                st.session_state.jira_registered_issues.extend(
                    issue
                    for issue in created_issues
                    if issue.get("case_id") not in existing_case_ids
                )
                save_json_file(JIRA_REGISTERED_ISSUES_FILE, st.session_state.jira_registered_issues)
                st.success(f"Jira 이슈 {len(created_issues)}건을 등록했습니다.")
                st.dataframe(pd.DataFrame(created_issues), hide_index=True, width="stretch")
                st.rerun()
            if failed_issues:
                st.error("일부 Jira 등록에 실패했습니다.")
                st.dataframe(pd.DataFrame(failed_issues), hide_index=True, width="stretch")

    if st.session_state.jira_registered_issues:
        st.markdown("#### 최근 Jira 등록 결과")
        st.dataframe(
            pd.DataFrame(st.session_state.jira_registered_issues),
            hide_index=True,
            width="stretch",
        )

    st.markdown("#### Jira 등록 필드")
    st.dataframe(
        pd.DataFrame(
            [
                {"필드": "Issue Type", "값": "Bug"},
                {"필드": "Summary", "값": "[QA FAIL] {case_id} - 결함 요약"},
                {"필드": "Description", "값": "질문, 실제 응답, 기대 정책, 실패 사유, 재현 절차"},
                {"필드": "Priority", "값": "심각도 기준 자동 매핑"},
                {"필드": "Labels", "값": "qa-fail, chatbot, regression"},
            ]
        ),
        hide_index=True,
        width="stretch",
    )

    st.markdown("#### 처리 흐름")
    st.code(
        """FAIL 사례 확인
  -> Jira Bug 이슈 등록
  -> 담당자 배정
  -> 답변/규칙/지식베이스 수정
  -> 재테스트
  -> PASS 확인 후 종료""",
        language="text",
    )

    return True


def _build_issue_url(result):
    self_url = result.get("self", "")
    key = result.get("key", "")
    if not self_url or not key:
        return ""
    base_url = self_url.split("/rest/api/", 1)[0]
    return f"{base_url}/browse/{key}"
