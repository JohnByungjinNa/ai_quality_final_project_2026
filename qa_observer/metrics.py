import math
import threading
import time
from collections import defaultdict
from datetime import datetime


def _escape_label(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class ObserverMetrics:
    """Small dependency-free Prometheus registry for observer self-metrics."""

    def __init__(self):
        self._lock = threading.RLock()
        self._counters = defaultdict(float)
        self._gauges = {("qa_observer_start_time_seconds", ()): time.time()}

    def increment(self, name, labels=None, value=1.0):
        labels = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._counters[(name, labels)] += float(value)

    def set_gauge(self, name, value, labels=None):
        labels = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._gauges[(name, labels)] = float(value)

    def render(self, aggregate_rows=None):
        descriptions = {
            "qa_observer_events_received_total": ("counter", "Validated and rejected events received."),
            "qa_observer_events_stored_total": ("counter", "Events appended to JSONL storage."),
            "qa_observer_event_validation_errors_total": ("counter", "Event contract validation errors."),
            "qa_observer_event_conflicts_total": ("counter", "Duplicate-key payload conflicts."),
            "qa_observer_event_duplicates_total": ("counter", "Idempotent duplicate events."),
            "qa_observer_grafana_webhook_requests_total": ("counter", "Grafana alert webhook requests."),
            "qa_observer_collector_runs_total": ("counter", "Collector executions."),
            "qa_observer_collector_items_total": ("counter", "Items processed by collectors."),
            "qa_observer_retention_deleted_files_total": ("counter", "Expired event files deleted."),
            "qa_observer_last_success_timestamp_seconds": ("gauge", "Last successful collector Unix timestamp."),
            "qa_observer_stored_event_keys": ("gauge", "Deduplication keys loaded in memory."),
            "qa_observer_start_time_seconds": ("gauge", "Observer process start Unix timestamp."),
            "qa_observer_up": ("gauge", "Whether the observer is ready."),
        }
        with self._lock:
            samples = list(self._counters.items()) + list(self._gauges.items())
        by_name = defaultdict(list)
        for (name, labels), value in samples:
            by_name[name].append((labels, value))

        lines = []
        for name in sorted(by_name):
            metric_type, help_text = descriptions.get(name, ("gauge", name))
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {metric_type}")
            for labels, value in sorted(by_name[name], key=lambda item: item[0]):
                label_text = ""
                if labels:
                    label_text = "{" + ",".join(
                        f'{key}="{_escape_label(label_value)}"' for key, label_value in labels
                    ) + "}"
                number = "0" if not math.isfinite(value) else f"{value:g}"
                lines.append(f"{name}{label_text} {number}")
        if aggregate_rows:
            lines.extend(_render_dashboard_aggregates(aggregate_rows))
        return "\n".join(lines) + "\n"


def _render_dashboard_aggregates(rows):
    lines = [
        "# HELP qa_dashboard_aggregate_value Current UTC-day aggregate from QA events.",
        "# TYPE qa_dashboard_aggregate_value gauge",
    ]
    latest_by_context = {}
    for row in sorted(
        rows,
        key=lambda item: (
            item["environment"], item["service"], item["provider"], item["model"], item["metric"]
        ),
    ):
        labels = {
            "environment": row["environment"],
            "service": row["service"],
            "provider": row["provider"],
            "model": row["model"],
            "metric": row["metric"],
        }
        values = {
            "sum": float(row["sum_value"]),
            "count": float(row["sample_count"]),
            "min": float(row["min_value"]),
            "max": float(row["max_value"]),
        }
        values["average"] = values["sum"] / values["count"] if values["count"] else 0
        for aggregation, value in values.items():
            metric_labels = dict(labels, aggregation=aggregation)
            label_text = ",".join(
                f'{key}="{_escape_label(label_value)}"'
                for key, label_value in sorted(metric_labels.items())
            )
            lines.append(f"qa_dashboard_aggregate_value{{{label_text}}} {value:g}")
        context_key = (row["environment"], row["service"])
        latest_by_context[context_key] = max(
            latest_by_context.get(context_key, ""), row.get("updated_at_utc", "")
        )
    lines.extend(
        [
            "# HELP qa_dashboard_data_updated_timestamp_seconds Latest aggregate update Unix timestamp.",
            "# TYPE qa_dashboard_data_updated_timestamp_seconds gauge",
        ]
    )
    for (environment, service), value in sorted(latest_by_context.items()):
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (AttributeError, ValueError):
            continue
        lines.append(
            "qa_dashboard_data_updated_timestamp_seconds"
            f'{{environment="{_escape_label(environment)}",service="{_escape_label(service)}"}} '
            f"{timestamp:g}"
        )
    return lines
