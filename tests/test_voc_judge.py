import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.services import voc_judge_service, voc_quality_service
from dashboard.services.voc_quality_service import load_independent_judge_rubric


def test_judge_controls_render_provider_and_model_selection():
    app = AppTest.from_file("tests/fixtures/voc_judge_controls_app.py", default_timeout=15)
    app.run()
    assert not app.exception
    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert len(app.selectbox) == 1
    assert len(app.text_input) == 1


def _payload(**overrides):
    rubric = load_independent_judge_rubric()
    payload = {
        "dimension_scores": {
            key: {"score": spec["max_points"], "reason": f"{key} 근거 확인"}
            for key, spec in rubric["dimensions"].items()
        },
        "immediate_fail_rules_triggered": [],
        "evidence": ["VOC-1"],
        "risks": [],
        "recommendations": ["운영 검토"],
    }
    payload.update(overrides)
    return payload


def _evaluate(monkeypatch, responses, **kwargs):
    calls = {"count": 0}
    monkeypatch.delenv("A2A_JUDGE_ANTHROPIC_INPUT_KRW_PER_MTOK", raising=False)
    monkeypatch.delenv("A2A_JUDGE_ANTHROPIC_OUTPUT_KRW_PER_MTOK", raising=False)

    def fake_invoke(**_call_kwargs):
        value = responses[min(calls["count"], len(responses) - 1)]
        calls["count"] += 1
        if isinstance(value, Exception):
            raise value
        return value, {"input_tokens": 100, "output_tokens": 50}

    monkeypatch.setattr(voc_judge_service, "_invoke_provider", fake_invoke)
    generator_snapshot = kwargs.pop(
        "generator_snapshot",
        {"policy": {"provider": "anthropic", "model": "claude-sonnet-4-6"}},
    )
    result = voc_judge_service.evaluate_independent_judge(
        case={"case_id": "TC-01", "question": "질문"},
        execution={"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
        trace={"trace_id": "trace-1", "events": []},
        rubric=load_independent_judge_rubric(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        generator_snapshot=generator_snapshot,
        backoff_base_seconds=0,
        **kwargs,
    )
    return result, calls["count"]


def test_judge_calculates_pass_and_does_not_trust_model_total(monkeypatch):
    raw = _payload(total_score=1, decision="FAIL")
    result, calls = _evaluate(
        monkeypatch,
        [json.dumps(raw, ensure_ascii=False)],
        generator_snapshot={"policy": {"provider": "openai", "model": "gpt-generator"}},
    )

    assert calls == 1
    assert result["decision"] == "PASS"
    assert result["total_score"] == 100
    assert result["independence_grade"] == "A"
    assert result["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert result["cost"]["pricing_status"] == "NOT_CONFIGURED"


def test_judge_requires_dimension_pass_floors_for_pass(monkeypatch):
    payload = _payload()
    payload["dimension_scores"]["safety"]["score"] = 11
    result, _ = _evaluate(monkeypatch, [json.dumps(payload, ensure_ascii=False)])

    assert result["total_score"] == 96
    assert result["all_pass_floors_met"] is False
    assert result["decision"] == "REVIEW_REQUIRED"


def test_judge_immediate_fail_rule_overrides_score(monkeypatch):
    payload = _payload(immediate_fail_rules_triggered=["fabricated_voc_evidence"])
    result, _ = _evaluate(monkeypatch, [json.dumps(payload, ensure_ascii=False)])

    assert result["total_score"] == 100
    assert result["decision"] == "FAIL"


def test_judge_malformed_json_is_separate_error(monkeypatch):
    result, calls = _evaluate(monkeypatch, ["not-json"])

    assert calls == 1
    assert result["decision"] == "ERROR"
    assert result["error_type"] == "JSONDecodeError"


def test_judge_retries_429_and_preserves_attempts(monkeypatch):
    result, calls = _evaluate(
        monkeypatch,
        [RuntimeError("HTTP 429 rate limit"), json.dumps(_payload(), ensure_ascii=False)],
        generator_snapshot={"policy": {"provider": "openai", "model": "gpt-generator"}},
    )

    assert calls == 2
    assert result["decision"] == "PASS"
    assert [item["status"] for item in result["attempts"]] == ["ERROR", "SUCCESS"]


def test_judge_independence_c_forces_human_review(monkeypatch):
    result, _ = _evaluate(monkeypatch, [json.dumps(_payload(), ensure_ascii=False)])

    assert result["rubric_decision"] == "PASS"
    assert result["decision"] == "REVIEW_REQUIRED"
    assert result["independence_hold"] is True


def test_judge_timeout_exhaustion_and_authentication_no_retry(monkeypatch):
    timeout, timeout_calls = _evaluate(
        monkeypatch,
        [TimeoutError("request timeout")],
        max_retries=1,
    )
    assert timeout_calls == 2
    assert timeout["decision"] == "ERROR"

    auth, auth_calls = _evaluate(
        monkeypatch,
        [RuntimeError("401 authentication invalid api key")],
        max_retries=2,
    )
    assert auth_calls == 1
    assert auth["error_type"] == "AUTHENTICATION"


def test_independence_grade_distinguishes_provider_and_model():
    generator = {"policy": {"provider": "anthropic", "model": "claude-sonnet-4-6"}}
    assert voc_judge_service.independence_grade("openai", "gpt-5.2", generator)["grade"] == "A"
    assert voc_judge_service.independence_grade("anthropic", "claude-opus", generator)["grade"] == "B"
    assert voc_judge_service.independence_grade("anthropic", "claude-sonnet-4-6", generator)["grade"] == "C"


def test_manual_run_saves_judge_result_and_separate_counts(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    store._ACTIVE_RUN_IDS.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
    )
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {"trace_id": "trace-judge", "events": []},
    )
    monkeypatch.setattr(
        voc_quality_service.voc_judge_service,
        "evaluate_independent_judge",
        lambda **_kwargs: {
            "status": "PASS",
            "decision": "PASS",
            "total_score": 88,
            "dimension_scores": {},
            "provider": "anthropic",
            "model": "judge-model",
            "independence_grade": "B",
            "attempts": [{"attempt": 1, "status": "SUCCESS"}],
        },
    )

    result = voc_quality_service.run_test_case(
        "TC-01",
        judge_config={"enabled": True, "provider": "anthropic", "model": "judge-model"},
    )
    stored = store.load_voc_run(result["run_id"])

    assert result["evidence_status"] == "PASS"
    assert stored["manifest"]["judge_enabled"] is True
    assert stored["summary"]["counts"]["PASS"] == 1
    assert stored["summary"]["judge_counts"]["PASS"] == 1
    case_dir = Path(result["run_dir"]) / "cases" / "TC-01"
    assert (case_dir / "judge_result.json").exists()
    assert store.verify_run_integrity(result["run_id"])["ok"]


def test_disabled_judge_is_not_run_without_changing_pipeline_success(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    store._ACTIVE_RUN_IDS.clear()
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
    )
    monkeypatch.setattr(voc_quality_service, "pipeline_trace_events", lambda *_args: {"trace_id": "t", "events": []})

    result = voc_quality_service.run_test_case("TC-01")
    stored = store.load_voc_run(result["run_id"])

    assert result["evidence_status"] == "REVIEW_REQUIRED"
    assert result["judge_result"]["decision"] == "NOT_RUN"
    assert stored["summary"]["judge_counts"]["NOT_RUN"] == 1


def test_judge_error_does_not_hide_pipeline_success(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    store._ACTIVE_RUN_IDS.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
    )
    monkeypatch.setattr(voc_quality_service, "pipeline_trace_events", lambda *_args: {"trace_id": "t", "events": []})
    monkeypatch.setattr(
        voc_quality_service.voc_judge_service,
        "evaluate_independent_judge",
        lambda **_kwargs: {
            "status": "ERROR",
            "decision": "ERROR",
            "total_score": None,
            "provider": "anthropic",
            "model": "judge-model",
            "independence_grade": "B",
            "error": "malformed JSON",
            "attempts": [],
        },
    )

    result = voc_quality_service.run_test_case(
        "TC-01",
        judge_config={"enabled": True, "provider": "anthropic", "model": "judge-model"},
    )
    stored = store.load_voc_run(result["run_id"])

    assert result["evidence_status"] == "REVIEW_REQUIRED"
    assert stored["summary"]["counts"]["ERROR"] == 0
    assert stored["summary"]["judge_counts"]["ERROR"] == 1


def test_batch_judge_aggregates_voc_and_skips_fault_case(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    store._ACTIVE_RUN_IDS.clear()
    voc_quality_service._ACTIVE_BATCH_SIGNATURES.clear()
    voc_quality_service._BATCH_STOP_EVENTS.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
    )
    monkeypatch.setattr(voc_quality_service, "_run_cmd", lambda *_args, **_kwargs: {"ok": True, "output": "PASS"})
    monkeypatch.setattr(voc_quality_service, "pipeline_trace_events", lambda *_args: {"trace_id": "t", "events": []})
    monkeypatch.setattr(
        voc_quality_service.voc_judge_service,
        "evaluate_independent_judge",
        lambda **_kwargs: {
            "status": "PASS",
            "decision": "PASS",
            "total_score": 90,
            "provider": "anthropic",
            "model": "judge-model",
            "independence_grade": "B",
            "attempts": [],
        },
    )
    config = {"enabled": True, "provider": "anthropic", "model": "judge-model"}
    run = voc_quality_service.start_batch_run(["TC-01", "FT-01"], judge_config=config)
    result = voc_quality_service.execute_batch_run(
        run["run_id"], ["TC-01", "FT-01"], judge_config=config, backoff_base_seconds=0
    )

    assert result["summary"]["counts"]["PASS"] == 1
    assert result["summary"]["counts"]["REVIEW_REQUIRED"] == 1
    assert result["summary"]["judge_counts"]["PASS"] == 1
    assert result["summary"]["judge_counts"]["NOT_RUN"] == 1


def test_saved_pipeline_reevaluation_preserves_previous_judge_result(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    store._ACTIVE_RUN_IDS.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
    )
    monkeypatch.setattr(voc_quality_service, "pipeline_trace_events", lambda *_args: {"trace_id": "t", "events": []})
    original = voc_quality_service.run_test_case("TC-01")
    monkeypatch.setattr(
        voc_quality_service.voc_judge_service,
        "evaluate_independent_judge",
        lambda **_kwargs: {
            "status": "PASS",
            "decision": "PASS",
            "total_score": 91,
            "provider": "anthropic",
            "model": "judge-model",
            "independence_grade": "B",
            "attempts": [],
        },
    )

    reevaluated = voc_quality_service.reevaluate_voc_run_case(
        original["run_id"],
        "TC-01",
        {"enabled": True, "provider": "anthropic", "model": "judge-model"},
    )

    assert reevaluated["judge_result"]["decision"] == "PASS"
    assert reevaluated["judge_result"]["evaluation_history"][0]["decision"] == "NOT_RUN"
    assert reevaluated["summary"]["counts"]["PASS"] == 1
    assert reevaluated["summary"]["judge_counts"]["PASS"] == 1
