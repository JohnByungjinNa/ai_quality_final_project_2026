import sys

import httpx

from core.paths import PROJECT_DIR


if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import JIRA_API_TOKEN, JIRA_BASE_URL, JIRA_EMAIL, JIRA_PROJECT_KEY  # noqa: E402


class JiraConfigurationError(RuntimeError):
    pass


class JiraIssueCreateError(RuntimeError):
    pass


def missing_jira_settings():
    required_settings = {
        "JIRA_BASE_URL": JIRA_BASE_URL,
        "JIRA_EMAIL": JIRA_EMAIL,
        "JIRA_API_TOKEN": JIRA_API_TOKEN,
        "JIRA_PROJECT_KEY": JIRA_PROJECT_KEY,
    }
    return [key for key, value in required_settings.items() if not value]


def ensure_jira_configured():
    missing = missing_jira_settings()
    if missing:
        raise JiraConfigurationError(f"Jira 설정이 누락되었습니다: {', '.join(missing)}")


def create_issue_for_fail_case(fail_case):
    ensure_jira_configured()
    payload = build_issue_payload(fail_case)
    url = f"{JIRA_BASE_URL}/rest/api/3/issue"

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(
                url,
                json=payload,
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message = _extract_jira_error_message(exc.response)
        raise JiraIssueCreateError(f"Jira 이슈 생성 실패: {message}") from exc
    except httpx.HTTPError as exc:
        raise JiraIssueCreateError(f"Jira 연결 실패: {exc}") from exc

    return response.json()


def build_issue_payload(fail_case):
    case_id = str(fail_case.get("case_id", "")).strip() or "UNKNOWN"
    summary = str(fail_case.get("summary", "")).strip() or "FAIL 사례"
    severity = str(fail_case.get("severity", "Medium")).strip() or "Medium"

    return {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": f"[QA FAIL] {case_id} - {summary}",
            "issuetype": {"name": "작업"},
            "priority": {"name": map_severity_to_priority(severity)},
            "labels": ["qa-fail", "chatbot", "regression"],
            "description": build_adf_description(fail_case),
        }
    }


def build_adf_description(fail_case):
    lines = [
        ("Case ID", fail_case.get("case_id", "-")),
        ("심각도", fail_case.get("severity", "-")),
        ("담당", fail_case.get("owner", "-")),
        ("요약", fail_case.get("summary", "-")),
        ("상태", fail_case.get("status", "-")),
    ]
    content = []
    for label, value in lines:
        content.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"{label}: {value}",
                    }
                ],
            }
        )

    content.append(
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "재현 절차: 실패한 테스트 케이스를 재실행하고 기대 정책과 실제 응답을 비교합니다.",
                }
            ],
        }
    )
    return {"type": "doc", "version": 1, "content": content}


def map_severity_to_priority(severity):
    priority_by_severity = {
        "Critical": "Highest",
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
    }
    return priority_by_severity.get(severity, "Medium")


def _extract_jira_error_message(response):
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"

    messages = []
    if body.get("errorMessages"):
        messages.extend(body["errorMessages"])
    if body.get("errors"):
        messages.extend(f"{key}: {value}" for key, value in body["errors"].items())
    return "; ".join(messages) or f"HTTP {response.status_code}"
