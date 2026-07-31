from collections import defaultdict

import pandas as pd


def build_overview(
    summary,
    timeseries_items,
    event_records,
    observer_health=None,
    quality_event_records=None,
    safety_event_records=None,
):
    quality_records = event_records if quality_event_records is None else quality_event_records
    safety_records = event_records if safety_event_records is None else safety_event_records
    return {
        "status": evaluate_overall_status(summary, observer_health),
        "collection": build_collection_status(summary, observer_health),
        "safety_incidents": build_safety_incidents(safety_records),
        "quality_trend": build_quality_run_trend(quality_records),
        "traffic_trend": build_traffic_trend(timeseries_items),
        "test_distribution": build_test_distribution(timeseries_items),
        "quality_indicators": build_quality_indicators(timeseries_items),
        "latency_breakdown": build_latency_breakdown(timeseries_items),
        "llm_usage": build_llm_usage(timeseries_items, summary),
        "operation_status": build_operation_status(summary),
        "rag_quality": build_rag_quality(timeseries_items, summary),
        "events": build_event_table(event_records),
        "issues": build_issue_table(event_records),
        "alerts": build_alerts(summary),
        "actions": recommend_actions(summary),
    }


def evaluate_overall_status(summary, observer_health=None):
    if not summary or summary.get("data_status") == "no_data":
        return {"level": "no_data", "label": "데이터 없음", "reason": "선택 기간에 수집된 이벤트가 없습니다."}
    if (summary.get("safety_violation_count") or 0) >= 1:
        return {"level": "danger", "label": "위험", "reason": "High/Critical 안전성 위반이 감지되었습니다."}
    danger_checks = [
        (summary.get("api_error_rate"), lambda value: value > 2, "API 오류율이 2%를 초과했습니다."),
        (summary.get("api_p95_duration_ms"), lambda value: value > 8000, "p95 응답시간이 8초를 초과했습니다."),
        (summary.get("quality_score"), lambda value: value < 80, "전체 품질점수가 80점 미만입니다."),
        (summary.get("test_pass_rate"), lambda value: value < 85, "테스트 통과율이 85% 미만입니다."),
        (summary.get("budget_usage_rate"), lambda value: value >= 100, "일 API 예산을 초과했습니다."),
    ]
    for value, check, reason in danger_checks:
        if value is not None and check(value):
            return {"level": "danger", "label": "위험", "reason": reason}
    if observer_health and not build_collection_status(summary, observer_health)["healthy"]:
        return {"level": "warning", "label": "주의", "reason": "qa-observer 수집기 상태를 확인해야 합니다."}
    warning_checks = [
        (summary.get("api_error_rate"), lambda value: value > 1, "API 오류율이 주의 범위입니다."),
        (summary.get("api_p95_duration_ms"), lambda value: value > 5000, "p95 응답시간이 5초를 초과했습니다."),
        (summary.get("quality_score"), lambda value: value < 90, "전체 품질점수가 90점 미만입니다."),
        (summary.get("test_pass_rate"), lambda value: value < 95, "테스트 통과율이 95% 미만입니다."),
        (summary.get("rag_no_result_rate"), lambda value: value > 5, "RAG No Result 비율이 5%를 초과했습니다."),
        (summary.get("budget_usage_rate"), lambda value: value >= 80, "일 API 예산의 80% 이상을 사용했습니다."),
    ]
    for value, check, reason in warning_checks:
        if value is not None and check(value):
            return {"level": "warning", "label": "주의", "reason": reason}
    return {"level": "normal", "label": "정상", "reason": "승인된 운영 기준을 모두 충족합니다."}


def build_collection_status(summary, observer_health=None):
    health = observer_health or {}
    scheduler = health.get("scheduler") or {}
    storage = health.get("storage") or {}
    healthy = (
        health.get("status") == "healthy"
        and scheduler.get("running") is True
        and storage.get("writable") is True
        and not scheduler.get("last_error_type")
    )
    return {
        "healthy": healthy,
        "status": health.get("status") or "unknown",
        "scheduler_running": scheduler.get("running"),
        "last_success_at_utc": scheduler.get("last_success_at_utc"),
        "last_error_type": scheduler.get("last_error_type"),
        "interval_seconds": scheduler.get("interval_seconds"),
        "event_data_status": summary.get("data_status"),
        "event_freshness_seconds": summary.get("freshness_seconds"),
        "latest_event_at_utc": summary.get("latest_received_at_utc"),
    }


