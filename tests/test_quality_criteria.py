from dataclasses import replace

from components.report_visuals import compute_release_decision, summarize_pipeline_outputs
from quality_criteria import QUALITY_PRESETS, get_quality_criteria, validate_quality_criteria


def _case(case_id, rule_decision, api_decision, safety=4):
    def result(decision):
        return {
            "evaluation_result": {
                "overall_decision": decision,
                "accuracy": {"score": 4},
                "groundedness": {"score": 4},
                "helpfulness": {"score": 4},
                "safety": {"score": safety},
                "comment": "정상 평가",
            }
        }

    return {
        "case_id": case_id,
        "rule_based": result(rule_decision),
        "api_based": result(api_decision),
    }


def test_presets_have_increasing_release_requirements():
    initial = QUALITY_PRESETS["initial"]
    mid = QUALITY_PRESETS["mid"]
    advanced = QUALITY_PRESETS["advanced"]

    assert initial.rule_pass_rate_min < mid.rule_pass_rate_min < advanced.rule_pass_rate_min
    assert initial.api_pass_rate_min < mid.api_pass_rate_min < advanced.api_pass_rate_min
    assert initial.safety_avg_min < mid.safety_avg_min < advanced.safety_avg_min


def test_custom_criteria_round_trip_from_dictionary():
    custom = replace(
        QUALITY_PRESETS["mid"],
        stage="custom",
        stage_label="사용자 정의",
        pass_min_score=5,
        api_pass_rate_min=92.0,
    )

    restored = get_quality_criteria(custom.to_dict())

    assert restored.stage == "custom"
    assert restored.pass_min_score == 5
    assert restored.api_pass_rate_min == 92.0


def test_invalid_score_order_is_rejected():
    invalid = replace(QUALITY_PRESETS["mid"], pass_min_score=3, review_min_score=3)

    assert validate_quality_criteria(invalid)


def test_combined_pass_count_uses_same_case_intersection():
    outputs = [
        _case("TC-1", "PASS", "FAIL"),
        _case("TC-2", "FAIL", "PASS"),
        _case("TC-3", "PASS", "PASS"),
    ]

    summary = summarize_pipeline_outputs(outputs, "mid")

    assert summary["rule_passed_count"] == 2
    assert summary["api_passed_count"] == 2
    assert summary["combined_passed_count"] == 1
    assert summary["failed_count"] == 2


def test_release_decision_uses_selected_stage_thresholds():
    outputs = [_case(f"TC-{index}", "PASS", "PASS", safety=4) for index in range(10)]

    assert compute_release_decision(outputs, 90, 90, "mid")[0] == "배포 가능"
    assert compute_release_decision(outputs, 90, 90, "advanced")[0] == "조건부 배포"
