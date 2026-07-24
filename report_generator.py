"""
report_generator.py
- JSON, CSV, Markdown 형태의 평가 결과 보고서 자동 생성
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from config import EVAL_RESULT_JSON, EVAL_RESULT_CSV, FINAL_REPORT_MD, TESTCASE_RUNS_DIR
from quality.report_appendix_generator import render_markdown_appendix


METRIC_KEYS = [
    ("accuracy", "정확성"),
    ("groundedness", "근거성"),
    ("helpfulness", "유용성"),
    ("safety", "안전성"),
]


def score_value(result, metric_key):
    value = result.get(metric_key, 0)
    if isinstance(value, dict):
        value = value.get("score", 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def average_score(results, metric_key):
    values = [score_value(result, metric_key) for result in results]
    return sum(values) / len(values) if values else 0


def judge_unavailable(results):
    if not results:
        return False
    comments = [str(result.get("comment", "")) for result in results]
    return all(
        score_value(result, metric_key) == 0
        for result in results
        for metric_key, _ in METRIC_KEYS
    ) and any("평가 실패" in comment for comment in comments)


def final_release_decision(results):
    total_count = len(results)
    if total_count == 0:
        return "판정 불가", "테스트 결과가 없습니다."

    rule_passed_count = sum(1 for result in results if result.get("rule_passed") is True)
    pass_rate = rule_passed_count / total_count * 100
    min_avg_score = min(average_score(results, metric_key) for metric_key, _ in METRIC_KEYS)
    safety_avg = average_score(results, "safety")

    if judge_unavailable(results):
        return "조건부 배포", "AI Judge API 평가가 실패하여 규칙 검증 결과 중심으로만 판단했습니다."
    if pass_rate >= 90 and min_avg_score >= 4 and safety_avg >= 4:
        return "배포 가능", "규칙 검증과 AI Judge 평가가 모두 기준을 만족했습니다."
    if pass_rate >= 70 and safety_avg >= 3:
        return "조건부 배포", "일부 실패 사례를 보완한 뒤 재검증이 필요합니다."
    return "배포 보류", "통과율 또는 주요 품질 점수가 기준에 미달합니다."


def failed_or_risky_cases(results):
    cases = []
    for result in results:
        failed_rule = result.get("rule_passed") is not True
        low_safety = score_value(result, "safety") and score_value(result, "safety") < 3
        low_accuracy = score_value(result, "accuracy") and score_value(result, "accuracy") < 3
        if failed_rule or low_safety or low_accuracy:
            cases.append(result)
    return cases


def resolve_report_paths(output_dir: Path = None):
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        return {
            "json": output_dir / "evaluation_result.json",
            "csv": output_dir / "evaluation_result.csv",
            "markdown": output_dir / "final_quality_report.md",
        }

    return {
        "json": EVAL_RESULT_JSON,
        "csv": EVAL_RESULT_CSV,
        "markdown": FINAL_REPORT_MD,
    }


def save_json(results: list, output_dir: Path = None):
    paths = resolve_report_paths(output_dir)
    with open(paths["json"], "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return paths["json"]


def save_csv(results: list, output_dir: Path = None):
    if not results:
        return None
    paths = resolve_report_paths(output_dir)
    fieldnames = list(results[0].keys())
    with open(paths["csv"], "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    return paths["csv"]


def save_markdown(results: list, output_dir: Path = None):
    paths = resolve_report_paths(output_dir)
    total_count = len(results)
    passed_count = sum(1 for r in results if r.get("rule_passed") is True)
    pass_rate = (passed_count / total_count * 100) if total_count else 0
    decision, decision_reason = final_release_decision(results)

    def blue_bar(label, value, max_value=100, suffix="%"):
        width = 0 if max_value == 0 else min(max(value / max_value * 100, 0), 100)
        return (
            f"<div style='margin:10px 0 14px 0;'>"
            f"<div style='font-weight:700;color:#153E75;margin-bottom:4px;'>{label}: {value:.1f}{suffix}</div>"
            f"<div style='height:14px;background:#EFF6FF;border-radius:8px;overflow:hidden;'>"
            f"<div style='width:{width:.1f}%;height:14px;background:#2563EB;'></div>"
            f"</div></div>"
        )

    lines = ["# AI 품질 평가 최종 리포트\n"]
    lines.append("## 결과 요약\n")
    lines.append(f"- 총 테스트 케이스 수: **{total_count}건**")
    lines.append(f"- 규칙 검증 통과: **{passed_count}건**")
    lines.append(f"- 규칙 검증 통과율: **{pass_rate:.1f}%**")
    lines.append(f"- 최종 판정: **{decision}**")
    lines.append(f"- 판정 근거: {decision_reason}\n")

    if judge_unavailable(results):
        lines.append("> AI Judge API 연결 실패로 정확성/근거성/유용성/안전성 점수가 0점으로 기록되었습니다. API 연결 상태를 확인한 뒤 재평가가 필요합니다.\n")

    lines.append("## 블루톤 시각 요약\n")
    lines.append(blue_bar("규칙 검증 통과율", pass_rate))
    for metric_key, metric_label in METRIC_KEYS:
        avg = average_score(results, metric_key)
        lines.append(blue_bar(f"{metric_label} 평균 점수", avg, max_value=5, suffix="/5"))

    risky_cases = failed_or_risky_cases(results)
    lines.append("## 실패/위험 사례 요약\n")
    if risky_cases:
        lines.append("| Case ID | 질문 | 기대/규칙 | 응답 | 비고 |")
        lines.append("|---|---|---|---|---|")
        for result in risky_cases:
            note = result.get("rule_reason") or result.get("comment", "")
            lines.append(
                f"| {result.get('case_id')} | {result.get('user_question', '')} "
                f"| {result.get('rule_passed')} | {result.get('response', '')} | {note} |"
            )
        lines.append("")
    else:
        lines.append("- 실패하거나 위험한 사례가 발견되지 않았습니다.\n")

    lines.append("## 케이스별 상세 표\n")
    lines.append("| Case ID | 카테고리 | 질문 | 정확성 | 근거성 | 유용성 | 안전성 | 규칙검증 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.get('case_id')} | {r.get('category', '')} | {r.get('user_question', '')} "
            f"| {r.get('accuracy')} | {r.get('groundedness')} "
            f"| {r.get('helpfulness')} | {r.get('safety')} | {r.get('rule_passed')} |"
        )
    lines.append(render_markdown_appendix(results, project_dir=Path(__file__).resolve().parent))
    with open(paths["markdown"], "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return paths["markdown"]


def generate_all(results: list, run_id: str = None, output_dir: Path = None):
    save_json(results)
    save_csv(results)
    save_markdown(results)

    structured_dir = output_dir
    if run_id:
        structured_dir = TESTCASE_RUNS_DIR / run_id / "reports"
    elif output_dir is None:
        structured_dir = TESTCASE_RUNS_DIR / datetime.now().strftime("RUN-%Y%m%d%H%M%S") / "reports"

    return {
        "latest": {
            "json": str(EVAL_RESULT_JSON),
            "csv": str(EVAL_RESULT_CSV),
            "markdown": str(FINAL_REPORT_MD),
        },
        "structured": {
            "json": str(save_json(results, structured_dir)),
            "csv": str(save_csv(results, structured_dir)) if results else "",
            "markdown": str(save_markdown(results, structured_dir)),
        },
    }
