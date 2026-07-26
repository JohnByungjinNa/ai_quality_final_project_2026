from dashboard.pages_top.github_view import render_github_page
import streamlit as st


render_github_page(st.session_state.get("github_fixture_sub_menu", "환경 설정"))
