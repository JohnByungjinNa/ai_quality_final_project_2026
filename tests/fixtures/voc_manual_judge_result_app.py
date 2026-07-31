from pathlib import Path
import sys

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top.voc_quality_view import _render_goal_judge_result


st.session_state.goal_testcase_result = {
    "case": {"case_id": "TC-01"},
    "judge_result": {
        "decision": "PASS",
        "total_score": 91,
        "provider": "anthropic",
        "model": "claude-opus-4-6",
        "rubric_version": "1.0",
        "independence_grade": "B",
        "duration_seconds": 12.4,
        "evaluation_history": [
            {
                "decision": "REVIEW_REQUIRED",
                "total_score": 78,
                "provider": "openai",
                "model": "gpt-5.2",
                "rubric_version": "1.0",
                "independence_grade": "A",
                "duration_seconds": 9.1,
                "evaluated_at": "2026-07-31T12:00:00+09:00",
            },
        ],
        "dimension_scores": {
            "accuracy": {"score": 23, "reason": "VOC 내용과 일치"},
        },
        "evidence": ["Trace와 요약 내용 일치"],
        "risks": ["표본 범위 확인 필요"],
        "recommendations": ["회귀 테스트 유지"],
    },
}

_render_goal_judge_result("TC-01")
