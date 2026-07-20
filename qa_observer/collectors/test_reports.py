import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


SEOUL = ZoneInfo("Asia/Seoul")


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _local_text_to_utc(value):
    text = str(value or "").strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SEOUL)
    return parsed.astimezone(timezone.utc)


def _utc_text(value):
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _is_judge_error(row):
    scores = [row.get(name) for name in ("accuracy", "groundedness", "helpfulness", "safety")]
    zero_scores = all(str(score or "0") in {"0", "0.0"} for score in scores)
    comment = str(row.get("comment") or "").lower()
    return zero_scores and any(token in comment for token in ("평가 실패", "오류", "error"))


class TestReportCollector:
    source_name = "test_reports"

    def __init__(self, settings, contract, store, logger=None):
        self.settings = settings
        self.contract = contract
        self.store = store
        self.logger = logger

    def sync(self):
        checkpoints = self.store.load_checkpoints()
        source_state = checkpoints.setdefault(self.source_name, {})
        runs = source_state.setdefault("runs", {})
        processed = 0
        duplicates = 0
        skipped = 0
        errors = []

        manifests = sorted(self.settings.reports_dir.glob("*/run_manifest.json"))
        for manifest_path in manifests:
            run_id = manifest_path.parent.name
            fingerprint = _file_sha256(manifest_path)
            if runs.get(run_id) == fingerprint:
                skipped += 1
                continue
            try:
                event = self._build_event(manifest_path)
                self.contract.validate(event)
                result = self.store.append(event)
                runs[run_id] = fingerprint
                if result["stored"]:
                    processed += 1
                else:
                    duplicates += 1
            except Exception as exc:
                errors.append({"run_id": run_id, "error_type": type(exc).__name__})
                if self.logger:
                    self.logger.error(
                        "test report sync failed run_id=%s error=%s", run_id, type(exc).__name__
                    )

        source_state["last_scan_at_utc"] = _utc_text(datetime.now(timezone.utc))
        source_state["last_manifest_count"] = len(manifests)
        self.store.save_checkpoints(checkpoints)
        return {
            "source": self.source_name,
            "processed": processed,
            "duplicates": duplicates,
            "skipped": skipped,
            "errors": errors,
            "manifest_count": len(manifests),
        }

    def _build_event(self, manifest_path):
        manifest = _read_json(manifest_path, {})
        run_id = str(manifest.get("id") or manifest_path.parent.name)
        started = _local_text_to_utc(manifest.get("started_at"))
        ended = _local_text_to_utc(manifest.get("ended_at")) or started
        if started is None or ended is None:
            raise ValueError("run manifest requires started_at and ended_at")

        evaluation_path = manifest_path.parent / "reports" / "evaluation_result.json"
        rows = _read_json(evaluation_path, [])
        if not isinstance(rows, list):
            rows = []
        snapshot = _read_json(manifest_path.parent / "dashboard_snapshot.json", {})
        final = snapshot.get("final", {}) if isinstance(snapshot, dict) else {}
        total = int(manifest.get("test_case_count") or final.get("total_cases") or len(rows))
        error_count = sum(1 for row in rows if isinstance(row, dict) and _is_judge_error(row))
        pass_count = int(final.get("api_pass_count") or 0)
        if "api_pass_count" not in final and rows:
            threshold = int((manifest.get("quality_criteria") or {}).get("pass_min_score", 4))
            pass_count = sum(
                1
                for row in rows
                if isinstance(row, dict)
                and not _is_judge_error(row)
                and all(float(row.get(name) or 0) >= threshold for name in (
                    "accuracy", "groundedness", "helpfulness", "safety"
                ))
            )
        error_count = min(error_count, max(total - pass_count, 0))
        fail_count = max(total - pass_count - error_count, 0)
        duration_ms = max(int(round(float(manifest.get("duration_seconds") or 0) * 1000)), 0)

        stable_text = f"test.run.completed:v1:{run_id}"
        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_text))
        dedup_key = hashlib.sha256(stable_text.encode("utf-8")).hexdigest()
        relative_manifest = manifest_path.relative_to(self.settings.reports_dir).as_posix()
        return {
            "event_id": event_id,
            "event_type": "test.run.completed",
            "schema_version": 1,
            "occurred_at": _utc_text(ended),
            "source": {"component": "test_report_collector", "instance": None},
            "context": {
                "environment": self.settings.environment,
                "service": self.settings.target_service,
                "trace_id": None,
                "run_id": run_id,
                "case_id": None,
            },
            "dedup_key": dedup_key,
            "payload": {
                "started_at": _utc_text(started),
                "ended_at": _utc_text(ended),
                "duration_ms": duration_ms,
                "criteria_stage": str((manifest.get("quality_criteria") or {}).get("stage") or "unknown"),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "error_count": error_count,
                "total_count": total,
                "source_manifest_path": relative_manifest,
            },
        }
