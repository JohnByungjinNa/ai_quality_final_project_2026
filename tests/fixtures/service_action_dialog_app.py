import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for path in (PROJECT_ROOT, DASHBOARD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pages_top import service_management


st.session_state.setdefault(
    "service_pending_action",
    {
        "service_id": "fastapi",
        "service_name": "FastAPI",
        "action": "시작",
        "mode": "local",
    },
)
service_management.render_service_action_dialog(st.session_state.service_pending_action)
