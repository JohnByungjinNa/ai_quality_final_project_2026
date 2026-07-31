import json
from copy import deepcopy

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


def _validity_payload_at_total(rubric, total, *, floor_miss_key=None, holds=None):
    scores = {
        key: float(spec["pass_floor"])
        for key, spec in rubric["dimensions"].items()
    }
    if floor_miss_key:
        scores[floor_miss_key] -= 1
    difference = round(float(total) - sum(scores.values()), 2)
    if difference >= 0:
        for key, spec in rubric["dimensions"].items():
            if key == floor_miss_key:
                continue
            available = float(spec["max_points"]) - scores[key]
            addition = min(available, difference)
            scores[key] += addition
            difference = round(difference - addition, 2)
    else:
        for key in scores:
            reduction = min(scores[key], -difference)
            scores[key] -= reduction
            difference = round(difference + reduction, 2)
    assert abs(difference) < 0.001
    return {
        "dimension_scores": {
            key: {"score": score, "reason": f"{key} 경계값 근거"}
            for key, score in scores.items()
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


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        (64.99, "REJECTED"),
        (65, "REVISION_REQUIRED"),
        (79.99, "REVISION_REQUIRED"),
        (80, "AI_PASS"),
    ],
)
def test_validity_decision_uses_rubric_score_boundaries(total, expected):
    rubric = voc_quality_service.load_improvement_validity_rubric()

    result = voc_validity_service._validate_and_score(
        _validity_payload_at_total(rubric, total),
        rubric,
        [],
    )

    assert result["total_score"] == total
    assert result["decision"] == expected


def test_validity_ai_pass_requires_floors_and_no_holds():
    rubric = voc_quality_service.load_improvement_validity_rubric()

    floor_miss = voc_validity_service._validate_and_score(
        _validity_payload_at_total(rubric, 80, floor_miss_key="cause_linkage"),
        rubric,
        [],
    )
    held = voc_validity_service._validate_and_score(
        _validity_payload_at_total(rubric, 100),
        rubric,
        ["missing_voc_or_trace_evidence"],
    )

    assert floor_miss["all_pass_floors_met"] is False
    assert floor_miss["decision"] == "REVISION_REQUIRED"
    assert held["decision"] == "REVISION_REQUIRED"


def test_validity_decision_threshold_is_read_from_rubric():
    rubric = deepcopy(voc_quality_service.load_improvement_validity_rubric())
    rubric["automatic_decisions"][0]["min_score"] = 90
    rubric["automatic_decisions"][1]["max_score"] = 89.99

    result = voc_validity_service._validate_and_score(
        _validity_payload_at_total(rubric, 80),
        rubric,
        [],
    )

    assert result["decision"] == "REVISION_REQUIRED"


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
    candidate = next(
        item for item in voc_quality_service.list_improvement_validity_candidates()
        if item["run_id"] == run["run_id"] and item["case_id"] == "TC-01"
    )
    assert candidate["qa_review_ready"] is True
    assert candidate["business_review_ready"] is False
    assert candidate["review_action_label"] == "QA 검토 가능"

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
    candidate = next(
        item for item in voc_quality_service.list_improvement_validity_candidates()
        if item["run_id"] == run["run_id"] and item["case_id"] == "TC-01"
    )
    assert candidate["qa_review_ready"] is False
    assert candidate["business_review_ready"] is True
    assert candidate["review_action_label"] == "업무 승인 가능"
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


