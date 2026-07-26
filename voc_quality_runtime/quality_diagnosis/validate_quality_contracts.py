from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CATALOG_FILE = ROOT / "quality_test_catalog.json"
TEST_CASES_FILE = ROOT / "test_cases.json"
SYSTEM_RUBRIC_FILE = ROOT / "system_quality_rubric.json"
JUDGE_RUBRIC_FILE = ROOT / "independent_judge_rubric.json"
VALIDITY_RUBRIC_FILE = ROOT / "improvement_validity_rubric.json"
EVIDENCE_CONTRACT_FILE = ROOT / "quality_evidence_contract.json"

EXPECTED_GROUP_COUNTS = {
    "voc_functional": 20,
    "isolated_fault": 6,
    "agent_role": 6,
    "quality_gate": 3,
}
EXPECTED_STATUSES = {"PASS", "FAIL", "ERROR", "NOT_RUN", "REVIEW_REQUIRED"}
EXPECTED_RUN_TYPES = {"MANUAL", "BATCH", "RETEST", "BASELINE"}
EXPECTED_RUN_LIFECYCLE = {"RUNNING", "COMPLETED", "ERROR", "INTERRUPTED"}
EXPECTED_AGENT_SOURCES = {
    "AG-01": "interpreter",
    "AG-02": "retriever",
    "AG-03": "summarizer",
    "AG-04": "evaluator",
    "AG-05": "critic",
    "AG-06": "improver",
}
EXPECTED_EXECUTION_TYPES = {
    "voc_pipeline",
    "fault_proxy",
    "isolated_fault",
    "agent_role_quality",
    "quality_gate",
}
EXPECTED_FAULT_PROXY = {"TC-19": "FT-01", "TC-20": "FT-03"}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_weighted_rubric(rubric: dict, *, dimensions_key: str) -> None:
    dimensions = rubric[dimensions_key]
    assert rubric["total_points"] == 100
    assert sum(item["max_points"] for item in dimensions.values()) == 100
    for name, item in dimensions.items():
        criteria_points = sum(item["criteria"].values())
        assert criteria_points == item["max_points"], (
            f"{rubric['rubric_id']} {name}: criteria={criteria_points}, "
            f"max={item['max_points']}"
        )
        assert 0 < item["pass_floor"] <= item["max_points"], name


def validate_catalog() -> dict:
    catalog = load(CATALOG_FILE)
    cases = catalog["cases"]
    ids = [item["case_id"] for item in cases]
    groups = Counter(item["group"] for item in cases)

    assert catalog["suite_id"] == "VOC-QA-35"
    assert catalog["total_cases"] == 35 == len(cases)
    assert len(ids) == len(set(ids)), "duplicate quality case_id"
    assert groups == Counter(EXPECTED_GROUP_COUNTS)
    assert {
        key: value["expected_count"] for key, value in catalog["groups"].items()
    } == EXPECTED_GROUP_COUNTS

    functional_ids = {item["case_id"] for item in cases if item["group"] == "voc_functional"}
    source_cases = {item["case_id"]: item for item in load(TEST_CASES_FILE)["cases"]}
    source_case_ids = set(source_cases)
    assert functional_ids == source_case_ids == {f"TC-{index:02d}" for index in range(1, 21)}

    fault_ids = {item["case_id"] for item in cases if item["group"] == "isolated_fault"}
    assert fault_ids == {f"FT-{index:02d}" for index in range(1, 7)}

    system_categories = set(load(SYSTEM_RUBRIC_FILE)["categories"])
    for item in cases:
        assert item["implementation_status"] in {"IMPLEMENTED", "DEFINED"}
        assert item["source_ref"] and item["acceptance"]
        assert item["execution_type"] in EXPECTED_EXECUTION_TYPES
        assert isinstance(item.get("execution"), dict) and item["execution"]
        execution = item["execution"]
        if item["case_id"] in source_cases:
            assert execution["category"] == source_cases[item["case_id"]]["category"]
            assert execution.get("expected_system_behavior")
            if item["case_id"] in EXPECTED_FAULT_PROXY:
                assert item["execution_type"] == "fault_proxy"
                assert execution["fault_case_id"] == EXPECTED_FAULT_PROXY[item["case_id"]]
            else:
                assert item["execution_type"] == "voc_pipeline"
                assert execution.get("question")
                assert execution["expected_task"] in {"summary", "policy", "both"}
        if item["group"] == "isolated_fault":
            assert item["execution_type"] == "isolated_fault"
            assert execution["fault_case_id"] == item["case_id"]
        if item["group"] == "agent_role":
            assert item["execution_type"] == "agent_role_quality"
        if item["group"] == "quality_gate":
            assert item["execution_type"] == "quality_gate"
        if item["case_id"] in EXPECTED_AGENT_SOURCES:
            assert EXPECTED_AGENT_SOURCES[item["case_id"]] in system_categories

    baseline = catalog["baseline_claim"]
    expected = baseline["expected_summary"]
    assert expected == {"total": 35, "passed": 33, "failed": 2}
    assert expected["passed"] + expected["failed"] == expected["total"]
    assert baseline["status"] == "PENDING_EVIDENCE"
    assert all(item["evidence_status"] == "PENDING" for item in baseline["candidate_defects"])
    return catalog


