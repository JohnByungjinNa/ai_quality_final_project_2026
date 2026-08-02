from __future__ import annotations

from collections import Counter
from copy import deepcopy


STATE_MODEL_VERSION = "2026-07-31.step3"
SUITE_ID = "VOC-QA-35"

RUN_TYPES = ("MANUAL", "BATCH", "RETEST", "BASELINE")
RUN_OPERATION_POLICIES = {
    "MANUAL": {
        "label": "수동 단건 수행",
        "basis": "Case 1건을 즉시 실행해 Agent 파이프라인·독립 LLM 평가·개선안 타당성 평가 흐름을 확인합니다.",
        "recommended_when": "개별 Case 디버깅, 시연 전 단건 확인, 개선안 보완 후 빠른 확인",
        "lineage_rule": "동일 Case를 다시 실행해도 과거 Run은 유지되며 새 Run으로 기록합니다.",
        "next_review": "결과가 안정적이면 독립 LLM 평가와 개선안 타당성 평가로 넘깁니다.",
    },
    "BATCH": {
        "label": "검증 회차",
        "basis": "선택한 Case 묶음을 하나의 회차로 실행해 배포 후보 품질을 봅니다.",
        "recommended_when": "35건 전체 회차, 실행 가능 Case 묶음, 릴리즈 전 회귀 검증",
        "lineage_rule": "새 회차이므로 부모 Run 없이 독립 Run으로 기록합니다.",
        "next_review": "회차 기준 통과율, 미실행/후속 구현, 결함, 개선안 타당성 상태를 확인합니다.",
    },
    "RETEST": {
        "label": "보완 후 재시험",
        "basis": "기존 Run에서 발견된 실패·검토 필요 Case를 보완한 뒤 부모 Run과 비교합니다.",
        "recommended_when": "VOC 근거 보강, 개선안 재작성, Agent/프롬프트 수정 후 확인",
        "lineage_rule": "parent_run_id로 원본 Run과 연결되어 전후 비교 대상이 됩니다.",
        "next_review": "부모 Run 대비 개선 여부와 잔여 보완 대상을 확인합니다.",
    },
    "BASELINE": {
        "label": "기준선",
        "basis": "향후 개선 비교를 위해 저장하는 기준 Run입니다.",
        "recommended_when": "초기 기준 수립, Rubric/모델 변경 전 비교점 고정",
        "lineage_rule": "비교 기준으로 사용하며 배포 승인을 직접 의미하지 않습니다.",
        "next_review": "후속 일괄 Run 또는 재시험 Run과 비교합니다.",
    },
    "RUBRIC_REEVALUATION": {
        "label": "Rubric 변경 재평가",
        "basis": "Run 저장 당시 Rubric과 현재 Rubric의 버전 또는 해시가 달라졌는지 확인합니다.",
        "recommended_when": "Rubric 기준 변경 후 과거 Run을 현재 기준으로 다시 판단해야 할 때",
        "lineage_rule": "Agent 파이프라인 실행 결과는 유지하고 평가 기준만 새로 적용하는 재평가 흐름입니다.",
        "next_review": "기준 변경 항목을 확인한 뒤 독립 LLM 평가/개선안 타당성 평가 재평가 여부를 결정합니다.",
    },
}
RUBRIC_VERSION_SCOPES = {
    "internal_pipeline": "내부 파이프라인",
    "independent_judge": "독립 LLM 평가",
    "improvement_validity": "개선안 타당성 평가",
}
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
    "VALIDITY_EVALUATION_REQUIRED": "개선안 타당성 평가 필요",
    "REWORK_REQUIRED": "보완·재시험 필요",
    "QA_REVIEW": "QA 검토 가능",
    "BUSINESS_APPROVAL": "업무 승인 가능",
    "FORMAL_APPROVED": "정식 승인 완료",
    "NO_ACTION": "추가 조치 없음",
}

