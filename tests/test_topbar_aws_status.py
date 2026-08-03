from pathlib import Path

from dashboard.navigation import _aws_login_poll_action, _topbar_aws_status
from dashboard.services import integration_status_service


ROOT = Path(__file__).resolve().parents[1]


def test_topbar_aws_status_distinguishes_connected_and_login_required():
    connected = _topbar_aws_status({"authenticated": True, "profile": "JohnNa-QA"})
    logged_out = _topbar_aws_status({"authenticated": False, "session_status": "login_required"})

    assert connected["label"] == "연결됨"
    assert connected["tone"] == "connected"
    assert logged_out["label"] == "로그인 필요"
    assert logged_out["tone"] == "login-required"


def test_topbar_aws_status_requires_expected_user_and_configuration():
    wrong_user = _topbar_aws_status({"authenticated": False, "session_status": "unexpected_principal"})
    missing_cli = _topbar_aws_status({"authenticated": False, "session_status": "cli_missing"})

    assert wrong_user["label"] == "사용자 확인"
    assert wrong_user["tone"] == "error"
    assert missing_cli["label"] == "설정 필요"


def test_topbar_places_aws_badge_before_notification_and_team_name():
    source = (ROOT / "dashboard" / "navigation.py").read_text(encoding="utf-8")

    assert source.index("topbar_aws_action_") < source.index("topbar-bell")
    assert source.index("topbar-bell") < source.index("최강3조")
    assert source.count('vertical_alignment="center"') >= 3


def test_topbar_automatically_polls_and_refreshes_after_aws_login():
    source = (ROOT / "dashboard" / "navigation.py").read_text(encoding="utf-8")

    assert "AWS_LOGIN_POLL_INTERVAL_SECONDS = 2" in source
    assert '@st.fragment(run_every=f"{AWS_LOGIN_POLL_INTERVAL_SECONDS}s")' in source
    assert "def _poll_aws_login_completion()" in source
    assert "load_integration_status.clear()" in source
    assert 'st.rerun(scope="app")' in source
    assert "_poll_aws_login_completion()" in source


def test_aws_login_poll_detects_completion_and_timeout():
    assert _aws_login_poll_action(
        {"authenticated": True, "session_status": "authenticated"},
        100,
        now=102,
    ) == "connected"
    assert _aws_login_poll_action(
        {"authenticated": False, "session_status": "login_required"},
        100,
        now=102,
    ) == "pending"
    assert _aws_login_poll_action({}, 100, now=401) == "expired"


def test_topbar_button_shows_only_aws_icon_and_uses_three_status_colors():
    navigation = (ROOT / "dashboard" / "navigation.py").read_text(encoding="utf-8")
    styles = (ROOT / "dashboard" / "streamlit_app.py").read_text(encoding="utf-8")

    assert 'f"![AWS]({AWS_CONSOLE_ICON_URL})"' in navigation
    assert "f\"AWS {aws_status['label']}\"" not in navigation
    constants = (ROOT / "dashboard" / "core" / "constants.py").read_text(encoding="utf-8")
    assert "libra-css/images/site/fav/favicon.ico" in constants
    assert 'button[data-testid="stPopoverButton"]' in styles
    assert 'div[data-testid="stPopover"] > button' not in styles
    assert 'button[data-testid="stPopoverButton"] p img' in styles
    cube_icon = ROOT / "dashboard" / "assets" / "providers" / "aws-console-cube.svg"
    cube_svg = cube_icon.read_text(encoding="utf-8")
    assert cube_icon.is_file()
    assert '<svg xmlns="http://www.w3.org/2000/svg"' in cube_svg
    assert 'stroke="#fff"' in cube_svg
    assert "AWS_CUBE_MASK_DATA = base64.b64encode(" in styles
    assert 'url("data:image/svg+xml;base64,{AWS_CUBE_MASK_DATA}")' in styles
    assert '-webkit-mask: url("{AWS_CONSOLE_ICON_URL}")' not in styles
    assert "background-color: #94a3b8" in styles
    assert "background-color: #4ade80" in styles
    assert "background-color: #f87171" in styles
    assert "border: 0 !important" in styles
    assert "content: none !important" in styles
    assert "st.popover(" in navigation
    assert '"AWS 로그인"' in navigation
    assert '"로그아웃"' in navigation
    assert '"AWS 연결 정보"' in navigation


def test_topbar_login_launches_temporary_browser_auth_without_access_keys(tmp_path, monkeypatch):
    captured = {}

    class FakeProcess:
        pid = 321

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess()

    monkeypatch.setattr(integration_status_service, "_resolve_aws_cli", lambda *_args: "aws.exe")
    monkeypatch.setattr(integration_status_service.subprocess, "Popen", fake_popen)

    result = integration_status_service.start_aws_browser_login(
        project_dir=tmp_path,
        home_dir=tmp_path,
        environ={"PATH": ""},
        platform_name="nt",
    )

    assert result["ok"] is True
    command_text = " ".join(captured["command"])
    assert "login --profile 'JohnNa-QA' --region 'ap-northeast-2'" in command_text
    assert "create-access-key" not in command_text
    assert captured["kwargs"]["cwd"] == tmp_path


def test_topbar_logout_clears_only_temporary_profile_credentials(tmp_path, monkeypatch):
    captured = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return Completed()

    monkeypatch.setattr(integration_status_service, "_resolve_aws_cli", lambda *_args: "aws.exe")
    monkeypatch.setattr(integration_status_service.subprocess, "run", fake_run)

    result = integration_status_service.logout_aws_session(
        project_dir=tmp_path,
        home_dir=tmp_path,
        environ={"PATH": ""},
    )

    assert result["ok"] is True
    assert captured["command"] == [
        "aws.exe",
        "logout",
        "--profile",
        "JohnNa-QA",
        "--region",
        "ap-northeast-2",
        "--no-cli-pager",
    ]
    assert "--all" not in captured["command"]
    assert captured["kwargs"]["cwd"] == tmp_path
