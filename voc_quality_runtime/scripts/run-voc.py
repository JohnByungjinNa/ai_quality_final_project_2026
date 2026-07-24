from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from grpc_server import VOCGRPCRuntime


def write_report(payload: dict) -> dict:
    output_dir = ROOT / "quality_diagnosis" / "Reports" / "VOC"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"voc_analysis_{stamp}.json"
    md_path = output_dir / f"voc_analysis_{stamp}.md"
    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    result = payload.get("result", {})
    markdown = "\n".join([
        "# VOC 분석 결과",
        "",
        f"- 실행 시각: {payload['run_at']}",
        f"- 성공 여부: {result.get('ok', False)}",
        f"- 질문: {payload['question']}",
        "",
        "## 요약",
        "",
        result.get("summary", "") or "-",
        "",
        "## 정책 개선안",
        "",
        result.get("policy", "") or "-",
        "",
        "## Trace",
        "",
        f"`{result.get('trace', '')}`",
    ])
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    (output_dir / "latest.json").write_text(json_text, encoding="utf-8")
    (output_dir / "latest.md").write_text(markdown, encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


async def execute(question: str, csv_path: str, timeout: float, task_override: str | None = None) -> dict:
    runtime = VOCGRPCRuntime()
    return await runtime.run_with_question(
        question=question,
        csv_path=csv_path,
        timeout=timeout,
        task_override=task_override,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="VOC 질문을 6-Agent 파이프라인으로 처리합니다.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--csv-path", default=str(ROOT / "voc.csv"))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--task-override", choices=("summary", "policy", "both"))
    parser.add_argument("--save-report", action="store_true")
    args = parser.parse_args()

    payload = {
        "run_at": datetime.now().astimezone().isoformat(),
        "question": args.question,
        "result": {},
    }
    try:
        payload["result"] = asyncio.run(execute(
            args.question,
            args.csv_path,
            args.timeout,
            task_override=args.task_override,
        ))
        if args.save_report:
            payload["reports"] = write_report(payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["result"].get("ok") else 2
    except Exception as exc:
        payload["result"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "message": "VOC 분석 파이프라인 실행에 실패했습니다.",
        }
        if args.save_report:
            payload["reports"] = write_report(payload)
        print(json.dumps(payload, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
