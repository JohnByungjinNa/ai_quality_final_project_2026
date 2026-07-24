import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALERTING_DIR = PROJECT_ROOT / "docker" / "grafana" / "provisioning" / "alerting"


def _load(name):
    return json.loads((ALERTING_DIR / name).read_text(encoding="utf-8"))


def test_alert_rules_have_stable_ids_thresholds_and_runbooks():
    document = _load("alert-rules.json")
    rules = document["groups"][0]["rules"]

    assert document["apiVersion"] == 1
    assert len(rules) == 8
    assert len({rule["uid"] for rule in rules}) == len(rules)
    assert all(len(rule["uid"]) <= 40 for rule in rules)
    assert all(rule["annotations"].get("runbook_url") for rule in rules)
    assert all(rule["annotations"].get("runbook_id") for rule in rules)
    assert all(rule["labels"]["service"] == "ai-quality-chatbot" for rule in rules)
    assert all(rule["data"][0]["datasourceUid"] == "prometheus" for rule in rules)

    expressions = {rule["uid"]: rule["data"][0]["model"]["expr"] for rule in rules}
    assert expressions["qa_observer_down"] == "qa_observer_up"
    assert "safety.violations" in expressions["qa_safety_violation"]
    assert "api.service_errors" in expressions["qa_api_error_rate"]
    assert "agent_response_seconds_bucket" in expressions["qa_api_p95_latency"]
    assert "test.pass_count" in expressions["qa_test_pass_rate"]
    assert "rag.no_result" in expressions["qa_rag_no_result"]
    assert "llm.cost_micros_krw" in expressions["qa_llm_budget_critical"]


def test_internal_contact_point_and_policy_are_local_only():
    contact = _load("contact-points.json")["contactPoints"][0]
    receiver = contact["receivers"][0]
    policy = _load("notification-policies.json")["policies"][0]

    assert contact["name"] == "qa-observer-local"
    assert receiver["type"] == "webhook"
    assert receiver["disableResolveMessage"] is False
    assert receiver["settings"]["url"] == "http://qa-observer:8010/v1/alerts/grafana"
    assert receiver["settings"]["authorization_scheme"] == "Bearer"
    assert receiver["settings"]["authorization_credentials"].startswith("$")
    assert policy["receiver"] == contact["name"]
    assert policy["group_by"] == ["alertname", "service", "severity"]


def test_prometheus_datasource_has_uid_used_by_rules():
    datasource = (
        PROJECT_ROOT / "docker" / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    ).read_text(encoding="utf-8")
    assert "uid: prometheus" in datasource
