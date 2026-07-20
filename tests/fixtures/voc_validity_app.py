from dashboard.pages_top import voc_quality_view as view


view.list_improvement_validity_candidates = lambda: [
    {
        "run_id": "RUN-20260716-120000-000000-abcd",
        "case_id": "TC-01",
        "started_at": "2026-07-16T12:00:00+09:00",
        "run_type": "MANUAL",
        "question": "VOC 질문",
        "judge_status": "PASS",
        "judge_score": 90,
        "validity_status": "NOT_RUN",
        "validity_score": None,
        "workflow_state": "DRAFT",
        "formal_approval": False,
    },
    {
        "run_id": "RUN-20260716-130000-000000-efgh",
        "case_id": "TC-02",
        "started_at": "2026-07-16T13:00:00+09:00",
        "run_type": "BATCH",
        "question": "두 번째 VOC 질문",
        "judge_status": "PASS",
        "judge_score": 94,
        "validity_status": "AI_PASS",
        "validity_score": 92,
        "workflow_state": "AI_REVIEWED",
        "formal_approval": False,
    },
]
view.load_voc_case_history_detail = lambda _run_id, case_id: {
    "pipeline_result": {
        "execution": {
            "question": "VOC 질문" if case_id == "TC-01" else "두 번째 VOC 질문",
            "result": {
                "ok": True,
                "summary": "VOC 근거 요약",
                "policy": "담당·일정·KPI가 포함된 개선안",
            },
        }
    },
    "judge_result": {
        "decision": "PASS",
        "total_score": 90 if case_id == "TC-01" else 94,
        "independence_grade": "B",
        "provider": "anthropic",
        "model": "judge-model",
    },
    "validity_result": (
        {}
        if case_id == "TC-01"
        else {
            "decision": "AI_PASS",
            "total_score": 92,
            "workflow_state": "AI_REVIEWED",
            "formal_approval": False,
            "dimension_scores": {},
        }
    ),
    "trace": {
        "trace_id": "trace-validity",
        "events": [
            {
                "source": "Retriever",
                "target": "Summarizer",
                "status": "success",
                "duration_ms": 120,
            }
        ],
    },
}
view.validity_provider_options = lambda: [
    {
        "provider": "anthropic",
        "label": "Anthropic",
        "default_model": "validity-model",
        "credential_configured": True,
    }
]
view._load_validity_candidates.clear()
view.render_improvement_validity()
