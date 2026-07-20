from dashboard.pages_top import voc_quality_view as view


CANDIDATE = {
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
}

view.load_voc_case_history_detail = lambda *_args: {
    "pipeline_result": {
        "execution": {
            "question": "두 번째 VOC 질문",
            "result": {
                "ok": True,
                "summary": "VOC 근거 요약",
                "policy": "담당·일정·KPI가 포함된 개선안",
            },
        }
    },
    "judge_result": {
        "decision": "PASS",
        "total_score": 94,
        "independence_grade": "B",
        "provider": "anthropic",
        "model": "judge-model",
    },
    "validity_result": {
        "decision": "AI_PASS",
        "total_score": 92,
        "workflow_state": "AI_REVIEWED",
        "formal_approval": False,
    },
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

view._render_validity_candidate_dialog(CANDIDATE)
