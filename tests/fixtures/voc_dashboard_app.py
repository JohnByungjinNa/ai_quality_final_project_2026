from pathlib import Path
import sys
from datetime import date


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top import voc_quality_view


voc_quality_view._load_voc_dashboard_snapshot = lambda: {
    "runtime": {"ok": True, "env_configured": True, "missing": []},
    "agents": {
        "running": 5,
        "total": 6,
        "all_running": False,
        "agents": [
            {"name": "Interpreter", "port": 6101, "status": "RUNNING", "healthy": True, "pid": "101"},
            {"name": "Critic", "port": 6105, "status": "STOPPED", "healthy": False, "pid": ""},
        ],
    },
    "testcases": {"total": 35, "categories": {}},
    "runs": [
        {
            "run_id": "RUN-TEST",
            "run_type": "BATCH",
            "status": "COMPLETED",
            "started_at": f"{date.today().isoformat()}T20:00:00+09:00",
            "selected_count": 35,
            "judge_enabled": True,
            "judge_status": "사용",
            "counts": {"PASS": 30, "REVIEW_REQUIRED": 3, "FAIL": 1, "ERROR": 1, "NOT_RUN": 0},
            "judge_counts": {"PASS": 28, "REVIEW_REQUIRED": 5, "FAIL": 1, "ERROR": 1, "NOT_RUN": 0},
        }
    ],
    "defects": [
        {
            "title": "연결 오류",
            "severity": "HIGH",
            "status": "OPEN",
            "evidence_status": "CONFIRMED",
            "owner": "QA",
            "created_at": f"{date.today().isoformat()}T19:00:00+09:00",
            "related_run_ids": ["RUN-TEST"],
        }
    ],
    "validity_candidates": [
        {
            "run_id": "RUN-TEST",
            "case_id": "TC-01",
            "question": "보험금 청구 진행 상태가 보이지 않습니다.",
            "run_type": "BATCH",
            "judge_status": "PASS",
            "validity_status": "AI_PASS",
            "workflow_state": "AI_REVIEWED",
            "formal_approval": False,
            "immediate_hold_count": 0,
            "validity_score": 91,
            "started_at": f"{date.today().isoformat()}T20:00:00+09:00",
        },
        {
            "run_id": "RUN-TEST",
            "case_id": "TC-02",
            "question": "개선안의 담당 일정 KPI가 부족합니다.",
            "run_type": "BATCH",
            "judge_status": "PASS",
            "validity_status": "REVISION_REQUIRED",
            "workflow_state": "DRAFT",
            "formal_approval": False,
            "immediate_hold_count": 0,
            "validity_score": 67,
            "started_at": f"{date.today().isoformat()}T20:00:00+09:00",
        },
        {
            "run_id": "RUN-TEST",
            "case_id": "TC-03",
            "question": "아직 타당성 평가가 필요합니다.",
            "run_type": "BATCH",
            "judge_status": "PASS",
            "validity_status": "NOT_RUN",
            "workflow_state": "DRAFT",
            "formal_approval": False,
            "immediate_hold_count": 0,
            "started_at": f"{date.today().isoformat()}T20:00:00+09:00",
        },
    ],
    "audit": {"traces": 12, "success": 80, "failure": 2},
    "a2a": {"decision": "FAIL", "reason": "최근 Trace에 연결 실패가 있습니다."},
}

voc_quality_view.render_dashboard()
