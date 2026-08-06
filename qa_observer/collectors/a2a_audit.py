import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, float("inf"))
ALLOWED_STATUS = {"success", "failure"}


def _safe_label(value, fallback="unknown", limit=64):
    text = str(value or fallback).strip()
    return (text or fallback)[:limit]


def _timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


class A2AAuditCollector:
    source_name = "a2a_audit"

    def __init__(self, settings, metrics, logger=None, max_bytes=8_000_000):
        configured_path = getattr(settings, "a2a_audit_path", None)
        fallback_path = Path(getattr(settings, "data_dir", ".")) / "a2a_events.jsonl"
        self.path = Path(configured_path) if configured_path else fallback_path
        self.metrics = metrics
        self.logger = logger
        self.max_bytes = max_bytes

    def sync(self):
        events = self._read_events()
        calls = defaultdict(int)
        durations = defaultdict(list)
        last_success = defaultdict(float)
        traces = defaultdict(list)
        latest = 0.0

        for event in events:
            status = str(event.get("status") or "").lower()
            trace_id = str(event.get("trace_id") or "")
            if trace_id:
                traces[trace_id].append(status)
            latest = max(latest, _timestamp(event.get("timestamp")))
            if status not in ALLOWED_STATUS:
                continue
            labels = (
                _safe_label(event.get("source")),
                _safe_label(event.get("target")),
                _safe_label(event.get("operation")),
                status,
            )
            calls[labels] += 1
            duration = max(float(event.get("duration_ms") or 0) / 1000, 0.0)
            durations[labels].append(duration)
            if status == "success":
                last_success[labels[:3]] = max(last_success[labels[:3]], _timestamp(event.get("timestamp")))

        counters = []
        gauges = [
            ("voc_agent_audit_file_up", {}, 1 if self.path.is_file() else 0),
            ("voc_agent_audit_events", {}, len(events)),
            ("voc_agent_audit_last_event_timestamp_seconds", {}, latest),
        ]
        histograms = []
        for (source, target, operation, status), count in sorted(calls.items()):
            labels = {"source": source, "target": target, "operation": operation, "status": status}
            counters.append(("voc_agent_rpc_calls_total", labels, count))
            samples = durations[(source, target, operation, status)]
            bucket_values = []
            for boundary in BUCKETS:
                label = "+Inf" if boundary == float("inf") else f"{boundary:g}"
                bucket_values.append((label, sum(value <= boundary for value in samples)))
            histograms.append(
                ("voc_agent_rpc_duration_seconds", labels, {
                    "buckets": bucket_values,
                    "count": len(samples),
                    "sum": sum(samples),
                })
            )
        for (source, target, operation), value in sorted(last_success.items()):
            gauges.append((
                "voc_agent_rpc_last_success_timestamp_seconds",
                {"source": source, "target": target, "operation": operation},
                value,
            ))
        trace_counts = defaultdict(int)
        for statuses in traces.values():
            trace_counts["failure" if "failure" in statuses else "success"] += 1
        for status, value in sorted(trace_counts.items()):
            counters.append(("voc_agent_traces_total", {"status": status}, value))

        self.metrics.replace_a2a_snapshot(counters, gauges, histograms)
        return {
            "source": self.source_name,
            "processed": len(events),
            "duplicates": 0,
            "skipped": 0,
            "errors": [],
            "file_count": int(self.path.is_file()),
        }

    def _read_events(self):
        if not self.path.is_file():
            return []
        try:
            with self.path.open("rb") as stream:
                size = stream.seek(0, 2)
                stream.seek(max(0, size - self.max_bytes))
                if size > self.max_bytes:
                    stream.readline()
                text = stream.read().decode("utf-8-sig", errors="replace")
        except OSError as exc:
            if self.logger:
                self.logger.warning("a2a audit read failed error=%s", type(exc).__name__)
            return []
        events = []
        for line in text.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return events
