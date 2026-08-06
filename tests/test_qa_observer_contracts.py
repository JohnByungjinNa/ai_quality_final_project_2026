import copy
import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "qa_observer" / "event-envelope-v1.schema.json"
SQLITE_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "qa_observer" / "sqlite-v1.sql"


def _base_event():
    return {
        "event_id": "00000000-0000-4000-8000-000000000001",
        "schema_version": 1,
        "occurred_at": "2026-07-14T00:00:00Z",
        "source": {"component": "contract-test", "instance": None},
        "context": {
            "environment": "local",
            "service": "chatbot",
            "trace_id": "0" * 32,
            "run_id": "RUN-1",
            "case_id": "TC-1",
        },
        "dedup_key": "contract-test-key-0001",
    }


def _payloads():
    fingerprint = "hmac-sha256:v1:" + "a" * 64
    return {
        "api.request.completed": {
            "method": "GET",
            "route_template": "/ask",
            "status_code": 200,
            "duration_ms": 20,
            "timeout": False,
            "error_type": None,
        },
        "llm.call.completed": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "operation": "judge",
            "status": "success",
            "input_tokens": 10,
            "output_tokens": 5,
            "cached_input_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 15,
            "duration_ms": 100,
            "prompt_fingerprint": fingerprint,
            "prompt_chars": 40,
            "response_fingerprint": fingerprint,
            "response_chars": 20,
            "price_snapshot_id": None,
            "input_cost_micros_krw": 1,
            "output_cost_micros_krw": 1,
            "total_cost_micros_krw": 2,
            "error_type": None,
        },
        "rag.search.completed": {
            "query_fingerprint": fingerprint,
            "query_chars": 10,
            "top_k": 3,
            "result_count": 1,
            "no_result": False,
            "duration_ms": 5,
            "expected_document_fingerprint": None,
            "top_k_hit": None,
            "results": [
                {
                    "rank": 1,
                    "document_fingerprint": fingerprint,
                    "chunk_fingerprint": fingerprint,
                    "score": 2.0,
                }
            ],
        },
        "quality.evaluation.completed": {
            "evaluation_id": "EVAL-1",
            "evaluator_type": "llm_judge",
            "overall_decision": "PASS",
            "summary_code": None,
            "safety_violation_severity": None,
            "scores": {"accuracy": {"evaluated": True, "score": 5}},
        },
        "test.run.completed": {
            "started_at": "2026-07-14T00:00:00Z",
            "ended_at": "2026-07-14T00:00:01Z",
            "duration_ms": 1000,
            "criteria_stage": "advanced",
            "pass_count": 1,
            "fail_count": 0,
            "error_count": 0,
            "total_count": 1,
            "source_manifest_path": None,
        },
        "safety.violation.detected": {
            "category": "pii",
            "severity": "high",
            "action": "blocked",
            "blocked": True,
            "content_fingerprint": fingerprint,
            "policy_version": "v1",
        },
        "defect.changed": {
            "defect_id": "DEF-1",
            "action": "opened",
            "defect_type": "quality",
            "severity": "high",
            "status": "open",
            "summary_code": "LOW_GROUNDEDNESS",
            "external_system": None,
            "external_issue_key": None,
        },
        "evidence.upload.completed": {
            "status": "success",
            "uploaded": True,
            "verified": True,
            "duration_ms": 123,
            "file_count": 3,
            "bytes_total": 4096,
            "error_type": None,
        },
        "collector.sync.completed": {
            "source_name": "test_reports",
            "status": "success",
            "items_processed": 1,
            "checkpoint": "RUN-1",
            "error_type": None,
        },
    }


def test_event_schema_accepts_all_v1_types_and_rejects_raw_prompt():
    schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    for index, (event_type, payload) in enumerate(_payloads().items(), start=1):
        event = _base_event()
        event["event_id"] = f"00000000-0000-4000-8000-{index:012d}"
        event["dedup_key"] = f"contract-test-key-{index:04d}"
        event["event_type"] = event_type
        event["payload"] = payload
        validator.validate(event)

    invalid = _base_event()
    invalid["event_type"] = "llm.call.completed"
    invalid["payload"] = copy.deepcopy(_payloads()["llm.call.completed"])
    invalid["payload"]["prompt"] = "must-not-be-stored"
    assert list(validator.iter_errors(invalid))


def test_sqlite_v1_schema_and_constraints():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SQLITE_SCHEMA_PATH.read_text(encoding="utf-8"))

    required_tables = {
        "events",
        "api_request_events",
        "llm_price_snapshots",
        "llm_usage_events",
        "rag_search_events",
        "rag_search_results",
        "test_runs",
        "test_case_results",
        "quality_evaluations",
        "quality_metric_scores",
        "safety_violations",
        "defects",
        "collector_checkpoints",
        "retention_policies",
        "schema_migrations",
    }
    actual_tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert required_tables <= actual_tables
    assert connection.execute("SELECT COUNT(*) FROM retention_policies").fetchone()[0] == 7
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    event_values = (
        "00000000-0000-4000-8000-000000000001",
        "quality.evaluation.completed",
        1,
        "2026-07-14T00:00:00Z",
        "2026-07-14T00:00:01Z",
        "local",
        "chatbot-api",
        "judge_agent",
        "0" * 32,
        "RUN-1",
        "TC-1",
        "dedup-key-0000000001",
        "{}",
    )
    connection.execute(
        """
        INSERT INTO events (
            event_id,event_type,schema_version,occurred_at_utc,received_at_utc,
            environment,service,source_component,trace_id,run_id,case_id,
            dedup_key,payload_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        event_values,
    )
    connection.execute(
        """
        INSERT INTO quality_evaluations (
            evaluation_id,event_id,run_id,case_id,evaluator_type,overall_decision
        ) VALUES ('EVAL-1', ?, 'RUN-1', 'TC-1', 'llm_judge', 'PASS')
        """,
        (event_values[0],),
    )
    connection.execute(
        "INSERT INTO quality_metric_scores VALUES ('EVAL-1','accuracy',5,1,5,1)"
    )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO events (
                event_id,event_type,schema_version,occurred_at_utc,received_at_utc,
                environment,service,source_component,dedup_key,payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "00000000-0000-4000-8000-000000000002",
                "api.request.completed",
                1,
                "2026-07-14T00:00:00Z",
                "2026-07-14T00:00:01Z",
                "local",
                "api",
                "api",
                "dedup-key-0000000001",
                "{}",
            ),
        )

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO quality_metric_scores VALUES ('EVAL-1','safety',6,1,5,1)"
        )
