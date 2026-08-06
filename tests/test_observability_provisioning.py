import json
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_three_separate_grafana_dashboards_are_provisioned():
    dashboard_dir = PROJECT_ROOT / "docker" / "grafana" / "provisioning" / "dashboards" / "json"
    dashboards = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(dashboard_dir.glob("*.json"))]

    assert {dashboard["uid"] for dashboard in dashboards} == {
        "ai-qa-slo",
        "ai-qa-agent-pipeline",
        "ai-qa-audit-finops",
    }
    assert all(dashboard.get("panels") for dashboard in dashboards)


def test_observability_stack_is_isolated_and_declares_all_requested_components():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    rules = (PROJECT_ROOT / "docker" / "prometheus" / "rules" / "ai-qa-recording-rules.yml").read_text(encoding="utf-8")
    navigation = (PROJECT_ROOT / "dashboard" / "navigation.py").read_text(encoding="utf-8")

    assert "blackbox-exporter:" in compose
    assert "tempo:" in compose
    assert "qa:error_budget_api:remaining_ratio" in rules
    assert "qa:agent_rpc_duration_seconds:p95_5m" in rules
    assert "qa:llm_cost_per_quality_pass_krw:today" in rules
    assert '"관측성"' in navigation
    assert "SLO·Error Budget" in navigation
    assert "Agent Pipeline" in navigation
    assert "Drift·FinOps" in navigation


def test_separate_observability_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/observability_app.py", default_timeout=10)
    app.run()

    assert not app.exception
    assert app.title[0].value == "AI QA 관측성 센터"
    assert {metric.label for metric in app.metric} >= {
        "API 가용성",
        "5초 이내 응답",
        "테스트 통과",
        "품질 PASS",
    }
