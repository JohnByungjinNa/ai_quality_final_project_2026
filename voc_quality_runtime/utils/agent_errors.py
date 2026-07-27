from __future__ import annotations

import re

import grpc


_SECRET_PATTERNS = (
    re.compile(r"sk-proj-[A-Za-z0-9_*.-]{8,}"),
    re.compile(r"sk-[A-Za-z0-9_*.-]{12,}"),
)


def _redact(value: str) -> str:
    text = str(value or "")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED_CREDENTIAL]", text)
    return text


def agent_rpc_error(exc: Exception, component: str) -> tuple[grpc.StatusCode, str]:
    """외부 API 오류를 비밀값 없는 표준 gRPC 상태와 안내로 변환합니다."""
    raw = _redact(f"{type(exc).__name__}: {exc}")
    lowered = raw.lower()
    if (
        "incorrect api key" in lowered
        or "authentication_error" in lowered
        or ("401" in lowered and ("openai" in lowered or "api key" in lowered))
    ):
        return (
            grpc.StatusCode.UNAUTHENTICATED,
            f"{component}: OpenAI API 키 인증 실패(HTTP 401). "
            ".env의 OPENAI_API_KEY를 교체하고 Agent 전체를 재시작하세요.",
        )
    if "rate limit" in lowered or "429" in lowered:
        return (
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            f"{component}: 외부 LLM 호출 한도 초과(HTTP 429). 잠시 후 다시 시도하세요.",
        )
    if "timeout" in lowered or "timed out" in lowered or "deadline" in lowered:
        return (
            grpc.StatusCode.DEADLINE_EXCEEDED,
            f"{component}: 외부 LLM 응답 시간이 초과되었습니다.",
        )
    return grpc.StatusCode.INTERNAL, f"{component}: {raw[:400]}"