def test_validity_supplement_is_saved_and_used_for_auto_evaluation(monkeypatch, tmp_path):
    store, run = _create_completed_case(monkeypatch, tmp_path)
    captured = {}

    def fake_validity_evaluator(**kwargs):
        captured["execution"] = kwargs["execution"]
        return {
            "status": "AI_PASS",
            "decision": "AI_PASS",
            "workflow_state": "AI_REVIEWED",
            "formal_approval": False,
            "dimension_scores": {},
            "total_score": 91,
            "all_pass_floors_met": True,
            "immediate_hold_rules_triggered": [],
            "evidence": [],
            "risks": [],
            "recommendations": [],
            "attempts": [],
        }

    monkeypatch.setattr(
        voc_quality_service.voc_validity_service,
        "evaluate_improvement_validity",
        fake_validity_evaluator,
    )
    saved = voc_quality_service.save_voc_validity_supplement(
        run["run_id"],
        "TC-01",
        {
            "owner": "모바일앱개발팀 리드",
            "schedule": "2026-08-01 착수, 2026-08-15 QA, 2026-08-22 배포",
            "kpi": "구독 갱신 오류율 2.1%에서 0.5% 이하로 감소",
        },
    )
    assert saved["validity_supplement"]["filled_fields"] == ["owner", "schedule", "kpi"]
    assert store.load_case_artifacts(run["run_id"], "TC-01")["validity_supplement"]["owner"] == "모바일앱개발팀 리드"

    evaluated = voc_quality_service.evaluate_voc_improvement_validity(
        run["run_id"], "TC-01", {"provider": "anthropic", "model": "validity-model"}
    )

    policy = captured["execution"]["result"]["policy"]
    assert "[사용자 개선안 타당성 평가 보완 입력]" in policy
    assert "모바일앱개발팀 리드" in policy
    assert captured["execution"]["result"]["validity_supplement_applied"] is True
    assert evaluated["validity_result"]["supplemental_evidence_applied"] is True
    assert evaluated["validity_result"]["supplemental_evidence"]["kpi"].startswith("구독 갱신 오류율")


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
        {"개선안 타당성 평가 필요", "보완·재시험 필요", "QA 검토 가능", "업무 승인 가능", "정식 승인 완료"}
    )
    assert {control.label for control in app.segmented_control}.issuperset({"회차 유형", "평가 상태"})
    assert not any(selectbox.label in {"회차 유형", "평가 상태"} for selectbox in app.selectbox)
    assert len(app.dataframe) >= 3
    assert app.dataframe[0].value.columns.tolist() == [
        "수행 일시", "Run ID", "Case ID", "수행 유형", "질문", "독립 LLM 평가",
        "독립 LLM 점수", "개선안 타당성", "타당성 점수", "승인 단계", "다음 조치", "정식 승인",
    ]
    assert any("QA 검토/승인 대기 대상" in item.value for item in app.markdown)
    assert any("선택 기준 · TC-01" in item.value for item in app.markdown)
    assert any("평가 항목과 점수 지표" in item.value for item in app.markdown)
    assert any("개선안 타당성 평가 수행 절차" in item.value for item in app.markdown)
    assert any("QA 검토 가능 조건" in item.value for item in app.markdown)

    app.toggle[0].set_value(True).run()
    assert not app.exception
    assert any("사용 순서" in item.value for item in app.markdown)
    assert any("연결 재시험" in button.label for button in app.button)


