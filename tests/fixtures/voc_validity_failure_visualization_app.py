from dashboard.pages_top import voc_quality_view as view


rubric = {
    "automatic_decisions": [
        {
            "decision": "AI_PASS",
            "min_score": 80,
            "max_score": 100,
            "requires_all_pass_floors": True,
        }
    ],
    "dimensions": {
        "cause_linkage": {
            "label": "불만 원인과 개선안 연결",
            "max_points": 22,
            "pass_floor": 16,
            "criteria": {},
        },
        "evidence_traceability": {
            "label": "VOC·Trace 근거 추적성",
            "max_points": 22,
            "pass_floor": 14,
            "criteria": {},
        },
    },
}
result = {
    "decision": "REVISION_REQUIRED",
    "workflow_state": "REVISION_REQUIRED",
    "formal_approval": False,
    "total_score": 77,
    "dimension_scores": {
        "cause_linkage": {"score": 17, "reason": "연결 근거 일부 확인"},
        "evidence_traceability": {"score": 10, "reason": "Trace 근거 누락"},
    },
    "immediate_hold_rules_triggered": [
        "missing_voc_or_trace_evidence",
        "judge_error_or_not_run",
    ],
}
artifacts = {"trace": {"trace_id": "", "events": []}}

view._render_validity_result(result, rubric, artifacts)
