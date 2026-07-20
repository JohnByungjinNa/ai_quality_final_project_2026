import json

import pytest
from streamlit.testing.v1 import AppTest

from dashboard.pages_top import voc_quality_view
from dashboard.services import voc_quality_service, voc_validity_service


def _validity_payload(rubric, *, holds=None):
    return {
        "dimension_scores": {
            key: {"score": spec["max_points"], "reason": f"{key} 근거 확인"}
            for key, spec in rubric["dimensions"].items()
        },
        "immediate_hold_rules_triggered": holds or [],
        "evidence": ["VOC와 Trace 확인"],
        "risks": [],
        "recommendations": ["QA 검토"],
    }


def _create_completed_case(monkeypatch, tmp_path):
    store = voc_quality_service.voc_run_store
    monkeypatch.setattr(store, "VOC_QUALITY_RUNS_DIR", tmp_path / "runs")
    store._ACTIVE_RUN_IDS.clear()
    monkeypatch.setattr(
        voc_quality_service,
        "run_voc_analysis",
        lambda *_args, **_kwargs: {
            "ok": True,
            "result": {"ok": True, "summary": "VOC 근거 요약", "policy": "담당·일정·KPI가 있는 개선안"},
        },
    )
    monkeypatch.setattr(
        voc_quality_service,
        "pipeline_trace_events",
        lambda *_args: {
            "trace_id": "trace-validity",
            "events": [{"source": "Retriever", "target": "Summarizer", "status": "success"}],
        },
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
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
    result = voc_quality_service.run_test_case(
        "TC-01",
        judge_config={"enabled": True, "provider": "anthropic", "model": "judge-model"},
    )
    return store, result


def test_validity_server_recalculates_score_and_ai_pass(monkeypatch):
    rubric = voc_quality_service.load_improvement_validity_rubric()
    payload = _validity_payload(rubric)
    payload.update({"total_score": 1, "decision": "REJECTED"})
    monkeypatch.setattr(
        voc_validity_service.voc_judge_service,
        "_invoke_provider",
        lambda **_kwargs: (json.dumps(payload, ensure_ascii=False), {"input_tokens": 10, "output_tokens": 5}),
    )
    result = voc_validity_service.evaluate_improvement_validity(
        case={"case_id": "TC-01", "question": "질문"},
        execution={"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
        trace={"trace_id": "trace", "events": [{"status": "success"}]},
        judge_result={"decision": "PASS", "total_score": 90},
        defects={"defects": []},
        rubric=rubric,
        provider="anthropic",
        model="validity-model",
    )

    assert result["total_score"] == 100
    assert result["decision"] == "AI_PASS"
    assert result["workflow_state"] == "AI_REVIEWED"
    assert result["formal_approval"] is False


def test_validity_evidence_holds_force_revision(monkeypatch):
    rubric = voc_quality_service.load_improvement_validity_rubric()
    monkeypatch.setattr(
        voc_validity_service.voc_judge_service,
        "_invoke_provider",
        lambda **_kwargs: (
            json.dumps(_validity_payload(rubric), ensure_ascii=False),
            {"input_tokens": 10, "output_tokens": 5},
        ),
    )
    result = voc_validity_service.evaluate_improvement_validity(
        case={"case_id": "TC-01", "question": "질문"},
        execution={"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
        trace={},
        judge_result={"decision": "ERROR"},
        defects={"defects": [{"severity": "HIGH", "status": "OPEN"}]},
        rubric=rubric,
        provider="anthropic",
        model="validity-model",
    )

    assert result["total_score"] == 100
    assert result["decision"] == "REVISION_REQUIRED"
    assert set(result["immediate_hold_rules_triggered"]) == {
        "missing_voc_or_trace_evidence",
        "judge_error_or_not_run",
        "unresolved_high_or_critical_defect",
    }


def test_model_cannot_invent_server_owned_defect_hold(monkeypatch):
    rubric = voc_quality_service.load_improvement_validity_rubric()
    payload = _validity_payload(rubric, holds=["unresolved_high_or_critical_defect"])
    monkeypatch.setattr(
        voc_validity_service.voc_judge_service,
        "_invoke_provider",
        lambda **_kwargs: (json.dumps(payload, ensure_ascii=False), {}),
    )
    result = voc_validity_service.evaluate_improvement_validity(
        case={"case_id": "TC-01", "question": "질문"},
        execution={"ok": True, "result": {"ok": True, "summary": "요약", "policy": "개선안"}},
        trace={"trace_id": "trace", "events": [{"status": "success"}]},
        judge_result={"decision": "PASS"},
        defects={"defects": []},
        rubric=rubric,
        provider="anthropic",
        model="validity-model",
    )
    assert result["decision"] == "ERROR"
    assert "모델이 판정할 수 없는" in result["error"]


def test_validity_human_approval_requires_qa_then_business(monkeypatch, tmp_path):
    store, run = _create_completed_case(monkeypatch, tmp_path)
    rubric = voc_quality_service.load_improvement_validity_rubric()
    monkeypatch.setattr(
        voc_validity_service.voc_judge_service,
        "_invoke_provider",
        lambda **_kwargs: (
            json.dumps(_validity_payload(rubric), ensure_ascii=False),
            {"input_tokens": 10, "output_tokens": 5},
        ),
    )
    evaluated = voc_quality_service.evaluate_voc_improvement_validity(
        run["run_id"], "TC-01", {"provider": "anthropic", "model": "validity-model"}
    )
    assert evaluated["validity_result"]["workflow_state"] == "AI_REVIEWED"

    with pytest.raises(ValueError, match="QA_REVIEWED"):
        voc_quality_service.review_voc_improvement_validity(
            run["run_id"], "TC-01", reviewer_role="BUSINESS",
            reviewer_name_or_id="business-1", decision="APPROVE", comment="승인",
        )
    qa = voc_quality_service.review_voc_improvement_validity(
        run["run_id"], "TC-01", reviewer_role="QA",
        reviewer_name_or_id="demo-reviewer", decision="APPROVE", comment="QA 역할로 근거 확인",
    )
    assert qa["validity_result"]["workflow_state"] == "QA_REVIEWED"
    business = voc_quality_service.review_voc_improvement_validity(
        run["run_id"], "TC-01", reviewer_role="BUSINESS",
        reviewer_name_or_id="demo-reviewer", decision="APPROVE", comment="업무 역할로 운영 적용 승인",
    )
    result = business["validity_result"]
    assert result["workflow_state"] == "BUSINESS_APPROVED"
    assert result["formal_approval"] is True
    assert [item["reviewer_role"] for item in result["human_reviews"]] == ["QA", "BUSINESS"]
    assert {item["reviewer_name_or_id"] for item in result["human_reviews"]} == {"demo-reviewer"}
    stored = store.load_voc_run(run["run_id"])
    assert stored["summary"]["deployment_decision"] == "FORMAL_QUALITY_APPROVED"
    assert store.verify_run_integrity(run["run_id"])["ok"]


def test_validity_rejects_blank_reviewer_and_comment(monkeypatch, tmp_path):
    store, run = _create_completed_case(monkeypatch, tmp_path)
    store.save_validity_evaluation(
        run["run_id"], "TC-01",
        {
            "decision": "AI_PASS", "workflow_state": "AI_REVIEWED", "total_score": 90,
            "immediate_hold_rules_triggered": [], "formal_approval": False,
        },
    )
    with pytest.raises(ValueError, match="검토자"):
        store.apply_validity_human_review(
            run["run_id"], "TC-01", reviewer_role="QA", reviewer_name_or_id="",
            decision="APPROVE", comment="확인",
        )


def test_improvement_validity_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/voc_validity_app.py", default_timeout=15)
    app.run()
    assert not app.exception
    assert any("검증 대상 선택" in item.value for item in app.markdown)
    assert {metric.label for metric in app.metric}.issuperset(
        {"전체 대상", "평가 전", "QA 검토 가능", "정식 승인"}
    )
    assert len(app.dataframe) == 1
    assert app.dataframe[0].value.columns.tolist() == [
        "선택", "수행 일시", "Run ID", "Case ID", "유형", "질문", "Judge",
        "Judge 점수", "타당성", "타당성 점수", "승인 단계", "정식 승인",
    ]
    assert any("선택 대상 · TC-01" in item.value for item in app.markdown)

    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert any("사용 순서" in item.value for item in app.markdown)
    assert any("연결 재시험" in button.label for button in app.button)


def test_validity_candidate_detail_dialog_renders_execution_evidence():
    app = AppTest.from_file("tests/fixtures/voc_validity_dialog_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    assert any("Pipeline 요약" in item.value for item in app.markdown)
    assert any("최종 개선안" in item.value for item in app.markdown)
    assert {metric.label for metric in app.metric}.issuperset(
        {"Case", "Judge", "타당성", "승인 단계", "Judge 점수", "타당성 점수"}
    )
    assert any(button.label == "이 대상으로 검증 진행" for button in app.button)


def test_validity_candidate_filter_and_rows_are_list_friendly():
    candidates = [
        {
            "run_id": "RUN-01", "case_id": "TC-01", "question": "보험 갱신 오류",
            "run_type": "MANUAL", "validity_status": "NOT_RUN", "formal_approval": False,
        },
        {
            "run_id": "RUN-02", "case_id": "TC-02", "question": "결제 실패",
            "run_type": "BATCH", "validity_status": "AI_PASS", "formal_approval": True,
        },
    ]

    assert [
        item["case_id"]
        for item in voc_quality_view._filter_validity_candidates(
            candidates, query="보험", status_filter="전체"
        )
    ] == ["TC-01"]
    assert [
        item["case_id"]
        for item in voc_quality_view._filter_validity_candidates(
            candidates, query="", status_filter="정식 승인"
        )
    ] == ["TC-02"]
    rows = voc_quality_view._validity_candidate_rows(candidates, "RUN-02::TC-02")
    assert rows.loc[0, "선택"] == ""
    assert rows.loc[1, "선택"] == "●"
    assert rows.loc[1, "정식 승인"] == "승인"