def test_validity_candidate_detail_dialog_renders_execution_evidence():
    app = AppTest.from_file("tests/fixtures/voc_validity_dialog_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    import inspect
    source = inspect.getsource(voc_quality_view._render_validity_candidate_dialog)
    assert '["대상 요약", "Agent 파이프라인 결과", "독립 LLM 평가", "개선안 타당성 평가", "QA 검토·승인"]' in source
    assert any("Agent 파이프라인 요약" in item.value for item in app.markdown)
    assert any("최종 개선안" in item.value for item in app.markdown)
    assert {metric.label for metric in app.metric}.issuperset(
        {"Case", "독립 LLM 평가", "개선안 타당성 평가", "승인 단계", "독립 LLM 평가 점수", "개선안 타당성 점수"}
    )
    assert not any(button.label == "이 대상으로 검증 진행" for button in app.button)


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
        {
            "run_id": "RUN-03", "case_id": "TC-03", "question": "갱신 보완",
            "run_type": "BATCH", "validity_status": "AI_PASS",
            "workflow_state": "AI_REVIEWED", "formal_approval": False,
            "immediate_hold_count": 0,
        },
        {
            "run_id": "RUN-04", "case_id": "TC-04", "question": "업무 승인",
            "run_type": "BATCH", "validity_status": "AI_PASS",
            "workflow_state": "QA_REVIEWED", "formal_approval": False,
            "immediate_hold_count": 0,
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
            candidates, query="", status_filter="전체", run_type_filter="일괄 수행"
        )
    ] == ["TC-02", "TC-03", "TC-04"]
    assert [
        item["case_id"]
        for item in voc_quality_view._filter_validity_candidates(
            candidates, query="", status_filter="정식 승인"
        )
    ] == ["TC-02"]
    assert [
        item["case_id"]
        for item in voc_quality_view._filter_validity_candidates(
            candidates, query="", status_filter="QA 검토 가능"
        )
    ] == ["TC-03"]
    assert [
        item["case_id"]
        for item in voc_quality_view._filter_validity_candidates(
            candidates, query="", status_filter="업무 승인 가능"
        )
    ] == ["TC-04"]
    rows = voc_quality_view._validity_candidate_rows(candidates, "RUN-02::TC-02")
    assert "선택" not in rows.columns
    assert rows.loc[1, "정식 승인"] == "승인"
    assert rows.loc[2, "다음 조치"] == "QA 검토 가능"
    cards = {card["label"]: card for card in voc_quality_view._validity_focus_cards(candidates)}
    assert cards["개선안 타당성 평가 필요"]["value"] == "1건"
    assert cards["보완·재시험 필요"]["value"] == "0건"
    assert cards["QA 검토 가능"]["value"] == "1건"
    assert cards["업무 승인 가능"]["value"] == "1건"
    assert cards["정식 승인 완료"]["delta"] == "전체 대비 25%"


def test_validity_selection_basis_and_qa_gate_are_explicit():
    candidate = {
        "run_id": "RUN-01",
        "case_id": "TC-01",
        "started_at": "2026-07-16T12:00:00+09:00",
        "run_type": "RETEST",
        "parent_run_id": "RUN-PARENT",
        "question": "VOC 개선안 재검증",
        "judge_status": "PASS",
        "judge_score": 93,
        "validity_status": "AI_PASS",
        "validity_score": 91,
        "workflow_state": "AI_REVIEWED",
    }
    artifacts = {
        "pipeline_result": {
            "mode": "voc",
            "execution": {
                "ok": True,
                "question": "실행 질문",
                "result": {"ok": True},
            },
        }
    }
    result = {
        "decision": "AI_PASS",
        "workflow_state": "AI_REVIEWED",
        "immediate_hold_rules_triggered": [],
    }

    basis = voc_quality_view._validity_selection_basis(candidate, artifacts)
    gate = voc_quality_view._validity_qa_gate_model(candidate, result)

    assert basis["run_type_label"] == "재시험"
    assert basis["parent_run_id"] == "RUN-PARENT"
    assert basis["pipeline_success"] is True
    assert gate["ready"] is True
    assert gate["summary"] == "QA 검토 가능"


def test_validity_qa_gate_blocks_immediate_hold_rules():
    candidate = {
        "validity_status": "AI_PASS",
        "workflow_state": "AI_REVIEWED",
    }
    result = {
        "decision": "AI_PASS",
        "workflow_state": "AI_REVIEWED",
        "immediate_hold_rules_triggered": ["unresolved_high_or_critical_defect"],
    }

    gate = voc_quality_view._validity_qa_gate_model(candidate, result)

    assert gate["ready"] is False
    assert "즉시 보류 규칙" in gate["blocked_reasons"]
    assert gate["holds"] == ["unresolved_high_or_critical_defect"]


