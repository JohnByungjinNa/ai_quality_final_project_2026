import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for path in (PROJECT_ROOT, DASHBOARD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pages_top.ops_monitoring import render_k6_summary, render_request_dashboard


snapshot = {
    "request_metrics_available": False,
    "request_metrics_source": {
        "name": "Prometheus → FastAPI /metrics",
        "window": "최근 5분",
        "scope": "/metrics를 제외한 FastAPI 전체 HTTP 요청",
    },
    "total_requests": None,
    "success_requests": None,
    "error_requests": None,
    "error_rate": None,
    "avg_latency": None,
    "p95_latency": None,
    "request_series": pd.DataFrame(),
    "duration_series": pd.DataFrame(),
    "k6_summary": {
        "run_id": "20260715_112430",
        "created_at": "2026-07-15T11:24:30",
        "target_url": "http://localhost:8000/health",
        "total_requests": 1591,
        "failure_rate": 0,
        "avg_duration_seconds": 0.029,
        "p95_duration_seconds": 0.071,
        "throughput": 32.86,
        "vus": 200,
    },
}

render_request_dashboard(snapshot)
render_k6_summary(snapshot)
