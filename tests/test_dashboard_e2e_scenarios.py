import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard.services.overview_dashboard import build_overview
from qa_observer.app import create_app
from qa_observer.settings import PROJECT_ROOT, ObserverSettings


CONTRACT_PATH = PROJECT_ROOT / "contracts" / "qa_observer" / "event-envelope-v1.schema.json"
ALERT_RULES_PATH = (
    PROJECT_ROOT / "docker" / "grafana" / "provisioning" / "alerting" / "alert-rules.json"
)
FINGERPRINT = "hmac-sha256:v1:" + "a" * 64


def _settings(tmp_path):
    return ObserverSettings(
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
        contract_path=CONTRACT_PATH,
        environment="local",
        service_name="qa-observer-acceptance",
        target_service="chatbot-test",
        sync_interval_seconds=3600,
        grafana_webhook_token="acceptance-token",
    )


def _event(index, event_type, payload):
    return {
        "event_id": f"00000000-0000-4000-8000-{index:012d}",
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": f"2026-07-14T00:{index:02d}:00Z",
        "source": {"component": "acceptance-scenario", "instance": None},
        "context": {
            "environment": "local",
            "service": "chatbot-test",
            "trace_id": f"{index:032x}",
            "run_id": f"RUN-E2E-{index:02d}",
            "case_id": f"TC-E2E-{index:02d}",
        },
        "dedup_key": f"dashboard-e2e-scenario-{index:04d}",
        "payload": payload,
    }


def _api(duration_ms=100, status_code=200):
    return {
        "method": "POST",
        "route_template": "/ask",
        "status_code": status_code,
        "duration_ms": duration_ms,
        "timeout": False,
        "error_type": None if status_code < 500 else "scenario_error",
    }


def _llm(cost_micros_krw=10_000_000_000):
    return {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "operation": "quality_judge",
        "status": "success",
        "input_tokens": 100,
        "output_tokens": 20,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "total_tokens": 120,
        "duration_ms": 300,
        "prompt_fingerprint": FINGERPRINT,
        "prompt_chars": 100,
        "response_fingerprint": FINGERPRINT,
        "response_chars": 50,
        "price_snapshot_id": "acceptance-price",
        "input_cost_micros_krw": cost_micros_krw,
        "output_cost_micros_krw": 0,
        "total_cost_micros_krw": cost_micros_krw,
        "error_type": None,
    }


def _rag(no_result=False):
    results = [] if no_result else [
        {
            "rank": 1,
            "document_fingerprint": FINGERPRINT,
            "chunk_fingerprint": FINGERPRINT,
            "score": 2.0,
        }
    ]
    return {
        "query_fingerprint": FINGERPRINT,
        "query_chars": 20,
        "top_k": 3,
        "result_count": len(results),
        "no_result": no_result,
        "duration_ms": 40,
        "expected_document_fingerprint": None,
        "top_k_hit": None,
        "results": results,
    }


def _quality():
    return {
        "evaluation_id": "EVAL-E2E-NORMAL",
        "evaluator_type": "llm_judge",
        "overall_decision": "PASS",
        "summary_code": None,
        "safety_violation_severity": None,
        "scores": {
            name: {"evaluated": True, "score": 5}
            for name in ("accuracy", "groundedness", "helpfulness", "safety")
        },
    }


def _test_run():
    return {
        "started_at": "2026-07-14T00:00:00Z",
        "ended_at": "2026-07-14T00:00:01Z",
        "duration_ms": 1000,
        "criteria_stage": "advanced",
        "pass_count": 10,
        "fail_count": 0,
        "error_count": 0,
        "total_count": 10,
        "source_manifest_path": None,
    }


def _safety():
    return {
        "category": "pii",
        "severity": "high",
        "action": "blocked",
        "blocked": True,
        "content_fingerprint": FINGERPRINT,
        "policy_version": "v1",
    }


SCENARIOS = {
    "api_error": {
        "events": [("api.request.completed", _api(status_code=503))],
        "level": "danger",
        "metric": "api.service_errors",
        "rule_uid": "qa_api_error_rate",
        "action_text": "API 5xx",
    },
    "latency": {
        "events": [("api.request.completed", _api(duration_ms=6001))],
        "level": "warning",
        "metric": "api.duration_ms",
        "rule_uid": "qa_api_p95_latency",
        "action_text": "지연",
    },
    "cost_overrun": {
        "events": [("llm.call.completed", _llm(cost_micros_krw=50_000_000_001))],
        "level": "danger",
        "metric": "llm.cost_micros_krw",
        "rule_uid": "qa_llm_budget_critical",
        "action_text": "토큰",
    },
    "rag_failure": {
        "events": [("rag.search.completed", _rag(no_result=True))],
        "level": "warning",
        "metric": "rag.no_result",
        "rule_uid": "qa_rag_no_result",
        "action_text": "No-result",
    },
    "safety_violation": {
        "events": [("safety.violation.detected", _safety())],
        "level": "danger",
        "metric": "safety.violations",
        "rule_uid": "qa_safety_violation",
        "action_text": "안전성",
    },
}