VOC_STATUS_DISPLAY_LABELS = {
    "PASS": "통과",
    "FAIL": "실패",
    "ERROR": "오류",
    "REVIEW_REQUIRED": "검토 필요",
    "NOT_RUN": "미실행",
    "RUNNING": "진행 중",
    "STARTED": "시작",
    "COMPLETED": "완료",
    "ENDED": "종료",
    "INTERRUPTED": "중단됨",
    "SUCCESS": "성공",
    "DRAFT": "초안",
    "PENDING": "대기",
    "CONFIRMED": "확인됨",
    "OPEN": "접수",
    "ANALYZED": "분석 완료",
    "FIXED": "조치 완료",
    "RETESTED": "재시험 완료",
    "CLOSED": "종결",
    "RESOLVED": "해결",
    "IMPLEMENTED": "실행 구현 완료",
    "DEFINED": "정의됨 · 후속 구현",
    "MANUAL": "수동 수행",
    "BATCH": "일괄 수행",
    "RETEST": "재시험",
    "BASELINE": "기준 회차",
    "VOC": "VOC",
    "FAULT": "장애 시험",
    "AI_PASS": "AI 평가 통과",
    "AI_REVIEWED": "AI 평가 완료",
    "QA_REVIEWED": "QA 검토 완료",
    "REVISION_REQUIRED": "보완 필요",
    "REJECTED": "반려",
    "APPROVE": "승인",
    "APPROVED": "승인 완료",
    "FORMAL_APPROVED": "정식 승인",
    "NOT_APPROVED": "미승인",
    "BUSINESS_APPROVED": "업무 승인 완료",
    "PARTIALLY_APPROVED": "일부 승인",
    "BUSINESS_REVIEW_REQUIRED": "업무 검토 필요",
    "HUMAN_REVIEW_REQUIRED": "QA 검토 필요",
    "REMAINING_CASE_REVIEW_REQUIRED": "잔여 Case 검토 필요",
    "FORMAL_QUALITY_APPROVED": "정식 품질 승인",
    "READY_FOR_UAT": "UAT 준비 완료",
    "HOLD": "보류",
    "EVIDENCE_DRAFT": "증적 초안",
    "NOT_CONFIGURED": "미설정",
    "CONFIGURED": "설정됨",
    "NOT_AVAILABLE": "확인 불가",
    "NOT_EVALUATED": "평가 전",
    "UNKNOWN": "미확인",
    "STOPPED": "중지",
    "STARTING/FAILED": "시작 실패",
    "AUTH_FAILED": "인증 실패",
    "OPENAI_AUTH_FAILED": "OpenAI 인증 실패",
    "CONNECTION_ERROR": "연결 오류",
    "CHECK_ERROR": "점검 오류",
    "PERMISSION_DENIED": "권한 거부",
    "CLIENT_ERROR": "클라이언트 오류",
    "SERVER_ERROR": "서버 오류",
    "RPC_ERROR": "RPC 오류",
    "VALIDITY_EVALUATION_REQUIRED": "개선안 타당성 평가 필요",
    "REWORK_REQUIRED": "보완·재시험 필요",
    "QA_REVIEW": "QA 검토 가능",
    "BUSINESS_APPROVAL": "업무 승인 가능",
    "NO_ACTION": "추가 조치 없음",
    "미판정": "미판정",
}

