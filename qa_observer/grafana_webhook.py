import hashlib
import re
import uuid
from datetime import datetime, timezone

from qa_observer.telemetry import make_event


def events_from_grafana_webhook(payload, settings):
    alerts = payload.get("alerts", []) if isinstance(payload, dict) else []
    events = []
    for alert in alerts[:50]:
        if not isinstance(alert, dict):
            continue
        labels = alert.get("labels") if isinstance(alert.get("labels"), dict) else {}
        status = str(alert.get("status") or payload.get("status") or "").lower()
        if status not in {"firing", "resolved"}:
            continue
        alert_name = _safe_code(labels.get("alertname") or labels.get("grafana_folder") or "grafana-alert")
        rule_identity = str(
            alert.get("fingerprint")
            or labels.get("rule_uid")
            or payload.get("groupKey")
            or alert_name
        )
        transition_at = _safe_time(alert.get("endsAt") if status == "resolved" else alert.get("startsAt"))
        stable_key = ":".join(
            ["grafana", rule_identity, status, str(alert.get("startsAt") or ""), str(alert.get("endsAt") or "")]
        )
        event = make_event(
            "defect.changed",
            {
                "defect_id": f"grafana-{_safe_code(rule_identity, 112)}",
                "action": "resolved" if status == "resolved" else "opened",
                "defect_type": alert_name,
                "severity": _severity(labels.get("severity")),
                "status": "resolved" if status == "resolved" else "open",
                "summary_code": alert_name,
                "external_system": "grafana",
                "external_issue_key": None,
            },
            "grafana-alerting",
            occurred_at=transition_at,
            environment=labels.get("environment") or settings.environment,
            service=labels.get("service") or settings.target_service,
        )
        event["event_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
        event["dedup_key"] = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
        event["context"]["trace_id"] = hashlib.sha256(rule_identity.encode("utf-8")).hexdigest()[:32]
        events.append(event)
    return events


def _severity(value):
    return {
        "critical": "critical",
        "high": "high",
        "warning": "medium",
        "medium": "medium",
        "info": "low",
        "low": "low",
    }.get(str(value or "").lower(), "medium")


def _safe_code(value, maximum=128):
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip("-._").lower()
    return (text or "unknown")[:maximum]


def _safe_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.year >= 2000:
            return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    except (TypeError, ValueError):
        pass
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
