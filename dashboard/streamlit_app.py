import os
import threading
import time

import streamlit as st

from navigation import render_navigation
from pages_top.knowledge_base import render_knowledge_db_page
from pages_top.knowledge_base_view import render_knowledge_base_page
from pages_top.docker_view import render_docker_page
from pages_top.github_view import render_github_page
from pages_top.jira_view import render_jira_page
from pages_top.performance import render_performance_page
from pages_top.placeholder import render_placeholder_page
from pages_top.testcase import render_testcase_page
from pages_top.testcase_execution_view import render_testcase_execution_page
from pages_top.testcase_history_view import render_testcase_history_page
from pages_top.pytest_result_view import render_pytest_result_page
from pages_top.testcase_upload_view import render_testcase_upload_page
from pages_top.voc_quality import render_voc_quality_page
from pages_top.overview_dashboard import render_overview_dashboard_page
from components.shutdown_overlay import render_shutdown_overlay
from core.app_state import initialize_session_state
from core.constants import SYSTEM_NAME
from core.paths import TOPBAR_HEIGHT
from services.service_control import cleanup_prometheus_temporary_config, stop_related_services


MIN_STREAMLIT_VERSION = (1, 59, 0)


def _version_tuple(value):
    parts = []
    for part in str(value).split(".")[:3]:
        digits = "".join(character for character in part if character.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0])[:3])


def schedule_streamlit_shutdown(delay_seconds=1.4):
    def stop_process():
        try:
            stop_related_services()
        finally:
            cleanup_prometheus_temporary_config()
            time.sleep(delay_seconds)
            os._exit(0)

    thread = threading.Thread(target=stop_process, daemon=True)
    thread.start()


# 1. 페이지 기본 설정 (와이드 모드 및 사이드바 초기화)
st.set_page_config(
    page_title=SYSTEM_NAME,
    layout="wide",
    initial_sidebar_state="expanded"
)

if _version_tuple(st.__version__) < MIN_STREAMLIT_VERSION:
    st.error(
        f"지원하지 않는 Streamlit {st.__version__} 환경으로 실행되었습니다. "
        "프로젝트 가상환경의 Streamlit 1.59 이상으로 다시 실행하세요.",
        icon=":material/error:",
    )
    st.code(r"powershell -ExecutionPolicy Bypass -File .\tools\start_dashboard.ps1 -Restart", language="powershell")
    st.stop()

# 2. 세션 스테이트(Session State)를 이용한 메뉴 관리 초기화
if "current_menu" not in st.session_state:
    st.session_state.current_menu = "종합 현황"
if "current_sub_menu" not in st.session_state:
    st.session_state.current_sub_menu = "AI QA 종합 현황"
initialize_session_state()

