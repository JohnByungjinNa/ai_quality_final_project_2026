from datetime import datetime, timedelta
from pathlib import Path
import sys

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top import voc_quality_view as view


RUN_ID = "RUN-20260717-001000-000001-abcd"
started_at = datetime.now().astimezone() - timedelta(seconds=90)
st.session_state[f"voc_batch_initial_estimate_{RUN_ID}"] = 180
view.get_batch_run_progress = lambda _run_id: {
    "run_id": RUN_ID,
    "run_dir": "reports/voc_quality_runs/test",
    "status": "RUNNING",
    "started_at": started_at.isoformat(),
    "finished_at": "",
    "total": 4,
    "completed": 2,
    "counts": {"REVIEW_REQUIRED": 2, "FAIL": 0, "ERROR": 0, "NOT_RUN": 0},
    "judge_counts": {},
    "case_results": [],
    "stop_requested": False,
    "judge_config": {"enabled": False},
    "errors": [],
}

view._render_batch_progress_dialog(RUN_ID)
