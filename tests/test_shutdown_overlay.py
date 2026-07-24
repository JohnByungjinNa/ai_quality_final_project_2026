from dashboard.components.shutdown_overlay import (
    SHUTDOWN_OVERLAY_HTML,
    SHUTDOWN_OVERLAY_JS,
)
from dashboard.core.constants import SYSTEM_NAME


def test_shutdown_overlay_uses_system_name_and_close_action():
    assert f"{SYSTEM_NAME} 서비스가 종료되었습니다." in SHUTDOWN_OVERLAY_HTML
    assert "웹페이지 닫기" in SHUTDOWN_OVERLAY_HTML
    assert "window.close()" in SHUTDOWN_OVERLAY_JS
    assert "브라우저 보안 정책" in SHUTDOWN_OVERLAY_HTML
