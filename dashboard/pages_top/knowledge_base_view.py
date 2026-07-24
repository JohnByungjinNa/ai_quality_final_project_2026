import streamlit as st
import pandas as pd
from pathlib import Path

from services.knowledge_helpers import (
    chunk_text,
    get_indexed_knowledge_files,
    import_rule_knowledge_module,
    is_knowledge_index_current,
    list_knowledge_upload_files,
    read_knowledge_file_text,
    rebuild_knowledge_index,
    remove_knowledge_upload_file,
    status_color,
    status_icon_svg,
)
from core.paths import RULE_KNOWLEDGE_UPLOAD_DIR, SUPPORTED_KNOWLEDGE_EXTENSIONS
from core.storage import safe_filename

def render_knowledge_base_page():
    RULE_KNOWLEDGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    knowledge_files = list_knowledge_upload_files()
    indexed_files = get_indexed_knowledge_files()
    index_is_current = is_knowledge_index_current()
    has_index_state = bool(knowledge_files or indexed_files)
    has_changes = has_index_state and not index_is_current
    _render_search_apply_button_style(has_changes)
    uploader_key = f"knowledge_upload_files_{st.session_state.knowledge_uploader_key}"
    pending_upload_files = st.session_state.get(uploader_key) or []
    upload_clicked = False
    rebuild_clicked = False

    status_cols = st.columns(2)
    with status_cols[0]:
        upload_status = "empty" if not knowledge_files else "ok"
        upload_color = status_color(upload_status)
        upload_badge_text = {"ok": "업로드됨", "empty": "대기"}[upload_status]
        upload_badge_bg = {"ok": "#dcfce7", "empty": "#f1f5f9"}[upload_status]
        upload_badge_color = {"ok": "#166534", "empty": "#475569"}[upload_status]
        with st.container(border=True):
            upload_body_cols = st.columns([4.6, 1.25])
            with upload_body_cols[0]:
                st.markdown(
                    f"""
                    <div style="min-height:82px;">
                      <div style="font-size:13px;color:#64748b;font-weight:700;margin-bottom:6px;">업로드 파일</div>
                      <div style="font-size:28px;color:#153E75;font-weight:800;line-height:1;">{len(knowledge_files)}개</div>
                      <div style="font-size:12px;color:#64748b;margin-top:8px;line-height:1.35;">업로드 폴더에 저장된 지식 파일</div>
                    </div>
                    <div style="display:inline-block;padding:3px 8px;border-radius:999px;background:{upload_badge_bg};color:{upload_badge_color};font-size:12px;font-weight:700;">{upload_badge_text}</div>
                    """,
                    unsafe_allow_html=True,
                )
            with upload_body_cols[1]:
                st.markdown(
                    f'<div style="display:flex;justify-content:center;margin-bottom:4px;">{status_icon_svg("folder", upload_color)}</div>',
                    unsafe_allow_html=True,
                )
                upload_clicked = st.button(
                    "업로드 저장",
                    key="knowledge_upload_save_button",
                    type="primary",
                    use_container_width=True,
                    disabled=not pending_upload_files,
                )
    with status_cols[1]:
        index_status = "changed" if has_changes else ("ok" if indexed_files else "empty")
        index_color = status_color(index_status)
        index_badge_text = {"ok": "반영 완료", "changed": "검색 반영 필요", "empty": "대기"}[index_status]
        index_badge_bg = {"ok": "#dcfce7", "changed": "#fee2e2", "empty": "#f1f5f9"}[index_status]
        index_badge_color = {"ok": "#166534", "changed": "#991b1b", "empty": "#475569"}[index_status]
        with st.container(border=True):
            index_body_cols = st.columns([4.6, 1.25])
            with index_body_cols[0]:
                st.markdown(
                    f"""
                    <div style="min-height:82px;">
                      <div style="font-size:13px;color:#64748b;font-weight:700;margin-bottom:6px;">답변 검색 반영</div>
                      <div style="font-size:28px;color:#153E75;font-weight:800;line-height:1;">{len(indexed_files)}개</div>
                      <div style="font-size:12px;color:#64748b;margin-top:8px;line-height:1.35;">챗봇 답변 검색에 사용되는 파일</div>
                    </div>
                    <div style="display:inline-block;padding:3px 8px;border-radius:999px;background:{index_badge_bg};color:{index_badge_color};font-size:12px;font-weight:700;">{index_badge_text}</div>
                    """,
                    unsafe_allow_html=True,
                )
            with index_body_cols[1]:
                st.markdown(
                    f'<div style="display:flex;justify-content:center;margin-bottom:4px;">{status_icon_svg("database", index_color)}</div>',
                    unsafe_allow_html=True,
                )
                rebuild_clicked = st.button(
                    "검색 반영 확인",
                    key="rag_rebuild_button",
                    type="primary" if has_changes else "secondary",
                    use_container_width=True,
                    disabled=not has_changes,
                    help="업로드/삭제/수정된 파일을 답변 검색 인덱스에 반영합니다.",
                )

    if st.session_state.knowledge_flash_message:
        st.success(st.session_state.knowledge_flash_message)
        st.session_state.knowledge_flash_message = ""

    if has_changes:
        st.warning("업로드 파일 변경사항이 아직 답변 검색에 반영되지 않았습니다. 검색 반영 확인을 실행하세요.")

    uploaded_files = st.file_uploader(
        "지식베이스 파일",
        type=["txt", "md", "docx", "pdf"],
        accept_multiple_files=True,
        key=uploader_key,
        label_visibility="collapsed",
        help="txt, md, docx, pdf 파일을 업로드할 수 있습니다.",
    )

    if upload_clicked and uploaded_files:
        saved_count = 0
        for uploaded_file in uploaded_files:
            suffix = Path(uploaded_file.name).suffix.lower()
            if suffix not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
                st.error(f"{uploaded_file.name} 파일은 지원하지 않는 형식입니다.")
                continue

            save_path = RULE_KNOWLEDGE_UPLOAD_DIR / safe_filename(uploaded_file.name)
            save_path.write_bytes(uploaded_file.getvalue())
            saved_count += 1

        if saved_count:
            st.session_state.knowledge_flash_message = (
                f"지식베이스 파일 {saved_count}개를 업로드 폴더에 저장했습니다. 답변 검색에 반영하려면 검색 반영 확인을 실행하세요."
            )
            st.session_state.knowledge_uploader_key += 1
            st.rerun()

    if rebuild_clicked:
        try:
            with st.spinner("지식베이스 검색 반영 상태를 확인하는 중입니다..."):
                result = rebuild_knowledge_index()
            st.session_state.knowledge_flash_message = (
                f"검색 반영 확인 완료: {result.get('file_count', 0)}개 파일, {result.get('chunk_count', 0)}개 검색 단락"
            )
            st.rerun()
        except Exception as exc:
            st.error(f"검색 반영 확인 중 오류가 발생했습니다: {exc}")

    if not knowledge_files:
        st.info("아직 등록된 지식베이스 파일이 없습니다.")
        st.markdown(
            """
            <div class="section-card">
                <p class="section-desc">추천 기능: 출결/수료/교육시간처럼 실패가 자주 나는 카테고리 문서를 업로드하면 챗봇 답변 검색에 사용되어 평가 점수 개선에 도움이 됩니다.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    rows = []
    current_preview_file = st.session_state.knowledge_preview_file
    if current_preview_file and not (RULE_KNOWLEDGE_UPLOAD_DIR / current_preview_file).exists():
        current_preview_file = None
        st.session_state.knowledge_preview_file = None

    for index, file_path in enumerate(knowledge_files, start=1):
        rows.append(
            {
                "선택": False,
                "NO": index,
                "파일명": file_path.name,
                "형식": file_path.suffix.upper().lstrip("."),
                "크기(KB)": round(file_path.stat().st_size / 1024, 1),
                "수정일시": file_path.stat().st_mtime,
                "상태": "검색 반영됨" if file_path.name in indexed_files else "업로드됨",
                "_filename": file_path.name,
            }
        )

    file_list = pd.DataFrame(rows)
    file_list["수정일시"] = pd.to_datetime(file_list["수정일시"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")

    list_col, preview_col = st.columns([1.15, 1.35])
    with list_col:
        st.markdown("#### 지식베이스 파일 목록")
        edited_files = st.data_editor(
            file_list.drop(columns=["_filename"]),
            key="knowledge_file_table",
            hide_index=True,
            use_container_width=True,
            height=250,
            disabled=["NO", "파일명", "형식", "크기(KB)", "수정일시", "상태"],
            column_config={
                "선택": st.column_config.CheckboxColumn("선택", help="삭제하거나 미리볼 파일을 선택하세요.", width="small"),
                "NO": st.column_config.NumberColumn("NO", width="small"),
                "파일명": st.column_config.TextColumn("파일명", width="large"),
                "형식": st.column_config.TextColumn("형식", width="small"),
                "크기(KB)": st.column_config.NumberColumn("크기(KB)", width="small"),
                "수정일시": st.column_config.TextColumn("수정일시", width="medium"),
                "상태": st.column_config.TextColumn("상태", width="small"),
            },
        )

        selected_filenames = [
            file_list.iloc[index]["_filename"]
            for index, selected in enumerate(edited_files["선택"].tolist())
            if selected
        ]
        preview_filename = selected_filenames[-1] if selected_filenames else None

        st.session_state.knowledge_preview_file = preview_filename

        if st.button("선택 삭제", use_container_width=True, disabled=not selected_filenames):
            for filename in selected_filenames:
                remove_knowledge_upload_file(filename)
            st.session_state.knowledge_preview_file = None
            st.warning(
                f"선택한 파일 {len(selected_filenames)}개를 업로드 폴더에서 삭제했습니다. 답변 검색 반영을 갱신하려면 검색 반영 확인을 실행하세요."
            )
            st.rerun()

        st.markdown(
            f'<div class="table-summary">총 {len(knowledge_files)}건 · 5건 초과 시 목록 내부 스크롤로 확인</div>',
            unsafe_allow_html=True,
        )

    with preview_col:
        st.markdown("#### 파일 내용 미리보기")

        if not preview_filename:
            st.markdown(
                """
                <div style="height:250px;border:1px dashed #bfdbfe;border-radius:8px;background:#f8fbff;display:flex;align-items:center;justify-content:center;color:#1e3a8a;font-size:13px;">
                    왼쪽 목록에서 파일을 선택하면 내용이 표시됩니다.
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            preview_path = RULE_KNOWLEDGE_UPLOAD_DIR / preview_filename
            preview_text = read_knowledge_file_text(preview_path)
            chunks = []
            try:
                knowledge_base = import_rule_knowledge_module()
                chunks = getattr(knowledge_base, "chunk_text", chunk_text)(preview_text)
            except Exception:
                chunks = chunk_text(preview_text)

            st.text_area(
                "파일 내용",
                preview_text[:20000],
                height=250,
                label_visibility="collapsed",
                disabled=True,
            )
            if len(preview_text) > 20000:
                st.caption("미리보기는 처음 20,000자까지만 표시합니다.")

            preview_status = "반영됨" if preview_filename in indexed_files else "미반영"
            preview_status_color = "#166534" if preview_status == "반영됨" else "#991b1b"
            st.markdown(
                f"""
                <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:10px;">
                  <div style="border:1px solid #d9e6f5;border-radius:8px;background:#f8fbff;padding:10px;">
                    <div style="font-size:12px;color:#64748b;font-weight:700;">문자 수</div>
                    <div style="font-size:18px;color:#1e3a8a;font-weight:800;">{len(preview_text):,}</div>
                  </div>
                  <div style="border:1px solid #d9e6f5;border-radius:8px;background:#f8fbff;padding:10px;">
                    <div style="font-size:12px;color:#64748b;font-weight:700;">검색 단락</div>
                    <div style="font-size:18px;color:#1e3a8a;font-weight:800;">{len(chunks)}개</div>
                  </div>
                  <div style="border:1px solid #d9e6f5;border-radius:8px;background:#f8fbff;padding:10px;">
                    <div style="font-size:12px;color:#64748b;font-weight:700;">상태</div>
                    <div style="font-size:18px;color:{preview_status_color};font-weight:800;">{preview_status}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("#### 문서 검색 테스트")
    if has_changes:
        st.caption("검색 테스트는 마지막으로 검색 반영 확인을 완료한 인덱스를 기준으로 실행됩니다.")
    search_query = st.text_input(
        "검색 질문",
        placeholder="예: 총 교육시간은 몇 시간인가요?",
        label_visibility="collapsed",
    )
    if search_query.strip():
        try:
            knowledge_base = import_rule_knowledge_module()
            search_uploaded = getattr(knowledge_base, "search_uploaded_knowledge", None)
            matches = search_uploaded(search_query, limit=3) if search_uploaded else []
        except Exception as exc:
            st.error(f"문서 검색 중 오류가 발생했습니다: {exc}")
            matches = []

        if matches:
            match_rows = pd.DataFrame(
                [
                    {
                        "파일명": match.get("filename", ""),
                        "점수": match.get("score", 0),
                        "매칭 키워드": ", ".join(match.get("matched_keywords", [])),
                        "검색 내용": match.get("text", ""),
                    }
                    for match in matches
                ]
            )
            st.dataframe(match_rows, hide_index=True, use_container_width=True)
        else:
            st.info("업로드 문서에서 관련 내용을 찾지 못했습니다.")

    st.markdown(
        """
        <div class="section-card">
            <p class="section-desc">업로드된 지식 파일은 챗봇 답변 생성 시 먼저 검색됩니다. 문서에서 관련 내용을 찾으면 해당 내용을 우선 사용하고, 검색 결과가 없으면 기본 정책 정보로 답변합니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_search_apply_button_style(is_active):
    if not is_active:
        return

    st.markdown(
        """
        <style>
        .st-key-rag_rebuild_button button {
            background-color: #dc2626 !important;
            border-color: #dc2626 !important;
            color: #ffffff !important;
        }
        .st-key-rag_rebuild_button button:hover {
            background-color: #b91c1c !important;
            border-color: #b91c1c !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

