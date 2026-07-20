import hashlib
import hmac
import json
import logging
import os
import threading
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path


LOGGER = logging.getLogger("qa_observer.telemetry")
_CONTEXT = ContextVar("qa_observer_context", default={})
_OUTBOX_LOCK = threading.RLock()
_FORBIDDEN_PAYLOAD_KEYS = {
    "prompt",
    "question",
    "user_question",
    "response",
    "answer",
    "text",
    "chunk_text",
}


def _utc_now_text():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _project_root():
    return Path(__file__).resolve().parents[1]


def _data_dir():
    value = os.getenv("QA_OBSERVER_DATA_DIR", "").strip()
    path = Path(value) if value else _project_root() / "data" / "qa_observer"
    if not path.is_absolute():
        path = _project_root() / path
    return path.resolve()


@contextmanager
def observation_context(**values):
    current = dict(_CONTEXT.get())
    current.update({key: value for key, value in values.items() if value is not None})
    token = _CONTEXT.set(current)
    try:
        yield current
    finally:
        _CONTEXT.reset(token)


def current_context():
    return dict(_CONTEXT.get())


def content_fingerprint(value):
    key = os.getenv("QA_OBSERVER_HMAC_KEY", "")
    if not key or value is None:
        return None
    version = os.getenv("QA_OBSERVER_HMAC_KEY_VERSION", "v1").strip() or "v1"
    if not version.startswith("v") or not version[1:].isdigit():
        version = "v1"
    digest = hmac.new(key.encode("utf-8"), str(value).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{version}:{digest}"


def make_event(event_type, payload, source_component, occurred_at=None, **context_overrides):
    context = current_context()
    context.update({key: value for key, value in context_overrides.items() if value is not None})
    event_id = str(uuid.uuid4())
    environment = str(
        context.get("environment") or os.getenv("QA_OBSERVER_ENVIRONMENT", "local")
    ).lower()
    if environment not in {"local", "dev", "stage", "prod"}:
        environment = "local"
    service = str(
        context.get("service")
        or os.getenv("QA_OBSERVER_TARGET_SERVICE", "ai-quality-chatbot")
    )
    trace_id = context.get("trace_id") or uuid.uuid4().hex
    return {
        "event_id": event_id,
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": occurred_at or _utc_now_text(),
        "source": {
            "component": source_component,
            "instance": os.getenv("QA_OBSERVER_SOURCE_INSTANCE") or None,
        },
        "context": {
            "environment": environment,
            "service": service,
            "trace_id": trace_id,
            "run_id": context.get("run_id"),
            "case_id": context.get("case_id"),
        },
        "dedup_key": hashlib.sha256(f"{event_type}:v1:{event_id}".encode("utf-8")).hexdigest(),
        "payload": payload,
    }


def emit_event(event):
    if _has_forbidden_payload_key(event.get("payload")):
        LOGGER.error("telemetry event dropped event_type=%s reason=forbidden_payload_key", event.get("event_type"))
        return {"status": "dropped", "reason": "forbidden_payload_key"}

    observer_url = os.getenv("QA_OBSERVER_URL", "").strip().rstrip("/")
    if observer_url:
        try:
            body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            request = urllib.request.Request(
                observer_url + "/v1/events",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            timeout = max(float(os.getenv("QA_OBSERVER_TIMEOUT_SECONDS", "0.25")), 0.05)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if 200 <= response.status < 300:
                    return {"status": "sent", "event_id": event["event_id"]}
        except urllib.error.HTTPError as exc:
            if exc.code in {409, 422}:
                LOGGER.error(
                    "telemetry event rejected event_type=%s status=%s",
                    event.get("event_type"),
                    exc.code,
                )
                return {"status": "rejected", "http_status": exc.code}
        except (OSError, ValueError, TimeoutError) as exc:
            LOGGER.warning(
                "telemetry delivery unavailable event_type=%s error=%s",
                event.get("event_type"),
                type(exc).__name__,
            )

    try:
        return _append_to_outbox(event)
    except OSError as exc:
        LOGGER.error(
            "telemetry event dropped event_type=%s error=%s",
            event.get("event_type"),
            type(exc).__name__,
        )
        return {"status": "dropped", "reason": "outbox_io_error"}


def emit(event_type, payload, source_component, **context_overrides):
    event = make_event(event_type, payload, source_component, **context_overrides)
    return emit_event(event)


def _append_to_outbox(event):
    occurred_date = str(event["occurred_at"])[:10]
    event_dir = event["event_type"].replace(".", "_")
    outbox_dir = _data_dir() / "outbox" / event_dir
    outbox_dir.mkdir(parents=True, exist_ok=True)
    path = outbox_dir / f"{occurred_date}-{os.getpid()}.jsonl"
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
    encoded = line.encode("utf-8")
    with _OUTBOX_LOCK:
        descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            written = 0
            while written < len(encoded):
                written += os.write(descriptor, encoded[written:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return {"status": "queued", "event_id": event["event_id"], "path": str(path)}


def _has_forbidden_payload_key(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _FORBIDDEN_PAYLOAD_KEYS:
                return True
            if _has_forbidden_payload_key(item):
                return True
    elif isinstance(value, list):
        return any(_has_forbidden_payload_key(item) for item in value)
    return False