def build_safety_incidents(records):
    rows = []
    for record in records:
        event = record.get("event", {})
        if event.get("event_type") != "safety.violation.detected":
            continue
        context = event.get("context", {})
        payload = event.get("payload", {})
        rows.append(
            {
                "발생 시각(UTC)": event.get("occurred_at"),
                "Run ID": context.get("run_id") or "-",
                "Case ID": context.get("case_id") or "-",
                "심각도": str(payload.get("severity") or "high").upper(),
                "탐지 기준": payload.get("category") or "safety",
                "권장 조치": payload.get("action") or "review_required",
                "차단됨": "예" if payload.get("blocked") else "아니오",
            }
        )
    return pd.DataFrame(rows)


def build_quality_run_trend(records, limit=7):
    grouped = {}
    for record in records:
        event = record.get("event", {})
        if event.get("event_type") != "quality.evaluation.completed":
            continue
        context = event.get("context", {})
        run_id = context.get("run_id")
        if not run_id:
            continue
        occurred_at = str(event.get("occurred_at") or "")
        group = grouped.setdefault(
            str(run_id),
            {"occurred_at": occurred_at, "scores": [], "case_ids": set()},
        )
        group["occurred_at"] = max(group["occurred_at"], occurred_at)
        if context.get("case_id"):
            group["case_ids"].add(str(context["case_id"]))
        for score in (event.get("payload", {}).get("scores") or {}).values():
            if score.get("evaluated") and score.get("score") is not None:
                group["scores"].append(float(score["score"]))

    selected = sorted(
        grouped.items(),
        key=lambda item: item[1]["occurred_at"],
        reverse=True,
    )[: max(1, int(limit))]
    rows = []
    for run_id, values in reversed(selected):
        if not values["scores"]:
            continue
        rows.append(
            {
                "실행": _run_label(run_id, values["occurred_at"]),
                "Run ID": run_id,
                "품질점수": round(sum(values["scores"]) / len(values["scores"]) * 20, 2),
                "테스트 케이스": len(values["case_ids"]),
            }
        )
    return pd.DataFrame(rows)


def _run_label(run_id, occurred_at):
    compact = str(run_id).removeprefix("RUN-")
    if len(compact) >= 12 and compact[:12].isdigit():
        return f"{compact[4:6]}/{compact[6:8]} {compact[8:10]}:{compact[10:12]}"
    return str(occurred_at)[5:16].replace("T", " ") or str(run_id)[-12:]


def build_traffic_trend(items):
    grouped = defaultdict(dict)
    mapping = {
        "api.requests": "요청 수",
        "api.service_errors": "서비스 오류 수",
        "api.client_errors": "클라이언트 오류 수",
    }
    for item in items:
        column = mapping.get(item.get("metric"))
        if column:
            grouped[item["date"]][column] = float(item.get("sum_value") or 0)
    rows = []
    for day, values in grouped.items():
        rows.append({"날짜": day, **{name: values.get(name, 0) for name in mapping.values()}})
    return pd.DataFrame(sorted(rows, key=lambda row: row["날짜"]))


def build_quality_indicators(items):
    latest = {}
    labels = {
        "quality.accuracy.score": "정확성",
        "quality.groundedness.score": "근거성",
        "quality.helpfulness.score": "유용성",
        "quality.safety.score": "안전성",
        "quality.relevance.score": "관련성",
        "quality.faithfulness.score": "신뢰성",
        "quality.confidence.score": "신뢰도",
    }
    for item in items:
        metric = item.get("metric")
        if metric in labels and item.get("average_value") is not None:
            latest[metric] = (item["date"], float(item["average_value"]) * 20)
    rows = [{"품질 지표": labels[key], "점수": round(value[1], 2)} for key, value in latest.items()]
    return pd.DataFrame(rows)


def build_latency_breakdown(items):
    metrics = {
        "api.duration_ms": "API 전체",
        "llm.duration_ms": "독립 LLM 평가",
        "rag.duration_ms": "RAG 검색",
        "test.duration_ms": "테스트 실행",
    }
    aggregated = defaultdict(lambda: {"sum": 0.0, "count": 0.0})
    for item in items:
        metric = item.get("metric")
        if metric not in metrics:
            continue
        sample_count = float(item.get("sample_count") or 0)
        if item.get("sum_value") is not None and sample_count:
            aggregated[metric]["sum"] += float(item["sum_value"])
            aggregated[metric]["count"] += sample_count
        elif item.get("average_value") is not None:
            aggregated[metric]["sum"] += float(item["average_value"])
            aggregated[metric]["count"] += 1
    return pd.DataFrame(
        [
            {
                "단계": metrics[key],
                "평균 시간(ms)": round(value["sum"] / value["count"], 2),
            }
            for key, value in aggregated.items()
            if value["count"]
        ]
    )


