import json
import os
from pathlib import Path

import pytest

from rule_validator import validate
from service_agent import get_response


PROJECT_DIR = Path(__file__).resolve().parents[1]
UPLOADS_FILE = PROJECT_DIR / "data" / "testcases" / "testcase_uploads.json"


def _load_target_upload():
    if not UPLOADS_FILE.exists():
        pytest.skip("등록된 테스트케이스 목록 파일이 없습니다.", allow_module_level=True)

    with UPLOADS_FILE.open("r", encoding="utf-8") as file:
        uploads = json.load(file)

    uploads = [upload for upload in uploads if upload.get("data")]
    if not uploads:
        pytest.skip("등록된 테스트케이스가 없습니다.", allow_module_level=True)

    selected_upload_id = os.environ.get("AIQA_TESTCASE_UPLOAD_ID", "").strip()
    if selected_upload_id:
        for upload in uploads:
            if upload.get("id") == selected_upload_id:
                return upload
        pytest.fail(f"선택한 테스트케이스 업로드 ID를 찾을 수 없습니다: {selected_upload_id}")

    return sorted(
        uploads,
        key=lambda upload: (upload.get("uploaded_at", ""), upload.get("id", "")),
    )[-1]


TARGET_UPLOAD = _load_target_upload()
TARGET_CASES = TARGET_UPLOAD["data"]


def _case_id(test_case):
    return f"{TARGET_UPLOAD.get('filename', 'selected')}::{test_case.get('case_id', 'NO_ID')}"


def test_selected_registered_upload_has_testcases():
    assert TARGET_UPLOAD.get("filename")
    assert len(TARGET_CASES) == int(TARGET_UPLOAD.get("row_count", len(TARGET_CASES)))


@pytest.mark.parametrize("test_case", TARGET_CASES, ids=_case_id)
def test_selected_registered_testcase_rule_validation(test_case):
    question = test_case.get("user_question", "")
    expected_keyword = test_case.get("expected_keyword", "")

    assert question, "user_question 값이 비어 있습니다."

    answer = get_response(question)
    assert answer, "챗봇 응답이 비어 있습니다."

    if not expected_keyword:
        return

    result = validate(answer, expected_keyword)
    assert result["passed"], (
        f"{test_case.get('case_id')} 실패: "
        f"expected_keyword={expected_keyword!r}, answer={answer!r}, reason={result['reason']}"
    )
