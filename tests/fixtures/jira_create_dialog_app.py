import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for path in (PROJECT_ROOT, DASHBOARD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pages_top import jira_view


jira_view.load_json_file = lambda _path, default: default
jira_view.jira_environment_snapshot = lambda: {
    "ready": False,
    "missing": ["JIRA_API_KEY"],
    "project_key": "KAN",
}
jira_view.render_jira_page("Jira 등록")
