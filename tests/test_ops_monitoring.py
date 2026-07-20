import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard.pages_top import ops_monitoring
from dashboard.pages_top.ops_monitoring import (
    NETWORK_SAMPLE_INTERVAL_SECONDS,
    NETWORK_PANEL_COLUMN_RATIO,
    NETWORK_PORT_GRID_COLUMNS,
    build_network_traffic_chart,
    update_network_traffic_history,
)


class SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


def test_network_uses_lightweight_five_second_sampling():
    assert NETWORK_SAMPLE_INTERVAL_SECONDS == 5


def test_network_layout_prioritizes_traffic_and_stacks_ports_vertically():
    assert NETWORK_PANEL_COLUMN_RATIO == (1.7, 0.8)
    assert NETWORK_PANEL_COLUMN_RATIO[0] > NETWORK_PANEL_COLUMN_RATIO[1] * 2
    assert NETWORK_PORT_GRID_COLUMNS == 1


def test_ops_monitoring_defaults_to_manual_refresh():
    app = AppTest.from_file("tests/fixtures/ops_refresh_control_app.py", default_timeout=10)
    app.run()

    assert not app.exception
    assert app.radio[0].label == "새로고침 방식"
    assert app.radio[0].value == "수동"
    assert app.session_state["ops_refresh_mode"] == "수동"
    assert app.button[0].label == "수동 새로고침"


def test_network_traffic_chart_uses_smooth_curves():
    history = pd.DataFrame(
        [
            {"time": "2026-07-15T09:00:00", "Inbound Mbps": 1.2, "Outbound Mbps": 0.4},
            {"time": "2026-07-15T09:00:05", "Inbound Mbps": 2.1, "Outbound Mbps": 0.8},
            {"time": "2026-07-15T09:00:10", "Inbound Mbps": 1.7, "Outbound Mbps": 0.6},
        ]
    )

    spec = build_network_traffic_chart(history).to_dict()

    assert spec["layer"][0]["mark"]["type"] == "area"
    assert spec["layer"][0]["mark"]["interpolate"] == "monotone"
    assert spec["layer"][1]["mark"]["type"] == "line"
    assert spec["layer"][1]["mark"]["interpolate"] == "monotone"
    assert "params" not in spec


def test_network_history_calculates_rate_and_ignores_cached_duplicate(monkeypatch):
    state = SessionState()
    monkeypatch.setattr(ops_monitoring.st, "session_state", state)

    update_network_traffic_history(
        {"sampled_at": 100.0, "total_received_bytes": 1_000_000, "total_sent_bytes": 500_000}
    )
    rates = update_network_traffic_history(
        {"sampled_at": 101.0, "total_received_bytes": 2_000_000, "total_sent_bytes": 750_000}
    )
    duplicate_rates = update_network_traffic_history(
        {"sampled_at": 101.0, "total_received_bytes": 2_000_000, "total_sent_bytes": 750_000}
    )

    assert rates == {"inbound_mbps": 8.0, "outbound_mbps": 2.0}
    assert duplicate_rates == rates
    assert len(state.ops_network_history) == 2


def test_ops_request_metrics_do_not_mix_testcase_and_k6_fallbacks(monkeypatch):
    ops_monitoring.collect_ops_snapshot.clear()
    monkeypatch.setattr(ops_monitoring.PrometheusClient, "is_available", lambda self: False)
    monkeypatch.setattr(
        ops_monitoring,
        "load_evaluation_summary",
        lambda: {"case_count": 30, "failed_count": 7},
    )
    monkeypatch.setattr(
        ops_monitoring,
        "load_k6_summary",
        lambda: {
            "total_requests": 1591,
            "avg_duration_seconds": 0.029,
            "p95_duration_seconds": 0.071,
        },
    )
    monkeypatch.setattr(ops_monitoring, "build_feature_statuses", lambda *args: [])

    snapshot = ops_monitoring.collect_ops_snapshot()

    assert snapshot["request_metrics_available"] is False
    assert snapshot["total_requests"] is None
    assert snapshot["error_requests"] is None
    assert snapshot["avg_latency"] is None
    assert snapshot["p95_latency"] is None
    assert snapshot["k6_summary"]["total_requests"] == 1591
    ops_monitoring.collect_ops_snapshot.clear()


