import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from quality_criteria import get_quality_criteria

METRICS = [
    ("accuracy", "정확성"),
    ("groundedness", "근거성"),
    ("helpfulness", "유용성"),
    ("safety", "안전성"),
]


def build_dashboard_snapshot(
    pipeline_outputs, run_id, started_at=None, ended_at=None, reports_dir=None, quality_criteria=None
):
    cases = pipeline_outputs or []
    criteria = get_quality_criteria(quality_criteria)
    rule = build_agent_summary(cases, "rule_based", criteria)
    api = build_agent_summary(cases, "api_based", criteria)
    return {
        "snapshot_type": "test_run_dashboard",
        "run_id": run_id,
        "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(started_at, "strftime") else started_at,
        "ended_at": ended_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ended_at, "strftime") else ended_at,
        "quality_criteria": criteria.to_dict(),
        "final": {
            "rule_pass_rate": rule["pass_rate"],
            "api_pass_rate": api["pass_rate"],
            "rule_pass_count": rule["decision_counts"]["PASS"],
            "api_pass_count": api["decision_counts"]["PASS"],
            "total_cases": len(cases),
            "defect_count": len(build_defects(cases, criteria)),
            "weakest_rule_metric": weakest_metric(rule),
            "weakest_api_metric": weakest_metric(api),
        },
        "advanced_metrics": {
            "coverage": build_coverage(cases),
            "redteam": build_redteam(cases),
            "pii": build_pii(cases),
            "cost": build_cost_estimate(cases),
            "hallucination": build_hallucination(cases, criteria),
        },
        "quality": {
            "rule_based": rule,
            "api_based": api,
            "comparison": build_case_comparison(cases),
            "defects": build_defects(cases, criteria),
        },
        "ops": load_ops_snapshot(reports_dir),
        "k6": load_k6_snapshot(reports_dir),
    }


def save_dashboard_snapshot(run_dir, snapshot):
    path = Path(run_dir) / "dashboard_snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def build_agent_summary(cases, agent_key, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    decisions = [get_decision(case, agent_key) for case in cases]
    metric_rates = {}
    metric_scores = {}
    for metric_key, label in METRICS:
        scores = [get_metric_score(case, agent_key, metric_key) for case in cases]
        passed = sum(1 for score in scores if score >= criteria.pass_min_score)
        metric_rates[metric_key] = {
            "label": label,
            "pass_count": passed,
            "fail_count": max(len(scores) - passed, 0),
            "rate": rate(passed, len(scores)),
            "score_100": rate(passed, len(scores)),
            "avg_score_5": round(sum(scores) / len(scores), 2) if scores else 0,
        }
        metric_scores[metric_key] = metric_rates[metric_key]["score_100"]
    return {
        "label": "규칙 기반" if agent_key == "rule_based" else "API 기반",
        "decision_counts": {decision: decisions.count(decision) for decision in ("PASS", "REVIEW", "FAIL")},
        "pass_rate": rate(decisions.count("PASS"), len(decisions)),
        "metric_rates": metric_rates,
        "metric_scores": metric_scores,
        "type_distribution": build_type_distribution(cases, agent_key),
    }


def build_case_comparison(cases):
    rows = []
    for case in cases:
        rule = get_decision(case, "rule_based")
        api = get_decision(case, "api_based")
        rows.append(
            {
                "case_id": case.get("case_id", ""),
                "category": case.get("category", ""),
                "test_type": case.get("test_type", ""),
                "rule_decision": rule,
                "api_decision": api,
                "matched": rule == api,
            }
        )
    return rows


def build_type_distribution(cases, agent_key):
    grouped = defaultdict(Counter)
    for case in cases:
        test_type = case.get("test_type") or "기타"
        grouped[test_type][get_decision(case, agent_key)] += 1
    return {
        test_type: {"pass": counts["PASS"], "review": counts["REVIEW"], "fail": counts["FAIL"]}
        for test_type, counts in grouped.items()
    }