VOC_NEXT_ACTIONS = {
    "WAIT_PIPELINE": {
        "label": "Agent 파이프라인 완료 대기",
        "menu": "수동/일괄 TC 수행",
        "detail": "현재 실행 중인 회차가 끝날 때까지 진행 상태를 확인합니다.",
        "tone": "blue",
        "icon": "progress_activity",
    },
    "CHECK_PIPELINE_ERROR": {
        "label": "Agent 파이프라인 오류 확인",
        "menu": "수행 이력",
        "detail": "오류 Case의 실행 Trace와 증적을 확인한 뒤 Agent 상태 또는 입력 데이터를 보완합니다.",
        "tone": "red",
        "icon": "error",
    },
    "REVIEW_PIPELINE_RESULT": {
        "label": "Agent 파이프라인 결과 보완",
        "menu": "수행 이력",
        "detail": "실패·검토 필요 Case의 VOC 근거, 기대값, Agent 응답을 확인합니다.",
        "tone": "orange",
        "icon": "rate_review",
    },
    "RUN_JUDGE": {
        "label": "독립 LLM 평가",
        "menu": "수행 이력",
        "detail": "저장된 Agent 파이프라인 결과를 독립 LLM 평가로 재평가해 객관 판정 증적을 만듭니다.",
        "tone": "blue",
        "icon": "rule",
    },
    "RUN_VALIDITY": {
        "label": "개선안 타당성 평가",
        "menu": "개선안 타당성 검증",
        "detail": "Agent 파이프라인 최종 개선안과 독립 LLM 평가 증적을 기준으로 실행 가능성·근거·KPI를 평가합니다.",
        "tone": "blue",
        "icon": "fact_check",
    },
    "REWORK_AND_RETEST": {
        "label": "보완 입력·재시험",
        "menu": "개선안 타당성 검증",
        "detail": "부족한 담당·일정·KPI·근거를 보완하고 필요하면 연결 재시험을 수행합니다.",
        "tone": "red",
        "icon": "edit_note",
    },
    "QA_REVIEW": {
        "label": "QA 검토 저장",
        "menu": "개선안 타당성 검증",
        "detail": "AI_PASS이고 즉시 보류 규칙이 없는 대상에 QA 검토 의견을 저장합니다.",
        "tone": "green",
        "icon": "rate_review",
    },
    "BUSINESS_APPROVAL": {
        "label": "업무 승인 저장",
        "menu": "개선안 타당성 검증",
        "detail": "QA 검토 완료 건을 업무 관점에서 최종 승인합니다.",
        "tone": "green",
        "icon": "verified",
    },
    "CHECK_REMAINING_CASES": {
        "label": "잔여 Case 검토",
        "menu": "개선안 타당성 검증",
        "detail": "일부 승인된 회차의 미승인 Case를 이어서 평가·승인합니다.",
        "tone": "orange",
        "icon": "pending_actions",
    },
    "RUBRIC_REEVALUATE": {
        "label": "Rubric 기준 영향 확인",
        "menu": "수행 이력",
        "detail": "Run 저장 당시 평가 기준과 현재 Rubric이 달라졌습니다. 독립 LLM PASS 확보 목적이 아니라 기존 결과를 보존한 상태에서 기준 변경 영향을 확인합니다.",
        "tone": "orange",
        "icon": "rule_settings",
    },
    "REPORT_READY": {
        "label": "보고서·최종 시연",
        "menu": "품질 보고서 / 최종 인수·시연",
        "detail": "정식 승인 결과를 품질 보고서와 최종 인수·시연 화면에 연결합니다.",
        "tone": "green",
        "icon": "summarize",
    },
    "NO_ACTION": {
        "label": "추가 조치 없음",
        "menu": "수행 이력",
        "detail": "현재 상태에서 즉시 필요한 조치는 없습니다. 상세 증적만 확인하세요.",
        "tone": "gray",
        "icon": "check_circle",
    },
}

EXECUTABLE_IMPLEMENTATION_STATUS = "IMPLEMENTED"
VOC_EVALUATION_EXECUTION_TYPES = {"voc_pipeline"}
FAULT_VERIFICATION_EXECUTION_TYPES = {"fault_proxy", "isolated_fault"}

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


