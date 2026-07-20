import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone


def _utc_text():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ObserverScheduler:
    def __init__(self, settings, contract, store, collectors, metrics, logger):
        self.settings = settings
        self.contract = contract
        self.store = store
        self.collectors = {collector.source_name: collector for collector in collectors}
        self.metrics = metrics
        self.logger = logger
        self.last_started_at_utc = None
        self.last_success_at_utc = None
        self.last_error_type = None
        self.source_status = {
            name: {"last_started_at_utc": None, "last_success_at_utc": None, "last_error_type": None}
            for name in self.collectors
        }
        self._task = None
        self._stop = asyncio.Event()
        self._run_lock = asyncio.Lock()
        self._last_cleanup_date = None

    async def start(self):
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(), name="qa-observer-scheduler")

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run_once(self, source_name=None):
        async with self._run_lock:
            if source_name is not None:
                if source_name not in self.collectors:
                    raise KeyError(f"unknown collector: {source_name}")
                selected = [self.collectors[source_name]]
            else:
                selected = list(self.collectors.values())

            self.last_started_at_utc = _utc_text()
            results = []
            for collector in selected:
                results.append(await self._run_collector(collector))
            await asyncio.to_thread(self._cleanup_if_due)
            self.metrics.set_gauge("qa_observer_stored_event_keys", self.store.dedup_key_count)

            failures = [item for item in results if item["errors"]]
            if failures:
                self.last_error_type = failures[0]["errors"][0]["error_type"]
            else:
                self.last_error_type = None
                self.last_success_at_utc = _utc_text()
            if source_name is not None:
                return results[0]
            return {
                "collectors": results,
                "processed": sum(item["processed"] for item in results),
                "duplicates": sum(item["duplicates"] for item in results),
                "skipped": sum(item["skipped"] for item in results),
                "errors": [error for item in results for error in item["errors"]],
            }

    def status(self):
        return {
            "running": self._task is not None and not self._task.done(),
            "last_started_at_utc": self.last_started_at_utc,
            "last_success_at_utc": self.last_success_at_utc,
            "last_error_type": self.last_error_type,
            "interval_seconds": self.settings.sync_interval_seconds,
            "sources": self.source_status,
        }

    async def _loop(self):
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.sync_interval_seconds)
            except asyncio.TimeoutError:
                continue

    async def _run_collector(self, collector):
        state = self.source_status[collector.source_name]
        state["last_started_at_utc"] = _utc_text()
        try:
            result = await asyncio.to_thread(collector.sync)
            status = "success" if not result["errors"] else "error"
            self.metrics.increment(
                "qa_observer_collector_runs_total",
                {"source": collector.source_name, "status": status},
            )
            self.metrics.increment(
                "qa_observer_collector_items_total",
                {"source": collector.source_name},
                result["processed"],
            )
            if status == "success":
                state["last_success_at_utc"] = _utc_text()
                state["last_error_type"] = None
                self.metrics.set_gauge(
                    "qa_observer_last_success_timestamp_seconds",
                    time.time(),
                    {"source": collector.source_name},
                )
            else:
                state["last_error_type"] = result["errors"][0]["error_type"]

            if result["processed"] > 0 or result["errors"]:
                await asyncio.to_thread(self._record_collector_event, collector.source_name, result, status)
            self.logger.info(
                "collector complete source=%s processed=%s skipped=%s errors=%s",
                collector.source_name,
                result["processed"],
                result["skipped"],
                len(result["errors"]),
            )
            return result
        except Exception as exc:
            state["last_error_type"] = type(exc).__name__
            self.metrics.increment(
                "qa_observer_collector_runs_total",
                {"source": collector.source_name, "status": "error"},
            )
            self.logger.error(
                "collector execution failed source=%s error=%s",
                collector.source_name,
                type(exc).__name__,
            )
            return {
                "source": collector.source_name,
                "processed": 0,
                "duplicates": 0,
                "skipped": 0,
                "errors": [{"error_type": type(exc).__name__}],
            }

    def _record_collector_event(self, source_name, result, status):
        occurred_at = _utc_text()
        event_id = str(uuid.uuid4())
        stable = f"{source_name}:{occurred_at}:{event_id}"
        checkpoint = str(result.get("manifest_count", result.get("file_count", ""))) or None
        event = {
            "event_id": event_id,
            "event_type": "collector.sync.completed",
            "schema_version": 1,
            "occurred_at": occurred_at,
            "source": {"component": "qa_observer_scheduler", "instance": None},
            "context": {
                "environment": self.settings.environment,
                "service": self.settings.service_name,
                "trace_id": None,
                "run_id": None,
                "case_id": None,
            },
            "dedup_key": hashlib.sha256(stable.encode("utf-8")).hexdigest(),
            "payload": {
                "source_name": source_name,
                "status": status,
                "items_processed": result["processed"],
                "checkpoint": checkpoint,
                "error_type": result["errors"][0]["error_type"] if result["errors"] else None,
            },
        }
        self.contract.validate(event)
        self.store.append(event)

    def _cleanup_if_due(self):
        today = datetime.now(timezone.utc).date()
        if self._last_cleanup_date == today:
            return
        deleted = self.store.cleanup_retention(today=today)
        self._last_cleanup_date = today
        if deleted:
            self.metrics.increment("qa_observer_retention_deleted_files_total", value=len(deleted))
            self.logger.info("retention cleanup deleted_files=%s", len(deleted))