def test_validity_approval_workflow_model_moves_from_qa_to_business_approval():
    result = {
        "decision": "AI_PASS",
        "workflow_state": "QA_REVIEWED",
        "total_score": 91,
        "formal_approval": False,
        "immediate_hold_rules_triggered": [],
    }

    model = voc_quality_view._validity_approval_workflow_model(result)

    assert model["readiness"]["action"] == "BUSINESS_APPROVAL"
    assert model["readiness"]["action_label"] == "업무 승인 가능"
    assert model["readiness"]["deployment_decision"] == "BUSINESS_REVIEW_REQUIRED"
    assert [stage["label"] for stage in model["stages"]] == [
        "개선안 타당성 평가", "QA 검토", "업무 승인", "최종 배포 판정"
    ]
    assert model["stages"][1]["status"] == "완료"
    assert model["stages"][2]["status"] == "현재 단계"


def test_validity_dimension_rows_show_scores_and_korean_criteria():
    rubric = {
        "version": "1.0",
        "dimensions": {
            "cause_linkage": {
                "label": "불만 원인과 개선안 연결",
                "max_points": 20,
                "pass_floor": 18,
                "criteria": {
                    "complaint_to_root_cause": 8,
                    "root_cause_to_action": 8,
                    "expected_customer_impact": 4,
                },
            }
        },
    }
    result = {
        "dimension_scores": {
            "cause_linkage": {
                "score": 18,
                "max_points": 20,
                "reason": "VOC 원인과 개선안이 연결됨",
            }
        }
    }

    rows = voc_quality_view._validity_dimension_rows(rubric, result)

    assert rows.loc[0, "결과 점수"] == 18
    assert rows.loc[0, "달성률"] == 90
    assert rows.loc[0, "판정"] == "기준 충족"
    assert "불만↔근본 원인 8점" in rows.loc[0, "세부 지표"]


def test_ai_pass_failure_model_separates_four_failure_types():
    rubric = voc_quality_service.load_improvement_validity_rubric()
    result = {
        "decision": "REVISION_REQUIRED",
        "total_score": 77,
        "dimension_scores": {
            key: {
                "score": (
                    10
                    if key == "evidence_traceability"
                    else float(spec["pass_floor"])
                ),
                "reason": "평가 근거",
            }
            for key, spec in rubric["dimensions"].items()
        },
        "immediate_hold_rules_triggered": [
            "missing_voc_or_trace_evidence",
            "judge_error_or_not_run",
        ],
    }
    artifacts = {"trace": {"trace_id": "", "events": []}}

    model = voc_quality_view._validity_ai_pass_failure_model(
        result,
        rubric,
        artifacts,
    )
    categories = {item["key"]: item for item in model["categories"]}

    assert model["failed_count"] == 4
    assert categories["score"]["failed"] is True
    assert categories["score"]["value"] == "77 / 80점"
    assert categories["floors"]["failed"] is True
    assert "VOC·실행 Trace 근거 추적성" in categories["floors"]["details"][0]
    assert categories["holds"]["details"] == ["독립 LLM 평가 미수행·오류"]
    assert categories["evidence"]["failed"] is True
    assert any("Trace ID" in detail for detail in categories["evidence"]["details"])


def test_ai_pass_failure_model_reports_all_conditions_met():
    rubric = voc_quality_service.load_improvement_validity_rubric()
    result = {
        "decision": "AI_PASS",
        "total_score": 100,
        "dimension_scores": {
            key: {"score": float(spec["max_points"]), "reason": "충족"}
            for key, spec in rubric["dimensions"].items()
        },
        "immediate_hold_rules_triggered": [],
    }
    artifacts = {
        "trace": {
            "trace_id": "trace-pass",
            "events": [{"source": "Interpreter", "target": "Retriever"}],
        }
    }

    model = voc_quality_view._validity_ai_pass_failure_model(
        result,
        rubric,
        artifacts,
    )

    assert model["passed"] is True
    assert model["failed_count"] == 0
    assert all(item["failed"] is False for item in model["categories"])


def test_ai_pass_failure_visualization_renders_four_categories():
    app = AppTest.from_file(
        "tests/fixtures/voc_validity_failure_visualization_app.py",
        default_timeout=15,
    )
    app.run()

    assert not app.exception
    rendered = "\n".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert "AI 평가 통과 진단" in rendered
    assert "점수 부족" in rendered
    assert "항목별 하한 미달" in rendered
    assert "즉시 보류 규칙" in rendered
    assert "VOC·실행 Trace 근거 부족" in rendered
    assert "실패 원인 4개 유형" in rendered


