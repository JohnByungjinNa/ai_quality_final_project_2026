import streamlit as st

from services.pytest_runner import load_registered_testcase_uploads, run_pytest


def _format_upload_option(upload):
    return (
        f"{upload.get('uploaded_at', '-')} | "
        f"{upload.get('filename', '-')} | "
        f"{upload.get('row_count', 0)}건"
    )


def render_pytest_result_page():
    st.markdown(
        """
        <div class="section-card">
            <p class="section-desc">프로젝트 자동 테스트를 실행하고 pytest 결과를 확인합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    include_coverage = st.checkbox("커버리지 포함", value=False)
    uploads = load_registered_testcase_uploads()
    selected_upload = None

    if uploads:
        selected_upload = st.selectbox(
            "자동 테스트 대상",
            uploads,
            format_func=_format_upload_option,
            help="등록된 테스트케이스 목록 중 pytest에 사용할 파일을 선택합니다.",
        )
        st.caption(f"선택 ID: {selected_upload.get('id', '-')}")
    else:
        st.warning("등록된 테스트케이스가 없습니다. 기본 pytest 테스트만 실행됩니다.")

    if st.button("pytest 실행", type="primary"):
        with st.spinner("pytest 실행 중입니다..."):
            st.session_state.pytest_result = run_pytest(
                include_coverage=include_coverage,
                testcase_upload_id=selected_upload.get("id") if selected_upload else None,
            )

    result = st.session_state.get("pytest_result")
    if not result:
        st.info("pytest 실행 버튼을 눌러 자동 테스트 결과를 확인하세요.")
        return

    summary = result.get("summary", {})
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    seconds = summary.get("seconds")
    coverage = result.get("coverage")

    cols = st.columns(5)
    result_label = "전체 통과" if result["returncode"] == 0 else "품질 이슈 발견"
    cols[0].metric("검증 결과", result_label)
    cols[1].metric("통과 테스트", f"{passed}개")
    cols[2].metric("실패 테스트", f"{failed}개")
    cols[3].metric("소요시간", f"{seconds:.2f}초" if seconds is not None else "-")
    cols[4].metric("커버리지", f"{coverage}%" if coverage is not None else "-")

    if result["returncode"] == 0:
        st.success("선택한 테스트케이스가 모두 기대 조건을 만족했습니다.")
    else:
        st.error("자동 테스트는 정상 실행되었고, 검증 실패 항목이 발견되었습니다.")

    st.markdown("#### 실행 명령")
    st.code(result["command"], language="powershell")

    st.markdown("#### stdout")
    st.code(result["stdout"] or "(출력 없음)", language="text")

    if result["stderr"]:
        st.markdown("#### stderr")
        st.code(result["stderr"], language="text")