def validate_contracts() -> None:
    judge = load(JUDGE_RUBRIC_FILE)
    validity = load(VALIDITY_RUBRIC_FILE)
    evidence = load(EVIDENCE_CONTRACT_FILE)

    validate_weighted_rubric(judge, dimensions_key="dimensions")
    validate_weighted_rubric(validity, dimensions_key="dimensions")

    assert judge["judge_provider_policy"] == "runtime_configurable"
    assert judge["default_provider"]
    assert {item["decision"] for item in judge["decisions"]} == {
        "PASS", "REVIEW_REQUIRED", "FAIL"
    }
    assert set(judge["non_quality_statuses"]) == {"ERROR", "NOT_RUN"}
    assert len(judge["immediate_fail_rules"]) >= 4

    assert validity["automatic_decisions"][0]["decision"] == "AI_PASS"
    assert "QA_REVIEWED" in validity["workflow_states"]
    assert "BUSINESS_APPROVED" in validity["workflow_states"]
    assert "AI_PASS만으로" in validity["formal_approval_rule"]
    assert len(validity["immediate_hold_rules"]) >= 5

    assert evidence["contract_id"] == "VOC-QUALITY-EVIDENCE-V1"
    assert evidence["suite_id"] == "VOC-QA-35"
    assert set(evidence["execution_statuses"]) == EXPECTED_STATUSES
    assert set(evidence["run_types"]) == EXPECTED_RUN_TYPES
    assert set(evidence["run_lifecycle_statuses"]) == EXPECTED_RUN_LIFECYCLE
    assert set(evidence["model_independence_grades"]) == {"A", "B", "C"}
    assert set(evidence["release_gates"]) == {
        "TECHNICAL_PILOT", "FORMAL_QUALITY_APPROVAL"
    }
    required_run_files = set(evidence["artifact_layout"]["required_run_files"])
    assert required_run_files == {"manifest.json", "summary.json", "defects.json"}
    assert len(evidence["required_manifest_fields"]) >= 12
    retention = evidence["retention_policy"]
    assert retention["default_run_days"] > retention["incomplete_run_days"] > 0
    assert retention["formal_release_days"] >= retention["default_run_days"]
    assert retention["auto_delete_enabled"] is False


def main() -> None:
    catalog = validate_catalog()
    validate_contracts()
    groups = Counter(item["group"] for item in catalog["cases"])
    print("PASS: VOC quality contracts")
    print(f"  suite: {catalog['suite_id']} ({catalog['total_cases']} cases)")
    for name, count in EXPECTED_GROUP_COUNTS.items():
        print(f"  {name}: {groups[name]}")
    print("  independent Judge rubric: 100 points")
    print("  improvement validity rubric: 100 points")
    print("  baseline 33 PASS / 2 FAIL: PENDING_EVIDENCE")


if __name__ == "__main__":
    main()
