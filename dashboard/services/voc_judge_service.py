from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path


SUPPORTED_PROVIDERS = ("anthropic", "openai", "gemini")
TRANSIENT_MARKERS = (
    "429", "rate limit", "rate_limit", "too many requests", "timeout",
    "timed out", "deadline_exceeded", "overloaded",
)
AUTH_MARKERS = (
    "authentication", "unauthorized", "invalid api key", "api key not valid",
    "credentials missing", "permission denied", "401", "403",
)


def gemini_api_key() -> str:
    configured = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_GENAI_API_KEY")
        or ""
    )
    if configured:
        return configured
    project_root = Path(__file__).resolve().parents[2]
    for path in (project_root / "voc_quality_runtime" / ".env", project_root / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            trimmed = line.strip()
            if not trimmed or trimmed.startswith("#") or "=" not in trimmed:
                continue
            key, value = trimmed.split("=", 1)
            if key.strip() not in {"GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY"}:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            return value
    return ""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def judge_provider_options() -> list[dict]:
    return [
        {
            "provider": "anthropic",
            "label": "Anthropic",
            "default_model": os.environ.get("A2A_MODEL_JUDGE_ANTHROPIC")
            or "claude-haiku-4-5",
            "credential_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        {
            "provider": "openai",
            "label": "OpenAI",
            "default_model": os.environ.get("A2A_MODEL_JUDGE_OPENAI")
            or os.environ.get("A2A_MODEL_SUMMARY", "gpt-5.2"),
            "credential_configured": bool(os.environ.get("OPENAI_API_KEY")),
        },
        {
            "provider": "gemini",
            "label": "Gemini",
            "default_model": os.environ.get("A2A_MODEL_JUDGE_GEMINI")
            or os.environ.get("A2A_MODEL_GEMINI")
            or "gemini-3.5-flash-lite",
            "credential_configured": bool(gemini_api_key()),
        },
    ]


def independence_grade(provider: str, model: str, generator_snapshot: dict) -> dict:
    target = generator_snapshot.get("policy", {})
    generator_provider = str(target.get("provider") or "").lower()
    generator_model = str(target.get("model") or "")
    judge_provider = str(provider or "").lower()
    if judge_provider != generator_provider:
        grade = "A"
        reason = "최종 개선안 생성 Provider와 Judge Provider가 다릅니다."
    elif _normalized_model(model) != _normalized_model(generator_model):
        grade = "B"
        reason = "Provider는 같지만 모델과 호출 세션·Judge 프롬프트가 분리됩니다."
    else:
        grade = "C"
        reason = "최종 개선안 생성과 같은 Provider·모델이어서 편향 위험이 높습니다."
    return {
        "grade": grade,
        "reason": reason,
        "generator_provider": generator_provider,
        "generator_model": generator_model,
        "judge_provider": judge_provider,
        "judge_model": model,
    }


def apply_independence_gate(result: dict) -> dict:
    gated = dict(result)
    rubric_decision = gated.get("rubric_decision") or gated.get("decision")
    independence_hold = gated.get("independence_grade") == "C" and rubric_decision == "PASS"
    gated["rubric_decision"] = rubric_decision
    gated["independence_hold"] = independence_hold
    gated["independence_hold_reason"] = (
        "독립성 C는 같은 Provider·모델 편향 위험으로 사람 검토가 필요합니다."
        if independence_hold else ""
    )
    if independence_hold:
        gated["decision"] = "REVIEW_REQUIRED"
        gated["status"] = "REVIEW_REQUIRED"
    return gated


def _normalized_model(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def evaluate_independent_judge(
    *,
    case: dict,
    execution: dict,
    trace: dict,
    rubric: dict,
    provider: str,
    model: str,
    generator_snapshot: dict,
    timeout_seconds: int = 90,
    max_retries: int = 2,
    backoff_base_seconds: float = 1.0,
) -> dict:
    provider = str(provider or "").lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"지원하지 않는 Judge Provider입니다: {provider}")
    if not str(model or "").strip():
        raise ValueError("Judge 모델명을 입력하세요.")

    prompt = _build_prompt(case, execution, trace, rubric)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    independence = independence_grade(provider, model, generator_snapshot)
    attempts = []
    started = time.perf_counter()
    raw_text = ""
    usage = {}

    for attempt in range(1, max_retries + 2):
        attempt_started = _now_iso()
        try:
            raw_text, usage = _invoke_provider(
                provider=provider,
                model=model,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
            parsed = _parse_json_response(raw_text)
            scored = _validate_and_score(parsed, rubric)
            effective_decision = scored["decision"]
            independence_hold = independence["grade"] == "C" and effective_decision == "PASS"
            if independence_hold:
                effective_decision = "REVIEW_REQUIRED"
            attempts.append(
                {
                    "attempt": attempt,
                    "started_at": attempt_started,
                    "finished_at": _now_iso(),
                    "status": "SUCCESS",
                }
            )
            cost = _calculate_cost(provider, usage)
            return {
                "status": effective_decision,
                "rubric_id": rubric.get("rubric_id"),
                "rubric_version": rubric.get("version"),
                "provider": provider,
                "model": model,
                "independence_grade": independence["grade"],
                "independence": independence,
                "dimension_scores": scored["dimension_scores"],
                "total_score": scored["total_score"],
                "decision": effective_decision,
                "rubric_decision": scored["decision"],
                "independence_hold": independence_hold,
                "independence_hold_reason": (
                    "독립성 C는 같은 Provider·모델 편향 위험으로 사람 검토가 필요합니다."
                    if independence_hold else ""
                ),
                "all_pass_floors_met": scored["all_pass_floors_met"],
                "immediate_fail_rules_triggered": scored["immediate_fail_rules_triggered"],
                "evidence": parsed.get("evidence", []),
                "risks": parsed.get("risks", []),
                "recommendations": parsed.get("recommendations", []),
                "usage": usage,
                "cost": cost,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "prompt_sha256": prompt_hash,
                "attempts": attempts,
                "evaluated_at": _now_iso(),
            }
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            transient = _is_transient(message)
            auth_error = _is_auth_error(message)
            attempts.append(
                {
                    "attempt": attempt,
                    "started_at": attempt_started,
                    "finished_at": _now_iso(),
                    "status": "ERROR",
                    "transient": transient,
                    "error_type": "AUTHENTICATION" if auth_error else type(exc).__name__,
                    "message": message[:500],
                }
            )
            if auth_error or not transient or attempt > max_retries:
                return {
                    "status": "ERROR",
                    "decision": "ERROR",
                    "rubric_id": rubric.get("rubric_id"),
                    "rubric_version": rubric.get("version"),
                    "provider": provider,
                    "model": model,
                    "independence_grade": independence["grade"],
                    "independence": independence,
                    "dimension_scores": {},
                    "total_score": None,
                    "evidence": [],
                    "risks": [],
                    "recommendations": [],
                    "usage": usage,
                    "cost": _calculate_cost(provider, usage),
                    "duration_seconds": round(time.perf_counter() - started, 3),
                    "prompt_sha256": prompt_hash,
                    "attempts": attempts,
                    "error_type": "AUTHENTICATION" if auth_error else type(exc).__name__,
                    "error": message[:1000],
                    "raw_response_excerpt": raw_text[:1000],
                    "evaluated_at": _now_iso(),
                }
            time.sleep(max(0.0, backoff_base_seconds) * (2 ** (attempt - 1)))

    raise RuntimeError("Judge 실행이 예상하지 못한 상태로 종료되었습니다.")


def _build_prompt(case: dict, execution: dict, trace: dict, rubric: dict) -> str:
    result = execution.get("result", {}) if isinstance(execution, dict) else {}
    evidence = {
        "case_id": case.get("case_id"),
        "question": case.get("question", ""),
        "expected_intent": case.get("expected_intent", ""),
        "expected_task": case.get("expected_task", ""),
        "required_output": case.get("required_output", []),
        "prohibited_output": case.get("prohibited_output", []),
        "pipeline_ok": bool(execution.get("ok") and result.get("ok")),
        "summary": result.get("summary", ""),
        "policy": result.get("policy", ""),
        "intent": result.get("intent_json", {}),
        "evaluator": result.get("eval_json", {}),
        "critic": result.get("summary_critic_json", {}),
        "trace_id": trace.get("trace_id", ""),
        "trace_events": trace.get("events", [])[-30:],
    }
    judge_contract = {
        "rubric_id": rubric.get("rubric_id"),
        "rubric_version": rubric.get("version"),
        "dimensions": rubric.get("dimensions", {}),
        "immediate_fail_rules": rubric.get("immediate_fail_rules", []),
    }
    schema_example = {
        "dimension_scores": {
            key: {"score": 0, "reason": "근거 기반 판정 사유"}
            for key in rubric.get("dimensions", {})
        },
        "immediate_fail_rules_triggered": [],
        "evidence": ["확인한 구체적 근거"],
        "risks": ["잔여 위험"],
        "recommendations": ["보완 권고"],
    }
    return (
        "당신은 VOC 개선안 생성 Pipeline과 분리된 독립 품질 Judge입니다.\n"
        "아래 증적만 사용하고, 없는 사실을 추정하지 마세요. 각 차원 점수는 max_points 이하여야 합니다.\n"
        "각 차원의 reason은 300자 이내, evidence·risks·recommendations는 각각 최대 5개와 항목당 200자 이내로 작성하세요.\n"
        "응답은 설명문이나 Markdown 없이 JSON 객체 하나만 반환하세요.\n\n"
        f"[평가 계약]\n{json.dumps(judge_contract, ensure_ascii=False)}\n\n"
        f"[실행 증적]\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
        f"[출력 JSON 구조]\n{json.dumps(schema_example, ensure_ascii=False)}"
    )


def _invoke_provider(*, provider: str, model: str, prompt: str, timeout_seconds: int) -> tuple[str, dict]:
    if provider == "anthropic":
        from anthropic import Anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("Anthropic credentials missing")
        response = Anthropic(api_key=api_key, timeout=timeout_seconds).messages.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(getattr(block, "text", "") for block in response.content)
        usage = {
            "input_tokens": int(getattr(response.usage, "input_tokens", 0) or 0),
            "output_tokens": int(getattr(response.usage, "output_tokens", 0) or 0),
        }
        return text, usage

    if provider == "gemini":
        from google import genai
        from google.genai import types

        api_key = gemini_api_key()
        if not api_key:
            raise RuntimeError("Gemini credentials missing")
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)),
        )
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=4096,
                response_mime_type="application/json",
            ),
        )
        text = str(getattr(response, "text", "") or "").strip()
        usage_obj = getattr(response, "usage_metadata", None)
        usage = {
            "input_tokens": int(getattr(usage_obj, "prompt_token_count", 0) or 0),
            "output_tokens": int(getattr(usage_obj, "candidates_token_count", 0) or 0),
        }
        return text, usage

    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI credentials missing")
    response = OpenAI(api_key=api_key, timeout=timeout_seconds).chat.completions.create(
        model=model,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    usage_obj = getattr(response, "usage", None)
    usage = {
        "input_tokens": int(getattr(usage_obj, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage_obj, "completion_tokens", 0) or 0),
    }
    return response.choices[0].message.content or "", usage


def _parse_json_response(raw_text: str) -> dict:
    text = str(raw_text or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Judge 응답은 JSON 객체여야 합니다.")
    return payload


def _validate_and_score(payload: dict, rubric: dict) -> dict:
    dimensions = rubric.get("dimensions", {})
    scores = payload.get("dimension_scores")
    if not isinstance(scores, dict) or set(scores) != set(dimensions):
        raise ValueError("Judge 차원 점수 키가 Rubric과 일치하지 않습니다.")
    normalized = {}
    all_floors = True
    for key, spec in dimensions.items():
        item = scores[key]
        if not isinstance(item, dict) or "score" not in item:
            raise ValueError(f"{key} 점수와 사유가 필요합니다.")
        score = float(item["score"])
        if score < 0 or score > float(spec["max_points"]):
            raise ValueError(f"{key} 점수가 허용 범위를 벗어났습니다.")
        reason = str(item.get("reason") or "").strip()
        if not reason:
            raise ValueError(f"{key} 판정 사유가 필요합니다.")
        normalized[key] = {"score": score, "reason": reason, "max_points": spec["max_points"]}
        all_floors = all_floors and score >= float(spec["pass_floor"])

    allowed_fail_rules = set(rubric.get("immediate_fail_rules", []))
    triggered = payload.get("immediate_fail_rules_triggered", [])
    if not isinstance(triggered, list) or any(rule not in allowed_fail_rules for rule in triggered):
        raise ValueError("정의되지 않은 즉시 FAIL 규칙이 포함됐습니다.")
    for field in ("evidence", "risks", "recommendations"):
        if field not in payload or not isinstance(payload[field], list):
            raise ValueError(f"Judge 응답의 {field}는 배열이어야 합니다.")
    total = round(sum(item["score"] for item in normalized.values()), 2)
    if triggered or total < 65:
        decision = "FAIL"
    elif total >= 80 and all_floors:
        decision = "PASS"
    else:
        decision = "REVIEW_REQUIRED"
    return {
        "dimension_scores": normalized,
        "total_score": total,
        "decision": decision,
        "all_pass_floors_met": all_floors,
        "immediate_fail_rules_triggered": triggered,
    }


def _is_transient(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in TRANSIENT_MARKERS)


def _is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in AUTH_MARKERS)


def _calculate_cost(provider: str, usage: dict) -> dict:
    prefix = f"A2A_JUDGE_{provider.upper()}"
    input_rate = os.environ.get(f"{prefix}_INPUT_KRW_PER_MTOK")
    output_rate = os.environ.get(f"{prefix}_OUTPUT_KRW_PER_MTOK")
    if input_rate is None or output_rate is None:
        return {
            "currency": "KRW",
            "amount": None,
            "pricing_status": "NOT_CONFIGURED",
        }
    amount = (
        int(usage.get("input_tokens", 0)) * float(input_rate)
        + int(usage.get("output_tokens", 0)) * float(output_rate)
    ) / 1_000_000
    return {
        "currency": "KRW",
        "amount": round(amount, 6),
        "pricing_status": "CONFIGURED",
        "input_krw_per_mtok": float(input_rate),
        "output_krw_per_mtok": float(output_rate),
    }
