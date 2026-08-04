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
        "ai": {"configured_count": 3, "total_count": 3, "providers": []},
        "evidence": {
            "configuration_ready": True,
            "upload_count": 1,
            "latest": {
                "run_id": "RUN-20260716-110130-319110-c8fe",
                "file_count": 2,
            },
        },
        "voc": {
            "available": True,
            "run_id": "RUN-20260804-124356-733943-20af",
            "status": "COMPLETED",
            "pass_count": 1,
            "attention_count": 0,
            "deployment_decision": "FORMAL_QUALITY_APPROVED",
        },
    },
    context="overview",
)