# 3. 상단바를 화면 전체 너비로 '고정(fixed)'시키기 위한 커스텀 CSS
#    - st.container(key="topbar")가 렌더링하는 div에 .st-key-topbar 클래스가 붙는 것을 이용해
#      해당 컨테이너 자체를 position: fixed 로 뷰포트 상단에 고정한다.
#    - 고정된 만큼 본문/사이드바 상단에 여백(padding-top)을 줘서 내용이 가려지지 않게 한다.
st.markdown(f"""
    <style>
    /* 스트림릿 기본 헤더(햄버거 메뉴 영역) 숨기기 */
    [data-testid="stHeader"] {{
        background: transparent !important;
        height: {TOPBAR_HEIGHT} !important;
        pointer-events: none !important;
        z-index: 1000001 !important;
    }}

    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"] {{
        display: none !important;
    }}

    [data-testid="collapsedControl"] {{
        display: flex !important;
        position: fixed !important;
        top: calc({TOPBAR_HEIGHT} + 8px) !important;
        left: 12px !important;
        z-index: 1000000 !important;
        pointer-events: auto !important;
        background: #ffffff !important;
        border: 1px solid #d9e0ea !important;
        border-radius: 6px !important;
        box-shadow: 0 2px 8px rgba(15, 45, 89, 0.18) !important;
    }}

    [data-testid="collapsedControl"] button,
    [data-testid="stSidebarCollapsedControl"] button,
    button[title="Open sidebar"],
    button[aria-label="Open sidebar"] {{
        display: inline-flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        pointer-events: auto !important;
    }}

    /* 본문 컨테이너 - 고정 상단바 높이만큼 위 여백 확보 */
    .block-container {{
        padding-top: calc({TOPBAR_HEIGHT} + 1.2rem) !important;
        padding-bottom: 1rem !important;
    }}

    /* 사이드바도 고정 상단바 높이만큼 아래로 밀어주기 */
    section[data-testid="stSidebar"] > div:first-child {{
        padding-top: {TOPBAR_HEIGHT};
        background-color: #172235;
    }}

    section[data-testid="stSidebar"] {{
        background-color: #172235;
    }}

    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
        color: #c9d4e5;
    }}

    section[data-testid="stSidebar"] hr {{
        border-color: rgba(255,255,255,0.08);
        margin: 0.6rem 0 0.8rem;
    }}

    .sidebar-title {{
        color: #ffffff;
        font-size: 15px;
        font-weight: 700;
        padding: 16px 2px 14px;
        margin: 0 0 8px 0;
        letter-spacing: 0;
        border-bottom: 1px solid rgba(255,255,255,0.10);
    }}

    .sidebar-title::before {{
        content: "";
        display: inline-block;
        width: 6px;
        height: 6px;
        margin-right: 8px;
        border-radius: 50%;
        background-color: #60a5fa;
        vertical-align: 2px;
    }}

    .page-kicker {{
        color: #7b8798;
        font-size: 13px;
        font-weight: 500;
        margin: 0 0 18px 0;
    }}

    section[data-testid="stSidebar"] .stButton {{
        margin: 0;
    }}

    section[data-testid="stSidebar"] .stButton > button {{
        width: 100%;
        height: 38px;
        justify-content: flex-start;
        border: 0 !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        padding: 0 16px !important;
        font-size: 13px !important;
        text-align: left;
        transition: background-color 0.12s ease, color 0.12s ease;
    }}

    section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {{
        background-color: transparent !important;
        color: #aab7cc !important;
    }}

    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
        background-color: #2c4567 !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border-left: 3px solid #4f8ff0 !important;
    }}

    section[data-testid="stSidebar"] .stButton > button:hover {{
        background-color: #243852 !important;
        color: #ffffff !important;
    }}

    /* ===== 상단바(topbar) 컨테이너를 화면 전체 폭 고정으로 ===== */
    .st-key-topbar {{
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        width: 100%;
        z-index: 999999;
        background-color: #0f2d59;
        padding: 0 24px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
    }}
    .st-key-topbar > div {{
        display: flex;
        align-items: center;
        height: {TOPBAR_HEIGHT};
    }}

    /* 로고 영역 */
    .brand-title {{
        font-size: 20px;
        font-weight: 700;
        color: #ffffff;
        white-space: nowrap;
        display: inline-flex;
        align-items: center;
        height: 100%;
    }}

    /* 우측 사용자 정보 영역 */
    .topbar-right {{
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: 14px;
        white-space: nowrap;
    }}
    .topbar-bell {{
        font-size: 18px;
        color: #d7e0f0;
        cursor: pointer;
    }}
    .topbar-avatar {{
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background-color: #2f6fed;
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        font-weight: 700;
    }}
    .topbar-username {{
        font-size: 13px;
        color: #ffffff;
        font-weight: 500;
    }}

    /* 메뉴 버튼들을 '탭'처럼 보이도록 스타일 재정의 */
    .st-key-topbar .stButton > button {{
        border: none !important;
        border-radius: 0 !important;
        background-color: transparent !important;
        padding: 0 4px !important;
        height: {TOPBAR_HEIGHT};
        font-size: 14px !important;
        box-shadow: none !important;
    }}
    /* 선택된(활성) 메뉴 탭 */
    .st-key-topbar .stButton > button[kind="primary"] {{
        color: #ffffff !important;
        font-weight: 700 !important;
        border-bottom: 3px solid #4f8ff0 !important;
    }}
    /* 선택되지 않은(비활성) 메뉴 탭 */
    .st-key-topbar .stButton > button[kind="secondary"] {{
        color: #aebbd6 !important;
        font-weight: 500 !important;
        border-bottom: 3px solid transparent !important;
    }}
    .st-key-topbar .stButton > button:hover {{
        color: #ffffff !important;
        background-color: rgba(255,255,255,0.06) !important;
    }}
    .st-key-topbar .stButton > button:focus:not(:active) {{
        color: #ffffff !important;
    }}

    .st-key-topbar .st-key-streamlit_shutdown_button button {{
        height: 28px !important;
        min-height: 28px !important;
        min-width: 48px !important;
        padding: 0 8px !important;
        border-radius: 6px !important;
        border: 1px solid rgba(255,255,255,0.26) !important;
        background-color: rgba(255,255,255,0.10) !important;
        color: #ffffff !important;
        font-size: 12px !important;
        font-weight: 700 !important;
        line-height: 1 !important;
        box-shadow: none !important;
    }}

    .st-key-topbar .st-key-streamlit_shutdown_button button:hover {{
        background-color: rgba(255,255,255,0.20) !important;
        border-color: rgba(255,255,255,0.42) !important;
        color: #ffffff !important;
    }}

    .section-card {{
        background-color: #ffffff;
        border: 1px solid #d9e0ea;
        border-radius: 8px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }}

    .section-title {{
        color: #193c73;
        font-size: 15px;
        font-weight: 700;
        margin-bottom: 6px;
    }}

    .section-desc {{
        color: #68758a;
        font-size: 13px;
        margin-bottom: 0;
    }}

    .table-summary {{
        color: #64748b;
        font-size: 13px;
        margin-top: 8px;
    }}

    .detail-status {{
        color: #1f3f73;
        font-size: 13px;
        text-align: right;
        margin-bottom: 12px;
    }}

    .detail-note {{
        color: #8a94a6;
        font-size: 13px;
        margin: 10px 0 18px;
    }}
    /* 레이어 팝업 넓이 조절 */
    div[data-testid="stDialog"] div[role="dialog"] {{
        width: 90vw !important;
        max-width: 1400px !important;
        background-color: #ffffff !important;
        color: #15243b !important;
    }}
    div[data-testid="stDialog"] div[role="dialog"] [data-testid="stMarkdownContainer"] {{
        color: #15243b;
    }}
    div[data-testid="stDialog"] div[role="dialog"] [data-testid="stTabs"] {{
        background-color: #ffffff !important;
    }}
    div[data-testid="stDialog"] div[role="dialog"] [data-baseweb="tab-list"] {{
        background-color: #f8fbff !important;
        border-bottom: 1px solid #c8d9ee !important;
    }}
    div[data-testid="stDialog"] div[role="dialog"] button[data-baseweb="tab"] {{
        color: #40536d !important;
        font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif !important;
        font-weight: 700 !important;
    }}
    div[data-testid="stDialog"] div[role="dialog"] button[data-baseweb="tab"][aria-selected="true"] {{
        color: #0b4f91 !important;
        background-color: #edf4fb !important;
    }}
    </style>
""", unsafe_allow_html=True)


