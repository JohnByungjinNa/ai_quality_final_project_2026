import sys
from pathlib import Path


DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "dashboard"
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from pages_top import observability


observability._snapshot = lambda _base_url: {
    "api_availability": 0.999,
    "api_latency": 0.98,
    "test_pass": 0.97,
    "quality_pass": 0.96,
    "budget_api": 0.9,
    "budget_test": 0.4,
    "budget_quality": 0.2,
}
observability._range = lambda *_args, **_kwargs: []
observability.render_observability_page("SLO·Error Budget")
