import streamlit as st

from core.constants import SYSTEM_NAME


SHUTDOWN_OVERLAY_HTML = f"""
<div class="system-shutdown-overlay" role="status" aria-live="polite">
  <div class="system-shutdown-card">
    <div class="system-shutdown-title">{SYSTEM_NAME} 서비스가 종료되었습니다.</div>
    <div class="system-shutdown-desc">관련 서비스를 종료했습니다. 다시 사용하려면 통합 실행기를 실행하세요.</div>
    <button class="system-shutdown-close" type="button">웹페이지 닫기</button>
    <div class="system-shutdown-fallback" hidden>
      브라우저 보안 정책으로 이 탭을 자동으로 닫을 수 없습니다. 탭의 닫기 버튼을 이용해 주세요.
    </div>
  </div>
</div>
"""

SHUTDOWN_OVERLAY_CSS = """
.system-shutdown-overlay {
  position: fixed;
  inset: 0;
  z-index: 2147483647;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: 24px;
  background: rgba(229, 231, 235, 0.96);
  backdrop-filter: grayscale(1) blur(2px);
  font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
}
.system-shutdown-card {
  width: min(560px, 100%);
  box-sizing: border-box;
  padding: 28px 30px;
  text-align: center;
  color: #334155;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.42);
  border-radius: 12px;
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.14);
}
.system-shutdown-title {
  margin-bottom: 10px;
  color: #1f2937;
  font-size: 24px;
  font-weight: 800;
  line-height: 1.35;
}
.system-shutdown-desc {
  color: #64748b;
  font-size: 14px;
  line-height: 1.6;
}
.system-shutdown-close {
  min-width: 150px;
  margin-top: 20px;
  padding: 10px 18px;
  border: 1px solid #0b4f91;
  border-radius: 8px;
  background: #0b4f91;
  color: #ffffff;
  font: inherit;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
}
.system-shutdown-close:hover {
  background: #083d70;
}
.system-shutdown-close:focus-visible {
  outline: 3px solid rgba(37, 99, 235, 0.35);
  outline-offset: 2px;
}
.system-shutdown-fallback {
  margin-top: 14px;
  color: #b45309;
  font-size: 12px;
  line-height: 1.5;
}
"""

SHUTDOWN_OVERLAY_JS = """
export default function(component) {
  const { parentElement } = component
  const closeButton = parentElement.querySelector('.system-shutdown-close')
  const fallback = parentElement.querySelector('.system-shutdown-fallback')
  if (!closeButton || closeButton.dataset.bound === 'true') return

  closeButton.dataset.bound = 'true'
  closeButton.onclick = () => {
    window.close()
    window.setTimeout(() => {
      if (!document.hidden && fallback) {
        fallback.hidden = false
        closeButton.textContent = '브라우저에서 탭을 닫아주세요'
      }
    }, 250)
  }
}
"""

_SHUTDOWN_OVERLAY = st.components.v2.component(
    "system_shutdown_overlay",
    html=SHUTDOWN_OVERLAY_HTML,
    css=SHUTDOWN_OVERLAY_CSS,
    js=SHUTDOWN_OVERLAY_JS,
    isolate_styles=False,
)


def render_shutdown_overlay():
    _SHUTDOWN_OVERLAY(key="system_shutdown_overlay")
