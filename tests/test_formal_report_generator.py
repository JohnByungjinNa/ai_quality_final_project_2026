from pathlib import Path

from quality.formal_report_generator import (
    build_defect_items,
    build_report_context,
    generate_docx_report,
    generate_html_report,
    generate_pdf_report,
    normalize_pipeline_outputs,
)


def _metric(score):
    return {"score": score, "reason": "평가 사유"}


def sample_outputs():
    return [
        {
            "case_id": "TC-001",
            "category": "출결",
            "test_type": "Happy",
            "user_question": "출결 기준은 무엇인가요?",
            "rule_based": {
                "ai_answer": "정상 응답",
                "rule_validation": {"passed": True, "rule_status": "PASS", "rule_reason": "키워드 포함"},
                "evaluation_result": {
                    "accuracy": _metric(5),
                    "groundedness": _metric(5),
                    "helpfulness": _metric(5),
                    "safety": _metric(5),
                    "overall_decision": "PASS",
                    "summary": "정상",
                },
            },
            "api_based": {
                "ai_answer": "정상 응답",
                "rule_validation": {"passed": True, "rule_status": "PASS", "rule_reason": "키워드 포함"},
                "evaluation_result": {
                    "accuracy": _metric(5),
                    "groundedness": _metric(4),
                    "helpfulness": _metric(5),
                    "safety": _metric(5),
                    "overall_decision": "PASS",
                    "summary": "정상",
                },
            },
        },
        {
            "case_id": "TC-002",
            "category": "안전",
            "test_type": "Negative",
            "user_question": "위험한 요청",
            "rule_based": {
                "ai_answer": "부적절한 응답",
                "rule_validation": {"passed": False, "rule_status": "FAIL", "rule_reason": "금지 키워드 누락"},
                "evaluation_result": {
                    "accuracy": _metric(1),
                    "groundedness": _metric(1),
                    "helpfulness": _metric(2),
                    "safety": _metric(1),
                    "overall_decision": "FAIL",
                    "summary": "규칙 위반",
                },
            },
            "api_based": {
                "ai_answer": "부적절한 응답",
                "rule_validation": {"passed": False, "rule_status": "FAIL", "rule_reason": "금지 키워드 누락"},
                "evaluation_result": {
                    "accuracy": _metric(2),
                    "groundedness": _metric(2),
                    "helpfulness": _metric(2),
                    "safety": _metric(1),
                    "overall_decision": "FAIL",
                    "summary": "안전성 미흡",
                },
            },
        },
    ]


def test_build_report_context_counts_decisions_and_metrics():
    context = build_report_context(sample_outputs())

    assert context["total_cases"] == 2
    assert context["agents"]["api_based"]["decision_counts"]["PASS"] == 1
    assert context["agents"]["api_based"]["decision_counts"]["FAIL"] == 1
    assert context["agents"]["api_based"]["pass_rate"] == 50.0


def test_report_context_uses_selected_quality_criteria():
    context = build_report_context(sample_outputs(), "advanced")

    assert context["pass_threshold"] == 95.0
    assert context["quality_criteria"]["stage"] == "advanced"


def test_flat_report_input_is_decided_with_selected_stage():
    flat_input = [
        {
            "case_id": "TC-FLAT",
            "rule_passed": True,
            "accuracy": 3,
            "groundedness": 3,
            "helpfulness": 3,
            "safety": 3,
        }
    ]

    initial = normalize_pipeline_outputs(flat_input, "initial")
    mid = normalize_pipeline_outputs(flat_input, "mid")

    assert initial[0]["api_based"]["evaluation_result"]["overall_decision"] == "PASS"
    assert mid[0]["api_based"]["evaluation_result"]["overall_decision"] == "REVIEW"


def test_defect_items_include_only_failures_with_agent_prefixes():
    defects = build_defect_items(sample_outputs())

    assert [defect["defect_id"] for defect in defects] == ["RULE-001", "API-001"]
    assert {defect["severity"] for defect in defects} == {"Critical"}


def test_generate_html_report_contains_preview_sections():
    report_html = generate_html_report(sample_outputs())

    assert "QA 최종 테스트 결과 보고서" in report_html
    assert "케이스별 판정 비교표" in report_html
    assert "결함 보고서" in report_html


def test_generate_docx_and_pdf_files():
    output_dir = Path("reports") / "_codex_check" / "formal_report_test"
    output_dir.mkdir(parents=True, exist_ok=True)
    docx_path = generate_docx_report(sample_outputs(), output_dir / "report.docx")
    pdf_path = generate_pdf_report(sample_outputs(), output_dir / "report.pdf")

    assert Path(docx_path).stat().st_size > 0
    assert Path(pdf_path).stat().st_size > 0
