import httpx

from dashboard.services import qa_observer_client


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_get_json_uses_startup_safe_default_timeout(monkeypatch):
    observed = {}

    def fake_get(url, params, timeout):
        observed.update(url=url, params=params, timeout=timeout)
        return _Response({"status": "healthy"})

    monkeypatch.delenv("QA_OBSERVER_REQUEST_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr(qa_observer_client.httpx, "get", fake_get)

    result = qa_observer_client._get_json("http://127.0.0.1:8010", "/health")

    assert result == {"status": "healthy"}
    assert observed["timeout"] == 5.0


def test_get_json_retries_transient_startup_timeout(monkeypatch):
    attempts = []

    def fake_get(url, params, timeout):
        attempts.append(timeout)
        if len(attempts) == 1:
            request = httpx.Request("GET", url)
            raise httpx.ReadTimeout("observer is warming up", request=request)
        return _Response({"items": []})

    monkeypatch.setattr(qa_observer_client.httpx, "get", fake_get)
    monkeypatch.setattr(qa_observer_client.time, "sleep", lambda _delay: None)

    result = qa_observer_client._get_json("http://127.0.0.1:8010", "/v1/aggregates")

    assert result == {"items": []}
    assert len(attempts) == 2


def test_request_timeout_can_be_overridden(monkeypatch):
    monkeypatch.setenv("QA_OBSERVER_REQUEST_TIMEOUT_SECONDS", "8.5")

    assert qa_observer_client._request_timeout_seconds() == 8.5


def test_dashboard_bundle_fetches_safety_events_with_a_dedicated_filter(monkeypatch):
    observed = []

    def fake_get_json(_base_url, path, params=None):
        observed.append((path, params or {}))
        return {"items": []}

    monkeypatch.setattr(qa_observer_client, "_get_json", fake_get_json)

    bundle = qa_observer_client.fetch_dashboard_bundle("2026-07-01", "2026-07-16")

    assert "safety_events" in bundle
    assert (
        "/v1/events",
        {
            "date_from": "2026-07-01",
            "date_to": "2026-07-16",
            "event_type": "safety.violation.detected",
            "limit": 500,
        },
    ) in observed
