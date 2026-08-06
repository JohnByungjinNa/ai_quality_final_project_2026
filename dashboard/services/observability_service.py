from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


DEFAULT_PROMETHEUS_URL = "http://127.0.0.1:9090"
DEFAULT_GRAFANA_URL = "http://localhost:3000"
DEFAULT_TEMPO_URL = "http://localhost:3200"


class ObservabilityError(RuntimeError):
    pass


def prometheus_url():
    return os.getenv("PROMETHEUS_URL", DEFAULT_PROMETHEUS_URL).strip().rstrip("/")


def grafana_url():
    return os.getenv("GRAFANA_DASHBOARD_URL", DEFAULT_GRAFANA_URL).strip().rstrip("/")


def tempo_url():
    return os.getenv("TEMPO_URL", DEFAULT_TEMPO_URL).strip().rstrip("/")


def instant_query(expression, base_url=None):
    payload = _get_json(base_url or prometheus_url(), "/api/v1/query", {"query": expression})
    return _result(payload)


def range_query(expression, *, hours=6, step=60, base_url=None):
    end = time.time()
    payload = _get_json(
        base_url or prometheus_url(),
        "/api/v1/query_range",
        {"query": expression, "start": end - hours * 3600, "end": end, "step": step},
    )
    return _result(payload)


def readiness_snapshot(base_url=None):
    queries = {
        "api_availability": "qa:sli_api_availability:ratio_5m",
        "api_latency": "qa:sli_api_latency_le_5s:ratio_5m",
        "test_pass": "qa:sli_test_pass:ratio_today",
        "quality_pass": "qa:sli_quality_pass:ratio_today",
        "budget_api": "qa:error_budget_api:remaining_ratio",
        "budget_test": "qa:error_budget_test:remaining_ratio",
        "budget_quality": "qa:error_budget_quality:remaining_ratio",
        "agent_failure": "qa:agent_rpc_failure:ratio_5m",
        "quality_score": "qa:quality_score:today",
        "llm_cost": "qa:llm_cost_krw:today",
        "cost_per_pass": "qa:llm_cost_per_quality_pass_krw:today",
        "demo_ready": "min(probe_success{job=\"blackbox-http\"})",
    }
    url = base_url or prometheus_url()
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {name: executor.submit(instant_query, query, url) for name, query in queries.items()}
        values = {}
        for name, future in futures.items():
            try:
                values[name] = _single_value(future.result())
            except ObservabilityError:
                values[name] = None
    return values


def _single_value(rows):
    if not rows:
        return None
    value = rows[0].get("value")
    try:
        return float(value[1])
    except (IndexError, TypeError, ValueError):
        return None


def _get_json(base_url, path, params=None):
    try:
        response = httpx.get(base_url + path, params=params, timeout=4.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ObservabilityError(f"observability request failed: {type(exc).__name__}") from exc
    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise ObservabilityError("Prometheus returned an invalid response")
    return payload


def _result(payload):
    result = (payload.get("data") or {}).get("result")
    if not isinstance(result, list):
        raise ObservabilityError("Prometheus result is not a list")
    return result
