import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import json

from core.paths import LEGACY_TESTCASE_UPLOADS_FILE, TESTCASE_UPLOADS_FILE
from core.storage import (
    deserialize_uploads,
    load_json_file,
    remove_all_upload_artifacts,
    remove_upload_artifacts,
    save_testcase_uploads,
    save_uploaded_testcase_artifacts,
)

def read_testcase_file(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    file_extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if file_extension == "json":
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                json_data = json.loads(file_bytes.decode(encoding))
                break
            except UnicodeDecodeError:
                continue
        else:
            json_data = json.loads(file_bytes.decode())

        if isinstance(json_data, list):
            return pd.json_normalize(json_data)

        if isinstance(json_data, dict):
            list_values = [value for value in json_data.values() if isinstance(value, list)]
            if list_values:
                return pd.json_normalize(list_values[0])
            return pd.json_normalize([json_data])

        return pd.DataFrame({"value": [json_data]})

    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(BytesIO(file_bytes), encoding=encoding)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(BytesIO(file_bytes))


def render_testcase_upload_page():
    st.markdown(
        """
        <div class="section-card">
            <p class="section-desc">CSV 또는 JSON 파일을 선택하거나 아래 영역에 드래그앤드롭하여 테스트케이스 목록에 등록합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded_files = st.file_uploader(
        "테스트케이스 파일",
        type=["csv", "json"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="CSV 또는 JSON 파일을 업로드할 수 있습니다.",
        key=f"testcase_csv_uploader_{st.session_state.testcase_uploader_key}",
    )

    if st.session_state.testcase_flash_message:
        st.success(st.session_state.testcase_flash_message)
        st.session_state.testcase_flash_message = ""

    action_cols = st.columns([1, 1, 5])
    with action_cols[0]:
        upload_clicked = st.button(
            "업로드",
            type="primary",
            width="stretch",
            disabled=not uploaded_files,
        )
    with action_cols[1]:
        clear_clicked = st.button(
            "초기화",
            width="stretch",
            disabled=not st.session_state.testcase_uploads,
        )

    if clear_clicked:
        remove_all_upload_artifacts()
        st.session_state.testcase_uploads = []
        save_testcase_uploads()
        st.session_state.testcase_uploader_key += 1
        st.session_state.testcase_flash_message = "업로드 목록과 저장된 실제 파일이 초기화되었습니다."
        st.rerun()

    if upload_clicked and uploaded_files:
        uploaded_count = 0
        for uploaded_file in uploaded_files:
            try:
                dataframe = read_testcase_file(uploaded_file)
            except Exception as exc:
                st.error(f"{uploaded_file.name} 파일을 읽을 수 없습니다. CSV/JSON 형식을 확인해 주세요. ({exc})")
                continue

            uploaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_type = uploaded_file.name.rsplit(".", 1)[-1].upper()
            upload_id = f"UP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(st.session_state.testcase_uploads) + 1:03d}"
            upload_item = {
                "id": upload_id,
                "filename": uploaded_file.name,
                "file_type": file_type,
                "row_count": len(dataframe),
                "column_count": len(dataframe.columns),
                "columns": ", ".join(map(str, dataframe.columns)),
                "uploaded_at": uploaded_at,
                "data": dataframe,
            }
            upload_item = save_uploaded_testcase_artifacts(uploaded_file, dataframe, upload_item)
            st.session_state.testcase_uploads.append(upload_item)
            uploaded_count += 1

        if uploaded_count:
            save_testcase_uploads()
            st.session_state.testcase_uploader_key += 1
            st.session_state.testcase_flash_message = f"테스트케이스 파일 {uploaded_count}개가 업로드되었습니다."
            st.rerun()

    st.markdown("#### 업로드된 테스트케이스 목록")

    if not st.session_state.testcase_uploads:
        st.info("아직 업로드된 테스트케이스 파일이 없습니다.")
        return

    list_rows = []
    for index, item in enumerate(st.session_state.testcase_uploads, start=1):
        list_rows.append(
            {
                "선택": False,
                "NO": index,
                "파일명": item["filename"],
                "형식": item.get("file_type", "CSV"),
                "테스트케이스 수": item["row_count"],
                "컬럼 수": item["column_count"],
                "업로드일시": item["uploaded_at"],
                "상태": "등록완료",
                "_id": item["id"],
            }
        )

    upload_list = pd.DataFrame(list_rows)
    edited_list = st.data_editor(
        upload_list.drop(columns=["_id"]),
        key="testcase_upload_table",
        hide_index=True,
        width="stretch",
        disabled=["NO", "파일명", "형식", "테스트케이스 수", "컬럼 수", "업로드일시", "상태"],
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", help="삭제할 항목을 선택하세요."),
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
        upload_list.iloc[index]["_id"]
        for index, selected in enumerate(edited_list["선택"].tolist())
        if selected
    ]

    bottom_cols = st.columns([1, 1, 5])
    with bottom_cols[0]:
        if st.button(
            "선택 삭제",
            width="stretch",
            disabled=not selected_ids,
        ):
            for item in st.session_state.testcase_uploads:
                if item["id"] in selected_ids:
                    remove_upload_artifacts(item)
            st.session_state.testcase_uploads = [
                item for item in st.session_state.testcase_uploads if item["id"] not in selected_ids
            ]
            save_testcase_uploads()
            st.session_state.testcase_flash_message = (
                f"선택한 테스트케이스 {len(selected_ids)}개와 저장된 실제 파일을 삭제했습니다."
            )
            st.rerun()

    st.markdown(
        f'<div class="table-summary">총 {len(st.session_state.testcase_uploads)}건</div>',
        unsafe_allow_html=True,
    )


