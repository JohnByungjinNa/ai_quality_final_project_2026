import json
import shutil
from pathlib import Path

import pandas as pd
import streamlit as st

from core.paths import REPORTS_DIR, TESTCASE_RUNS_DIR, TESTCASE_UPLOADS_DIR, TESTCASE_UPLOADS_FILE, TESTCASE_HISTORY_FILE

def serialize_uploads(uploads):
    serialized = []
    for item in uploads:
        dataframe = item.get("data", pd.DataFrame())
        records = json.loads(
            dataframe.to_json(orient="records", force_ascii=False, date_format="iso")
        )
        serialized.append(
            {
                "id": item["id"],
                "filename": item["filename"],
                "file_type": item.get("file_type", "CSV"),
                "row_count": item.get("row_count", len(dataframe)),
                "column_count": item.get("column_count", len(dataframe.columns)),
                "columns": item.get("columns", ", ".join(map(str, dataframe.columns))),
                "uploaded_at": item["uploaded_at"],
                "storage_dir": item.get("storage_dir", ""),
                "source_path": item.get("source_path", ""),
                "parsed_path": item.get("parsed_path", ""),
                "metadata_path": item.get("metadata_path", ""),
                "data": records,
            }
        )
    return serialized


def deserialize_uploads(uploads):
    restored = []
    for item in uploads:
        dataframe = pd.DataFrame(item.get("data", []))
        restored.append(
            {
                "id": item["id"],
                "filename": item["filename"],
                "file_type": item.get("file_type", "CSV"),
                "row_count": item.get("row_count", len(dataframe)),
                "column_count": item.get("column_count", len(dataframe.columns)),
                "columns": item.get("columns", ", ".join(map(str, dataframe.columns))),
                "uploaded_at": item["uploaded_at"],
                "storage_dir": item.get("storage_dir", ""),
                "source_path": item.get("source_path", ""),
                "parsed_path": item.get("parsed_path", ""),
                "metadata_path": item.get("metadata_path", ""),
                "data": dataframe,
            }
        )
    return restored


def load_json_file(file_path, default_value, fallback_path=None):
    if not file_path.exists():
        if fallback_path and fallback_path.exists():
            file_path = fallback_path
        else:
            return default_value

    try:
        with file_path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return default_value


def save_json_file(file_path, data):
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except TypeError:
        with file_path.open("w", encoding="utf-8") as file:
            json.dump(json.loads(json.dumps(data, default=str)), file, ensure_ascii=False, indent=2)


def safe_filename(filename):
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in filename)
    return safe or "uploaded_file"


def save_uploaded_testcase_artifacts(uploaded_file, dataframe, upload_item):
    upload_dir = TESTCASE_UPLOADS_DIR / upload_item["id"]
    upload_dir.mkdir(parents=True, exist_ok=True)

    source_path = upload_dir / safe_filename(uploaded_file.name)
    parsed_path = upload_dir / "parsed_records.json"
    metadata_path = upload_dir / "metadata.json"

    source_path.write_bytes(uploaded_file.getvalue())
    parsed_records = json.loads(
        dataframe.to_json(orient="records", force_ascii=False, date_format="iso")
    )
    metadata = {
        "id": upload_item["id"],
        "filename": upload_item["filename"],
        "file_type": upload_item.get("file_type", ""),
        "row_count": upload_item.get("row_count", 0),
        "column_count": upload_item.get("column_count", 0),
        "columns": upload_item.get("columns", ""),
        "uploaded_at": upload_item.get("uploaded_at", ""),
        "source_path": str(source_path),
        "parsed_path": str(parsed_path),
    }

    save_json_file(parsed_path, parsed_records)
    save_json_file(metadata_path, metadata)

    upload_item["storage_dir"] = str(upload_dir)
    upload_item["source_path"] = str(source_path)
    upload_item["parsed_path"] = str(parsed_path)
    upload_item["metadata_path"] = str(metadata_path)
    return upload_item


def _remove_path_within(root, target):
    root = Path(root).resolve()
    target = Path(target).resolve()
    if target == root or root not in target.parents or not target.exists():
        return False
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return True


def remove_upload_artifacts(upload_item):
    upload_id = str(upload_item.get("id", "")).strip()
    candidates = []
    if upload_id and Path(upload_id).name == upload_id:
        candidates.append(TESTCASE_UPLOADS_DIR / upload_id)
    if upload_item.get("storage_dir"):
        candidates.append(Path(upload_item["storage_dir"]))

    removed = False
    for candidate in candidates:
        removed = _remove_path_within(TESTCASE_UPLOADS_DIR, candidate) or removed
    return removed


def remove_all_upload_artifacts():
    if not TESTCASE_UPLOADS_DIR.exists():
        return 0
    removed = 0
    for target in list(TESTCASE_UPLOADS_DIR.iterdir()):
        removed += int(_remove_path_within(TESTCASE_UPLOADS_DIR, target))
    return removed


def remove_test_run_artifacts(history_item):
    run_id = str(history_item.get("id", "")).strip()
    if not run_id or Path(run_id).name != run_id:
        return 0

    targets = (
        (TESTCASE_RUNS_DIR, TESTCASE_RUNS_DIR / run_id),
        (REPORTS_DIR / "formal_reports", REPORTS_DIR / "formal_reports" / run_id),
    )
    return sum(int(_remove_path_within(root, target)) for root, target in targets)


def save_testcase_uploads():
    save_json_file(TESTCASE_UPLOADS_FILE, serialize_uploads(st.session_state.testcase_uploads))


def save_testcase_history():
    save_json_file(TESTCASE_HISTORY_FILE, st.session_state.testcase_execution_history)
