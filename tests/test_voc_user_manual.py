import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.navigation import SIDEBAR_MENU_OPTIONS
from dashboard.services.voc_quality_service import load_guide


PROJECT_DIR = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_DIR / "README.md"


def test_readme_uses_required_operating_manual_order():
    content = README_PATH.read_text(encoding="utf-8")
    headings = [
        "## 1. 프로젝트 목적",
        "## 2. 프로젝트 구조",
        "## 3. 설치 방법",
        "## 4. 환경변수 설정",
        "## 5. 실행 방법",
        "## 6. 테스트 방법",
        "## 7. 결과물 위치",
    ]
    positions = [content.index(heading) for heading in headings]

    assert positions == sorted(positions)
    assert all(label in content for label in SIDEBAR_MENU_OPTIONS["VOC 품질진단"])


def test_user_guide_reads_exact_root_readme_and_referenced_commands_exist():
    content = README_PATH.read_text(encoding="utf-8")

    assert load_guide("사용자 가이드") == content
    for relative_path in (
        "requirements.txt",
        "tools/start_dashboard.ps1",
        "voc_quality_runtime/.env.example",
        "voc_quality_runtime/scripts/agents.cmd",
        "voc_quality_runtime/scripts/quality-diagnosis.cmd",
    ):
        assert (PROJECT_DIR / relative_path).is_file(), relative_path


def test_user_manual_contains_no_plaintext_credentials():
    content = README_PATH.read_text(encoding="utf-8")
    patterns = (
        r"sk-proj-[A-Za-z0-9_-]{12,}",
        r"sk-ant-[A-Za-z0-9_-]{12,}",
        r"tvly-[A-Za-z0-9_-]{12,}",
    )

    assert not any(re.search(pattern, content) for pattern in patterns)


def test_user_guide_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_user_guide_app.py", default_timeout=20)
    app.run()

    assert not app.exception
    assert app.segmented_control[0].options == [
        "사용자 가이드", "품질진단 실행", "이식 가이드", "이식 체크리스트"
    ]
    assert any("프로젝트 목적" in item.value for item in app.markdown)
