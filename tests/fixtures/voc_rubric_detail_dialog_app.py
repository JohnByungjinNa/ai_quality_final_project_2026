from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "dashboard"))

from pages_top.voc_quality_view import (
    QUALITY_RUBRIC_SPECS,
    _rubric_draft,
    _rubric_item_detail_dialog,
    load_system_rubric,
)


rubric_type = "internal_pipeline"
draft = _rubric_draft(load_system_rubric(), rubric_type)
_rubric_item_detail_dialog(
    draft,
    rubric_type,
    QUALITY_RUBRIC_SPECS[rubric_type],
    "interpreter",
)