def test_validity_execution_steps_summarize_per_step_results():
    candidate = {
        "run_id": "RUN-01",
        "case_id": "TC-01",
        "run_type": "MANUAL",
        "validity_status": "AI_PASS",
        "workflow_state": "AI_REVIEWED",
    }
    artifacts = {
        "pipeline_result": {"mode": "voc", "execution": {"ok": True, "result": {"ok": True}}},
        "trace": {"trace_id": "trace-1", "events": [{"status": "success"}]},
        "judge_result": {"decision": "PASS"},
    }
    rubric = {
        "version": "1.0",
        "dimensions": {
            "cause_linkage": {"max_points": 20},
            "feasibility": {"max_points": 80},
        },
        "automatic_decisions": [
            {"decision": "AI_PASS", "min_score": 80, "requires_all_pass_floors": True}
        ],
    }
    result = {
        "decision": "AI_PASS",
        "workflow_state": "AI_REVIEWED",
        "total_score": 90,
        "all_pass_floors_met": True,
        "immediate_hold_rules_triggered": [],
        "provider": "anthropic",
        "model": "validity-model",
        "duration_seconds": 3.2,
        "attempts": [{"status": "SUCCESS"}],
    }

    rows = voc_quality_view._validity_execution_step_rows(candidate, artifacts, result, rubric)

    assert rows["수행 절차"].tolist() == [
        "대상 증적 수집",
        "보완 입력 반영",
        "평가 기준 구성",
        "독립 LLM 평가",
        "점수·판정 산출",
        "즉시 보류 규칙 확인",
        "QA Gate 판정",
    ]
    assert rows.iloc[-1]["상태"] == "가능"
    assert rows.iloc[-1]["절차별 결과"] == "QA 검토 가능"

def test_validity_rework_guide_targets_floor_misses_and_generates_instruction():
    rubric = {
        "dimensions": {
            "cause_linkage": {
                "label": "불만 원인과 개선안 연결",
                "max_points": 20,
                "pass_floor": 18,
            },
            "ownership_schedule_kpi": {
                "label": "담당·일정·KPI",
                "max_points": 15,
                "pass_floor": 11,
            },
            "risk_security_compliance": {
                "label": "리스크·보안·법규",
                "max_points": 25,
                "pass_floor": 10,
            },
        }
    }
    result = {
        "decision": "REVISION_REQUIRED",
        "workflow_state": "REVISION_REQUIRED",
        "total_score": 71,
        "dimension_scores": {
            "cause_linkage": {"score": 17, "reason": "우선순위 2~4 개선안이 누락됨"},
            "ownership_schedule_kpi": {"score": 9, "reason": "일정과 KPI가 없음"},
            "risk_security_compliance": {"score": 24, "reason": "충분함"},
        },
        "recommendations": ["VOC ID를 명시하세요."],
        "immediate_hold_rules_triggered": [],
    }
    candidate = {
        "run_id": "RUN-20260726-112222-362409-7297",
        "case_id": "TC-01",
        "question": "보험 갱신 오류",
    }
    artifacts = {
        "pipeline_result": {
            "execution": {
                "result": {
                    "summary": "모바일 갱신 오류 요약",
                    "policy": "세션 타임아웃 개선",
                }
            }
        }
    }

    rows = voc_quality_view._validity_rework_items(rubric, result)
    instruction = voc_quality_view._validity_rework_instruction(candidate, artifacts, result, rubric)

    assert rows["평가 항목"].tolist() == ["불만 원인과 개선안 연결", "담당·일정·KPI"]
    assert rows.loc[0, "부족 점수"] == 1
    assert "우선순위 2~4 개선안이 누락됨" in instruction
    assert "VOC ID" in instruction
    assert "정량 KPI" in instruction
    assert "원본 Run" in instruction
