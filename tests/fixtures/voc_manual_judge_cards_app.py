from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top import voc_quality_view as view


view.judge_provider_options = lambda: [
    {
        "provider": "anthropic",
        "label": "Anthropic",
        "default_model": "claude-haiku-4-5",
        "credential_configured": True,
    },
    {
        "provider": "openai",
        "label": "OpenAI",
        "default_model": "gpt-5.2",
        "credential_configured": True,
    },
]

view._manual_judge_config_controls("goal_TC-01")