if st.session_state.get("streamlit_shutdown_requested"):
    render_shutdown_overlay()
    if not st.session_state.get("streamlit_shutdown_started"):
        st.session_state.streamlit_shutdown_started = True
        schedule_streamlit_shutdown()
    st.stop()


active_menu, sidebar_sub_menu = render_navigation()

if active_menu == "종합 현황":
    handled = render_overview_dashboard_page()
elif active_menu == "성능관리":
    handled = render_performance_page(sidebar_sub_menu)
elif active_menu == "테스트 관리":
    handled = render_testcase_page(
        sidebar_sub_menu,
        render_testcase_upload_page,
        render_testcase_execution_page,
        render_testcase_history_page,
        render_pytest_result_page,
    )
elif active_menu in ("지식 파일 관리", "지식DB관리"):
    handled = render_knowledge_db_page(sidebar_sub_menu, render_knowledge_base_page)
elif active_menu == "Jira관리":
    handled = render_jira_page(sidebar_sub_menu)
elif active_menu == "GitHub 관리":
    handled = render_github_page(sidebar_sub_menu)
elif active_menu == "Docker 관리":
    handled = render_docker_page(sidebar_sub_menu)
elif active_menu == "VOC 품질진단":
    handled = render_voc_quality_page(sidebar_sub_menu)
else:
    handled = False

if not handled:
    render_placeholder_page(active_menu, sidebar_sub_menu)
