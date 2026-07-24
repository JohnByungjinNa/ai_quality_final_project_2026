from __future__ import annotations

import json
from pathlib import Path


RUBRIC_FILE = Path(__file__).with_name("system_quality_rubric.json")
EXPECTED_CATEGORIES = {
    "interpreter",
    "retriever",
    "summarizer",
    "evaluator",
    "critic",
    "improver",
    "agent_linkage",
    "fault_and_logging",
    "performance",
}
def main() -> None:
    rubric = json.loads(RUBRIC_FILE.read_text(encoding="utf-8"))
    categories = rubric["categories"]

    assert rubric["total_points"] == 100
    assert set(categories) == EXPECTED_CATEGORIES

    for name, category in categories.items():
        actual_points = sum(category["criteria"].values())
        assert actual_points == category["max_points"], (
            f"{name}: criteria={actual_points}, max={category['max_points']}"
        )

    assert sum(item["max_points"] for item in categories.values()) == 100
    assert rubric["immediate_deployment_hold"]

    decisions = rubric["deployment_decisions"]
    ranges = sorted((item["min"], item["max"]) for item in decisions)
    assert ranges[0][0] == 0 and ranges[-1][1] == 100
    assert all(round(current[0] - previous[1], 2) == 0.01 for previous, current in zip(ranges, ranges[1:]))

    thresholds = categories["performance"]["threshold_seconds"]
    assert thresholds["target"] < thresholds["warning"] < thresholds["critical"]

    print("PASS: system quality rubric totals 100 points")
    for name, category in categories.items():
        print(f"  {name}: {category['max_points']}")
    print(f"PASS: {len(rubric['immediate_deployment_hold'])} immediate deployment-hold rules")


if __name__ == "__main__":
    main()