def voc_status_label(value, default: str = "-") -> str:
    """Return the Korean display label for a persisted VOC status code."""
    if value is None:
        return default
    text = str(value)
    return VOC_STATUS_DISPLAY_LABELS.get(
        text,
        VOC_STATUS_DISPLAY_LABELS.get(text.upper(), text),
    )


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _action_payload(action: str, *, detail: str | None = None) -> dict:
    payload = deepcopy(VOC_NEXT_ACTIONS.get(action, VOC_NEXT_ACTIONS["NO_ACTION"]))
    payload["code"] = action
    if detail:
        payload["detail"] = detail
    return payload


def _case_judge_action(case_result: dict) -> dict | None:
    judge_status = str(case_result.get("judge_status") or "NOT_RUN")
    if judge_status == "ERROR":
        return _action_payload(
            "RUN_JUDGE",
            detail="독립 LLM 평가가 오류로 끝났습니다. Provider/API Key 상태를 확인한 뒤 재평가합니다.",
        )
    if judge_status == "NOT_RUN":
        return _action_payload(
            "RUN_JUDGE",
            detail="Agent 파이프라인 결과는 있으나 독립 LLM 평가 증적이 없습니다. 저장된 결과 재평가를 실행합니다.",
        )
    if judge_status in {"FAIL", "REVIEW_REQUIRED"}:
        return _action_payload(
            "REVIEW_PIPELINE_RESULT",
            detail=f"독립 LLM 평가 판정이 {voc_status_label(judge_status)}입니다. 판정 근거와 개선안을 확인합니다.",
        )
    return None


def voc_case_next_action(case_result: dict) -> dict:
    """Return the next user-facing action for a single Case result."""
    status = str(case_result.get("status") or "NOT_RUN")
    if status == "NOT_RUN":
        return _action_payload(
            "WAIT_PIPELINE",
            detail="아직 실행 결과가 없습니다. 후속 구현 대상이면 구현 후 재실행하고, 실행 가능 대상이면 Batch/수동 실행을 진행합니다.",
        )
    if status == "ERROR":
        return _action_payload(
            "CHECK_PIPELINE_ERROR",
            detail=case_result.get("message") or "파이프라인 실행 오류가 발생했습니다. Case 증적과 Agent 로그를 확인합니다.",
        )
    if status in {"FAIL", "REVIEW_REQUIRED"}:
        return _action_payload(
            "REVIEW_PIPELINE_RESULT",
            detail=case_result.get("message") or f"Case 상태가 {voc_status_label(status)}입니다. VOC 근거와 기대값을 확인합니다.",
        )

    judge_action = _case_judge_action(case_result)
    if judge_action:
        return judge_action

    validity_status = str(case_result.get("validity_status") or "NOT_RUN")
    workflow_state = str(case_result.get("approval_state") or "DRAFT")
    formal_approval = bool(case_result.get("formal_approval"))
    readiness = validity_human_review_readiness(
        validity_status=validity_status,
        workflow_state=workflow_state,
        immediate_hold_count=_as_int(case_result.get("immediate_hold_count")),
        formal_approval=formal_approval,
    )
    action = readiness["action"]
    if action == "VALIDITY_EVALUATION_REQUIRED":
        return _action_payload("RUN_VALIDITY")
    if action == "REWORK_REQUIRED":
        return _action_payload("REWORK_AND_RETEST")
    if action == "QA_REVIEW":
        return _action_payload("QA_REVIEW")
    if action == "BUSINESS_APPROVAL":
        return _action_payload("BUSINESS_APPROVAL")
    if action == "FORMAL_APPROVED":
        return _action_payload("REPORT_READY")
    return _action_payload("NO_ACTION")


