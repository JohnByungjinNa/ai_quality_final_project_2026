import sys
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from pages_top.ops_monitoring import render_ops_detail_page


render_ops_detail_page()
