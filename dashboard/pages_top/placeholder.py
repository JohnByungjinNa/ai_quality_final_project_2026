import streamlit as st


def render_placeholder_page(active_menu, sidebar_sub_menu):
    st.info(f"현재 **[{active_menu} > {sidebar_sub_menu}]** 서브 페이지가 성공적으로 로드되었습니다.")
    st.write(
        "해당 메뉴에 들어갈 세부 기능 및 UI 컴포넌트(파일 업로드, 테이블, 로그 등)를 "
        "이 영역에 구현하시면 됩니다."
    )