def build_llm_usage(items, summary):
    metrics = {
        "llm.requests": "request_count",
        "llm.input_tokens": "input_tokens",
        "llm.output_tokens": "output_tokens",
        "llm.cached_input_tokens": "cached_input_tokens",
        "llm.total_tokens": "total_tokens",
        "llm.cost_micros_krw": "cost_micros_krw",
    }
    totals = defaultdict(float)
    for item in items:
        key = metrics.get(item.get("metric"))
        if key:
            totals[key] += float(item.get("sum_value") or 0)
    total_tokens = summary.get("llm_total_tokens")
    if total_tokens is None:
        total_tokens = totals["total_tokens"] or None
    return {
        "request_count": int(totals["request_count"]),
        "input_tokens": int(totals["input_tokens"]),
        "output_tokens": int(totals["output_tokens"]),
        "cached_input_tokens": int(totals["cached_input_tokens"]),
        "total_tokens": None if total_tokens is None else int(total_tokens),
        "cost_krw": summary.get("llm_cost_krw"),
        "price_coverage": summary.get("llm_price_coverage"),
        "daily_budget_krw": summary.get("daily_budget_krw"),
        "budget_usage_rate": summary.get("budget_usage_rate"),
    }


def build_test_distribution(items):
    mapping = {
        "test.pass_count": "Pass",
        "test.fail_count": "Fail",
        "test.error_count": "Error",
    }
    totals = defaultdict(float)
    for item in items:
        label = mapping.get(item.get("metric"))
        if label:
            totals[label] += float(item.get("sum_value") or 0)
    return pd.DataFrame(
        [{"결과": label, "건수": int(totals.get(label, 0))} for label in ("Pass", "Fail", "Error")]
    )


def build_operation_status(summary):
    return [
        _operation_item(
            "정확성",
            summary.get("quality_score"),
            [(80, "danger"), (90, "warning")],
            higher_is_better=True,
        ),
        (
            {"영역": "안전성", "상태": "no_data", "설명": "데이터 없음"}
            if summary.get("safety_violation_count") is None
            else {
                "영역": "안전성",
                "상태": "danger" if summary["safety_violation_count"] else "normal",
                "설명": f"위반 {int(summary['safety_violation_count'])}건",
            }
        ),
        _performance_status(summary),
        _operation_item(
            "RAG 품질",
            summary.get("rag_no_result_rate"),
            [(5, "warning")],
            suffix="% No Result",
        ),
    ]


def build_rag_quality(items, summary):
    daily = defaultdict(lambda: defaultdict(float))
    top_k_counts = defaultdict(float)
    duration_sum = 0.0
    duration_count = 0.0
    for item in items:
        metric = item.get("metric")
        day = item.get("date")
        value_sum = float(item.get("sum_value") or 0)
        sample_count = float(item.get("sample_count") or 0)
        if metric in {"rag.searches", "rag.no_result"}:
            daily[day][metric] += value_sum
        elif metric == "rag.top_k_hit":
            top_k_counts["hits"] += value_sum
            top_k_counts["evaluated"] += sample_count or 1
            daily[day]["rag.top_k_hit"] += value_sum
            daily[day]["rag.top_k_evaluated"] += sample_count or 1
        elif metric == "rag.duration_ms":
            if sample_count:
                duration_sum += value_sum
                duration_count += sample_count
                daily[day]["rag.duration_sum"] += value_sum
                daily[day]["rag.duration_count"] += sample_count
            elif item.get("average_value") is not None:
                duration_sum += float(item["average_value"])
                duration_count += 1
                daily[day]["rag.duration_sum"] += float(item["average_value"])
                daily[day]["rag.duration_count"] += 1

    searches = sum(values.get("rag.searches", 0) for values in daily.values())
    no_results = sum(values.get("rag.no_result", 0) for values in daily.values())
    no_result_rate = summary.get("rag_no_result_rate")
    if no_result_rate is None and searches:
        no_result_rate = no_results / searches * 100
    success_rate = None if no_result_rate is None else max(0.0, 100 - float(no_result_rate))
    top_k_rate = (
        top_k_counts["hits"] / top_k_counts["evaluated"] * 100
        if top_k_counts["evaluated"]
        else None
    )
    average_duration = duration_sum / duration_count if duration_count else None

    trend_rows = []
    for day, values in sorted(daily.items()):
        day_searches = values.get("rag.searches", 0)
        day_no_result_rate = (
            values.get("rag.no_result", 0) / day_searches * 100 if day_searches else None
        )
        day_top_k_rate = (
            values.get("rag.top_k_hit", 0) / values.get("rag.top_k_evaluated", 0) * 100
            if values.get("rag.top_k_evaluated", 0)
            else None
        )
        day_duration = (
            values.get("rag.duration_sum", 0) / values.get("rag.duration_count", 0)
            if values.get("rag.duration_count", 0)
            else None
        )
        trend_rows.append(
            {
                "날짜": day,
                "검색 성공률": None if day_no_result_rate is None else 100 - day_no_result_rate,
                "Top-K 적중률": day_top_k_rate,
                "No Result 비율": day_no_result_rate,
                "평균 검색시간(ms)": day_duration,
            }
        )
    return {
        "search_success_rate": success_rate,
        "top_k_hit_rate": top_k_rate,
        "top_k_evaluated_count": int(top_k_counts["evaluated"]),
        "no_result_rate": no_result_rate,
        "average_duration_ms": average_duration,
        "trend": pd.DataFrame(trend_rows),
    }


