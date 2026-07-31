import streamlit as st
import pandas as pd

from core.paths import LEGACY_TESTCASE_HISTORY_FILE, TESTCASE_HISTORY_FILE
from core.storage import load_json_file, remove_test_run_artifacts, save_testcase_history
from components.report_visuals import render_agent_visual_summary, show_execution_detail_dialog
from quality_criteria import LEGACY_CRITERIA, get_quality_criteria
from testcase.helpers import build_execution_detail, get_execution_detail

def render_testcase_history_page():
    st.markdown(
        """
        <div class="section-card">
            <p class="section-desc">실행 완료된 테스트 내역을 확인할 수 있습니다. 이력을 삭제하면 해당 실행의 실제 결과 파일도 함께 삭제됩니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.testcase_history_flash_message:
        st.success(st.session_state.testcase_history_flash_message)
        st.session_state.testcase_history_flash_message = ""

    if not st.session_state.testcase_execution_history:
        st.info("아직 테스트 수행 이력이 없습니다.")
        return

    focused_run_id = st.session_state.pop("qa_safety_focus_run_id", None)
    focused_case_id = st.session_state.pop("qa_safety_focus_case_id", None)
    if focused_run_id:
        focused_item = next(
            (item for item in st.session_state.testcase_execution_history if str(item.get("id")) == str(focused_run_id)),
            None,
        )
        if focused_item:
            focus_label = f" · Case `{focused_case_id}`" if focused_case_id else ""
            st.info(
                f"안전성 위험이 감지된 실행 `{focused_run_id}`{focus_label}의 상세 결과입니다.",
                icon=":material/policy_alert:",
            )
            st.session_state.history_detail_open_id = focused_item["id"]
            show_execution_detail_dialog(focused_item, focus_case_id=focused_case_id)
        else:
            st.warning(
                f"실행 `{focused_run_id}`은 qa-observer 이벤트에는 있으나 현재 테스트 수행 이력에서 찾지 못했습니다. "
                "이력 파일 보존 여부를 확인하세요.",
                icon=":material/history_off:",
            )

    history_rows = []
    for index, item in enumerate(st.session_state.testcase_execution_history, start=1):
        stored_criteria = item.get("quality_criteria") or item.get("detail", {}).get("quality_criteria")
        criteria = get_quality_criteria(stored_criteria) if stored_criteria else LEGACY_CRITERIA
        history_rows.append(
            {
                "NO": index,
                "실행ID": item["id"],
                "실행일시": item["executed_at"],
                "운영 단계": criteria.stage_label,
                "대상파일": item["target_files"],
                "파일 수": item["file_count"],
                "총 건수": item["total_count"],
                "성공": item["passed_count"],
                "미통과": item["failed_count"],
                "소요시간(초)": item["duration_seconds"],
                "상태": item["status"],
                "_id": item["id"],
            }
        )

    history_list = pd.DataFrame(history_rows)
    history_event = st.dataframe(
        history_list.drop(columns=["_id"]),
        key="testcase_history_table",
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "NO": st.column_config.NumberColumn("NO", width="small"),
            "실행ID": st.column_config.TextColumn("실행ID", width="medium"),
            "실행일시": st.column_config.TextColumn("실행일시", width="medium"),
            "운영 단계": st.column_config.TextColumn("운영 단계", width="small"),
            "대상파일": st.column_config.TextColumn("대상파일", width="large"),
            "파일 수": st.column_config.NumberColumn("파일 수", width="small"),
            "총 건수": st.column_config.NumberColumn("총 건수", width="small"),
            "성공": st.column_config.NumberColumn("성공", width="small"),
            "미통과": st.column_config.NumberColumn("미통과", width="small"),
            "소요시간(초)": st.column_config.NumberColumn("소요시간(초)", width="small"),
            "상태": st.column_config.TextColumn("상태", width="small"),
        },
    )

    selected_rows = history_event.selection.rows
    selected_history_ids = []
    if selected_rows:
        selected_index = selected_rows[0]
        if 0 <= selected_index < len(history_list):
            selected_history_ids = [history_list.iloc[selected_index]["_id"]]
            selected_item = st.session_state.testcase_execution_history[selected_index]
            if st.session_state.history_detail_open_id != selected_item["id"]:
                st.session_state.history_detail_open_id = selected_item["id"]
                show_execution_detail_dialog(selected_item)
        else:
            st.session_state.history_detail_open_id = None
    else:
        st.session_state.history_detail_open_id = None

    bottom_cols = st.columns([1, 1, 5])
    with bottom_cols[0]:
        if st.button(
            "선택 삭제",
            width="stretch",
            disabled=not selected_history_ids,
        ):
            selected_history = [
                item
                for item in st.session_state.testcase_execution_history
                if item["id"] in selected_history_ids
            ]
            for item in selected_history:
                remove_test_run_artifacts(item)
            st.session_state.testcase_execution_history = [
                item
                for item in st.session_state.testcase_execution_history
                if item["id"] not in selected_history_ids
            ]
            st.session_state.history_detail_open_id = None
            save_testcase_history()
            st.session_state.testcase_history_flash_message = (
                f"선택한 테스트 수행 이력 {len(selected_history_ids)}건과 관련 결과 파일을 삭제했습니다."
            )
            st.rerun()
    with bottom_cols[1]:
        if st.button("전체 삭제", width="stretch"):
            for item in st.session_state.testcase_execution_history:
                remove_test_run_artifacts(item)
            st.session_state.testcase_execution_history = []
            st.session_state.history_detail_open_id = None
            save_testcase_history()
            st.session_state.testcase_history_flash_message = "테스트 수행 이력과 관련 결과 파일을 모두 삭제했습니다."
            st.rerun()

    st.markdown(
        f'<div class="table-summary">총 {len(st.session_state.testcase_execution_history)}건</div>',
        unsafe_allow_html=True,
    )


