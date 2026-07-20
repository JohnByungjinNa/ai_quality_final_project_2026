import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = PROJECT_DIR / "dashboard"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
