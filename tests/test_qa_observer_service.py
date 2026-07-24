import csv
import json
import time
from dataclasses import replace
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from qa_observer.app import create_app
from qa_observer.settings import PROJECT_ROOT, ObserverSettings
from qa_observer.storage import EventConflictError, FileEventStore


CONTRACT_PATH = PROJECT_ROOT / "contracts" / "qa_observer" / "event-envelope-v1.schema.json"


def _settings(tmp_path, **overrides):
    base = ObserverSettings(
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports" / "test_runs",
        contract_path=CONTRACT_PATH,
        environment="local",
        service_name="qa-observer-test",
        target_service="chatbot-test",
        sync_interval_seconds=3600,
        event_retention_days=90,
        collector_retention_days=30,
        quality_retention_days=365,
        defect_retention_days=730,
        aggregate_retention_days=730,
    )
    return replace(base, **overrides)


def _api_event(event_id="00000000-0000-4000-8000-000000000001", dedup_key="dedup-key-api-0001"):
    return {
        "event_id": event_id,
        "event_type": "api.request.completed",
        "schema_version": 1,
        "occurred_at": "2026-07-14T00:00:00Z",
        "source": {"component": "api", "instance": None},
        "context": {
            "environment": "local",
            "service": "chatbot-test",
            "trace_id": "0" * 32,
            "run_id": None,
            "case_id": None,
        },
        "dedup_key": dedup_key,
        "payload": {
            "method": "GET",
            "route_template": "/ask",
            "status_code": 503,
            "duration_ms": 120,
            "timeout": False,
            "error_type": "upstream_unavailable",
        },
    }


def _llm_event():
    return {
        "event_id": "00000000-0000-4000-8000-000000000101",
        "event_type": "llm.call.completed",
        "schema_version": 1,
        "occurred_at": "2026-07-14T00:01:00Z",
        "source": {"component": "judge-agent", "instance": None},
        "context": {
            "environment": "local",
            "service": "chatbot-test",
            "trace_id": "1" * 32,
            "run_id": "RUN-QUERY",
            "case_id": "TC-001",
        },
        "dedup_key": "dedup-key-llm-query-0101",
        "payload": {
            "provider": "openai",
            "model": "gpt-test",
            "operation": "quality_judge",
            "status": "success",
            "input_tokens": 100,
            "output_tokens": 23,
            "cached_input_tokens": 20,
            "reasoning_tokens": 3,
            "total_tokens": 123,
            "duration_ms": 450,
            "prompt_fingerprint": None,
            "prompt_chars": 50,
            "response_fingerprint": None,
            "response_chars": 30,
            "price_snapshot_id": None,
            "input_cost_micros_krw": None,
            "output_cost_micros_krw": None,
            "total_cost_micros_krw": None,
            "error_type": None,
        },
    }


