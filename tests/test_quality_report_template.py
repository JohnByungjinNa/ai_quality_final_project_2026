from components.quality_report_template import (
    build_agent_report_html,
    build_agent_report_model,
    build_comparison_summary_html,
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
