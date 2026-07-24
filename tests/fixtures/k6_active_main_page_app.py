import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for path in (PROJECT_ROOT, DASHBOARD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pages_top import k6_runner_view


ACTIVE_RUN = {
    "run_id": "20260715_120000",
    "status": "RUNNING",
    "created_at": datetime.now().isoformat(timespec="seconds"),
    "started_at": datetime.now().isoformat(timespec="seconds"),
    "settings": {
        "target_url": "http://localhost:8000/health",
        "vus": 20,
        "duration_seconds": 60,
        "ramp_up_seconds": 10,
        "p95_threshold_ms": 3000,
        "failure_rate_threshold_pct": 1.0,
        "checks_threshold_pct": 95.0,
        "think_time_seconds": 1.0,
    },
}

k6_runner_view.is_k6_available = lambda: True
k6_runner_view.get_cached_k6_version = lambda: "k6 test"
k6_runner_view.get_active_k6_run = lambda: ACTIVE_RUN
k6_runner_view.load_recent_runs = lambda limit=10: []

k6_runner_view.render_k6_runner_page()
