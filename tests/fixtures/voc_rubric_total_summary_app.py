from copy import deepcopy
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top.voc_quality_view import (
    QUALITY_RUBRIC_SPECS,
    _render_rubric_total_summary,
    load_system_rubric,
)


draft = deepcopy(load_system_rubric())
draft["categories"]["interpreter"]["criteria"]["intent"] = 2
_render_rubric_total_summary(
    draft,
    QUALITY_RUBRIC_SPECS["internal_pipeline"],
)
