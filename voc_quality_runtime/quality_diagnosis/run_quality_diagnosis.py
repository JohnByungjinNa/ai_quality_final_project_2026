from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "quality_diagnosis" / "Reports"


def execute(name: str, command: list[str]) -> dict:
    started = datetime.now().astimezone()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return {
        "name": name,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "return_code": completed.returncode,
        "started_at": started.isoformat(),
        "finished_at": datetime.now().astimezone().isoformat(),
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def write_validation_report(results: list[dict], stamp: str) -> tuple[Path, Path]:
    output_dir = REPORT_ROOT / "Validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_at": datetime.now().astimezone().isoformat(),
        "status": "PASS" if all(item["status"] == "PASS" for item in results) else "FAIL",
        "results": results,
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    lines = [
        "# 테스트 정의·평가 기준 검증",
        "",
        f"- 실행 시각: {payload['run_at']}",
        f"- 종합 결과: {payload['status']}",
        "",
    ]
    for item in results:
        lines.extend([
            f"## {item['name']} — {item['status']}",
            "",
            "```text",
            item["stdout"] or item["stderr"] or "출력 없음",
            "```",
            "",
        ])
    markdown = "\n".join(lines)
    json_path = output_dir / f"validation_{stamp}.json"
    md_path = output_dir / f"validation_{stamp}.md"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    (output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / "latest.md").write_text(markdown, encoding="utf-8")
    return json_path, md_path


def newest_report(directory: Path, pattern: str) -> str | None:
    candidates = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    return str(candidates[0]) if candidates else None


def write_summary(mode: str, steps: list[dict], artifacts: dict, stamp: str) -> tuple[Path, Path]:
    output_dir = REPORT_ROOT / "Summary"
    output_dir.mkdir(parents=True, exist_ok=True)
    overall = "PASS" if steps and all(step["status"] == "PASS" for step in steps) else "FAIL"
    payload = {
        "run_at": datetime.now().astimezone().isoformat(),
        "mode": mode,
        "status": overall,
        "steps": steps,
        "artifacts": artifacts,
    }
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    lines = [
        "# VOC 품질진단 실행 요약",
        "",
        f"- 실행 시각: {payload['run_at']}",
        f"- 실행 모드: {mode}",
        f"- 종합 결과: **{overall}**",
        "",
        "| 단계 | 결과 | 종료 코드 |",
        "|---|---:|---:|",
    ]
    for step in steps:
        lines.append(f"| {step['name']} | {step['status']} | {step['return_code']} |")
    lines.extend(["", "## 생성 보고서", ""])
    for name, path in artifacts.items():
        lines.append(f"- {name}: `{path}`")
    markdown = "\n".join(lines)
    json_path = output_dir / f"quality_diagnosis_{stamp}.json"
    md_path = output_dir / f"quality_diagnosis_{stamp}.md"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    (output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / "latest.md").write_text(markdown, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description="VOC 품질진단과 보고서 생성을 일괄 수행합니다.")
    parser.add_argument(
        "mode", nargs="?", default="all",
        choices=("all", "validation", "fault", "a2a"),
    )
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    steps: list[dict] = []
    artifacts: dict[str, str] = {}

    if args.mode in ("all", "validation"):
        validations = [
            execute("테스트케이스 검증", [sys.executable, "quality_diagnosis/validate_test_cases.py"]),
            execute("100점 평가표 검증", [sys.executable, "quality_diagnosis/validate_system_quality_rubric.py"]),
            execute("35건·Judge·타당성·증적 계약 검증", [
                sys.executable,
                "quality_diagnosis/validate_quality_contracts.py",
            ]),
        ]
        steps.extend(validations)
        json_path, md_path = write_validation_report(validations, stamp)
        artifacts["Validation JSON"] = str(json_path)
        artifacts["Validation Markdown"] = str(md_path)

    if args.mode in ("all", "fault"):
        result = execute("장애 진단 6종", [sys.executable, "quality_diagnosis/run_fault_tests.py"])
        steps.append(result)
        latest_fault = newest_report(REPORT_ROOT / "Fault", "fault_test_*.md")
        if latest_fault:
            artifacts["Fault Markdown"] = latest_fault
            artifacts["Fault JSON"] = str(Path(latest_fault).with_suffix(".json"))

    if args.mode in ("all", "a2a"):
        output = REPORT_ROOT / "A2A" / f"a2a_report_{stamp}.md"
        result = execute(
            "Agent 간 gRPC Trace 보고서",
            [sys.executable, "scripts/a2a-report.py", "--output", str(output)],
        )
        steps.append(result)
        if output.exists():
            artifacts["A2A Markdown"] = str(output)

    summary_json, summary_md = write_summary(args.mode, steps, artifacts, stamp)
    print(f"RESULT: {'PASS' if all(step['status'] == 'PASS' for step in steps) else 'FAIL'}")
    for step in steps:
        print(f"  {step['name']}: {step['status']}")
    print(f"Summary JSON: {summary_json}")
    print(f"Summary Markdown: {summary_md}")
    return 0 if steps and all(step["status"] == "PASS" for step in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