def test_k6_summary_keeps_run_identity_separate_from_ops_metrics():
    summary = ops_monitoring.normalize_k6_summary(
        {
            "run_id": "20260715_112430",
            "created_at": "2026-07-15T11:24:30",
            "settings": {"target_url": "http://localhost:8000/health"},
            "metrics": {
                "http_reqs": {"count": 100, "rate": 10},
                "http_req_duration": {"avg": 20, "p(95)": 50},
            },
        }
    )

    assert summary["run_id"] == "20260715_112430"
    assert summary["target_url"] == "http://localhost:8000/health"
    assert summary["total_requests"] == 100


def test_ops_request_panel_labels_source_and_keeps_k6_separate():
    app = AppTest.from_file("tests/fixtures/ops_request_metrics_app.py", default_timeout=10)

    app.run()

    assert not app.exception
    assert any("FastAPI 운영 요청" in heading.value for heading in app.markdown)
    assert any("최신 k6 결과나 테스트케이스" in caption.value for caption in app.caption)
    assert any("테스트케이스 평가 건수와 k6 결과를 섞어" in warning.value for warning in app.warning)
    assert any("Run ID: 20260715_112430" in caption.value for caption in app.caption)
    metric_markup = "\n".join(item.value for item in app.markdown if "ops-metric-grid" in item.value)
    assert "--ops-cols:6" in metric_markup
    assert all(label in metric_markup for label in ["총 요청 수", "성공 요청 수", "오류 요청 수", "오류율", "평균 응답시간", "p95 응답시간"])
    assert metric_markup.count("<strong>-</strong>") >= 6


def test_ops_visual_cards_use_inline_svg_and_equal_width_grid():
    assert "<svg" in ops_monitoring._ops_svg_icon("network")
    assert "<circle" in ops_monitoring._ops_svg_icon("network")
    assert ops_monitoring._ops_status_tone("정상") == "good"
    assert ops_monitoring._ops_status_tone("비정상") == "bad"


def test_feature_status_cards_fill_width_and_use_service_icons(monkeypatch):
    rendered = []
    monkeypatch.setattr(
        ops_monitoring.st,
        "markdown",
        lambda body, **kwargs: rendered.append(body),
    )
    statuses = [
        {"name": "Grafana", "status": "정상", "level": "ok"},
        {"name": "Prometheus", "status": "정상", "level": "ok"},
        {"name": "ChromaDB", "status": "정상", "level": "ok"},
        {"name": "Test수행", "status": "정상", "level": "ok"},
        {"name": "FastAPI /metrics", "status": "정상", "level": "ok"},
        {"name": "FastAPI /health", "status": "정상", "level": "ok"},
    ]

    ops_monitoring.render_major_feature_status({"feature_statuses": statuses})

    markup = "\n".join(rendered)
    assert "--ops-status-cols:6" in markup
    assert markup.count('<span class="ops-status-service-icon">') == 6
    assert all(name in markup for name in ["Grafana", "Prometheus", "ChromaDB", "Test수행", "FastAPI /metrics", "FastAPI /health"])


def test_network_port_icons_distinguish_up_down_and_hang():
    assert ops_monitoring._adapter_level("Up") == "up"
    assert ops_monitoring._adapter_level("Disconnected") == "down"
    assert ops_monitoring._adapter_level("Unknown") == "hang"
    assert ops_monitoring._adapter_status_label("Unknown") == "Hang"
    assert all("<svg" in ops_monitoring._ethernet_port_svg(level) for level in ["up", "down", "hang"])