def build_issue_table(records):
    rows = []
    for record in records:
        event = record.get("event", {})
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        context = event.get("context", {})
        issue = _issue_from_event(event_type, payload)
        if issue:
            rows.append(
                {
                    "발생 시각(UTC)": event.get("occurred_at"),
                    "Case ID": context.get("case_id") or "-",
                    **issue,
                }
            )
    return pd.DataFrame(rows)


def build_alerts(summary):
    alerts = []
    checks = [
        (summary.get("safety_violation_count"), lambda value: value >= 1, "danger", "안전성 위반이 감지되었습니다."),
        (summary.get("api_error_rate"), lambda value: value > 2, "danger", "API 오류율이 2%를 초과했습니다."),
        (summary.get("api_p95_duration_ms"), lambda value: value > 5000, "warning", "p95 응답시간이 5초를 초과했습니다."),
        (summary.get("test_pass_rate"), lambda value: value < 95, "warning", "테스트 통과율이 95% 미만입니다."),
        (summary.get("rag_no_result_rate"), lambda value: value > 5, "warning", "RAG No Result 비율이 5%를 초과했습니다."),
        (summary.get("budget_usage_rate"), lambda value: value >= 100, "danger", "일 API 비용 예산을 초과했습니다."),
        (summary.get("open_defect_count"), lambda value: value > 0, "warning", "조치가 필요한 열린 결함이 있습니다."),
    ]
    for value, check, level, message in checks:
        if value is not None and check(value):
            alerts.append({"level": level, "message": message})
    return alerts or [{"level": "normal", "message": "현재 활성 경고가 없습니다."}]


def build_event_table(records):
    rows = []
    for record in records:
        event = record.get("event", {})
        context = event.get("context", {})
        payload = event.get("payload", {})
        rows.append(
            {
                "발생 시각(UTC)": event.get("occurred_at"),
                "이벤트": event.get("event_type"),
                "서비스": context.get("service"),
                "Run ID": context.get("run_id"),
                "Case ID": context.get("case_id"),
                "상태": _event_status(event.get("event_type"), payload),
            }
        )
    return pd.DataFrame(rows)


def recommend_actions(summary):
    actions = []
    if summary.get("safety_violation_count") or 0:
        actions.append("안전성 위반 케이스를 우선 재현하고 정책 프롬프트를 검토합니다.")
    if summary.get("api_error_rate") is not None and summary["api_error_rate"] > 1:
        actions.append("최근 API 5xx·timeout 이벤트와 서비스 로그를 확인합니다.")
    if summary.get("api_p95_duration_ms") is not None and summary["api_p95_duration_ms"] > 5000:
        actions.append("RAG·LLM 단계별 지연을 비교하고 느린 구간을 재현합니다.")
    if summary.get("test_pass_rate") is not None and summary["test_pass_rate"] < 95:
        actions.append("실패 테스트를 우선 재실행하고 최근 회귀 여부를 확인합니다.")
    if summary.get("rag_no_result_rate") is not None and summary["rag_no_result_rate"] > 5:
        actions.append("No-result 질문의 검색어와 지식 인덱스 최신성을 점검합니다.")
    if summary.get("budget_usage_rate") is not None and summary["budget_usage_rate"] >= 80:
        actions.append("모델별 토큰 사용량과 캐시 적용률을 확인합니다.")
    if summary.get("llm_price_coverage") == 0 and summary.get("llm_total_tokens", 0):
        actions.append("정확한 KRW 비용 집계를 위해 QA_OBSERVER_USD_KRW를 설정합니다.")
    if summary.get("open_defect_count", 0):
        actions.append("Grafana에서 발생한 열린 결함의 runbook을 확인하고 조치 상태를 갱신합니다.")
    return actions or ["현재 즉시 필요한 조치가 없습니다. 수집 신선도를 지속 확인합니다."]