def voc_run_next_action(run: dict) -> dict:
    """Return the next user-facing action for a Run summary row."""
    status = str(run.get("status") or "DRAFT")
    selected_count = _as_int(run.get("selected_count"), len(run.get("selected_case_ids") or []))
    counts = run.get("counts") or {}
    judge_counts = run.get("judge_counts") or {}
    completed_count = _as_int(
        run.get("completed_count"),
        sum(_as_int(counts.get(status_key)) for status_key in CASE_EXECUTION_STATUSES),
    )

    if status == "RUNNING":
        return _action_payload(
            "WAIT_PIPELINE",
            detail=f"현재 {completed_count}/{selected_count or '-'}건 처리 중입니다. 실행 화면 또는 진행 팝업에서 상태를 확인합니다.",
        )
    if status in {"ERROR", "INTERRUPTED"}:
        return _action_payload(
            "CHECK_PIPELINE_ERROR",
            detail=f"Run 상태가 {voc_status_label(status)}입니다. 실패 Case와 Run 증적 ZIP을 먼저 확인합니다.",
        )
    if bool(run.get("reevaluation_required")):
        rubric_labels = str(run.get("rubric_changed_labels") or "").strip()
        detail = "현재 Rubric 기준이 Run 저장 당시와 달라 재평가 영향 확인이 필요합니다."
        if rubric_labels and rubric_labels != "-":
            detail = f"{rubric_labels} 기준이 변경되어 현재 기준 재평가 여부를 확인합니다."
        return _action_payload("RUBRIC_REEVALUATE", detail=detail)

    error_count = _as_int(counts.get("ERROR"))
    fail_count = _as_int(counts.get("FAIL"))
    review_count = _as_int(counts.get("REVIEW_REQUIRED"))
    pass_count = _as_int(counts.get("PASS"))
    judge_error = _as_int(judge_counts.get("ERROR"))
    judge_missing = _as_int(judge_counts.get("NOT_RUN"))

    if error_count:
        return _action_payload(
            "CHECK_PIPELINE_ERROR",
            detail=f"오류 Case {error_count}건이 있습니다. Case 증적과 Agent 로그를 확인합니다.",
        )
    if fail_count or review_count:
        return _action_payload(
            "REVIEW_PIPELINE_RESULT",
            detail=f"실패 {fail_count}건 · 검토 필요 {review_count}건입니다. VOC 근거/기대값 보완 후 재시험을 검토합니다.",
        )
    if judge_error:
        return _action_payload(
            "RUN_JUDGE",
            detail=f"독립 LLM 평가 오류 {judge_error}건이 있습니다. Provider/API Key 상태 확인 후 재평가합니다.",
        )
    if pass_count and judge_missing:
        return _action_payload(
            "RUN_JUDGE",
            detail=f"Agent 파이프라인 통과 Case 중 독립 LLM 평가 미수행 대상이 있습니다. 독립 LLM 평가 증적을 먼저 만듭니다.",
        )

    validity_state = str(run.get("validity_state") or "DRAFT")
    deployment_decision = str(run.get("deployment_decision") or "미판정")

    if deployment_decision == "FORMAL_QUALITY_APPROVED" or validity_state == "BUSINESS_APPROVED":
        return _action_payload("REPORT_READY")
    if validity_state == "PARTIALLY_APPROVED" or deployment_decision == "REMAINING_CASE_REVIEW_REQUIRED":
        return _action_payload("CHECK_REMAINING_CASES")
    if validity_state == "QA_REVIEWED" or deployment_decision == "BUSINESS_REVIEW_REQUIRED":
        return _action_payload("BUSINESS_APPROVAL")
    if validity_state == "AI_REVIEWED" or deployment_decision == "HUMAN_REVIEW_REQUIRED":
        return _action_payload("QA_REVIEW")
    if validity_state in {"REVISION_REQUIRED", "REJECTED"} or deployment_decision in {"REVISION_REQUIRED", "REJECTED"}:
        return _action_payload("REWORK_AND_RETEST")
    if pass_count and validity_state in {"DRAFT", "NOT_RUN", "NOT_EVALUATED"}:
        return _action_payload("RUN_VALIDITY")
    return _action_payload("NO_ACTION")


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
    voc_case_ids = []
    fault_case_ids = []
    pending_case_ids = []

    for item in cases:
        case_id = str(item.get("case_id") or "")
        if not case_id:
            continue
        execution_type = str(item.get("execution_type") or "defined_only")
        execution_types[execution_type] += 1
        implementation_status = str(item.get("implementation_status") or "DEFINED")
        implementation_statuses[implementation_status] += 1
        if implementation_status == EXECUTABLE_IMPLEMENTATION_STATUS:
            executable_case_ids.append(case_id)
            if execution_type in VOC_EVALUATION_EXECUTION_TYPES:
                voc_case_ids.append(case_id)
            elif execution_type in FAULT_VERIFICATION_EXECUTION_TYPES:
                fault_case_ids.append(case_id)
        else:
            pending_case_ids.append(case_id)

    return {
        "total_cases": len([item for item in cases if item.get("case_id")]),
        "execution_type_counts": dict(sorted(execution_types.items())),
        "implementation_status_counts": dict(sorted(implementation_statuses.items())),
        "executable_case_ids": executable_case_ids,
        "voc_case_ids": voc_case_ids,
        "fault_case_ids": fault_case_ids,
        "pending_case_ids": pending_case_ids,
        "executable_count": len(executable_case_ids),
        "voc_count": len(voc_case_ids),
        "fault_count": len(fault_case_ids),
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
        "voc_case_ids": selected_summary["voc_case_ids"],
        "fault_case_ids": selected_summary["fault_case_ids"],
        "judge_required_case_ids": selected_summary["voc_case_ids"],
        "validity_required_case_ids": selected_summary["voc_case_ids"],
        "pending_case_ids": selected_summary["pending_case_ids"],
        "executable_count": selected_summary["executable_count"],
        "voc_count": selected_summary["voc_count"],
        "fault_count": selected_summary["fault_count"],
        "pending_count": selected_summary["pending_count"],
        "execution_type_counts": selected_summary["execution_type_counts"],
        "implementation_status_counts": selected_summary["implementation_status_counts"],
    }


