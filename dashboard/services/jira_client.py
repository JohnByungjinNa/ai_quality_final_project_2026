from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx


PROJECT_DIR = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = PROJECT_DIR / "dashboard"

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from config import (  # noqa: E402
    JIRA_API_KEY,
    JIRA_API_TOKEN,
    JIRA_API_TOKEN_SOURCE,
    JIRA_BASE_URL,
    JIRA_DEFAULT_JQL,
    JIRA_EMAIL,
    JIRA_PROJECT_KEY,
)


class JiraConfigurationError(RuntimeError):
    pass


class JiraIssueCreateError(RuntimeError):
    pass


class JiraApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


DEFAULT_FIELDS = [
    "summary",
    "status",
    "issuetype",
    "priority",
    "assignee",
    "reporter",
    "created",
    "updated",
    "labels",
]


def missing_jira_settings() -> list[str]:
    required_settings = {
        "JIRA_BASE_URL": JIRA_BASE_URL,
        "JIRA_EMAIL": JIRA_EMAIL,
        "JIRA_API_TOKEN 또는 JIRA_API_KEY": JIRA_API_TOKEN or JIRA_API_KEY,
        "JIRA_PROJECT_KEY": JIRA_PROJECT_KEY,
    }
    return [key for key, value in required_settings.items() if not value]


def ensure_jira_configured() -> None:
    missing = missing_jira_settings()
    if missing:
        raise JiraConfigurationError(f"Jira 설정이 누락되었습니다: {', '.join(missing)}")


def jira_environment_snapshot() -> dict[str, Any]:
    return {
        "base_url": JIRA_BASE_URL,
        "email_configured": bool(JIRA_EMAIL),
        "api_token_configured": bool(JIRA_API_TOKEN or JIRA_API_KEY),
        "credential_source": JIRA_API_TOKEN_SOURCE,
        "project_key": JIRA_PROJECT_KEY,
        "default_jql": JIRA_DEFAULT_JQL,
        "missing": missing_jira_settings(),
        "ready": not missing_jira_settings(),
    }


def test_jira_connection() -> dict[str, Any]:
    myself = _request("GET", "/rest/api/3/myself")
    project = _request("GET", f"/rest/api/3/project/{JIRA_PROJECT_KEY}")
    return {
        "ok": True,
        "account_display_name": myself.get("displayName", "-"),
        "account_email": myself.get("emailAddress", ""),
        "project_key": project.get("key", JIRA_PROJECT_KEY),
        "project_name": project.get("name", "-"),
        "project_type": project.get("projectTypeKey", "-"),
    }


def list_project_issue_types() -> list[dict[str, str]]:
    project = _request("GET", f"/rest/api/3/project/{JIRA_PROJECT_KEY}")
    issue_types = project.get("issueTypes") or []
    normalized = []
    for item in issue_types:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or ""),
                "name": name,
                "description": str(item.get("description") or ""),
                "subtask": "하위 작업" if item.get("subtask") else "일반",
            }
        )
    return normalized


def search_jira_issues(
    jql: str | None = None,
    *,
    max_results: int = 50,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    ensure_jira_configured()
    query = (jql or JIRA_DEFAULT_JQL or f"project = {JIRA_PROJECT_KEY} ORDER BY updated DESC").strip()
    field_names = fields or DEFAULT_FIELDS
    max_results = max(1, min(int(max_results or 50), 100))

    try:
        payload = _request(
            "GET",
            "/rest/api/3/search/jql",
            params={
                "jql": query,
                "maxResults": max_results,
                "fields": ",".join(field_names),
            },
        )
    except JiraApiError as exc:
        if exc.status_code not in {404, 405, 410}:
            raise
        payload = _request(
            "POST",
            "/rest/api/3/search",
            json_body={
                "jql": query,
                "maxResults": max_results,
                "fields": field_names,
            },
        )

    issues = payload.get("issues") or []
    rows = [normalize_issue(issue) for issue in issues if isinstance(issue, dict)]
    return {
        "jql": query,
        "total": int(payload.get("total") or len(rows)),
        "max_results": max_results,
        "issues": rows,
        "raw_count": len(issues),
    }


def create_jira_issue(
    *,
    summary: str,
    description: str = "",
    issue_type: str = "작업",
    priority: str = "",
    labels: list[str] | None = None,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_jira_configured()
    summary = str(summary or "").strip()
    if not summary:
        raise JiraIssueCreateError("요약은 필수 입력값입니다.")

    fields: dict[str, Any] = {
        "project": {"key": JIRA_PROJECT_KEY},
        "summary": summary[:255],
        "issuetype": {"name": str(issue_type or "작업").strip() or "작업"},
        "description": build_adf_description_from_text(description or "-"),
    }
    if priority:
        fields["priority"] = {"name": str(priority).strip()}
    clean_labels = [
        label.strip().replace(" ", "-")
        for label in (labels or [])
        if str(label or "").strip()
    ]
    if clean_labels:
        fields["labels"] = clean_labels
    if extra_fields:
        fields.update(extra_fields)

    try:
        created = _request("POST", "/rest/api/3/issue", json_body={"fields": fields})
    except JiraApiError as exc:
        raise JiraIssueCreateError(f"Jira 이슈 생성 실패: {exc}") from exc

    return {
        "key": created.get("key", ""),
        "id": created.get("id", ""),
        "self": created.get("self", ""),
        "url": build_issue_url(created.get("key", "")),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def create_issue_for_fail_case(fail_case: dict[str, Any]) -> dict[str, Any]:
    payload = build_issue_payload(fail_case)
    try:
        created = _request("POST", "/rest/api/3/issue", json_body=payload)
    except JiraApiError as exc:
        raise JiraIssueCreateError(f"Jira 이슈 생성 실패: {exc}") from exc
    return created


def build_issue_payload(fail_case: dict[str, Any]) -> dict[str, Any]:
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


def build_adf_description(fail_case: dict[str, Any]) -> dict[str, Any]:
    lines = [
        ("Case ID", fail_case.get("case_id", "-")),
        ("심각도", fail_case.get("severity", "-")),
        ("담당", fail_case.get("owner", "-")),
        ("요약", fail_case.get("summary", "-")),
        ("상태", fail_case.get("status", "-")),
        ("재현 절차", "실패한 테스트 케이스를 재실행하고 기대 정책과 실제 응답을 비교합니다."),
    ]
    return build_adf_description_from_pairs(lines)


def build_adf_description_from_text(description: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(description or "").splitlines()]
    content = []
    for line in lines:
        if not line:
            content.append({"type": "paragraph"})
            continue
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line[:3000]}],
            }
        )
    if not content:
        content.append({"type": "paragraph", "content": [{"type": "text", "text": "-"}]})
    return {"type": "doc", "version": 1, "content": content}


