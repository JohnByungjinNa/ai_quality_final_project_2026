import json
import math
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone


def utc_text(value=None):
    return (value or datetime.now(timezone.utc)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ObserverQueryService:
    """Read-only queries over the MVP JSONL and daily CSV storage."""

    def __init__(self, store):
        self.store = store

    def events(
        self,
        date_from=None,
        date_to=None,
        event_type=None,
        environment=None,
        service=None,
        provider=None,
        model=None,
        limit=100,
    ):
        start, end = _date_window(date_from, date_to)
        type_dirs = [event_type.replace(".", "_")] if event_type else None
        records = []
        for path in sorted(self.store.events_dir.glob("*/*.jsonl"), reverse=True):
            if type_dirs and path.parent.name not in type_dirs:
                continue
            try:
                file_date = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if file_date < start or file_date > end:
                continue
            try:
                with path.open("r", encoding="utf-8") as stream:
                    for line in stream:
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                            event = record["event"]
                        except (json.JSONDecodeError, KeyError, TypeError):
                            continue
                        context = event.get("context", {})
                        payload = event.get("payload", {})
                        if environment and context.get("environment") != environment:
                            continue
                        if service and context.get("service") != service:
                            continue
                        if provider and payload.get("provider") != provider:
                            continue
                        if model and payload.get("model") != model:
                            continue
                        records.append(record)
            except OSError:
                continue
        records.sort(
            key=lambda item: (item.get("event", {}).get("occurred_at", ""), item.get("received_at_utc", "")),
            reverse=True,
        )
        if limit is None:
            return records
        return records[: max(1, min(int(limit), 500))]

    def timeseries(
        self,
        date_from=None,
        date_to=None,
        environment=None,
        service=None,
        provider=None,
        model=None,
        metric=None,
    ):
        start, end = _date_window(date_from, date_to)
        rows = self.store.list_aggregates(
            date_from=start.isoformat(),
            date_to=end.isoformat(),
            environment=environment,
            service=service,
            provider=provider,
            model=model,
            metric=metric,
        )
        grouped = {}
        for row in rows:
            key = (row["date"], row["metric"])
            item = grouped.setdefault(
                key,
                {
                    "date": row["date"],
                    "metric": row["metric"],
                    "sum_value": 0.0,
                    "sample_count": 0,
                    "min_value": None,
                    "max_value": None,
                },
            )
            value_sum = float(row["sum_value"])
            value_count = int(row["sample_count"])
            value_min = float(row["min_value"])
            value_max = float(row["max_value"])
            item["sum_value"] += value_sum
            item["sample_count"] += value_count
            item["min_value"] = value_min if item["min_value"] is None else min(item["min_value"], value_min)
            item["max_value"] = value_max if item["max_value"] is None else max(item["max_value"], value_max)
        items = []
        for item in grouped.values():
            item["average_value"] = (
                item["sum_value"] / item["sample_count"] if item["sample_count"] else None
            )
            items.append(item)
        return sorted(items, key=lambda item: (item["date"], item["metric"]))

    def dashboard_summary(
        self,
        date_from=None,
        date_to=None,
        environment=None,
        service=None,
        provider=None,
        model=None,
    ):
        start, end = _date_window(date_from, date_to)
        records = self.events(
            start.isoformat(),
            end.isoformat(),
            environment=environment,
            service=service,
            provider=provider,
            model=model,
            limit=None,
        )
        counts = defaultdict(int)
        durations = []
        quality_scores = []
        latest_received = None
        defect_states = {}
        for record in records:
            event = record["event"]
            event_type = event["event_type"]
            payload = event["payload"]
            counts["events"] += 1
            received = record.get("received_at_utc")
            if received and (latest_received is None or received > latest_received):
                latest_received = received
            if event_type == "api.request.completed":
                counts["api_requests"] += 1
                durations.append(float(payload["duration_ms"]))
                if payload["status_code"] >= 500 or payload["timeout"]:
                    counts["api_errors"] += 1
            elif event_type == "llm.call.completed":
                counts["llm_requests"] += 1
                counts["llm_tokens"] += int(payload["total_tokens"])
                if payload.get("total_cost_micros_krw") is not None:
                    counts["priced_llm_requests"] += 1
                    counts["llm_cost_micros_krw"] += int(payload["total_cost_micros_krw"])
            elif event_type == "rag.search.completed":
                counts["rag_searches"] += 1
                counts["rag_no_results"] += int(payload["no_result"])
            elif event_type == "quality.evaluation.completed":
                for score in payload["scores"].values():
                    if score.get("evaluated") and score.get("score") is not None:
                        quality_scores.append(float(score["score"]))
            elif event_type == "test.run.completed":
                counts["test_pass"] += int(payload["pass_count"])
                counts["test_total"] += int(payload["total_count"])
            elif event_type == "safety.violation.detected":
                counts["safety_violations"] += 1
            elif event_type == "defect.changed":
                defect_states.setdefault(payload["defect_id"], payload["status"])

        freshness_seconds = _freshness_seconds(latest_received)
        cost_krw = (
            counts["llm_cost_micros_krw"] / 1_000_000
            if counts["priced_llm_requests"]
            else None
        )
        budget_krw = _positive_float(os.getenv("QA_OBSERVER_DAILY_BUDGET_KRW", "50000"), 50000)
        return {
            "period": {"date_from": start.isoformat(), "date_to": end.isoformat()},
            "generated_at_utc": utc_text(),
            "event_count": counts["events"],
            "data_status": "no_data" if latest_received is None else ("stale" if freshness_seconds > 120 else "fresh"),
            "latest_received_at_utc": latest_received,
            "freshness_seconds": freshness_seconds,
            "quality_score": round(_average(quality_scores) * 20, 2) if quality_scores else None,
            "test_pass_rate": _percentage(counts["test_pass"], counts["test_total"]),
            "api_p95_duration_ms": _percentile(durations, 0.95),
            "api_error_rate": _percentage(counts["api_errors"], counts["api_requests"]),
            "safety_violation_count": counts["safety_violations"],
            "open_defect_count": sum(status in {"open", "investigating"} for status in defect_states.values()),
            "llm_total_tokens": counts["llm_tokens"],
            "llm_cost_krw": cost_krw,
            "llm_price_coverage": _percentage(counts["priced_llm_requests"], counts["llm_requests"]),
            "daily_budget_krw": budget_krw,
            "budget_usage_rate": _percentage(cost_krw, budget_krw) if cost_krw is not None else None,
            "rag_no_result_rate": _percentage(counts["rag_no_results"], counts["rag_searches"]),
        }


def _date_window(date_from=None, date_to=None):
    today = datetime.now(timezone.utc).date()
    end = date.fromisoformat(str(date_to)) if date_to else today
    start = date.fromisoformat(str(date_from)) if date_from else end - timedelta(days=6)
    if start > end:
        raise ValueError("date_from must be on or before date_to")
    if (end - start).days > 365:
        raise ValueError("date range must not exceed 366 days")
    return start, end


def _percentage(numerator, denominator):
    return round(numerator / denominator * 100, 4) if denominator else None


def _average(values):
    return round(sum(values) / len(values), 4) if values else None


def _percentile(values, quantile):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * quantile) - 1)
    return ordered[index]


def _freshness_seconds(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return max(0, round((datetime.now(timezone.utc) - parsed).total_seconds()))


def _positive_float(value, default):
    try:
        parsed = float(value)
        return parsed if parsed > 0 else float(default)
    except (TypeError, ValueError):
        return float(default)