def _rubric_version_value(version: dict | None, field: str) -> str:
    if not isinstance(version, dict):
        return ""
    return str(version.get(field) or "")


def rubric_version_drift(
    stored_versions: dict | None,
    current_versions: dict | None,
) -> dict:
    """Compare Run-snapshot Rubric versions with current Rubric versions."""
    stored = stored_versions if isinstance(stored_versions, dict) else {}
    current = current_versions if isinstance(current_versions, dict) else {}
    items = []
    for scope, label in RUBRIC_VERSION_SCOPES.items():
        stored_payload = stored.get(scope) if isinstance(stored.get(scope), dict) else {}
        current_payload = current.get(scope) if isinstance(current.get(scope), dict) else {}
        stored_version = _rubric_version_value(stored_payload, "version")
        current_version = _rubric_version_value(current_payload, "version")
        stored_sha256 = _rubric_version_value(stored_payload, "sha256")
        current_sha256 = _rubric_version_value(current_payload, "sha256")
        stored_missing = not bool(stored_payload)
        current_missing = not bool(current_payload)
        changed = (
            not stored_missing
            and not current_missing
            and (
                stored_version != current_version
                or (
                    bool(stored_sha256)
                    and bool(current_sha256)
                    and stored_sha256 != current_sha256
                )
            )
        )
        requires_reevaluation = changed or (stored_missing and not current_missing)
        needs_attention = requires_reevaluation or current_missing
        if changed:
            status = "변경됨"
            reason = "저장 당시 Rubric과 현재 Rubric의 버전 또는 해시가 다릅니다."
        elif stored_missing and not current_missing:
            status = "Run 기준 없음"
            reason = "이전 Run에 Rubric 스냅샷 정보가 없어 현재 기준과 동일성을 보장할 수 없습니다."
        elif current_missing:
            status = "현재 기준 확인 불가"
            reason = "현재 Rubric 정보를 읽지 못해 기준 변경 여부를 확인할 수 없습니다."
        else:
            status = "동일"
            reason = "저장 당시 Rubric과 현재 Rubric이 동일합니다."
        items.append(
            {
                "scope": scope,
                "label": label,
                "stored_version": stored_version or "-",
                "current_version": current_version or "-",
                "stored_sha256": stored_sha256,
                "current_sha256": current_sha256,
                "status": status,
                "reason": reason,
                "changed": changed,
                "requires_reevaluation": requires_reevaluation,
                "needs_attention": needs_attention,
            }
        )

    reevaluation_items = [item for item in items if item["requires_reevaluation"]]
    attention_items = [item for item in items if item["needs_attention"]]
    if reevaluation_items:
        status = "재평가 필요"
        tone = "red"
        detail = "기준이 바뀐 평가 항목은 현재 Rubric으로 다시 판단해야 합니다."
    elif attention_items:
        status = "확인 필요"
        tone = "orange"
        detail = "현재 Rubric 정보를 확인한 뒤 재평가 여부를 결정해야 합니다."
    else:
        status = "기준 동일"
        tone = "green"
        detail = "Run 저장 당시 기준과 현재 기준이 동일합니다."
    return {
        "status": status,
        "tone": tone,
        "detail": detail,
        "requires_reevaluation": bool(reevaluation_items),
        "needs_attention": bool(attention_items),
        "changed_count": len(reevaluation_items),
        "attention_count": len(attention_items),
        "changed_scopes": [item["scope"] for item in reevaluation_items],
        "changed_labels": [item["label"] for item in reevaluation_items],
        "items": items,
        "policy": deepcopy(RUN_OPERATION_POLICIES["RUBRIC_REEVALUATION"]),
    }


