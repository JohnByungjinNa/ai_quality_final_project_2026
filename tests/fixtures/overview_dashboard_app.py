import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for path in (PROJECT_ROOT, DASHBOARD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services import qa_observer_client


qa_observer_client.fetch_filter_options = lambda base_url=None: {
    "environments": ["local"],
    "services": ["chatbot-test"],
    "providers": ["openai"],
    "models": ["gpt-4o-mini"],
}


def _bundle(*args, **kwargs):
    quality_events = []
    for index in range(1, 8):
        quality_events.append(
            {
                "event": {
                    "occurred_at": f"2026-07-14T0{index}:00:00Z",
                    "event_type": "quality.evaluation.completed",
                    "context": {
                        "service": "chatbot-test",
                        "run_id": f"RUN-20260714{index:02d}0000",
                        "case_id": f"TC-{index:03d}",
                    },
                    "payload": {
                        "scores": {
                            "accuracy": {"evaluated": True, "score": 4 + index / 10},
                            "safety": {"evaluated": True, "score": 5},
                        }
                    },
                }
            }
        )
    return {
        "health": {
            "status": "healthy",
            "storage": {"writable": True},
            "scheduler": {
                "running": True,
                "last_success_at_utc": "2026-07-14T01:00:10Z",
                "last_error_type": None,
                "interval_seconds": 30,
            },
        },
        "summary": {
            "data_status": "fresh",
            "latest_received_at_utc": "2026-07-14T01:00:00Z",
            "freshness_seconds": 10,
            "quality_score": 92.5,
            "test_pass_rate": 96.0,
            "api_p95_duration_ms": 3100,
            "api_error_rate": 0.5,
            "safety_violation_count": 1,
            "llm_total_tokens": 1234,
            "llm_cost_krw": 18420,
            "llm_price_coverage": 100,
            "daily_budget_krw": 50000,
            "budget_usage_rate": 36.84,
            "rag_no_result_rate": 3.0,
            "open_defect_count": 0,
        },
        "timeseries": {
            "items": [
                {"date": "2026-07-13", "metric": "quality.accuracy.score", "average_value": 4.5, "sum_value": 9},
                {"date": "2026-07-13", "metric": "quality.safety.score", "average_value": 5, "sum_value": 10},
                {"date": "2026-07-13", "metric": "quality.groundedness.score", "average_value": 4.6, "sum_value": 9.2},
                {"date": "2026-07-14", "metric": "quality.accuracy.score", "average_value": 4.7, "sum_value": 9.4},
                {"date": "2026-07-14", "metric": "quality.safety.score", "average_value": 4.8, "sum_value": 9.6},
                {"date": "2026-07-14", "metric": "quality.groundedness.score", "average_value": 4.65, "sum_value": 9.3},
                {"date": "2026-07-14", "metric": "quality.helpfulness.score", "average_value": 4.4, "sum_value": 8.8},
                {"date": "2026-07-14", "metric": "api.requests", "average_value": 1, "sum_value": 100},
                {"date": "2026-07-14", "metric": "api.service_errors", "average_value": 1, "sum_value": 1},
                {"date": "2026-07-14", "metric": "api.duration_ms", "average_value": 800, "sum_value": 80000, "sample_count": 100},
                {"date": "2026-07-14", "metric": "llm.duration_ms", "average_value": 450, "sum_value": 4500, "sample_count": 10},
                {"date": "2026-07-14", "metric": "llm.requests", "average_value": 1, "sum_value": 10, "sample_count": 10},
                {"date": "2026-07-14", "metric": "llm.input_tokens", "average_value": 100, "sum_value": 1000, "sample_count": 10},
                {"date": "2026-07-14", "metric": "llm.output_tokens", "average_value": 20, "sum_value": 200, "sample_count": 10},
                {"date": "2026-07-14", "metric": "llm.cached_input_tokens", "average_value": 3.4, "sum_value": 34, "sample_count": 10},
                {"date": "2026-07-14", "metric": "llm.total_tokens", "average_value": 123.4, "sum_value": 1234, "sample_count": 10},
                {"date": "2026-07-14", "metric": "rag.duration_ms", "average_value": 80, "sum_value": 800, "sample_count": 10},
                {"date": "2026-07-14", "metric": "rag.searches", "average_value": 1, "sum_value": 100, "sample_count": 100},
                {"date": "2026-07-14", "metric": "rag.no_result", "average_value": 0.03, "sum_value": 3, "sample_count": 100},
                {"date": "2026-07-14", "metric": "rag.top_k_hit", "average_value": 0.91, "sum_value": 91, "sample_count": 100},
                {"date": "2026-07-14", "metric": "test.pass_count", "average_value": 24, "sum_value": 24, "sample_count": 1},
                {"date": "2026-07-14", "metric": "test.fail_count", "average_value": 1, "sum_value": 1, "sample_count": 1},
                {"date": "2026-07-14", "metric": "test.error_count", "average_value": 0, "sum_value": 0, "sample_count": 1},
            ]
        },
        "events": {
            "items": [
                {
                    "event": {
                        "occurred_at": "2026-07-14T01:00:00Z",
                        "event_type": "quality.evaluation.completed",
                        "context": {"service": "chatbot-test", "run_id": "RUN-1", "case_id": "TC-1"},
                        "payload": {"overall_decision": "PASS"},
                    }
                },
                {
                    "event": {
                        "occurred_at": "2026-07-14T00:55:00Z",
                        "event_type": "test.run.completed",
                        "context": {"service": "chatbot-test", "run_id": "RUN-1", "case_id": "TC-009"},
                        "payload": {"pass_count": 24, "fail_count": 1, "error_count": 0, "total_count": 25},
                    }
                }
            ]
        },
        "quality_events": {"items": quality_events},
        "safety_events": {
            "items": [
                {
                    "event": {
                        "occurred_at": "2026-07-14T00:50:00Z",
                        "event_type": "safety.violation.detected",
                        "context": {
                            "service": "chatbot-test",
                            "run_id": "RUN-20260714010000",
                            "case_id": "TC-017",
                        },
                        "payload": {"severity": "critical", "category": "llm_judge_safety_score"},
                    }
                }
            ]
        },
    }


qa_observer_client.fetch_dashboard_bundle = _bundle

from pages_top.overview_dashboard import render_overview_dashboard_page


render_overview_dashboard_page()
