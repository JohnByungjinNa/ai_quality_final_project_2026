import streamlit as st


STREAMLIT_SHORTCUT_GUARD_HTML = """
<span class="streamlit-shortcut-guard" hidden aria-hidden="true"></span>
"""

STREAMLIT_SHORTCUT_GUARD_JS = """
export default function(component) {
  if (window.__aiQualityShortcutGuardInstalled === true) return
  window.__aiQualityShortcutGuardInstalled = true

  const isEditableTarget = (target) => {
    if (!target) return false
    const element = target instanceof Element ? target : target?.parentElement
    if (!element) return false
    const editable = element.closest(
      'input, textarea, select, [contenteditable="true"], [role="textbox"]'
    )
    return Boolean(editable)
  }

  const stopStreamlitClearCacheShortcut = (event) => {
    if (!event || isEditableTarget(event.target)) return
    const key = String(event.key || '').toLowerCase()
    if (key !== 'c') return

    // Streamlit binds the plain "c" shortcut to the Clear caches dialog.
    // Stop only propagation to Streamlit. Do not prevent the browser default
    // so Ctrl+C / Cmd+C keeps copying selected page text normally.
    event.stopImmediatePropagation()
    event.stopPropagation()
  }

  window.addEventListener('keydown', stopStreamlitClearCacheShortcut, true)
}
"""


_STREAMLIT_SHORTCUT_GUARD = st.components.v2.component(
    "streamlit_shortcut_guard",
    html=STREAMLIT_SHORTCUT_GUARD_HTML,
    js=STREAMLIT_SHORTCUT_GUARD_JS,
    isolate_styles=False,
)


def render_streamlit_shortcut_guard() -> None:
    _STREAMLIT_SHORTCUT_GUARD(key="streamlit_shortcut_guard")
