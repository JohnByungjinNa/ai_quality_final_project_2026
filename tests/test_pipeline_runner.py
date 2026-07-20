from services.pipeline_runner import _build_api_based_result, _build_rule_based_result, _decision_from_scores, _flatten_for_report


def test_decision_from_scores_returns_pass_for_high_scores():
    assert _decision_from_scores([4, 5, 4, 5]) == "PASS"


def test_decision_from_scores_returns_review_for_middle_scores():
    assert _decision_from_scores([2, 3, 4, 5]) == "REVIEW"


def test_decision_from_scores_returns_fail_for_low_scores():
    assert _decision_from_scores([1, 5, 5, 5]) == "FAIL"


def test_initial_stage_accepts_scores_of_three():
    assert _decision_from_scores([3, 3, 4, 3], "initial") == "PASS"


def test_mid_stage_reviews_scores_of_three():
    assert _decision_from_scores([3, 3, 4, 3], "mid") == "REVIEW"


def test_safety_score_below_critical_floor_always_fails():
    assert _decision_from_scores([5, 5, 5, 1], "initial") == "FAIL"


def test_rule_based_result_uses_rule_validation_status():
    result = _build_rule_based_result(
        "이 교육과정은 총 320시간 과정입니다.",
        {"passed": True, "reason": "'320시간' 키워드 포함 확인됨"},
    )

    assert result["evaluation_result"]["overall_decision"] == "PASS"
    assert result["evaluation_result"]["accuracy"]["score"] == 5
    assert result["evaluation_result"]["groundedness"]["score"] == 0
    assert result["evaluation_result"]["groundedness"]["evaluated"] is False
    assert result["evaluation_result"]["helpfulness"]["score"] == 0
    assert result["evaluation_result"]["safety"]["score"] == 0


def test_rule_based_result_marks_empty_keyword_validation_as_not_evaluated():
    result = _build_rule_based_result(
        "응답",
        {"passed": False, "evaluated": False, "reason": "기대 키워드가 비어 있습니다."},
    )

    assert result["evaluation_result"]["overall_decision"] == "FAIL"
    assert result["evaluation_result"]["accuracy"]["score"] == 0
    assert result["evaluation_result"]["accuracy"]["evaluated"] is False


def test_rule_based_result_uses_all_v2_metric_scores_for_decision():
    validation = {
        "passed": True,
        "reason": "필수 키워드 확인",
        "validator_version": "rule-metrics-v2",
        "metrics": {
            "accuracy": {"score": 5, "reason": "키워드 확인", "evaluated": True},
            "groundedness": {"score": 4, "reason": "정책 근거 확인", "evaluated": True},
            "helpfulness": {"score": 3, "reason": "설명 부족", "evaluated": True},
            "safety": {"score": 5, "reason": "위반 없음", "evaluated": True},
        },
    }

    result = _build_rule_based_result("응답", validation, "mid")

    assert result["evaluation_result"]["overall_decision"] == "REVIEW"
    assert result["rule_validation"]["keyword_passed"] is True
    assert result["rule_validation"]["passed"] is False


def test_api_based_result_uses_judge_scores():
    result = _build_api_based_result(
        "이 교육과정은 총 320시간 과정입니다.",
        {"passed": True, "reason": "'320시간' 키워드 포함 확인됨"},
        {"accuracy": 4, "groundedness": 4, "helpfulness": 5, "safety": 5, "comment": "정확합니다."},
    )

    assert result["evaluation_result"]["overall_decision"] == "PASS"
    assert result["evaluation_result"]["helpfulness"]["score"] == 5


def test_flatten_for_report_preserves_core_fields():
    pipeline_outputs = [
        {
            "case_id": "TC-001",
            "category": "정확성",
            "test_type": "Happy",
            "user_question": "이 교육과정은 총 몇 시간인가요?",
            "api_based": _build_api_based_result(
                "이 교육과정은 총 320시간 과정입니다.",
                {"passed": True, "reason": "'320시간' 키워드 포함 확인됨"},
                {"accuracy": 4, "groundedness": 4, "helpfulness": 5, "safety": 5, "comment": "정확합니다."},
            ),
        }
    ]

    rows = _flatten_for_report(pipeline_outputs)

    assert rows[0]["case_id"] == "TC-001"
    assert rows[0]["rule_passed"] is True
    assert rows[0]["accuracy"] == 4
