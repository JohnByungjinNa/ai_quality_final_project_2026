from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = ROOT / "quality_diagnosis" / "Reports" / "A2A"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an Agent-to-Agent gRPC audit report")
    parser.add_argument("--input", default=".runtime/audit/a2a_events.jsonl")
    parser.add_argument("--output", help="Output Markdown path")
    parser.add_argument("--trace-id", help="Report only one VOC trace")
    args = parser.parse_args()

    source = Path(args.input)
    events = []
    if source.exists():
        events = [json.loads(line) for line in source.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if args.trace_id:
        events = [event for event in events if event["trace_id"] == args.trace_id]
    traces: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        traces[event["trace_id"]].append(event)

    lines = ["# Agent-to-Agent gRPC Audit Report", "", f"Generated: {datetime.now().astimezone().isoformat()}", ""]
    if not traces:
        lines += ["아직 A2A 감사 이벤트가 없습니다. 실제 VOC 요청을 처리한 뒤 다시 생성하세요.", ""]
    for trace_id, trace_events in sorted(traces.items(), key=lambda item: item[1][0]["timestamp"], reverse=True):
        keyword_counts = Counter(keyword for event in trace_events for keyword in event.get("keywords", []))
        observed_agents = list(dict.fromkeys(agent for event in trace_events for agent in event.get("agent_chain", [event["source"], event["target"]])))
        overall = "PASS" if all(event["status"] == "success" for event in trace_events) else "FAIL"
        lines += [f"## Trace `{trace_id}` — {overall}", "", f"Observed agents: {' → '.join(observed_agents) or '-'}", "", f"Keywords: {', '.join(k for k, _ in keyword_counts.most_common(12)) or '-'}", "", "| Time | gRPC path | Operation | Status | Duration | Keywords |", "|---|---|---|---|---:|---|"]
        for event in trace_events:
            path = f"{event['source']} → {event['target']}"
            keywords = ", ".join(event.get("keywords", []))
            lines.append(f"| {event['timestamp']} | {path} | {event['operation']} | {event['status']} | {event['duration_ms']} ms | {keywords} |")
        lines.append("")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = Path(args.output) if args.output else DEFAULT_REPORT_DIR / f"a2a_report_{stamp}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines)
    output.write_text(report_text, encoding="utf-8")
    (output.parent / "latest.md").write_text(report_text, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
