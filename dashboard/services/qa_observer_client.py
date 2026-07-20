import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx


DEFAULT_OBSERVER_URL = "http://127.0.0.1:8010"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 5.0
TRANSIENT_RETRY_DELAYS_SECONDS = (0.15, 0.35)


class QAObserverClientError(RuntimeError):
    pass


def observer_base_url():
    return os.getenv("QA_OBSERVER_URL", DEFAULT_OBSERVER_URL).strip().rstrip("/")


def fetch_filter_options(base_url=None):
    payload = _get_json(base_url or observer_base_url(), "/v1/aggregates")
    rows = payload.get("items", [])
    return {
        "environments": _unique(row.get("environment") for row in rows),
        "services": _unique(row.get("service") for row in rows),
        "providers": _unique(row.get("provider") for row in rows),
        "models": _unique(row.get("model") for row in rows),
    }


def fetch_dashboard_bundle(
    date_from,
    date_to,
    environment=None,
    service=None,
    provider=None,
    model=None,
    base_url=None,
):
    url = base_url or observer_base_url()
    params = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "environment": environment,
        "service": service,
        "provider": provider,
        "model": model,
    }
    params = {key: value for key, value in params.items() if value}
    requests = {
        "health": ("/health", {}),
        "summary": ("/v1/dashboard/summary", params),
        "timeseries": ("/v1/timeseries", params),
        "events": ("/v1/events", {**params, "limit": 100}),
        "quality_events": (
            "/v1/events",
            {**params, "event_type": "quality.evaluation.completed", "limit": 500},
        ),
        "safety_events": (
            "/v1/events",
            {**params, "event_type": "safety.violation.detected", "limit": 500},
        ),
    }
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {
            name: executor.submit(_get_json, url, path, query)
            for name, (path, query) in requests.items()
        }
        return {name: future.result() for name, future in futures.items()}


def _get_json(base_url, path, params=None):
    timeout = _request_timeout_seconds()
    for attempt in range(len(TRANSIENT_RETRY_DELAYS_SECONDS) + 1):
        try:
            response = httpx.get(base_url + path, params=params, timeout=timeout)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise QAObserverClientError("qa-observer returned a non-object response")
            return value
        except httpx.TransportError as exc:
            if attempt >= len(TRANSIENT_RETRY_DELAYS_SECONDS):
                raise QAObserverClientError(
                    f"qa-observer request failed: {type(exc).__name__}"
                ) from exc
            time.sleep(TRANSIENT_RETRY_DELAYS_SECONDS[attempt])
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise QAObserverClientError(
                f"qa-observer request failed: {type(exc).__name__}"
            ) from exc


def _request_timeout_seconds():
    raw_value = os.getenv("QA_OBSERVER_REQUEST_TIMEOUT_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        return max(float(raw_value), 0.1)
    except ValueError:
        return DEFAULT_REQUEST_TIMEOUT_SECONDS


def _unique(values):
    return sorted({str(value) for value in values if value not in (None, "")})
