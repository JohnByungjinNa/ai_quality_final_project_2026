"""
api_app.py
- 1단계 산출물: Service Agent를 FastAPI API로 제공
- /: API 안내
- /health: 서버 상태 확인
- /ask: 사용자 질문에 대한 챗봇 응답 반환
"""

import time
import uuid
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Response
from pydantic import BaseModel, Field

from service_agent import get_response
from qa_observer.telemetry import emit, observation_context


app = FastAPI(
    title="AI Education Chatbot Service Agent API",
    description="AI 교육과정 안내 챗봇 Service Agent API",
    version="1.0.0",
)


REQUEST_BUCKETS = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10]
_metrics_lock = Lock()
_request_counts = defaultdict(int)
_duration_bucket_counts = defaultdict(int)
_duration_count = 0
_duration_sum = 0.0


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="사용자 질문")


class AskResponse(BaseModel):
    question: str
    answer: str


@app.middleware("http")
async def collect_http_metrics(request, call_next):
    global _duration_count, _duration_sum

    start_time = time.perf_counter()
    trace_id = _trace_id_from_request(request) or uuid.uuid4().hex
    response = None
    error_type = None
    with observation_context(trace_id=trace_id, service="ai-quality-api"):
        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            error_type = type(exc).__name__.lower()
            raise
        finally:
            duration = time.perf_counter() - start_time
            path = request.url.path
            status_code = response.status_code if response is not None else 500
            if path != "/metrics":
                route = request.scope.get("route")
                route_template = getattr(route, "path", None) or path
                labels = (request.method, route_template, str(status_code))
                with _metrics_lock:
                    _request_counts[labels] += 1
                    _duration_count += 1
                    _duration_sum += duration
                    for bucket in REQUEST_BUCKETS:
                        if duration <= bucket:
                            _duration_bucket_counts[bucket] += 1
                    _duration_bucket_counts[float("inf")] += 1
                emit(
                    "api.request.completed",
                    {
                        "method": request.method,
                        "route_template": route_template,
                        "status_code": status_code,
                        "duration_ms": max(int(round(duration * 1000)), 0),
                        "timeout": False,
                        "error_type": error_type,
                    },
                    "fastapi_middleware",
                )


@app.get("/")
def root():
    return {
        "service": "AI Education Chatbot Service Agent API",
        "status": "running",
        "endpoints": {
            "health": "GET /health",
            "ask": "POST /ask",
            "docs": "GET /docs",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-agent"}


@app.get("/metrics")
def metrics():
    lines = [
        "# HELP http_requests_total Total HTTP requests.",
        "# TYPE http_requests_total counter",
    ]

    with _metrics_lock:
        request_counts = dict(_request_counts)
        bucket_counts = dict(_duration_bucket_counts)
        duration_count = _duration_count
        duration_sum = _duration_sum

    for (method, path, status), count in sorted(request_counts.items()):
        lines.append(
            f'http_requests_total{{method="{escape_label(method)}",path="{escape_label(path)}",status="{escape_label(status)}"}} {count}'
        )

    lines.extend(
        [
            "# HELP agent_response_seconds HTTP response duration in seconds.",
            "# TYPE agent_response_seconds histogram",
        ]
    )
    for bucket in REQUEST_BUCKETS:
        lines.append(f'agent_response_seconds_bucket{{le="{bucket:g}"}} {bucket_counts.get(bucket, 0)}')
    lines.append(f'agent_response_seconds_bucket{{le="+Inf"}} {bucket_counts.get(float("inf"), 0)}')
    lines.append(f"agent_response_seconds_count {duration_count}")
    lines.append(f"agent_response_seconds_sum {duration_sum}")

    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    answer = get_response(request.question)
    return {"question": request.question, "answer": answer}


@app.get("/ask", response_model=AskResponse)
def ask_get(question: str):
    answer = get_response(question)
    return {"question": question, "answer": answer}


def escape_label(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _trace_id_from_request(request):
    traceparent = str(request.headers.get("traceparent") or "").strip().lower()
    parts = traceparent.split("-")
    if len(parts) >= 4 and len(parts[1]) == 32 and all(char in "0123456789abcdef" for char in parts[1]):
        return parts[1]
    candidate = str(request.headers.get("x-trace-id") or "").strip().lower()
    if len(candidate) == 32 and all(char in "0123456789abcdef" for char in candidate):
        return candidate
    return None
