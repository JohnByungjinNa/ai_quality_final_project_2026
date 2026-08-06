import json
from types import SimpleNamespace

from qa_observer.collectors.a2a_audit import A2AAuditCollector
from qa_observer.metrics import ObserverMetrics


def test_a2a_jsonl_is_exposed_as_bounded_prometheus_metrics(tmp_path):
    audit_path = tmp_path / "a2a_events.jsonl"
    events = [
        {
            "timestamp": "2026-08-05T01:00:00Z",
            "trace_id": "a" * 32,
            "source": "orchestrator",
            "target": "validity_agent",
            "operation": "evaluate",
            "status": "success",
            "duration_ms": 250,
        },
        {
            "timestamp": "2026-08-05T01:00:01Z",
            "trace_id": "b" * 32,
            "source": "orchestrator",
            "target": "validity_agent",
            "operation": "evaluate",
            "status": "failure",
            "duration_ms": 600,
        },
    ]
    audit_path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")
    metrics = ObserverMetrics()

    result = A2AAuditCollector(SimpleNamespace(a2a_audit_path=audit_path), metrics).sync()
    rendered = metrics.render()

    assert result["processed"] == 2
    assert 'voc_agent_rpc_calls_total{operation="evaluate",source="orchestrator",status="success",target="validity_agent"} 1' in rendered
    assert 'voc_agent_rpc_calls_total{operation="evaluate",source="orchestrator",status="failure",target="validity_agent"} 1' in rendered
    assert 'voc_agent_rpc_duration_seconds_bucket{le="0.25",operation="evaluate"' in rendered
    assert 'voc_agent_traces_total{status="failure"} 1' in rendered


def test_a2a_collector_handles_unconfigured_or_missing_file(tmp_path):
    metrics = ObserverMetrics()
    settings = SimpleNamespace(a2a_audit_path=None, data_dir=tmp_path)

    result = A2AAuditCollector(settings, metrics).sync()

    assert result["processed"] == 0
    assert "voc_agent_audit_file_up 0" in metrics.render()
