import time

import streamlit as st

from components.integration_status import load_integration_status
from core.constants import AWS_CONSOLE_ICON_URL, SYSTEM_NAME
from services.integration_status_service import logout_aws_session, start_aws_browser_login


MENU_OPTIONS = ["종합 현황", "성능관리", "테스트 관리", "지식 파일 관리", "Jira관리", "GitHub 관리", "VOC 품질진단", "관측성"]
# MENU_OPTIONS = ["성능관리", "테스트 관리", "지식 파일 관리", "Jira관리", "Docker 관리"]
AWS_LOGIN_POLL_INTERVAL_SECONDS = 2
AWS_LOGIN_TIMEOUT_SECONDS = 300

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
    "관측성": ["SLO·Error Budget", "Agent Pipeline", "Drift·FinOps", "관측 인프라"],
    # "Docker 관리": ["Docker 통합 실행"],
}


def _select_menu(menu_name):
    st.session_state.current_menu = menu_name
    st.session_state.current_sub_menu = SIDEBAR_MENU_OPTIONS[menu_name][0]


def _select_sub_menu(menu_item):
    st.session_state.current_sub_menu = menu_item


def _topbar_aws_status(aws: dict) -> dict:
    if aws.get("authenticated"):
        return {
            "label": "연결됨",
            "tone": "connected",
            "title": f"AWS {aws.get('profile', 'JohnNa-QA')} 임시 세션 연결됨",
        }
    status = str(aws.get("session_status") or "")
    if status == "cli_missing":
        return {"label": "설정 필요", "tone": "setup", "title": "AWS CLI 설치가 필요합니다."}
    if status == "profile_missing":
        return {"label": "설정 필요", "tone": "setup", "title": "AWS JohnNa-QA 프로필 설정이 필요합니다."}
    if status == "unexpected_principal":
        return {"label": "사용자 확인", "tone": "error", "title": "JohnNa-QA 사용자가 아닙니다. 다시 로그인하세요."}
    return {
        "label": "로그인 필요",
        "tone": "login-required",
        "title": "AWS 브라우저 임시 인증이 필요합니다.",
    }


def _aws_login_poll_action(aws: dict, login_started_at: float, *, now: float) -> str:
    if login_started_at <= 0:
        return "inactive"
    if now - login_started_at >= AWS_LOGIN_TIMEOUT_SECONDS:
        return "expired"
    if aws.get("authenticated"):
        return "connected"
    if aws.get("session_status") in {
        "cli_missing",
        "profile_missing",
        "unexpected_principal",
    }:
        return "terminal"
    return "pending"


@st.fragment(run_every=f"{AWS_LOGIN_POLL_INTERVAL_SECONDS}s")
def _poll_aws_login_completion() -> None:
    """Refresh the full app as soon as the temporary AWS login becomes usable."""
    login_started_at = float(st.session_state.get("topbar_aws_login_started_at") or 0)
    if login_started_at <= 0:
        return

    if _aws_login_poll_action({}, login_started_at, now=time.time()) == "expired":
        st.session_state.pop("topbar_aws_login_started_at", None)
        load_integration_status.clear()
        st.rerun(scope="app")

    load_integration_status.clear()
    try:
        aws_snapshot = load_integration_status().get("aws") or {}
    except Exception:
        st.caption("AWS 로그인 완료 여부를 자동 확인하고 있습니다.")
        return

    action = _aws_login_poll_action(aws_snapshot, login_started_at, now=time.time())
    if action == "connected":
        st.session_state.pop("topbar_aws_login_started_at", None)
        st.toast("AWS 로그인이 완료되었습니다.", icon=":material/check_circle:")
        st.rerun(scope="app")

    if action == "terminal":
        st.session_state.pop("topbar_aws_login_started_at", None)
        st.rerun(scope="app")

    st.caption("브라우저 인증 완료 여부를 자동 확인하고 있습니다.")


