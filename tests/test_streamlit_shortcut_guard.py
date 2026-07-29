from pathlib import Path

from dashboard.components.streamlit_shortcut_guard import STREAMLIT_SHORTCUT_GUARD_JS


def test_streamlit_shortcut_guard_blocks_clear_cache_shortcut_without_blocking_copy():
    assert "keydown" in STREAMLIT_SHORTCUT_GUARD_JS
    assert "key !== 'c'" in STREAMLIT_SHORTCUT_GUARD_JS
    assert "stopImmediatePropagation" in STREAMLIT_SHORTCUT_GUARD_JS
    assert "preventDefault" not in STREAMLIT_SHORTCUT_GUARD_JS
    assert "Ctrl+C / Cmd+C keeps copying" in STREAMLIT_SHORTCUT_GUARD_JS
    assert "input, textarea, select" in STREAMLIT_SHORTCUT_GUARD_JS


def test_streamlit_app_mounts_shortcut_guard_near_startup():
    source = Path("dashboard/streamlit_app.py").read_text(encoding="utf-8")

    assert "from components.streamlit_shortcut_guard import render_streamlit_shortcut_guard" in source
    assert "render_streamlit_shortcut_guard()" in source
    assert source.index("st.set_page_config(") < source.index("render_streamlit_shortcut_guard()")
