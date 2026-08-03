import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
for path in (PROJECT_ROOT, DASHBOARD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from components.integration_status import render_integration_status


render_integration_status(
    {
        "aws": {
            "authenticated": True,
            "profile": "JohnNa-QA",
            "region": "ap-northeast-2",
            "session_status": "authenticated",
        },
        "ai": {
            "configured_count": 2,
            "total_count": 3,
            "providers": [
                {"name": "OpenAI", "configured": True, "status": "설정됨 · 호출 전 검증 필요"},
                {"name": "Anthropic", "configured": False, "status": "미설정"},
                {"name": "Gemini", "configured": True, "status": "설정됨 · 호출 전 검증 필요"},
            ],
        },
        "evidence": {"configuration_ready": True, "upload_count": 0},
        "voc": {"available": False},
    },
    context="ops",
)