def _write_test_report(settings):
    run_dir = settings.reports_dir / "RUN-20260714090000"
    (run_dir / "reports").mkdir(parents=True)
    manifest = {
        "id": run_dir.name,
        "started_at": "2026-07-14 09:00:00",
        "ended_at": "2026-07-14 09:00:02",
        "duration_seconds": 2.0,
        "test_case_count": 3,
        "quality_criteria": {"stage": "advanced", "pass_min_score": 4},
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "dashboard_snapshot.json").write_text(
        json.dumps({"final": {"api_pass_count": 2, "total_cases": 3}}), encoding="utf-8"
    )
    (run_dir / "reports" / "evaluation_result.json").write_text(
        json.dumps(
            [
                {"accuracy": 5, "groundedness": 5, "helpfulness": 5, "safety": 5},
                {"accuracy": 5, "groundedness": 5, "helpfulness": 5, "safety": 5},
                {
                    "accuracy": 0,
                    "groundedness": 0,
                    "helpfulness": 0,
                    "safety": 0,
                    "comment": "평가 실패(오류)",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_file_store_appends_aggregates_and_rebuilds_dedup(tmp_path):
    settings = _settings(tmp_path)
    store = FileEventStore(settings)
    store.initialize()
    event = _api_event()

    first = store.append(event)
    second = store.append(event)
    assert first == {"stored": True, "duplicate": False, "event_id": event["event_id"]}
    assert second["duplicate"] is True

    conflict = _api_event(event_id=event["event_id"], dedup_key="another-dedup-key")
    try:
        store.append(conflict)
        raise AssertionError("conflicting event was accepted")
    except EventConflictError:
        pass

    event_file = settings.data_dir / "events" / "api_request_completed" / "2026-07-14.jsonl"
    assert event_file.exists()
    record = json.loads(event_file.read_text(encoding="utf-8").strip())
    assert record["event"]["payload"]["route_template"] == "/ask"
    assert "prompt" not in record["event"]["payload"]

    with (settings.data_dir / "aggregates" / "daily-aggregates.csv").open(
        "r", encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    metrics = {row["metric"]: row for row in rows}
    assert metrics["api.requests"]["sum_value"] == "1"
    assert metrics["api.service_errors"]["sum_value"] == "1"
    assert metrics["api.duration_ms"]["sum_value"] == "120"

    restarted = FileEventStore(settings)
    restarted.initialize()
    assert restarted.dedup_key_count == 1
    assert restarted.append(event)["duplicate"] is True


def test_service_health_ingest_metrics_and_automatic_report_sync(tmp_path):
    settings = _settings(tmp_path)
    _write_test_report(settings)
    app = create_app(settings)

    with TestClient(app) as client:
        deadline = time.time() + 3
        while time.time() < deadline:
            aggregate = client.get("/v1/aggregates", params={"metric": "test.total_count"}).json()
            if aggregate["count"] == 1:
                break
            time.sleep(0.05)
        assert aggregate["items"][0]["sum_value"] == "3"

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"
        assert health.json()["scheduler"]["running"] is True

        response = client.post("/v1/events", json=_api_event())
        assert response.status_code == 200
        assert response.json()["stored"] is True
        duplicate = client.post("/v1/events", json=_api_event())
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicate"] is True

        invalid = _api_event(
            event_id="00000000-0000-4000-8000-000000000002",
            dedup_key="dedup-key-invalid-0002",
        )
        invalid["payload"]["prompt"] = "must-not-be-stored"
        rejected = client.post("/v1/events", json=invalid)
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "invalid_event"

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert "qa_observer_up 1" in metrics.text
        assert "qa_observer_events_stored_total" in metrics.text
        assert "qa_observer_collector_runs_total" in metrics.text

    checkpoint_path = settings.data_dir / "state" / "collector-checkpoints.json"
    checkpoints = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert "RUN-20260714090000" in checkpoints["test_reports"]["runs"]


def test_retention_uses_event_type_specific_periods(tmp_path):
    settings = _settings(
        tmp_path,
        event_retention_days=2,
        collector_retention_days=1,
        quality_retention_days=10,
    )
    store = FileEventStore(settings)
    store.initialize()
    old_api = settings.data_dir / "events" / "api_request_completed" / "2026-07-01.jsonl"
    old_test = settings.data_dir / "events" / "test_run_completed" / "2026-07-01.jsonl"
    old_api.parent.mkdir(parents=True)
    old_test.parent.mkdir(parents=True)
    old_api.write_text("", encoding="utf-8")
    old_test.write_text("", encoding="utf-8")

    deleted = store.cleanup_retention(today=date(2026, 7, 5))
    assert str(old_api) in deleted
    assert not old_api.exists()
    assert old_test.exists()


def test_dashboard_query_api_and_prometheus_business_metrics(tmp_path):
    settings = _settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.post("/v1/events", json=_api_event()).status_code == 200
        assert client.post("/v1/events", json=_llm_event()).status_code == 200

        summary = client.get(
            "/v1/dashboard/summary",
            params={"date_from": "2026-07-14", "date_to": "2026-07-14", "service": "chatbot-test"},
        )
        assert summary.status_code == 200
        body = summary.json()
        assert body["event_count"] == 2
        assert body["api_p95_duration_ms"] == 120
        assert body["api_error_rate"] == 100
        assert body["llm_total_tokens"] == 123
        assert body["llm_cost_krw"] is None
        assert body["llm_price_coverage"] == 0
        assert body["daily_budget_krw"] == 50000
        assert body["budget_usage_rate"] is None

        timeseries = client.get(
            "/v1/timeseries",
            params={
                "date_from": "2026-07-14",
                "date_to": "2026-07-14",
                "provider": "openai",
                "model": "gpt-test",
                "metric": "llm.total_tokens",
            },
        ).json()
        assert timeseries["count"] == 1
        assert timeseries["items"][0]["sum_value"] == 123
        assert timeseries["items"][0]["average_value"] == 123

        recent = client.get(
            "/v1/events",
            params={
                "date_from": "2026-07-14",
                "date_to": "2026-07-14",
                "event_type": "llm.call.completed",
            },
        ).json()
        assert recent["count"] == 1
        assert recent["items"][0]["event"]["payload"]["total_tokens"] == 123
        assert "prompt" not in recent["items"][0]["event"]["payload"]

        aggregate = client.get(
            "/v1/aggregates",
            params={"provider": "openai", "model": "gpt-test", "metric": "llm.total_tokens"},
        ).json()
        assert aggregate["count"] == 1

        metrics = client.get("/metrics").text
        assert "qa_dashboard_aggregate_value" in metrics
        assert 'metric="llm.total_tokens"' in metrics
        assert "qa_dashboard_data_updated_timestamp_seconds" in metrics

        invalid = client.get(
            "/v1/dashboard/summary",
            params={"date_from": "2026-07-15", "date_to": "2026-07-14"},
        )
        assert invalid.status_code == 422
        assert invalid.json()["detail"]["code"] == "invalid_date_range"


def test_grafana_webhook_auth_dedup_and_defect_lifecycle(tmp_path):
    settings = _settings(tmp_path, grafana_webhook_token="test-token")
    app = create_app(settings)
    firing = {
        "status": "firing",
        "groupKey": "qa-safety",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "Safety Violation Detected",
                    "service": "chatbot-test",
                    "severity": "critical",
                },
                "annotations": {"summary": "sensitive text must not be stored"},
                "startsAt": "2026-07-14T00:10:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "fingerprint": "alert-fingerprint-001",
            }
        ],
    }

    with TestClient(app) as client:
        unauthorized = client.post("/v1/alerts/grafana", json=firing)
        assert unauthorized.status_code == 401

        headers = {"Authorization": "Bearer test-token"}
        accepted = client.post("/v1/alerts/grafana", json=firing, headers=headers)
        assert accepted.status_code == 200
        assert accepted.json() == {"processed": 1, "duplicates": 0, "received": 1}

        duplicate = client.post("/v1/alerts/grafana", json=firing, headers=headers)
        assert duplicate.status_code == 200
        assert duplicate.json()["duplicates"] == 1

        summary = client.get(
            "/v1/dashboard/summary",
            params={"date_from": "2026-07-14", "date_to": "2026-07-14", "service": "chatbot-test"},
        ).json()
        assert summary["open_defect_count"] == 1

        resolved = json.loads(json.dumps(firing))
        resolved["status"] = "resolved"
        resolved["alerts"][0]["status"] = "resolved"
        resolved["alerts"][0]["endsAt"] = "2026-07-14T00:20:00Z"
        closed = client.post("/v1/alerts/grafana", json=resolved, headers=headers)
        assert closed.status_code == 200
        assert closed.json()["processed"] == 1

        summary = client.get(
            "/v1/dashboard/summary",
            params={"date_from": "2026-07-14", "date_to": "2026-07-14", "service": "chatbot-test"},
        ).json()
        assert summary["open_defect_count"] == 0

        events = client.get(
            "/v1/events",
            params={
                "date_from": "2026-07-14",
                "date_to": "2026-07-14",
                "event_type": "defect.changed",
            },
        ).json()["items"]
        assert len(events) == 2
        serialized = json.dumps(events, ensure_ascii=False)
        assert "sensitive text must not be stored" not in serialized
        assert {item["event"]["payload"]["status"] for item in events} == {"open", "resolved"}

        metrics = client.get("/metrics").text
        assert 'qa_observer_grafana_webhook_requests_total{status="accepted"} 3' in metrics
        assert 'qa_observer_grafana_webhook_requests_total{status="unauthorized"} 1' in metrics
