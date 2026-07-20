import streamlit as st

from core.paths import (
    LEGACY_TESTCASE_HISTORY_FILE,
    LEGACY_TESTCASE_UPLOADS_FILE,
    TESTCASE_HISTORY_FILE,
    TESTCASE_UPLOADS_FILE,
)
from core.storage import deserialize_uploads, load_json_file


def initialize_session_state():

    if "testcase_uploads" not in st.session_state:
        st.session_state.testcase_uploads = deserialize_uploads(
            load_json_file(TESTCASE_UPLOADS_FILE, [], LEGACY_TESTCASE_UPLOADS_FILE)
        )
    if "testcase_uploader_key" not in st.session_state:
        st.session_state.testcase_uploader_key = 0
    if "testcase_flash_message" not in st.session_state:
        st.session_state.testcase_flash_message = ""
    if "testcase_execution_history" not in st.session_state:
        st.session_state.testcase_execution_history = load_json_file(
            TESTCASE_HISTORY_FILE, [], LEGACY_TESTCASE_HISTORY_FILE
        )
    if "testcase_history_flash_message" not in st.session_state:
        st.session_state.testcase_history_flash_message = ""
    if "history_detail_open_id" not in st.session_state:
        st.session_state.history_detail_open_id = None
    if "knowledge_preview_file" not in st.session_state:
        st.session_state.knowledge_preview_file = None
    if "knowledge_selected_files" not in st.session_state:
        st.session_state.knowledge_selected_files = []
    if "knowledge_uploader_key" not in st.session_state:
        st.session_state.knowledge_uploader_key = 0
    if "knowledge_flash_message" not in st.session_state:
        st.session_state.knowledge_flash_message = ""
    if "streamlit_shutdown_requested" not in st.session_state:
        st.session_state.streamlit_shutdown_requested = False
    if "streamlit_shutdown_started" not in st.session_state:
        st.session_state.streamlit_shutdown_started = False

