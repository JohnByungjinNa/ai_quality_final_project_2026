"""
main.py
- 전체 자동화 파이프라인 실행
  1) test_cases.json 로드
  2) service_agent로 응답 생성
  3) rule_validator로 1차 검증
  4) judge_agent로 AI 평가
  5) report_generator로 결과 저장
"""

import json

from config import ensure_dirs, TEST_CASES_PATH
from service_agent import get_response
from rule_validator import validate
from judge_agent import evaluate
from report_generator import generate_all


def load_test_cases():
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_pipeline():
    ensure_dirs()
    test_cases = load_test_cases()
    results = []

    for tc in test_cases:
        response = get_response(tc["user_question"])
        rule_result = validate(response, tc["expected_keyword"])
        judge_result = evaluate(
            tc["user_question"], response, tc["expected_policy"]
        )

        results.append(
            {
                "case_id": tc["case_id"],
                "category": tc["category"],
                "test_type": tc["test_type"],
                "user_question": tc["user_question"],
                "response": response,
                "rule_passed": rule_result["passed"],
                "rule_reason": rule_result["reason"],
                **judge_result,
            }
        )

    generate_all(results)
    print(f"총 {len(results)}건 평가 완료. reports/ 폴더를 확인하세요.")


if __name__ == "__main__":
    run_pipeline()
