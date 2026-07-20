from pathlib import Path
import sys

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top import voc_quality_view as view


view.runtime_health = lambda: {"env_configured": True}
view._load_agent_management_snapshot = lambda: {
    "total": 6,
    "running": 5,
    "agents": [
        {
            "key": key,
            "name": name,
            "port": 6100 + index,
            "pid": str(100 + index) if index < 6 else "-",
            "status": "RUNNING" if index < 6 else "STOPPED",
            "healthy": index < 6,
            "started_at": f"2026-07-17T14:00:0{index}+09:00" if index < 6 else "",
        }
        for index, (key, name) in enumerate(
            (
                ("interpreter", "Interpreter"),
                ("retriever", "Retriever"),
                ("summarizer", "Summarizer"),
                ("evaluator", "Evaluator"),
                ("critic", "Critic"),
                ("improver", "Improver"),
            ),
            start=1,
        )
    ],
}
view._show_command_result = lambda **_: None

view.render_agents()
