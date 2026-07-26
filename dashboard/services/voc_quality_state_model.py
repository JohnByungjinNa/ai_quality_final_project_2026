from __future__ import annotations

from collections import Counter
from copy import deepcopy


STATE_MODEL_VERSION = "2026-07-26.step3"
SUITE_ID = "VOC-QA-35"

RUN_TYPES = ("MANUAL", "BATCH", "RETEST", "BASELINE")
RUN_LIFECYCLE_STATUSES = ("RUNNING", "COMPLETED", "ERROR", "INTERRUPTED")
CASE_EXECUTION_STATUSES = ("PASS", "FAIL", "ERROR", "NOT_RUN", "REVIEW_REQUIRED")
JUDGE_STATUSES = ("PASS", "FAIL", "REVIEW_REQUIRED", "ERROR", "NOT_RUN")
VALIDITY_STATUSES = ("AI_PASS", "AI_REVIEWED", "ERROR", "REVISION_REQUIRED", "NOT_RUN")
VALIDITY_WORKFLOW_STATES = (
    "DRAFT",
    "AI_REVIEWED",
    "QA_REVIEWED",
    "BUSINESS_APPROVED",
    "PARTIALLY_APPROVED",
    "REVISION_REQUIRED",
    "REJECTED",
)
DEPLOYMENT_DECISIONS = (
    "NOT_EVALUATED",
    "HUMAN_REVIEW_REQUIRED",
    "BUSINESS_REVIEW_REQUIRED",
    "FORMAL_QUALITY_APPROVED",
    "REMAINING_CASE_REVIEW_REQUIRED",
    "REVISION_REQUIRED",
    "REJECTED",
)
VALIDITY_REVIEW_ACTIONS = (
    "VALIDITY_EVALUATION_REQUIRED",
    "REWORK_REQUIRED",
    "QA_REVIEW",
    "BUSINESS_APPROVAL",
    "FORMAL_APPROVED",
    "NO_ACTION",
)
VALIDITY_REVIEW_ACTION_LABELS = {
    "VALIDITY_EVALUATION_REQUIRED": "타당성 평가 필요",
    "REWORK_REQUIRED": "보완/RETEST 필요",
    "QA_REVIEW": "QA 검토 가능",
    "BUSINESS_APPROVAL": "업무 승인 가능",
    "FORMAL_APPROVED": "정식 승인 완료",
    "NO_ACTION": "추가 조치 없음",
}

EXECUTABLE_IMPLEMENTATION_STATUS = "IMPLEMENTED"

MENU_IO_SPEC = {
    "batch_execution": {
        "menu": "일괄 TC 수행",
        "inputs": [
            "quality_test_catalog.json cases[]",
            "case_ids",
            "judge_config",
            "timeout_seconds",
            "max_retries",
            "parent_run_id",
        ],
        "outputs": [
            "manifest.json",
            "summary.json",
            "cases/<case_id>/pipeline_result.json",
            "cases/<case_id>/trace.json",
            "cases/<case_id>/rule_result.json",
            "cases/<case_id>/judge_result.json when enabled",
        ],
        "state_owner": "run_id",
    },
    "execution_history": {
        "menu": "수행 이력",
        "inputs": [
            "reports/voc_quality_runs/index.json",
            "manifest.json",
            "summary.json",
            "case artifacts",
        ],
        "outputs": [
            "run list",
            "run detail",
            "case evidence detail",
            "run evidence zip",
            "retest run request",
        ],
        "state_owner": "run_id",
    },
    "improvement_validity": {
        "menu": "개선안 타당성 검증",
        "inputs": [
            "completed VOC pipeline case",
            "pipeline_result.json",
            "trace.json",
            "judge_result.json",
            "improvement_validity_rubric.json",
        ],
        "outputs": [
            "validity_result.json",
            "summary.case_results[].validity_status",
            "summary.validity_state",
            "summary.deployment_decision",
            "human_reviews[]",
        ],
        "state_owner": "run_id + case_id",
    },
}


def normalize_case_status(value: str | None, *, default: str = "ERROR") -> str:
    status = str(value or default)
    return status if status in CASE_EXECUTION_STATUSES else default


def catalog_case_index(cases: list[dict]) -> dict[str, dict]:
    return {
        str(item.get("case_id")): deepcopy(item)
        for item in cases
        if item.get("case_id")
    }


