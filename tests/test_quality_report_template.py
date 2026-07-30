from components.quality_report_template import (
    build_agent_report_html,
    build_agent_report_model,
    build_comparison_summary_html,
    build_voc_quality_report_html,
)


def _metric(score, evaluated=True):
    return {"score": score, "reason": "평가 사유", "evaluated": evaluated}


def _case(case_id, decision, test_type="Happy", scores=(4, 4, 4, 5)):
    evaluation = {
        "accuracy": _metric(scores[0]),
        "groundedness": _metric(scores[1]),
        "helpfulness": _metric(scores[2]),
        "safety": _metric(scores[3]),
        "overall_decision": decision,
        "comment": "평가 요약",
    }
    return {
        "case_id": case_id,
        "category": "교육과정",
        "test_type": test_type,
        "user_question": "교육시간은 얼마인가요?",
        "rule_based": {"ai_answer": "총 320시간입니다.", "evaluation_result": evaluation},
        "api_based": {"ai_answer": "총 320시간입니다.", "evaluation_result": evaluation},
    }


def test_report_model_summarizes_decisions_and_types():
    model = build_agent_report_model(
        [_case("TC-1", "PASS"), _case("TC-2", "REVIEW", "Edge"), _case("TC-3", "FAIL", "Negative")],
        "api_based",
        "mid",
    )

    assert model["total"] == 3
    assert model["passed"] == 1
    assert model["review"] == 1
    assert model["failed"] == 1
    assert {row["type"] for row in model["type_rows"]} == {"Happy", "Edge", "Negative"}
    assert len(model["defects"]) == 2


def test_rule_report_only_scores_accuracy_even_for_legacy_results():
    case = _case("TC-1", "PASS", scores=(5, 5, 5, 5))
    for metric in ("groundedness", "helpfulness", "safety"):
        case["rule_based"]["evaluation_result"][metric].pop("evaluated")
    model = build_agent_report_model([case], "rule_based", "mid")
    metrics = {row["key"]: row for row in model["metric_rows"]}

    assert metrics["accuracy"]["score_100"] == 100.0
    assert metrics["groundedness"]["score_100"] is None
    assert metrics["helpfulness"]["status"] == "평가 제외"
    assert metrics["safety"]["score_100"] is None


def test_rule_report_displays_all_metrics_from_v2_validator():
    model = build_agent_report_model([_case("TC-1", "PASS", scores=(5, 4, 4, 5))], "rule_based", "mid")
    metrics = {row["key"]: row for row in model["metric_rows"]}

    assert metrics["accuracy"]["score_100"] == 100.0
    assert metrics["groundedness"]["score_100"] == 80.0
    assert metrics["helpfulness"]["score_100"] == 80.0
    assert metrics["safety"]["score_100"] == 100.0


def test_report_html_contains_reusable_reference_sections():
    model = build_agent_report_model([_case("TC-1", "PASS")], "api_based", "mid")

    report_html = build_agent_report_html(model)

    assert "테스트 요약 (Summary)" in report_html
    assert "테스트 결과 상세" in report_html
    assert "테스트 케이스 결과 목록" in report_html
    assert "주요 결함 요약" in report_html
    assert "종합 평가 및 의견" in report_html
    assert "개선 권고 사항" in report_html
    assert "<svg" in report_html
    assert "#155A96" in report_html
    assert "#5599D2" in report_html
    assert "#A9CAE7" in report_html
    assert "linear-gradient(90deg,#0F4C81,#2E78B7 58%,#5EA1D7)" in report_html


def test_comparison_summary_uses_report_cards_in_one_row():
    summary_html = build_comparison_summary_html(
        80,
        16,
        50,
        10,
        20,
        "조건부 배포",
        "실패 사례 보완 후 재검증이 필요합니다.",
    )

    assert "grid-template-columns:repeat(3" in summary_html
    assert "규칙 기반 합격률" in summary_html
    assert "80.0<small>%</small>" in summary_html
    assert "16/20" in summary_html
    assert "API 기반 합격률" in summary_html
    assert "10/20" in summary_html
    assert "최종 판정" in summary_html
    assert "조건부 배포" in summary_html
    assert "<svg" in summary_html


def test_voc_report_uses_chatbot_report_style_and_evidence_sections():
    model = {
        "report_id": "VOC-REPORT-RUN-001",
        "generated_at": "2026-07-30T10:00:00+09:00",
        "report_state": "EVIDENCE_DRAFT",
        "release_decision": "NOT_APPROVED",
        "run": {
            "run_id": "RUN-001",
            "run_type": "BATCH",
            "suite_id": "VOC-QA-35",
            "catalog_version": "1.0",
            "selected_count": 3,
            "counts": {
                "PASS": 2,
                "FAIL": 1,
                "ERROR": 0,
                "REVIEW_REQUIRED": 0,
                "NOT_RUN": 0,
            },
        },
        "integrity": {"ok": True},
        "evaluation": {
            "voc_examples": [{"case_id": "TC-01"}],
            "trace_cases": 3,
            "trace_events": 18,
            "judge_evaluated": 2,
            "judge_counts": {"PASS": 2},
            "validity_evaluated": 1,
            "validity_counts": {
                "AI_PASS": 1,
                "QA_REVIEWED": 1,
                "BUSINESS_APPROVED": 1,
            },
        },
        "coverage": [
            {
                "group": "기능",
                "expected": 3,
                "selected": 3,
                "PASS": 2,
                "FAIL": 1,
                "ERROR": 0,
                "REVIEW_REQUIRED": 0,
                "NOT_RUN": 0,
            }
        ],
        "claims": {
            "improvement_verified": False,
            "claim_text": "초기 33 PASS / 2 FAIL → 최종 35 PASS",
            "baseline": {"verified": False, "errors": ["기준선 없음"]},
            "final": {"verified": False, "errors": ["35건 Run 아님"]},
        },
        "defects": [],
        "risks": [{"level": "HIGH", "risk": "미통과 1건", "action": "재시험 수행"}],
        "roles": [
            {"role": "Evaluator", "scope": "내부 평가", "independence": "내부"},
            {"role": "독립 LLM Judge", "scope": "별도 평가", "independence": "외부"},
        ],
    }

    report_html = build_voc_quality_report_html(model)

    assert "VOC 품질진단 결과 보고서" in report_html
    assert "1. 테스트 요약" in report_html
    assert "품질 평가 단계 상세" in report_html
    assert "테스트 결과 상세" in report_html
    assert "개선 추이 및 결함 관리" in report_html
    assert "독립성 및 잔여 위험" in report_html
    assert "종합 평가 및 의견" in report_html
    assert "개선 권고 사항" in report_html
    assert "AI 평가 통과 1건" in report_html
    assert "QA 검토 완료 1건" in report_html
    assert "업무 승인 완료 1건" in report_html
    assert "증적 초안" in report_html
    assert "승인되지 않음" in report_html
    assert "AI_PASS" not in report_html
    assert "QA_REVIEWED" not in report_html
    assert "BUSINESS_APPROVED" not in report_html
    assert "EVIDENCE_DRAFT" not in report_html
    assert "NOT_APPROVED" not in report_html
    assert "linear-gradient(90deg,#0F4C81,#2E78B7 58%,#5EA1D7)" in report_html
