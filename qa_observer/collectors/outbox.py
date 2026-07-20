import json
import os
from datetime import datetime, timezone
from pathlib import Path

from qa_observer.storage import EventConflictError
from qa_observer.validation import EventValidationError


def _utc_text():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class OutboxCollector:
    source_name = "event_outbox"

    def __init__(self, settings, contract, store, logger=None):
        self.settings = settings
        self.contract = contract
        self.store = store
        self.logger = logger
        self.outbox_dir = settings.data_dir / "outbox"
        self.rejected_dir = self.outbox_dir / "rejected"

    def sync(self):
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        processed = 0
        duplicates = 0
        skipped = 0
        errors = []
        files = sorted(self.outbox_dir.glob("*/*.processing"))
        for source_path in sorted(self.outbox_dir.glob("*/*.jsonl")):
            if source_path.parent == self.rejected_dir:
                continue
            claimed = source_path.with_suffix(source_path.suffix + ".processing")
            try:
                os.replace(source_path, claimed)
                files.append(claimed)
            except OSError:
                skipped += 1

        for path in sorted(set(files)):
            file_failed = False
            try:
                with path.open("r", encoding="utf-8") as stream:
                    for line_number, line in enumerate(stream, start=1):
                        if not line.strip():
                            continue
                        event = None
                        try:
                            event = json.loads(line)
                            self.contract.validate(event)
                            result = self.store.append(event)
                            if result["stored"]:
                                processed += 1
                            else:
                                duplicates += 1
                        except (json.JSONDecodeError, EventValidationError, EventConflictError) as exc:
                            error = {
                                "file": path.name,
                                "line": line_number,
                                "event_id": event.get("event_id") if isinstance(event, dict) else None,
                                "error_type": type(exc).__name__,
                                "recorded_at_utc": _utc_text(),
                            }
                            errors.append(error)
                            self._write_rejection_metadata(error)
                            if self.logger:
                                self.logger.error(
                                    "outbox event rejected file=%s line=%s error=%s",
                                    path.name,
                                    line_number,
                                    type(exc).__name__,
                                )
                        except OSError as exc:
                            file_failed = True
                            errors.append(
                                {"file": path.name, "line": line_number, "error_type": type(exc).__name__}
                            )
                            break
                if not file_failed:
                    path.unlink()
            except OSError as exc:
                errors.append({"file": path.name, "line": 0, "error_type": type(exc).__name__})

        return {
            "source": self.source_name,
            "processed": processed,
            "duplicates": duplicates,
            "skipped": skipped,
            "errors": errors,
            "file_count": len(files),
        }

    def _write_rejection_metadata(self, value):
        self.rejected_dir.mkdir(parents=True, exist_ok=True)
        path = self.rejected_dir / f"{datetime.now(timezone.utc).date().isoformat()}.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
