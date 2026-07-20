from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top.voc_quality_view import _judge_config_controls


_judge_config_controls("judge_test")
