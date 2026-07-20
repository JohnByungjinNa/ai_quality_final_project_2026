from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES_FILE = Path(__file__).with_name("test_cases.json")
EXPECTED_COUNTS = {
    "normal_voc": 8,
    "ambiguous_question": 3,
    "compound_complaint": 3,
    "no_data": 2,
    "typo_or_ungrammatical": 2,
    "fault_condition": 2,
}
REQUIRED_FIELDS = {
    "case_id", "category", "question", "expected_task", "expected_intent",
    "expected_keywords", "expected_voc_ids", "required_output",
    "prohibited_output", "expected_system_behavior",
}


def main() -> None:
    payload = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) == 20, f"expected 20 cases, got {len(cases)}"
    assert Counter(case["category"] for case in cases) == Counter(EXPECTED_COUNTS)

    ids = [case["case_id"] for case in cases]
    assert ids == [f"TC-{number:02d}" for number in range(1, 21)]
    assert len(ids) == len(set(ids)), "duplicate case_id"

    with (ROOT / payload["dataset"]).open(encoding="utf-8-sig", newline="") as stream:
        voc_ids = {row["고객ID"] for row in csv.DictReader(stream)}

    for case in cases:
        missing = REQUIRED_FIELDS - case.keys()
        assert not missing, f"{case['case_id']} missing fields: {sorted(missing)}"
        assert case["expected_task"] in {"summary", "policy", "both"}
        for field in ("expected_keywords", "required_output", "prohibited_output"):
            assert isinstance(case[field], list) and case[field], f"{case['case_id']} invalid {field}"
        assert isinstance(case["expected_voc_ids"], list), (
            f"{case['case_id']} invalid expected_voc_ids"
        )
        unknown_ids = set(case["expected_voc_ids"]) - voc_ids
        assert not unknown_ids, f"{case['case_id']} unknown VOC IDs: {sorted(unknown_ids)}"
        if case["category"] == "no_data":
            required = " ".join(case["required_output"])
            prohibited = " ".join(case["prohibited_output"])
            assert "일치하는 사례 없음" in required, f"{case['case_id']} missing no-data notice"
            assert "추가" in required and "확인" in required, f"{case['case_id']} missing follow-up guidance"
            assert "단정" in prohibited, f"{case['case_id']} missing unsupported-claim prohibition"
        if case["category"] == "fault_condition":
            assert case.get("setup"), f"{case['case_id']} requires setup"

    print(f"PASS: {len(cases)} test cases")
    for category, count in EXPECTED_COUNTS.items():
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