def render_topbar():
    try:
        aws_snapshot = load_integration_status().get("aws") or {}
        aws_status = _topbar_aws_status(aws_snapshot)
    except Exception:
        aws_snapshot = {}
        aws_status = {"label": "확인 필요", "tone": "setup", "title": "AWS 상태를 확인할 수 없습니다."}

    login_started_at = float(st.session_state.get("topbar_aws_login_started_at") or 0)
    login_in_progress = (
        not aws_snapshot.get("authenticated")
        and login_started_at > 0
        and time.time() - login_started_at < 300
    )
    if login_in_progress:
        aws_status = {
            "label": "인증 진행 중",
            "tone": "pending",
            "title": "브라우저 인증 완료 여부를 자동 확인하고 있습니다.",
        }

    with st.container(key="topbar"):
        col_logo, col_menu, col_right = st.columns(
            [1.9, 4.9, 2.2],
            vertical_alignment="center",
        )

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
            info_col, stop_col = st.columns(
                [1.08, 0.42],
                gap="small",
                vertical_alignment="center",
            )
            with info_col:
                aws_col, user_col = st.columns([1.15, 0.85], gap="small", vertical_alignment="center")
                with aws_col:
                    aws_popover = st.popover(
                        f"![AWS]({AWS_CONSOLE_ICON_URL})",
                        key=f"topbar_aws_action_{aws_status['tone'].replace('-', '_')}",
                        help=aws_status["title"],
                        width="stretch",
                    )
                    with aws_popover:
                        st.caption("AWS 연결 정보")
                        if aws_snapshot.get("authenticated"):
                            st.markdown(":green-badge[연결됨]")
                        elif aws_status["tone"] == "error":
                            st.markdown(":red-badge[확인 필요]")
                        else:
                            st.markdown(":gray-badge[미연결]")
                        st.markdown(
                            f"**프로필** · `{aws_snapshot.get('profile') or 'JohnNa-QA'}`  \n"
                            f"**리전** · `{aws_snapshot.get('region') or 'ap-northeast-2'}`"
                        )

                        if aws_snapshot.get("authenticated"):
                            if st.button(
                                "로그아웃",
                                key="topbar_aws_logout",
                                icon=":material/logout:",
                                width="stretch",
                            ):
                                result = logout_aws_session()
                                if result.get("ok"):
                                    st.session_state.pop("topbar_aws_login_started_at", None)
                                    load_integration_status.clear()
                                    st.toast(result["message"], icon=":material/logout:")
                                    st.rerun()
                                else:
                                    st.error(result.get("message") or "AWS 로그아웃에 실패했습니다.")
                        elif login_in_progress:
                            _poll_aws_login_completion()
                            if st.button(
                                "연결 상태 확인",
                                key="topbar_aws_refresh_pending",
                                icon=":material/refresh:",
                                width="stretch",
                            ):
                                st.session_state.pop("topbar_aws_login_started_at", None)
                                load_integration_status.clear()
                                st.rerun()
                        else:
                            if st.button(
                                "AWS 로그인",
                                key="topbar_aws_login",
                                icon=":material/login:",
                                type="primary",
                                width="stretch",
                            ):
                                result = start_aws_browser_login()
                                if result.get("ok"):
                                    st.session_state["topbar_aws_login_started_at"] = time.time()
                                    st.toast(
                                        "AWS 브라우저 인증을 시작했습니다.",
                                        icon=":material/open_in_new:",
                                    )
                                    st.rerun()
                                else:
                                    st.error(result.get("message") or "AWS 로그인을 시작하지 못했습니다.")

                        if not login_in_progress and st.button(
                            "새로고침",
                            key="topbar_aws_refresh",
                            icon=":material/refresh:",
                            width="stretch",
                        ):
                            st.session_state.pop("topbar_aws_login_started_at", None)
                            load_integration_status.clear()
                            st.rerun()
                with user_col:
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