def _summary(client):
    response = client.get(
        "/v1/dashboard/summary",
        params={"date_from": "2026-07-14", "date_to": "2026-07-14", "service": "chatbot-test"},
    )
    assert response.status_code == 200
    return response.json()


def _alert_payload(rule_uid, status, ends_at):
    return {
        "status": status,
        "groupKey": rule_uid,
        "alerts": [
            {
                "status": status,
                "labels": {
                    "alertname": rule_uid,
                    "service": "chatbot-test",
                    "severity": "critical" if "critical" in rule_uid or "safety" in rule_uid else "warning",
                },
                "annotations": {"summary": "must-not-be-copied-to-event-storage"},
                "startsAt": "2026-07-14T01:00:00Z",
                "endsAt": ends_at,
                "fingerprint": f"fingerprint-{rule_uid}",
            }
        ],
    }


def test_normal_scenario_reaches_normal_dashboard_without_open_defects(tmp_path):
    settings = _settings(tmp_path)
    events = [
        ("api.request.completed", _api()),
        ("llm.call.completed", _llm()),
        ("rag.search.completed", _rag()),
        ("quality.evaluation.completed", _quality()),
        ("test.run.completed", _test_run()),
    ]

    with TestClient(create_app(settings)) as client:
        for index, (event_type, payload) in enumerate(events, start=1):
            assert client.post("/v1/events", json=_event(index, event_type, payload)).status_code == 200

        summary = _summary(client)
        timeseries = client.get(
            "/v1/timeseries", params={"date_from": "2026-07-14", "date_to": "2026-07-14"}
        ).json()["items"]
        recent = client.get(
            "/v1/events", params={"date_from": "2026-07-14", "date_to": "2026-07-14"}
        ).json()["items"]
        view = build_overview(summary, timeseries, recent)

        assert summary["quality_score"] == 100
        assert summary["test_pass_rate"] == 100
        assert summary["budget_usage_rate"] == 20
        assert summary["rag_no_result_rate"] == 0
        assert summary["open_defect_count"] == 0
        assert view["status"]["level"] == "normal"
        assert view["actions"] == ["현재 즉시 필요한 조치가 없습니다. 수집 신선도를 지속 확인합니다."]


@pytest.mark.parametrize("scenario_name", sorted(SCENARIOS))
def test_abnormal_scenario_reaches_dashboard_alert_and_resolved_defect(tmp_path, scenario_name):
    scenario = SCENARIOS[scenario_name]
    settings = _settings(tmp_path)
    rule_uids = {
        rule["uid"]
        for rule in json.loads(ALERT_RULES_PATH.read_text(encoding="utf-8"))["groups"][0]["rules"]
    }
    assert scenario["rule_uid"] in rule_uids

    with TestClient(create_app(settings)) as client:
        for index, (event_type, payload) in enumerate(scenario["events"], start=1):
            assert client.post("/v1/events", json=_event(index, event_type, payload)).status_code == 200

        summary = _summary(client)
        timeseries = client.get(
            "/v1/timeseries", params={"date_from": "2026-07-14", "date_to": "2026-07-14"}
        ).json()["items"]
        recent = client.get(
            "/v1/events", params={"date_from": "2026-07-14", "date_to": "2026-07-14"}
        ).json()["items"]
        view = build_overview(summary, timeseries, recent)

        assert view["status"]["level"] == scenario["level"]
        assert any(scenario["action_text"] in action for action in view["actions"])
        assert f'metric="{scenario["metric"]}"' in client.get("/metrics").text

        headers = {"Authorization": "Bearer acceptance-token"}
        firing = _alert_payload(scenario["rule_uid"], "firing", "0001-01-01T00:00:00Z")
        accepted = client.post("/v1/alerts/grafana", json=firing, headers=headers)
        assert accepted.status_code == 200
        assert accepted.json()["processed"] == 1
        assert _summary(client)["open_defect_count"] == 1

        resolved = _alert_payload(scenario["rule_uid"], "resolved", "2026-07-14T01:10:00Z")
        closed = client.post("/v1/alerts/grafana", json=resolved, headers=headers)
        assert closed.status_code == 200
        assert closed.json()["processed"] == 1
        assert _summary(client)["open_defect_count"] == 0

        stored = json.dumps(
            client.get(
                "/v1/events",
                params={
                    "date_from": "2026-07-14",
                    "date_to": "2026-07-14",
                    "event_type": "defect.changed",
                },
            ).json(),
            ensure_ascii=False,
        )
        assert "must-not-be-copied-to-event-storage" not in stored
