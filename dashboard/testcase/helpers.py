import pandas as pd
import streamlit as st

def build_upload_table_rows(include_selection=True):
    rows = []
    for index, item in enumerate(st.session_state.testcase_uploads, start=1):
        row = {
            "NO": index,
            "파일명": item["filename"],
            "형식": item.get("file_type", "CSV"),
            "테스트케이스 수": item["row_count"],
            "컬럼 수": item["column_count"],
            "업로드일시": item["uploaded_at"],
            "상태": "등록완료",
            "_id": item["id"],
        }
        if include_selection:
            row = {"선택": False, **row}
        rows.append(row)
    return pd.DataFrame(rows)


def build_execution_detail(selected_items, total_count, passed_count):
    rule_passed_count = round(passed_count * 0.4)
    api_passed_count = max(passed_count - rule_passed_count, 0)
    matched_count = min(rule_passed_count, api_passed_count)

    file_results = []
    for item in selected_items:
        file_total = item["row_count"]
        file_rule_passed = round(file_total * 0.4)
        file_api_passed = max(file_total - file_rule_passed, 0)
        file_results.append(
            {
                "파일명": item["filename"],
                "형식": item.get("file_type", "CSV"),
                "총 건수": file_total,
                "규칙기반 성공": file_rule_passed,
                "API기반 성공": file_api_passed,
                "판정일치": min(file_rule_passed, file_api_passed),
                "상태": "완료",
            }
        )

    return {
        "rule_passed_count": rule_passed_count,
        "api_passed_count": api_passed_count,
        "matched_count": matched_count,
        "file_results": file_results,
    }


def get_execution_detail(history_item):
    total_count = max(history_item.get("total_count", 0), 0)
    passed_count = max(history_item.get("passed_count", 0), 0)
    detail = history_item.get("detail")

    if detail:
        return detail

    return {
        "rule_passed_count": round(passed_count * 0.4),
        "api_passed_count": max(passed_count - round(passed_count * 0.4), 0),
        "matched_count": round(total_count * 0.8),
        "file_results": [
            {
                "파일명": history_item.get("target_files", "-"),
                "형식": "-",
                "총 건수": total_count,
                "규칙기반 성공": round(passed_count * 0.4),
                "API기반 성공": max(passed_count - round(passed_count * 0.4), 0),
                "판정일치": round(total_count * 0.8),
                "상태": history_item.get("status", "완료"),
            }
        ],
    }


def normalize_test_case(row, fallback_index):
    aliases = {
        "case_id": ["case_id", "TC ID", "테스트ID", "케이스ID", "ID"],
        "category": ["category", "카테고리", "분류"],
        "test_type": ["test_type", "유형", "테스트유형"],
        "user_question": ["user_question", "question", "질문", "사용자질문"],
        "expected_keyword": ["expected_keyword", "기대키워드", "예상키워드", "필수키워드"],
        "expected_policy": ["expected_policy", "기대정책", "검증정책", "정책"],
    }

    normalized = {}
    for target_key, candidates in aliases.items():
        value = ""
        for candidate in candidates:
            if candidate in row and pd.notna(row[candidate]):
                value = str(row[candidate]).strip()
                break
        normalized[target_key] = value

    if not normalized["case_id"]:
        normalized["case_id"] = f"TC-UPLOAD-{fallback_index:03d}"
    if not normalized["category"]:
        normalized["category"] = "정확성"
    if not normalized["test_type"]:
        normalized["test_type"] = "Upload"

    return normalized


def extract_test_cases_from_uploads(selected_items):
    test_cases = []
    for item in selected_items:
        dataframe = item.get("data", pd.DataFrame())
        for _, row in dataframe.fillna("").iterrows():
            test_case = normalize_test_case(row.to_dict(), len(test_cases) + 1)
            if test_case["user_question"]:
                test_cases.append(test_case)
    return test_cases


