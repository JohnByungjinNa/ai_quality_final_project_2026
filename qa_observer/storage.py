import csv
import hashlib
import json
import os
import threading
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


AGGREGATE_FIELDS = [
    "date",
    "environment",
    "service",
    "provider",
    "model",
    "metric",
    "sum_value",
    "sample_count",
    "min_value",
    "max_value",
    "updated_at_utc",
]


class EventConflictError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc)


def utc_text(value=None):
    return (value or utc_now()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(timezone.utc)


def _canonical_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _decimal_text(value):
    number = Decimal(str(value))
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


class FileEventStore:
    def __init__(self, settings, logger=None):
        self.settings = settings
        self.logger = logger
        self.events_dir = settings.data_dir / "events"
        self.aggregates_dir = settings.data_dir / "aggregates"
        self.state_dir = settings.data_dir / "state"
        self.aggregate_path = self.aggregates_dir / "daily-aggregates.csv"
        self.checkpoint_path = self.state_dir / "collector-checkpoints.json"
        self._lock = threading.RLock()
        self._event_hashes = {}
        self._dedup_hashes = {}
        self._aggregates = {}

    def initialize(self):
        for path in (self.events_dir, self.aggregates_dir, self.state_dir):
            path.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._load_aggregates()
            self._rebuild_dedup_index()

    @property
    def dedup_key_count(self):
        with self._lock:
            return len(self._dedup_hashes)

    def append(self, event):
        event_hash = _canonical_hash(event)
        event_id = event["event_id"]
        dedup_key = event["dedup_key"]
        with self._lock:
            existing_event_hash = self._event_hashes.get(event_id)
            existing_dedup_hash = self._dedup_hashes.get(dedup_key)
            if existing_event_hash == event_hash and existing_dedup_hash == event_hash:
                return {"stored": False, "duplicate": True, "event_id": event_id}
            if existing_event_hash is not None or existing_dedup_hash is not None:
                raise EventConflictError("event_id or dedup_key already exists with a different payload")

            received_at = utc_text()
            record = {"received_at_utc": received_at, "event": event}
            event_path = self._event_path(event)
            event_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            with event_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())

            self._event_hashes[event_id] = event_hash
            self._dedup_hashes[dedup_key] = event_hash
            self._update_aggregates(event, received_at)
            self._write_aggregates()
            return {"stored": True, "duplicate": False, "event_id": event_id}

    def list_aggregates(
        self,
        date_value=None,
        date_from=None,
        date_to=None,
        environment=None,
        service=None,
        provider=None,
        model=None,
        metric=None,
    ):
        with self._lock:
            rows = [dict(row) for row in self._aggregates.values()]
        if date_value:
            rows = [row for row in rows if row["date"] == date_value]
        if date_from:
            rows = [row for row in rows if row["date"] >= date_from]
        if date_to:
            rows = [row for row in rows if row["date"] <= date_to]
        if environment:
            rows = [row for row in rows if row["environment"] == environment]
        if service:
            rows = [row for row in rows if row["service"] == service]
        if provider:
            rows = [row for row in rows if row["provider"] == provider]
        if model:
            rows = [row for row in rows if row["model"] == model]
        if metric:
            rows = [row for row in rows if row["metric"] == metric]
        return sorted(
            rows,
            key=lambda row: (
                row["date"], row["environment"], row["service"],
                row["provider"], row["model"], row["metric"],
            ),
        )

    def load_checkpoints(self):
        with self._lock:
            if not self.checkpoint_path.exists():
                return {}
            try:
                value = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else {}
            except (OSError, json.JSONDecodeError):
                return {}

    def save_checkpoints(self, checkpoints):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(
            self.checkpoint_path,
            json.dumps(checkpoints, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )

    def check_writable(self):
        check_path = self.state_dir / ".write-check.tmp"
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            check_path.write_text("ok", encoding="utf-8")
            check_path.unlink()
            return True
        except OSError:
            return False

    def cleanup_retention(self, today=None):
        today = today or utc_now().date()
        deleted = []
        with self._lock:
            for path in self.events_dir.glob("*/*.jsonl"):
                try:
                    file_date = date.fromisoformat(path.stem)
                except ValueError:
                    continue
                event_type = path.parent.name
                retention_days = self._retention_days_for_type(event_type)
                if file_date < today - timedelta(days=retention_days):
                    path.unlink()
                    deleted.append(str(path))

            aggregate_cutoff = today - timedelta(days=self.settings.aggregate_retention_days)
            self._aggregates = {
                key: row
                for key, row in self._aggregates.items()
                if date.fromisoformat(row["date"]) >= aggregate_cutoff
            }
            self._write_aggregates()
            if deleted:
                self._rebuild_dedup_index()
        return deleted

    def stats(self):
        with self._lock:
            event_files = list(self.events_dir.glob("*/*.jsonl"))
            return {
                "event_files": len(event_files),
                "dedup_keys": len(self._dedup_hashes),
                "aggregate_rows": len(self._aggregates),
                "data_dir": str(self.settings.data_dir),
            }

    def _event_path(self, event):
        occurred = _parse_utc(event["occurred_at"])
        event_type_dir = event["event_type"].replace(".", "_")
        return self.events_dir / event_type_dir / f"{occurred.date().isoformat()}.jsonl"

    def _rebuild_dedup_index(self):
        self._event_hashes.clear()
        self._dedup_hashes.clear()
        for path in sorted(self.events_dir.glob("*/*.jsonl")):
            try:
                with path.open("r", encoding="utf-8") as stream:
                    for line_number, line in enumerate(stream, start=1):
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)["event"]
                            event_hash = _canonical_hash(event)
                            self._event_hashes[event["event_id"]] = event_hash
                            self._dedup_hashes[event["dedup_key"]] = event_hash
                        except (KeyError, TypeError, json.JSONDecodeError) as exc:
                            if self.logger:
                                self.logger.error(
                                    "invalid event log record file=%s line=%s error=%s",
                                    path.name,
                                    line_number,
                                    type(exc).__name__,
                                )
            except OSError as exc:
                if self.logger:
                    self.logger.error("cannot read event log file=%s error=%s", path.name, type(exc).__name__)

    def _load_aggregates(self):
        self._aggregates.clear()
        if not self.aggregate_path.exists():
            return
        with self.aggregate_path.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if not all(field in row for field in AGGREGATE_FIELDS):
                    continue
                key = self._aggregate_key(row)
                self._aggregates[key] = row

    def _update_aggregates(self, event, updated_at):
        context = event["context"]
        payload = event["payload"]
        occurred_date = _parse_utc(event["occurred_at"]).date().isoformat()
        provider = str(payload.get("provider") or "")
        model = str(payload.get("model") or "")
        base = {
            "date": occurred_date,
            "environment": context["environment"],
            "service": context["service"],
            "provider": provider,
            "model": model,
            "updated_at_utc": updated_at,
        }
        for metric, value in self._metric_samples(event):
            self._add_aggregate_sample(base, metric, value)

    def _add_aggregate_sample(self, base, metric, value):
        number = Decimal(str(value))
        candidate = dict(base, metric=metric)
        key = self._aggregate_key(candidate)
        current = self._aggregates.get(key)
        if current is None:
            self._aggregates[key] = dict(
                candidate,
                sum_value=_decimal_text(number),
                sample_count="1",
                min_value=_decimal_text(number),
                max_value=_decimal_text(number),
            )
            return
        current["sum_value"] = _decimal_text(Decimal(current["sum_value"]) + number)
        current["sample_count"] = str(int(current["sample_count"]) + 1)
        current["min_value"] = _decimal_text(min(Decimal(current["min_value"]), number))
        current["max_value"] = _decimal_text(max(Decimal(current["max_value"]), number))
        current["updated_at_utc"] = base["updated_at_utc"]

    @staticmethod
    def _metric_samples(event):
        event_type = event["event_type"]
        payload = event["payload"]
        samples = [("events.count", 1)]
        if event_type == "api.request.completed":
            samples.extend([("api.requests", 1), ("api.duration_ms", payload["duration_ms"])])
            if payload["status_code"] >= 500 or payload["timeout"]:
                samples.append(("api.service_errors", 1))
            if 400 <= payload["status_code"] < 500:
                samples.append(("api.client_errors", 1))
            if payload["timeout"]:
                samples.append(("api.timeouts", 1))
        elif event_type == "llm.call.completed":
            samples.extend(
                [
                    ("llm.requests", 1),
                    ("llm.input_tokens", payload["input_tokens"]),
                    ("llm.output_tokens", payload["output_tokens"]),
                    ("llm.cached_input_tokens", payload["cached_input_tokens"]),
                    ("llm.total_tokens", payload["total_tokens"]),
                    ("llm.duration_ms", payload["duration_ms"]),
                ]
            )
            if payload["status"] == "error":
                samples.append(("llm.errors", 1))
            if payload.get("total_cost_micros_krw") is not None:
                samples.append(("llm.cost_micros_krw", payload["total_cost_micros_krw"]))
        elif event_type == "rag.search.completed":
            samples.extend(
                [
                    ("rag.searches", 1),
                    ("rag.result_count", payload["result_count"]),
                    ("rag.duration_ms", payload["duration_ms"]),
                    ("rag.no_result", int(payload["no_result"])),
                ]
            )
            if payload.get("top_k_hit") is not None:
                samples.append(("rag.top_k_hit", int(payload["top_k_hit"])))
        elif event_type == "quality.evaluation.completed":
            for metric_name, item in payload["scores"].items():
                if item.get("evaluated") and item.get("score") is not None:
                    samples.append((f"quality.{metric_name}.score", item["score"]))
            samples.append((f"quality.decision.{payload['overall_decision'].lower()}", 1))
        elif event_type == "test.run.completed":
            for key in ("pass_count", "fail_count", "error_count", "total_count", "duration_ms"):
                samples.append((f"test.{key}", payload[key]))
        elif event_type == "safety.violation.detected":
            samples.extend(
                [("safety.violations", 1), (f"safety.violations.{payload['severity']}", 1)]
            )
        elif event_type == "defect.changed":
            samples.extend([("defects.changed", 1), (f"defects.status.{payload['status']}", 1)])
        elif event_type == "evidence.upload.completed":
            samples.extend(
                [
                    ("evidence.uploads", 1),
                    ("evidence.upload.success", int(payload["uploaded"])),
                    ("evidence.verify.success", int(payload["verified"])),
                    ("evidence.duration_ms", payload["duration_ms"]),
                    ("evidence.file_count", payload["file_count"]),
                    ("evidence.bytes", payload["bytes_total"]),
                ]
            )
            if payload["status"] == "error":
                samples.append(("evidence.errors", 1))
        elif event_type == "collector.sync.completed":
            samples.extend(
                [("collector.runs", 1), ("collector.items_processed", payload["items_processed"])]
            )
        return samples

    @staticmethod
    def _aggregate_key(row):
        return tuple(row.get(field, "") for field in AGGREGATE_FIELDS[:6])

    def _write_aggregates(self):
        self.aggregates_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.aggregate_path.with_suffix(".csv.tmp")
        with temp_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=AGGREGATE_FIELDS)
            writer.writeheader()
            for row in self.list_aggregates():
                writer.writerow({field: row.get(field, "") for field in AGGREGATE_FIELDS})
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, self.aggregate_path)

    def _atomic_write_text(self, path, content):
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with self._lock:
            with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)

    def _retention_days_for_type(self, event_type_dir):
        if event_type_dir == "collector_sync_completed":
            return self.settings.collector_retention_days
        if event_type_dir in {
            "quality_evaluation_completed", "test_run_completed", "safety_violation_detected"
        }:
            return self.settings.quality_retention_days
        if event_type_dir == "defect_changed":
            return self.settings.defect_retention_days
        return self.settings.event_retention_days
