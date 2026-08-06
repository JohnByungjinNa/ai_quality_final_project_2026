from __future__ import annotations

import json
import hashlib
import os
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Iterable, TypeVar
from contextlib import nullcontext

T = TypeVar("T")

AUDIT_DIR = Path(os.environ.get("A2A_AUDIT_DIR", ".runtime/audit"))
AUDIT_FILE = AUDIT_DIR / "a2a_events.jsonl"
_TRACER = None
_TRACER_INITIALIZED = False

_STOP_WORDS = {
    "그리고", "그러나", "대한", "관련", "고객", "내용", "있는", "없는", "합니다",
    "했습니다", "요청", "결과", "처리", "the", "and", "for", "with", "from",
}


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _tempo_tracer():
    global _TRACER, _TRACER_INITIALIZED
    if _TRACER_INITIALIZED:
        return _TRACER
    _TRACER_INITIALIZED = True
    if os.environ.get("A2A_TEMPO_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318").rstrip("/")
        provider = TracerProvider(
            resource=Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "voc-a2a-agent")})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces", timeout=2))
        )
        trace.set_tracer_provider(provider)
        _TRACER = trace.get_tracer("voc.a2a.audit")
    except Exception:
        _TRACER = None
    return _TRACER


def _rpc_span(trace_id: str, source: str, target: str, operation: str):
    tracer = _tempo_tracer()
    if tracer is None:
        return nullcontext(None)
    try:
        from opentelemetry import trace
        from opentelemetry.trace import NonRecordingSpan, SpanContext, SpanKind, TraceFlags, TraceState

        trace_value = int(trace_id, 16)
        parent_value = int(hashlib.sha256(f"{trace_id}:{source}".encode()).hexdigest()[:16], 16) or 1
        parent = NonRecordingSpan(
            SpanContext(trace_value, parent_value, True, TraceFlags.SAMPLED, TraceState())
        )
        return tracer.start_as_current_span(
            operation,
            context=trace.set_span_in_context(parent),
            kind=SpanKind.CLIENT,
            attributes={
                "rpc.system": "grpc",
                "rpc.service": target,
                "rpc.method": operation,
                "a2a.source": source,
                "a2a.target": target,
                "trace_id": trace_id,
            },
        )
    except Exception:
        return nullcontext(None)


def extract_keywords(values: Any, limit: int = 10) -> list[str]:
    if values is None:
        return []
    if isinstance(values, dict):
        text = " ".join(f"{key} {value}" for key, value in values.items())
    elif isinstance(values, (list, tuple, set)):
        text = " ".join(str(value) for value in values)
    else:
        text = str(values)
    tokens = re.findall(r"[가-힣A-Za-z0-9_]{2,}", text.lower())
    counts = Counter(token for token in tokens if token not in _STOP_WORDS and not token.isdigit())
    return [token for token, _ in counts.most_common(limit)]


def record_event(
    *,
    trace_id: str,
    source: str,
    target: str,
    operation: str,
    status: str,
    duration_ms: float,
    keywords: Iterable[str] = (),
    item_count: int | None = None,
    error: str | None = None,
    agent_chain: Iterable[str] = (),
    input_keywords: Iterable[str] = (),
    output_keywords: Iterable[str] = (),
) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "trace_id": trace_id,
        "source": source,
        "target": target,
        "operation": operation,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "keywords": list(dict.fromkeys(keywords))[:10],
    }
    if input_keywords:
        event["input_keywords"] = list(dict.fromkeys(input_keywords))[:10]
    if output_keywords:
        event["output_keywords"] = list(dict.fromkeys(output_keywords))[:10]
    if item_count is not None:
        event["item_count"] = item_count
    if error:
        event["error"] = error[:2000]
    if agent_chain:
        event["agent_chain"] = list(dict.fromkeys(agent_chain))
    with AUDIT_FILE.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + "\n")


async def audited_rpc(
    call: Awaitable[T],
    *,
    trace_id: str,
    source: str,
    target: str,
    operation: str,
    input_data: Any = None,
) -> T:
    started = time.perf_counter()
    input_keywords = extract_keywords(input_data)
    record_event(
        trace_id=trace_id,
        source=source,
        target=target,
        operation=operation,
        status="started",
        duration_ms=0,
        keywords=input_keywords,
        input_keywords=input_keywords,
    )
    with _rpc_span(trace_id, source, target, operation) as span:
        try:
            result = await call
            output_keywords = extract_keywords(result)
            if span is not None:
                span.set_attribute("a2a.status", "success")
            record_event(
                trace_id=trace_id,
                source=source,
                target=target,
                operation=operation,
                status="success",
                duration_ms=(time.perf_counter() - started) * 1000,
                keywords=input_keywords + output_keywords,
                input_keywords=input_keywords,
                output_keywords=output_keywords,
            )
            return result
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            if span is not None:
                span.set_attribute("a2a.status", "failure")
                span.record_exception(exc)
            known_agents = ("Interpreter", "Retriever", "Summarizer", "Evaluator", "Critic", "Improver")
            observed_chain = [source, target] + [name for name in known_agents if name in error_text]
            record_event(
                trace_id=trace_id,
                source=source,
                target=target,
                operation=operation,
                status="failure",
                duration_ms=(time.perf_counter() - started) * 1000,
                keywords=input_keywords,
                input_keywords=input_keywords,
                error=error_text,
                agent_chain=observed_chain,
            )
            raise