def run_lineage_policy(run: dict | None) -> dict:
    """Return the business policy for a Run's execution lineage."""
    payload = run if isinstance(run, dict) else {}
    run_type = str(payload.get("run_type") or "MANUAL")
    if run_type not in RUN_OPERATION_POLICIES:
        run_type = "MANUAL"
    policy = deepcopy(RUN_OPERATION_POLICIES[run_type])
    parent_run_id = str(payload.get("parent_run_id") or "")
    selected_count = _as_int(payload.get("selected_count"), len(payload.get("selected_case_ids") or []))
    policy.update(
        {
            "run_type": run_type,
            "parent_run_id": parent_run_id,
            "selected_count": selected_count,
            "has_parent": bool(parent_run_id),
        }
    )
    if run_type == "RETEST" and not parent_run_id:
        policy["lineage_rule"] = "재시험으로 표시되었지만 parent_run_id가 없어 원본 Run 연결 확인이 필요합니다."
    return policy


def build_state_model_snapshot(cases: list[dict], selected_case_ids: list[str]) -> dict:
    return {
        "model_version": STATE_MODEL_VERSION,
        "suite_id": SUITE_ID,
        "run_types": list(RUN_TYPES),
        "run_operation_policies": deepcopy(RUN_OPERATION_POLICIES),
        "rubric_version_scopes": deepcopy(RUBRIC_VERSION_SCOPES),
        "run_lifecycle_statuses": list(RUN_LIFECYCLE_STATUSES),
        "case_execution_statuses": list(CASE_EXECUTION_STATUSES),
        "judge_statuses": list(JUDGE_STATUSES),
        "validity_statuses": list(VALIDITY_STATUSES),
        "validity_workflow_states": list(VALIDITY_WORKFLOW_STATES),
        "deployment_decisions": list(DEPLOYMENT_DECISIONS),
        "validity_review_actions": list(VALIDITY_REVIEW_ACTIONS),
        "status_display_labels": deepcopy(VOC_STATUS_DISPLAY_LABELS),
        "next_actions": deepcopy(VOC_NEXT_ACTIONS),
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
