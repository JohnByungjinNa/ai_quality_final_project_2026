import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"


def test_dashboard_working_directory_can_import_root_packages():
    entrypoint = DASHBOARD_ROOT / "streamlit_app.py"
    source = entrypoint.read_text(encoding="utf-8")
    bootstrap = source[: source.index("import streamlit as st")]
    command = (
        f"__file__ = {str(entrypoint)!r}\n"
        + bootstrap
        + "\nimport qa_observer.telemetry\nprint('root-import-ok')\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        cwd=DASHBOARD_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "root-import-ok" in result.stdout
    assert source.index("sys.path.insert") < source.index("from navigation import render_navigation")
