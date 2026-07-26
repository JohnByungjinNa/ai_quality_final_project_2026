from pathlib import Path
import sys

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top.voc_quality_view import _render_goal_testcase_result


st.session_state.goal_testcase_result = {
    "mode": "voc",
    "case": {"case_id": "TC-01", "question": "보험금 청구 진행 상태가 앱에 표시되지 않습니다."},
    "run_id": "RUN-TEST",
    "evidence_status": "REVIEW_REQUIRED",
    "execution": {
        "result": {
            "ok": True,
            "message": "Pipeline completed via agent-to-agent calls",
            "summary": "VOC 요약",
            "policy": "0.용어 정의\n- 청구 진행 상태: 보험금 청구 처리 단계\n1. 앱 표시 개선\n- 청구 진행 상태를 앱에 표시합니다.",
            "intent_json": '{"task":"both","filters":["앱 오류","보험 갱신"],"max_items":30}',
            "eval_json": '{"S0":9.1,"S1":8.4,"S2":7.6}',
            "summary_critic_json": '{"need_refine":true,"edits":["오류 영향과 측정 지표를 구체화하세요."],"ask_more_samples":true}',
            "trace": "audit_trace_id=trace-test; retrieved=8; winner=S0; summary_refined; policy_refined; policy_received",
        }
    },
    "trace": {
        "trace_id": "trace-test",
        "events": [
            {
                "source": "Orchestrator",
                "target": "Interpreter",
                "operation": "ParseQuestion",
                "status": "success",
                "duration_ms": 120.5,
                "output_keywords": ["task", "filters", "앱 오류"],
            },
            {
                "source": "Summarizer",
                "target": "Retriever",
                "operation": "Retrieve",
                "status": "success",
                "duration_ms": 15.2,
                "item_count": 8,
                "output_keywords": ["보험", "갱신"],
            },
        ],
    },
}

_render_goal_testcase_result("TC-01")