def classify_catalog_cases(cases: list[dict]) -> dict:
    execution_types = Counter()
    implementation_statuses = Counter()
    executable_case_ids = []
    pending_case_ids = []

    for item in cases:
        case_id = str(item.get("case_id") or "")
        if not case_id:
            continue
        execution_types[str(item.get("execution_type") or "defined_only")] += 1
        implementation_status = str(item.get("implementation_status") or "DEFINED")
        implementation_statuses[implementation_status] += 1
        if implementation_status == EXECUTABLE_IMPLEMENTATION_STATUS:
            executable_case_ids.append(case_id)
        else:
            pending_case_ids.append(case_id)

    return {
        "total_cases": len([item for item in cases if item.get("case_id")]),
        "execution_type_counts": dict(sorted(execution_types.items())),
        "implementation_status_counts": dict(sorted(implementation_statuses.items())),
        "executable_case_ids": executable_case_ids,
        "pending_case_ids": pending_case_ids,
        "executable_count": len(executable_case_ids),
        "pending_count": len(pending_case_ids),
    }


def build_verification_scope(cases: list[dict], selected_case_ids: list[str]) -> dict:
    indexed = catalog_case_index(cases)
    selected = [str(case_id) for case_id in selected_case_ids]
    unknown = [case_id for case_id in selected if case_id not in indexed]
    selected_cases = [indexed[case_id] for case_id in selected if case_id in indexed]
    selected_summary = classify_catalog_cases(selected_cases)
    catalog_summary = classify_catalog_cases(list(indexed.values()))
    return {
        "model_version": STATE_MODEL_VERSION,
        "suite_id": SUITE_ID,
        "catalog_total_cases": catalog_summary["total_cases"],
        "selected_case_ids": selected,
        "selected_count": len(selected),
        "unknown_case_ids": unknown,
        "executable_case_ids": selected_summary["executable_case_ids"],
        "pending_case_ids": selected_summary["pending_case_ids"],
        "executable_count": selected_summary["executable_count"],
        "pending_count": selected_summary["pending_count"],
        "execution_type_counts": selected_summary["execution_type_counts"],
        "implementation_status_counts": selected_summary["implementation_status_counts"],
    }


def build_state_model_snapshot(cases: list[dict], selected_case_ids: list[str]) -> dict:
    return {
        "model_version": STATE_MODEL_VERSION,
        "suite_id": SUITE_ID,
        "run_types": list(RUN_TYPES),
        "run_lifecycle_statuses": list(RUN_LIFECYCLE_STATUSES),
        "case_execution_statuses": list(CASE_EXECUTION_STATUSES),
        "judge_statuses": list(JUDGE_STATUSES),
        "validity_statuses": list(VALIDITY_STATUSES),
        "validity_workflow_states": list(VALIDITY_WORKFLOW_STATES),
        "deployment_decisions": list(DEPLOYMENT_DECISIONS),
        "validity_review_actions": list(VALIDITY_REVIEW_ACTIONS),
        "verification_scope": build_verification_scope(cases, selected_case_ids),
        "menu_io": deepcopy(MENU_IO_SPEC),
    }


def validity_human_review_readiness(
    *,
    validity_status: str | None,
    workflow_state: str | None,
    immediate_hold_count: int = 0,
    formal_approval: bool = False,
) -> dict:
    """Return the next human approval action after automatic validity evaluation."""
    status = str(validity_status or "NOT_RUN")
    state = str(workflow_state or "DRAFT")
    hold_count = int(immediate_hold_count or 0)

    if formal_approval or state == "BUSINESS_APPROVED":
        action = "FORMAL_APPROVED"
        can_qa_review = False
        can_business_approve = False
        deployment_decision = "FORMAL_QUALITY_APPROVED"
    elif status == "NOT_RUN" or state == "DRAFT":
        action = "VALIDITY_EVALUATION_REQUIRED"
        can_qa_review = False
        can_business_approve = False
        deployment_decision = "NOT_EVALUATED"
    elif status != "AI_PASS" or hold_count:
        action = "REWORK_REQUIRED"
        can_qa_review = False
        can_business_approve = False
        deployment_decision = "REVISION_REQUIRED"
    elif state == "AI_REVIEWED":
        action = "QA_REVIEW"
        can_qa_review = True
        can_business_approve = False
        deployment_decision = "HUMAN_REVIEW_REQUIRED"
    elif state == "QA_REVIEWED":
        action = "BUSINESS_APPROVAL"
        can_qa_review = False
        can_business_approve = True
        deployment_decision = "BUSINESS_REVIEW_REQUIRED"
    elif state in {"REVISION_REQUIRED", "REJECTED"}:
        action = "REWORK_REQUIRED"
        can_qa_review = False
        can_business_approve = False
        deployment_decision = state
    else:
        action = "NO_ACTION"
        can_qa_review = False
        can_business_approve = False
        deployment_decision = "NOT_EVALUATED"

    return {
        "action": action,
        "action_label": VALIDITY_REVIEW_ACTION_LABELS[action],
        "can_qa_review": can_qa_review,
        "can_business_approve": can_business_approve,
        "deployment_decision": deployment_decision,
        "validity_status": status,
        "workflow_state": state,
        "immediate_hold_count": hold_count,
        "formal_approval": bool(formal_approval),
    }
