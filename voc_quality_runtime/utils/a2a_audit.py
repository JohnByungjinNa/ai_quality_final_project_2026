from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Iterable, TypeVar

T = TypeVar("T")

AUDIT_DIR = Path(os.environ.get("A2A_AUDIT_DIR", ".runtime/audit"))
AUDIT_FILE = AUDIT_DIR / "a2a_events.jsonl"

_STOP_WORDS = {
    "그리고", "그러나", "대한", "관련", "고객", "내용", "있는", "없는", "합니다",
    "했습니다", "요청", "결과", "처리", "the", "and", "for", "with", "from",
}


def new_trace_id() -> str:
    return uuid.uuid4().hex


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
    try:
        result = await call
        output_keywords = extract_keywords(result)
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
