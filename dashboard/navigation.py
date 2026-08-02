import streamlit as st

from core.constants import SYSTEM_NAME


MENU_OPTIONS = ["종합 현황", "성능관리", "테스트 관리", "지식 파일 관리", "Jira관리", "GitHub 관리", "VOC 품질진단"]
# MENU_OPTIONS = ["성능관리", "테스트 관리", "지식 파일 관리", "Jira관리", "Docker 관리"]

SIDEBAR_MENU_OPTIONS = {
    "종합 현황": ["AI QA 종합 현황"],
    "성능관리": ["운영 모니터링", "운영 세부데이터", "서비스 관리", "K6 성능테스트"],
    "테스트 관리": ["테스트케이스 업로드", "테스트 케이스 실행", "테스트 수행 이력", "자동 테스트 결과"],
    "지식 파일 관리": ["지식 파일 관리"],
    "Jira관리": ["Jira 현황", "Jira 등록", "등록 이력", "환경 설정"],
    "GitHub 관리": ["저장소 현황", "프로젝트 동기화", "환경 설정"],
    "VOC 품질진단": [
        "Dashboard",
        "Agent 관리",
        "테스트케이스",
        "품질 평가 기준",
        "수동 TC 수행",
        "일괄 TC 수행",
        "수행 이력",
        "개선안 타당성 검증",
        "장애·결함 관리",
        "품질 보고서",
        "사용자 가이드",
        "최종 인수·시연",
    ],
    # "Docker 관리": ["Docker 통합 실행"],
}


def _select_menu(menu_name):
    st.session_state.current_menu = menu_name
    st.session_state.current_sub_menu = SIDEBAR_MENU_OPTIONS[menu_name][0]


def _select_sub_menu(menu_item):
    st.session_state.current_sub_menu = menu_item


def render_topbar():
    with st.container(key="topbar"):
        col_logo, col_menu, col_right = st.columns([2.0, 5.2, 1.8])

        with col_logo:
            st.markdown(
                f'<div class="brand-title">💬 {SYSTEM_NAME}</div>',
                unsafe_allow_html=True,
            )

        with col_menu:
            menu_cols = st.columns(len(MENU_OPTIONS))
            for i, menu_name in enumerate(MENU_OPTIONS):
                with menu_cols[i]:
                    is_selected = st.session_state.current_menu == menu_name
                    button_style = "primary" if is_selected else "secondary"
                    st.button(
                        menu_name,
                        key=f"btn_{menu_name}",
                        width="stretch",
                        type=button_style,
                        on_click=_select_menu,
                        args=(menu_name,),
                    )

        with col_right:
            info_col, stop_col = st.columns([1.08, 0.42], gap="small")
            with info_col:
                st.markdown(
                    """
                    <div class="topbar-right">
                        <div class="topbar-bell">🔔</div>
                        <div class="topbar-avatar">8</div>
                        <div class="topbar-username">최강3조</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with stop_col:
                if st.button(
                    "종료",
                    key="streamlit_shutdown_button",
                    width="stretch",
                    help="Streamlit과 관련 서비스를 종료합니다.",
                ):
                    st.session_state.streamlit_shutdown_requested = True
                    st.session_state.streamlit_shutdown_started = False
                    st.rerun()


def render_sidebar():
    active_menu = st.session_state.current_menu
    if active_menu not in SIDEBAR_MENU_OPTIONS:
        active_menu = MENU_OPTIONS[0]
        st.session_state.current_menu = active_menu
        st.session_state.current_sub_menu = SIDEBAR_MENU_OPTIONS[active_menu][0]

    active_sub_menu_options = SIDEBAR_MENU_OPTIONS[active_menu]

    if st.session_state.current_sub_menu not in active_sub_menu_options:
        st.session_state.current_sub_menu = active_sub_menu_options[0]

    with st.sidebar:
        st.markdown(f'<div class="sidebar-title">{active_menu}</div>', unsafe_allow_html=True)
        st.markdown("---")

        for menu_item in active_sub_menu_options:
            is_selected = st.session_state.current_sub_menu == menu_item
            button_style = "primary" if is_selected else "secondary"
            st.button(
                menu_item,
                key=f"sidebar_{active_menu}_{menu_item}",
                width="stretch",
                type=button_style,
                on_click=_select_sub_menu,
                args=(menu_item,),
            )

    return active_menu, st.session_state.current_sub_menu


def render_navigation():
    render_topbar()
    active_menu, sidebar_sub_menu = render_sidebar()
    st.markdown(
        f'<div class="page-kicker">홈 &gt; {active_menu} &gt; {sidebar_sub_menu}</div>',
        unsafe_allow_html=True,
    )
    return active_menu, sidebar_sub_menu
