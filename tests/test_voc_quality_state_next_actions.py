from dashboard.services.voc_quality_state_model import (
    voc_case_next_action,
    voc_run_next_action,
    voc_status_label,
)


def test_voc_status_label_uses_korean_display_text():
    assert voc_status_label("AI_PASS") == "AI 평가 통과"
    assert voc_status_label("FORMAL_QUALITY_APPROVED") == "정식 품질 승인"
    assert voc_status_label("RUNNING") == "진행 중"


def test_run_next_action_waits_for_running_pipeline():
    action = voc_run_next_action(
        {
            "status": "RUNNING",
            "selected_count": 35,
            "completed_count": 3,
            "counts": {},
            "judge_counts": {},
        }
    )

    assert action["code"] == "WAIT_PIPELINE"
    assert action["label"] == "파이프라인 완료 대기"
    assert "3/35" in action["detail"]


def test_run_next_action_moves_from_pipeline_success_to_judge():
    action = voc_run_next_action(
        {
            "status": "COMPLETED",
            "selected_count": 1,
            "completed_count": 1,
            "counts": {"PASS": 1, "FAIL": 0, "ERROR": 0, "REVIEW_REQUIRED": 0},
            "judge_counts": {"NOT_RUN": 1},
            "validity_state": "DRAFT",
            "deployment_decision": "미판정",
        }
    )

    assert action["code"] == "RUN_JUDGE"
    assert action["label"] == "독립 Judge 평가"


def test_run_next_action_moves_from_ai_reviewed_to_qa_review():
    action = voc_run_next_action(
        {
            "status": "COMPLETED",
            "selected_count": 1,
            "completed_count": 1,
            "counts": {"PASS": 1, "FAIL": 0, "ERROR": 0, "REVIEW_REQUIRED": 0},
            "judge_counts": {"PASS": 1, "NOT_RUN": 0, "ERROR": 0},
            "validity_state": "AI_REVIEWED",
            "deployment_decision": "HUMAN_REVIEW_REQUIRED",
        }
    )

    assert action["code"] == "QA_REVIEW"
    assert action["label"] == "QA 검토 저장"


def test_case_next_action_covers_approval_flow():
    qa_action = voc_case_next_action(
        {
            "case_id": "TC-01",
            "status": "PASS",
            "judge_status": "PASS",
            "validity_status": "AI_PASS",
            "approval_state": "AI_REVIEWED",
            "formal_approval": False,
        }
    )
    business_action = voc_case_next_action(
        {
            "case_id": "TC-01",
            "status": "PASS",
            "judge_status": "PASS",
            "validity_status": "AI_PASS",
            "approval_state": "QA_REVIEWED",
            "formal_approval": False,
        }
    )
    report_action = voc_case_next_action(
        {
            "case_id": "TC-01",
            "status": "PASS",
            "judge_status": "PASS",
            "validity_status": "AI_PASS",
            "approval_state": "BUSINESS_APPROVED",
            "formal_approval": True,
        }
    )

    assert qa_action["code"] == "QA_REVIEW"
    assert business_action["code"] == "BUSINESS_APPROVAL"
    assert report_action["code"] == "REPORT_READY"
