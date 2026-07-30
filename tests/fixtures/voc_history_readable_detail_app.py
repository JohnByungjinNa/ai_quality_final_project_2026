from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top.voc_quality_view import (
    _render_history_case_artifact,
    _render_history_execution_info,
)


RUN_ID = "RUN-20260730-120000-000001-demo"
CASE_ID = "TC-01"
manifest = {
    "run_id": RUN_ID,
    "run_type": "MANUAL",
    "status": "COMPLETED",
    "started_at": "2026-07-30T12:00:00+09:00",
    "finished_at": "2026-07-30T12:01:08+09:00",
    "suite_id": "VOC-QA-35",
    "catalog_version": "1.0",
    "selected_case_ids": [CASE_ID],
    "rubric_versions": {
        "internal_pipeline": {"version": "A2A1.5", "sha256": "a" * 64},
        "independent_judge": {"version": "J1.5", "sha256": "b" * 64},
    },
    "model_snapshot": {
        "summary": {"provider": "openai", "model": "gpt-test", "credential_configured": True},
        "judge": {"provider": "gemini", "model": "gemini-test", "enabled": True},
    },
    "environment_fingerprint": {
        "python_version": "3.12",
        "operating_system": "Windows",
        "fingerprint_sha256": "c" * 64,
    },
}
summary = {"deployment_decision": "HUMAN_REVIEW_REQUIRED"}
artifacts = {
    "pipeline_result": {
        "run_id": RUN_ID,
        "case_id": CASE_ID,
        "mode": "voc",
        "recorded_at": "2026-07-30T12:01:08+09:00",
        "execution": {
            "ok": True,
            "question": "모바일 갱신 오류를 개선해 주세요.",
            "result": {
                "ok": True,
                "summary": "VOC 오류 원인과 영향을 요약했습니다.",
                "policy": "담당 조직과 KPI를 포함한 개선안입니다.",
                "trace": "trace-demo",
            },
            "reports": {"json": "report.json", "markdown": "report.md"},
        },
    },
    "trace": {
        "trace_id": "trace-demo",
        "events": [
            {
                "source": "Orchestrator",
                "target": "Interpreter",
                "status": "success",
                "duration_ms": 120,
                "message": "질문 해석 완료",
            }
        ],
    },
    "rule_result": {
        "status": "REVIEW_REQUIRED",
        "rubric_id": "VOC-INTERNAL-PIPELINE-100",
        "rubric_version": "A2A1.5",
        "message": "사람 검토가 필요합니다.",
    },
    "judge_result": {
        "decision": "PASS",
        "total_score": 91,
        "independence_grade": "A",
        "provider": "gemini",
        "model": "gemini-test",
        "rubric_version": "J1.5",
        "duration_seconds": 3.2,
        "dimension_scores": {
            "accuracy": {"score": 23, "max_points": 25, "reason": "VOC 근거와 일치합니다."}
        },
        "evidence": ["VOC와 Trace가 연결되었습니다."],
        "risks": ["운영 확인이 필요합니다."],
        "recommendations": ["KPI를 추적하세요."],
    },
    "validity_result": {
        "decision": "AI_PASS",
        "total_score": 84,
        "workflow_state": "QA_REVIEWED",
        "formal_approval": False,
        "provider": "anthropic",
        "model": "claude-test",
        "rubric_version": "RB1.5",
        "dimension_scores": {
            "feasibility": {"score": 18, "max_points": 20, "reason": "적용 계획이 구체적입니다."}
        },
        "recommendations": ["업무 승인 후 단계 배포하세요."],
        "human_reviews": [
            {
                "reviewer_role": "QA",
                "reviewer_name_or_id": "테스터",
                "decision": "APPROVE",
                "comment": "증적을 확인했습니다.",
                "reviewed_at": "2026-07-30T12:05:00+09:00",
            }
        ],
    },
}

_render_history_execution_info(manifest, summary)
for artifact_name in artifacts:
    _render_history_case_artifact(
        artifact_name,
        artifacts,
        run_id=RUN_ID,
        case_id=CASE_ID,
    )
