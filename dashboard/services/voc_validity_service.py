from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime

from services import voc_judge_service


SUPPORTED_PROVIDERS = voc_judge_service.SUPPORTED_PROVIDERS
MODEL_ASSESSABLE_HOLD_RULES = {"unsafe_or_noncompliant_action"}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def validity_provider_options() -> list[dict]:
    return [
        {
            "provider": "anthropic",
            "label": "Anthropic",
            "default_model": os.environ.get("A2A_MODEL_VALIDITY_ANTHROPIC")
            or os.environ.get("A2A_MODEL_JUDGE_ANTHROPIC")
            or "claude-opus-4-6",
            "credential_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        },
        {
            "provider": "openai",
            "label": "OpenAI",
            "default_model": os.environ.get("A2A_MODEL_VALIDITY_OPENAI")
            or os.environ.get("A2A_MODEL_JUDGE_OPENAI")
            or "gpt-5.2",
            "credential_configured": bool(os.environ.get("OPENAI_API_KEY")),
        },
        {
            "provider": "gemini",
            "label": "Gemini",
            "default_model": os.environ.get("A2A_MODEL_VALIDITY_GEMINI")
            or os.environ.get("A2A_MODEL_JUDGE_GEMINI")
            or os.environ.get("A2A_MODEL_GEMINI")
            or "gemini-2.5-pro",
            "credential_configured": bool(voc_judge_service.gemini_api_key()),
        },
    ]


def evaluate_improvement_validity(
    *,
    case: dict,
    execution: dict,
    trace: dict,
    judge_result: dict,
    defects: dict,
    rubric: dict,
    provider: str,
    model: str,
    timeout_seconds: int = 90,
    max_retries: int = 2,
    backoff_base_seconds: float = 1.0,
) -> dict:
    provider = str(provider or "").lower()
    model = str(model or "").strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"지원하지 않는 타당성 평가 Provider입니다: {provider}")
    if not model:
        raise ValueError("타당성 평가 모델명을 입력하세요.")

    pre_holds = _evidence_hold_rules(trace, judge_result, defects)
    prompt = _build_prompt(case, execution, trace, judge_result, defects, rubric)
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    attempts = []
    started = time.perf_counter()
    raw_text = ""
    usage = {}

    for attempt in range(1, max_retries + 2):
        attempt_started = _now_iso()
        try:
            raw_text, usage = voc_judge_service._invoke_provider(
                provider=provider,
                model=model,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
            parsed = voc_judge_service._parse_json_response(raw_text)
            scored = _validate_and_score(parsed, rubric, pre_holds)
            attempts.append(
                {
                    "attempt": attempt,
                    "started_at": attempt_started,
                    "finished_at": _now_iso(),
                    "status": "SUCCESS",
                }
            )
            return {
                "status": scored["decision"],
                "decision": scored["decision"],
                "workflow_state": "AI_REVIEWED"
                if scored["decision"] == "AI_PASS"
                else scored["decision"],
                "formal_approval": False,
                "rubric_id": rubric.get("rubric_id"),
                "rubric_version": rubric.get("version"),
                "provider": provider,
                "model": model,
                "dimension_scores": scored["dimension_scores"],
                "total_score": scored["total_score"],
                "all_pass_floors_met": scored["all_pass_floors_met"],
                "immediate_hold_rules_triggered": scored["immediate_hold_rules_triggered"],
                "evidence": parsed.get("evidence", []),
                "risks": parsed.get("risks", []),
                "recommendations": parsed.get("recommendations", []),
                "usage": usage,
                "cost": _calculate_cost(provider, usage),
                "duration_seconds": round(time.perf_counter() - started, 3),
                "prompt_sha256": prompt_hash,
                "attempts": attempts,
                "evaluated_at": _now_iso(),
            }
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            transient = voc_judge_service._is_transient(message)
            auth_error = voc_judge_service._is_auth_error(message)
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
                    "workflow_state": "DRAFT",
                    "formal_approval": False,
                    "rubric_id": rubric.get("rubric_id"),
                    "rubric_version": rubric.get("version"),
                    "provider": provider,
                    "model": model,
                    "dimension_scores": {},
                    "total_score": None,
                    "all_pass_floors_met": False,
                    "immediate_hold_rules_triggered": pre_holds,
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

    raise RuntimeError("타당성 평가가 예상하지 못한 상태로 종료되었습니다.")


def _evidence_hold_rules(trace: dict, judge_result: dict, defects: dict) -> list[str]:
    holds = []
    if not trace.get("trace_id") or not trace.get("events"):
        holds.append("missing_voc_or_trace_evidence")
    if judge_result.get("decision") != "PASS":
        holds.append("judge_error_or_not_run")
    for defect in defects.get("defects", []):
        severity = str(defect.get("severity") or "").upper()
        status = str(defect.get("status") or "OPEN").upper()
        if severity in {"HIGH", "CRITICAL"} and status not in {"CLOSED", "RESOLVED"}:
            holds.append("unresolved_high_or_critical_defect")
            break
    return holds


def _build_prompt(
    case: dict,
    execution: dict,
    trace: dict,
    judge_result: dict,
    defects: dict,
    rubric: dict,
) -> str:
    result = execution.get("result", {}) if isinstance(execution, dict) else {}
    evidence = {
        "case_id": case.get("case_id"),
        "question": case.get("question", ""),
        "required_output": case.get("required_output", []),
        "prohibited_output": case.get("prohibited_output", []),
        "summary": result.get("summary", ""),
        "policy": result.get("policy", ""),
        "trace_id": trace.get("trace_id", ""),
        "trace_events": trace.get("events", [])[-30:],
        "judge": {
            key: judge_result.get(key)
            for key in ("decision", "total_score", "evidence", "risks", "recommendations")
        },
        "defects": defects.get("defects", []),
    }
    contract = {
        "rubric_id": rubric.get("rubric_id"),
        "rubric_version": rubric.get("version"),
        "dimensions": rubric.get("dimensions", {}),
        "server_evaluated_hold_rules_triggered": _evidence_hold_rules(trace, judge_result, defects),
        "model_assessable_hold_rules": sorted(MODEL_ASSESSABLE_HOLD_RULES),
    }
    schema = {
        "dimension_scores": {
            key: {"score": 0, "reason": "증적 기반 평가 사유"}
            for key in rubric.get("dimensions", {})
        },
        "immediate_hold_rules_triggered": [],
        "evidence": ["확인한 구체적 근거"],
        "risks": ["잔여 위험"],
        "recommendations": ["실행 가능한 보완 조치"],
    }
    return (
        "당신은 최종 VOC 정책 개선안의 실행 타당성을 검증하는 독립 평가자입니다.\n"
        "아래 증적만 사용하고 없는 담당자·일정·KPI·법규·결함을 만들지 마세요.\n"
        "즉시 보류 규칙은 model_assessable_hold_rules 안에서만 선택하세요. Trace·Judge·결함 보류는 서버가 판정합니다.\n"
        "각 reason은 300자 이내, 배열은 최대 5개와 항목당 200자 이내로 작성하세요.\n"
        "응답은 Markdown 없이 JSON 객체 하나만 반환하세요.\n\n"
        f"[평가 계약]\n{json.dumps(contract, ensure_ascii=False)}\n\n"
        f"[실행 증적]\n{json.dumps(evidence, ensure_ascii=False, default=str)}\n\n"
        f"[출력 JSON 구조]\n{json.dumps(schema, ensure_ascii=False)}"
    )


def _validate_and_score(payload: dict, rubric: dict, pre_holds: list[str]) -> dict:
    dimensions = rubric.get("dimensions", {})
    scores = payload.get("dimension_scores")
    if not isinstance(scores, dict) or set(scores) != set(dimensions):
        raise ValueError("타당성 차원 점수 키가 Rubric과 일치하지 않습니다.")
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

    model_holds = payload.get("immediate_hold_rules_triggered", [])
    if not isinstance(model_holds, list) or any(rule not in MODEL_ASSESSABLE_HOLD_RULES for rule in model_holds):
        raise ValueError("모델이 판정할 수 없는 즉시 승인 보류 규칙이 포함됐습니다.")
    for field in ("evidence", "risks", "recommendations"):
        values = payload.get(field)
        if not isinstance(values, list):
            raise ValueError(f"타당성 응답의 {field}는 배열이어야 합니다.")
    holds = list(dict.fromkeys([*pre_holds, *model_holds]))
    total = round(sum(item["score"] for item in normalized.values()), 2)
    if total < 65:
        decision = "REJECTED"
    elif total >= 80 and all_floors and not holds:
        decision = "AI_PASS"
    else:
        decision = "REVISION_REQUIRED"
    return {
        "dimension_scores": normalized,
        "total_score": total,
        "decision": decision,
        "all_pass_floors_met": all_floors,
        "immediate_hold_rules_triggered": holds,
    }


def _calculate_cost(provider: str, usage: dict) -> dict:
    prefix = f"A2A_VALIDITY_{provider.upper()}"
    input_rate = os.environ.get(f"{prefix}_INPUT_KRW_PER_MTOK")
    output_rate = os.environ.get(f"{prefix}_OUTPUT_KRW_PER_MTOK")
    if input_rate is None or output_rate is None:
        return {"currency": "KRW", "amount": None, "pricing_status": "NOT_CONFIGURED"}
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
