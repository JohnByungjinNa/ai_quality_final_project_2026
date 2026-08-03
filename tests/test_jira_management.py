import pandas as pd
from streamlit.testing.v1 import AppTest

from dashboard.pages_top import jira_view
from dashboard.services import jira_client


def test_jira_issue_payload_uses_adf_description_and_priority():
    payload = jira_client.build_issue_payload(
        {
            "case_id": "TC-16",
            "summary": "관련 VOC 근거 부족",
            "severity": "High",
            "owner": "QA",
            "status": "검토 필요",
        }
    )

    fields = payload["fields"]
    assert fields["summary"] == "[QA FAIL] TC-16 - 관련 VOC 근거 부족"
    assert fields["priority"]["name"] == "High"
    assert fields["description"]["type"] == "doc"
    assert fields["description"]["content"][0]["content"][0]["text"] == "Case ID: TC-16"


def test_jira_issue_normalization_keeps_user_friendly_fields(monkeypatch):
    monkeypatch.setattr(jira_client, "JIRA_BASE_URL", "https://example.atlassian.net")

    row = jira_client.normalize_issue(
        {
            "key": "KAN-7",
            "fields": {
                "summary": "시연 화면 정리",
                "status": {
                    "name": "In Progress",
                    "statusCategory": {"key": "indeterminate"},
                },
                "issuetype": {"name": "작업"},
                "priority": {"name": "Medium"},
                "assignee": {"displayName": "홍길동"},
                "reporter": {"displayName": "QA"},
                "created": "2026-08-02T10:11:12.000+0900",
                "updated": "2026-08-02T13:14:15.000+0900",
                "labels": ["voc-quality"],
            },
        }
    )

    assert row["키"] == "KAN-7"
    assert row["상태 분류"] == "진행 중"
    assert row["담당자"] == "홍길동"
    assert row["URL"] == "https://example.atlassian.net/browse/KAN-7"


def test_jira_search_uses_project_jql_and_normalizes_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(jira_client, "JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setattr(jira_client, "JIRA_EMAIL", "tester@example.com")
    monkeypatch.setattr(jira_client, "JIRA_API_TOKEN", "token")
    monkeypatch.setattr(jira_client, "JIRA_PROJECT_KEY", "KAN")

    def fake_request(method, path, *, params=None, json_body=None):
        calls.append((method, path, params, json_body))
        return {
            "total": 1,
            "issues": [
                {
                    "key": "KAN-1",
                    "fields": {
                        "summary": "등록 테스트",
                        "status": {"name": "Done", "statusCategory": {"key": "done"}},
                        "issuetype": {"name": "작업"},
                    },
                }
            ],
        }

    monkeypatch.setattr(jira_client, "_request", fake_request)
    result = jira_client.search_jira_issues("project = KAN", max_results=10)

    assert calls[0][0:2] == ("GET", "/rest/api/3/search/jql")
    assert calls[0][2]["jql"] == "project = KAN"
    assert result["total"] == 1
    assert result["issues"][0]["상태 분류"] == "완료"


def test_jira_status_count_helper():
    counts = jira_view._issue_count_by(
        [{"상태 분류": "할 일"}, {"상태 분류": "할 일"}, {"상태 분류": "완료"}],
        "상태 분류",
    )

    assert counts == {"할 일": 2, "완료": 1}


def test_jira_visual_class_helpers_match_jira_like_badges():
    assert jira_view._jira_status_class("완료") == "done"
    assert jira_view._jira_status_class("진행 중") == "progress"
    assert jira_view._jira_status_class("할 일") == "todo"
    assert jira_view._jira_priority_class("High") == "high"
    assert jira_view._jira_priority_class("Low") == "low"
    assert jira_view._jira_issue_type_icon("버그") == "●"


def test_jira_create_form_opens_in_dialog_from_compact_action():
    app = AppTest.from_file("tests/fixtures/jira_create_dialog_app.py", default_timeout=15)

    app.run()

    assert not app.exception
    assert not app.text_input
    open_button = next(button for button in app.button if button.label == "Jira 이슈 등록")

    open_button.click().run()

    assert not app.exception
    assert {widget.label for widget in app.text_input} == {"요약", "Case ID", "Run ID", "라벨"}
    assert any(widget.label == "설명" for widget in app.text_area)
    create_buttons = [button for button in app.button if button.label == "Jira 이슈 등록"]
    assert any(button.disabled for button in create_buttons)
