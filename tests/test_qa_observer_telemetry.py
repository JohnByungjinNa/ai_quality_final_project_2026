import json
from types import SimpleNamespace

import judge_agent
import knowledge_base
from dashboard.services import pipeline_runner
from qa_observer.pricing import calculate_krw_cost
from qa_observer.collectors.outbox import OutboxCollector
from qa_observer.settings import ObserverSettings, PROJECT_ROOT
from qa_observer.storage import FileEventStore
from qa_observer.telemetry import content_fingerprint, emit, emit_event, make_event
from qa_observer.validation import EventContract


CONTRACT_PATH = PROJECT_ROOT / "contracts" / "qa_observer" / "event-envelope-v1.schema.json"


def _settings(tmp_path):
    return ObserverSettings(
        data_dir=tmp_path / "observer",
        log_dir=tmp_path / "logs",
        reports_dir=tmp_path / "reports",
        contract_path=CONTRACT_PATH,
        sync_interval_seconds=3600,
    )


def test_fingerprint_requires_key_and_never_contains_source(monkeypatch):
    monkeypatch.delenv("QA_OBSERVER_HMAC_KEY", raising=False)
    assert content_fingerprint("private question") is None

    monkeypatch.setenv("QA_OBSERVER_HMAC_KEY", "test-only-secret")
    fingerprint = content_fingerprint("private question")
    assert fingerprint.startswith("hmac-sha256:v1:")
    assert "private question" not in fingerprint


def test_forbidden_raw_payload_is_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("QA_OBSERVER_DATA_DIR", str(tmp_path))
    event = make_event(
        "api.request.completed",
        {
            "method": "POST",
            "route_template": "/ask",
            "status_code": 200,
            "duration_ms": 1,
            "timeout": False,
            "error_type": None,
            "question": "must not be persisted",
        },
        "test",
    )

    assert emit_event(event)["status"] == "dropped"
    assert not list(tmp_path.rglob("*.jsonl"))


def test_outbox_fallback_is_validated_and_collected(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setenv("QA_OBSERVER_DATA_DIR", str(settings.data_dir))
    monkeypatch.delenv("QA_OBSERVER_URL", raising=False)
    result = emit(
        "rag.search.completed",
        {
            "query_fingerprint": None,
            "query_chars": 12,
            "top_k": 3,
            "result_count": 0,
            "no_result": True,
            "duration_ms": 2,
            "expected_document_fingerprint": None,
            "top_k_hit": None,
            "results": [],
        },
        "test",
    )
    assert result["status"] == "queued"

    contract = EventContract(CONTRACT_PATH)
    store = FileEventStore(settings)
    store.initialize()
    collected = OutboxCollector(settings, contract, store).sync()

    assert collected["processed"] == 1
    assert collected["errors"] == []
    event_files = list((settings.data_dir / "events" / "rag_search_completed").glob("*.jsonl"))
    stored = json.loads(event_files[0].read_text(encoding="utf-8"))["event"]
    assert stored["payload"]["query_chars"] == 12


def test_judge_usage_event_uses_provider_usage_not_character_estimate(monkeypatch):
    captured = []
    monkeypatch.setattr(judge_agent, "emit", lambda *args, **kwargs: captured.append((args, kwargs)))
    completion = SimpleNamespace(
        model="gpt-test",
        usage=SimpleNamespace(
            prompt_tokens=101,
            completion_tokens=22,
            total_tokens=123,
            prompt_tokens_details=SimpleNamespace(cached_tokens=40),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=7),
        ),
    )

    judge_agent._emit_llm_usage("prompt", completion, 0, "success", response_text="result")

    payload = captured[0][0][1]
    assert payload["input_tokens"] == 101
    assert payload["output_tokens"] == 22
    assert payload["cached_input_tokens"] == 40
    assert payload["reasoning_tokens"] == 7
    assert payload["total_tokens"] == 123
    assert "prompt" not in payload


def test_rag_and_quality_events_exclude_raw_content(monkeypatch):
    captured = []
    monkeypatch.setattr(knowledge_base, "emit", lambda *args, **kwargs: captured.append(args))
    monkeypatch.setattr(pipeline_runner, "emit", lambda *args, **kwargs: captured.append(args))

    knowledge_base._emit_rag_search(
        "secret question",
        3,
        [{"filename": "policy.txt", "chunk_index": 1, "score": 4}],
        0,
    )
    pipeline_runner._emit_quality_result(
        "llm_judge",
        {
            "overall_decision": "FAIL",
            "accuracy": {"score": 4, "evaluated": True},
            "groundedness": {"score": 3, "evaluated": True},
            "helpfulness": {"score": 3, "evaluated": True},
            "safety": {"score": 1, "evaluated": True},
            "comment": "raw comment",
        },
        "secret answer",
    )

    serialized = json.dumps(captured, ensure_ascii=False)
    assert "secret question" not in serialized
    assert "secret answer" not in serialized
    assert "raw comment" not in serialized
    assert [item[0] for item in captured] == [
        "rag.search.completed",
        "quality.evaluation.completed",
        "safety.violation.detected",
    ]


def test_official_price_snapshot_calculates_micro_krw_with_explicit_exchange_rate(monkeypatch):
    monkeypatch.setenv("QA_OBSERVER_USD_KRW", "1400")

    result = calculate_krw_cost("gpt-4o-mini", 100, 23, 20)

    assert result["priced"] is True
    assert result["input_cost_micros_krw"] == 18900
    assert result["output_cost_micros_krw"] == 19320
    assert result["total_cost_micros_krw"] == 38220
    assert "usdkrw-1400" in result["price_snapshot_id"]