def build_defects(cases, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    defects = []
    for case in cases:
        for agent_key, prefix in (("rule_based", "RULE"), ("api_based", "API")):
            if get_decision(case, agent_key) != "FAIL":
                continue
            defects.append(
                {
                    "defect_id": f"{prefix}-{len(defects) + 1:03d}",
                    "agent": "규칙 기반" if agent_key == "rule_based" else "API 기반",
                    "case_id": case.get("case_id", ""),
                    "category": case.get("category", ""),
                    "test_type": case.get("test_type", ""),
                    "question": case.get("user_question", ""),
                    "summary": get_summary(case, agent_key),
                    "weak_metrics": ", ".join(
                        label
                        for metric, label in METRICS
                        if get_metric_score(case, agent_key, metric) < criteria.pass_min_score
                    ),
                    "severity": "High",
                    "priority": "High",
                    "status": "Open",
                }
            )
    return defects


def build_coverage(cases):
    categories = {case.get("category", "미분류") for case in cases}
    test_types = {case.get("test_type", "미분류") for case in cases}
    return {
        "category_count": len(categories),
        "test_type_count": len(test_types),
        "total_cases": len(cases),
        "covered_categories": sorted(categories),
    }


def build_redteam(cases):
    negative_cases = [case for case in cases if str(case.get("test_type", "")).lower() == "negative"]
    passed = sum(1 for case in negative_cases if get_decision(case, "api_based") == "PASS")
    return {"total": len(negative_cases), "passed": passed, "pass_rate": rate(passed, len(negative_cases))}


def build_pii(cases):
    risk_count = 0
    for case in cases:
        answer = str(case.get("api_based", {}).get("ai_answer", ""))
        if "@" in answer or "010-" in answer:
            risk_count += 1
    return {"risk_count": risk_count, "status": "확인 필요" if risk_count else "위험 없음"}


def build_cost_estimate(cases):
    estimated_tokens = sum(len(str(case.get("user_question", ""))) + len(str(case.get("api_based", {}).get("ai_answer", ""))) for case in cases)
    return {"estimated_tokens": estimated_tokens, "estimated_cost_krw": round(estimated_tokens * 0.0008, 2)}


def build_hallucination(cases, quality_criteria=None):
    criteria = get_quality_criteria(quality_criteria)
    low_grounded = sum(
        1
        for case in cases
        if get_metric_score(case, "api_based", "groundedness") < criteria.pass_min_score
    )
    return {"suspected_cases": low_grounded, "risk_rate": rate(low_grounded, len(cases))}


def load_ops_snapshot(reports_dir):
    if not reports_dir:
        return {}
    reports_dir = Path(reports_dir)
    for path in (reports_dir / "ops_metrics_snapshot.json", reports_dir.parent.parent / "ops_metrics_snapshot.json"):
        data = load_json(path)
        if data:
            return data
    return {}


def load_k6_snapshot(reports_dir):
    if not reports_dir:
        return {}
    reports_dir = Path(reports_dir)
    for path in (reports_dir / "k6_summary.json", reports_dir.parent.parent / "k6_summary.json"):
        data = load_json(path)
        if data:
            return data
    return {}


def load_json(path):
    try:
        path = Path(path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def get_decision(case, agent_key):
    return case.get(agent_key, {}).get("evaluation_result", {}).get("overall_decision", "FAIL")


def get_metric_score(case, agent_key, metric_key):
    value = case.get(agent_key, {}).get("evaluation_result", {}).get(metric_key, 0)
    if isinstance(value, dict):
        value = value.get("score", 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def get_summary(case, agent_key):
    return case.get(agent_key, {}).get("evaluation_result", {}).get("summary") or case.get(agent_key, {}).get("evaluation_result", {}).get("comment", "")


def weakest_metric(agent_summary):
    metrics = agent_summary.get("metric_rates", {})
    if not metrics:
        return "-"
    weakest = min(metrics.values(), key=lambda item: item.get("score_100", 0))
    return f"{weakest['label']} ({weakest['score_100']:.1f}점)"


def rate(part, total):
    return round(float(part) / float(total) * 100, 1) if total else 0.0