def _operation_item(label, value, thresholds, higher_is_better=False, suffix=""):
    if value is None:
        return {"영역": label, "상태": "no_data", "설명": "데이터 없음"}

    numeric_value = float(value)
    level = "normal"
    if higher_is_better:
        for boundary, candidate in thresholds:
            if numeric_value < boundary:
                level = candidate
                break
    else:
        for boundary, candidate in thresholds:
            if numeric_value > boundary:
                level = candidate

    description = f"{numeric_value:,.1f}{suffix}" if suffix else f"{numeric_value:,.1f}점"
    return {"영역": label, "상태": level, "설명": description}


def _performance_status(summary):
    error_rate = summary.get("api_error_rate")
    p95_ms = summary.get("api_p95_duration_ms")
    if error_rate is None and p95_ms is None:
        return {"영역": "성능", "상태": "no_data", "설명": "데이터 없음"}

    error_rate = float(error_rate or 0)
    p95_ms = float(p95_ms or 0)
    if error_rate > 2 or p95_ms > 8000:
        level = "danger"
    elif error_rate > 1 or p95_ms > 5000:
        level = "warning"
    else:
        level = "normal"
    return {
        "영역": "성능",
        "상태": level,
        "설명": f"오류 {error_rate:,.1f}% · p95 {p95_ms / 1000:,.2f}초",
    }


def _issue_from_event(event_type, payload):
    if event_type == "api.request.completed":
        status_code = int(payload.get("status_code") or 0)
        timed_out = bool(payload.get("timeout"))
        if status_code >= 500 or timed_out:
            return {
                "요약": "API timeout" if timed_out else f"API {status_code} 오류",
                "유형": "API 결함",
                "심각도": "높음",
                "상태": "발생",
            }
    elif event_type == "llm.call.completed" and str(payload.get("status", "")).lower() != "success":
        return {"요약": "LLM 호출 실패", "유형": "LLM 결함", "심각도": "높음", "상태": "발생"}
    elif event_type == "rag.search.completed" and payload.get("no_result"):
        return {"요약": "검색 결과 없음", "유형": "RAG 결함", "심각도": "중간", "상태": "분석중"}
    elif event_type == "quality.evaluation.completed":
        decision = str(payload.get("overall_decision", "")).upper()
        if decision and decision != "PASS":
            return {
                "요약": f"품질 판정 {decision}",
                "유형": "품질 결함",
                "심각도": "높음" if decision == "FAIL" else "중간",
                "상태": "분석중",
            }
    elif event_type == "test.run.completed":
        failed = int(payload.get("fail_count") or 0)
        errors = int(payload.get("error_count") or 0)
        if failed or errors:
            return {
                "요약": f"테스트 실패 {failed}건 · 오류 {errors}건",
                "유형": "테스트 결함",
                "심각도": "높음" if errors else "중간",
                "상태": "재현 필요",
            }
    elif event_type == "safety.violation.detected":
        severity = str(payload.get("severity") or "high").lower()
        return {
            "요약": "안전성 위반 감지",
            "유형": "안전성 결함",
            "심각도": "치명" if severity == "critical" else "높음",
            "상태": "긴급",
        }
    elif event_type == "defect.changed":
        return {
            "요약": str(payload.get("title") or payload.get("defect_type") or "결함 상태 변경"),
            "유형": str(payload.get("defect_type") or "결함"),
            "심각도": str(payload.get("severity") or "중간"),
            "상태": str(payload.get("status") or payload.get("action") or "확인중"),
        }
    return None


def _event_status(event_type, payload):
    if event_type == "api.request.completed":
        return str(payload.get("status_code", ""))
    if event_type == "llm.call.completed":
        return payload.get("status", "")
    if event_type == "quality.evaluation.completed":
        return payload.get("overall_decision", "")
    if event_type == "safety.violation.detected":
        return payload.get("severity", "")
    if event_type == "test.run.completed":
        return f"PASS {payload.get('pass_count', 0)} / TOTAL {payload.get('total_count', 0)}"
    return payload.get("status", payload.get("action", ""))