def build_adf_description_from_pairs(lines: list[tuple[str, Any]]) -> dict[str, Any]:
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
    return {"type": "doc", "version": 1, "content": content}


def map_severity_to_priority(severity: str) -> str:
    priority_by_severity = {
        "Critical": "Highest",
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
    }
    return priority_by_severity.get(str(severity or "").strip(), "Medium")


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    status = fields.get("status") if isinstance(fields.get("status"), dict) else {}
    status_category = (
        status.get("statusCategory")
        if isinstance(status.get("statusCategory"), dict)
        else {}
    )
    issue_type = fields.get("issuetype") if isinstance(fields.get("issuetype"), dict) else {}
    priority = fields.get("priority") if isinstance(fields.get("priority"), dict) else {}
    assignee = fields.get("assignee") if isinstance(fields.get("assignee"), dict) else {}
    reporter = fields.get("reporter") if isinstance(fields.get("reporter"), dict) else {}
    key = str(issue.get("key") or "")
    return {
        "키": key,
        "요약": fields.get("summary", "-"),
        "상태": status.get("name", "-"),
        "상태 분류": _status_category_label(status_category.get("key") or status_category.get("name")),
        "유형": issue_type.get("name", "-"),
        "우선순위": priority.get("name", "-") if priority else "-",
        "담당자": assignee.get("displayName", "미지정") if assignee else "미지정",
        "보고자": reporter.get("displayName", "-") if reporter else "-",
        "생성일": _compact_datetime(fields.get("created", "")),
        "수정일": _compact_datetime(fields.get("updated", "")),
        "라벨": ", ".join(fields.get("labels") or []),
        "URL": build_issue_url(key),
    }


def build_issue_url(issue_key: str) -> str:
    key = str(issue_key or "").strip()
    if not JIRA_BASE_URL or not key:
        return ""
    return f"{JIRA_BASE_URL}/browse/{key}"


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_jira_configured()
    url = f"{JIRA_BASE_URL}{path}"
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(
                method,
                url,
                params=params,
                json=json_body,
                auth=(JIRA_EMAIL, JIRA_API_TOKEN),
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()
    except httpx.HTTPStatusError as exc:
        message = _extract_jira_error_message(exc.response)
        raise JiraApiError(message, status_code=exc.response.status_code) from exc
    except httpx.HTTPError as exc:
        raise JiraApiError(f"Jira 연결 실패: {exc}") from exc
    except ValueError as exc:
        raise JiraApiError("Jira 응답을 JSON으로 해석할 수 없습니다.") from exc


def _extract_jira_error_message(response: httpx.Response) -> str:
    if response.status_code == 401:
        return (
            "Jira 인증 실패: JIRA_EMAIL과 JIRA_API_KEY 또는 JIRA_API_TOKEN 조합을 확인하세요. "
            "Atlassian Cloud는 id.atlassian.com에서 생성한 API 토큰을 이메일과 함께 사용합니다."
        )
    if response.status_code == 403:
        return "Jira 권한 부족: 계정이 해당 사이트 또는 프로젝트에 접근할 수 있는지 확인하세요."
    try:
        body = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"

    messages = []
    if isinstance(body, dict):
        if body.get("errorMessages"):
            messages.extend(str(item) for item in body["errorMessages"])
        if body.get("errors"):
            messages.extend(f"{key}: {value}" for key, value in body["errors"].items())
    return "; ".join(messages) or f"HTTP {response.status_code}"


def _compact_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return text.replace("T", " ")[:19]


def _status_category_label(value: Any) -> str:
    key = str(value or "").strip().lower()
    return {
        "new": "할 일",
        "indeterminate": "진행 중",
        "done": "완료",
    }.get(key, str(value or "-"))
