from dashboard.components.test_execution_dialog import (
    build_event_log_html,
    build_progress_html,
    build_result_summary_html,
    calculate_execution_progress,
)


def test_execution_progress_advances_by_stage_and_case():
    answer = calculate_execution_progress(1, 2, "챗봇 답변 생성")
    rule = calculate_execution_progress(1, 2, "규칙 검증")
    ai = calculate_execution_progress(1, 2, "AI 평가")
    next_case = calculate_execution_progress(2, 2, "챗봇 답변 생성")

    assert 0 < answer < rule < ai < next_case < 1


def test_progress_html_contains_current_execution_information():
    html = build_progress_html(0.48, "TC-002", 2, 5, "규칙 검증")

    assert "48%" in html
    assert "TC-002" in html
    assert "규칙 검증" in html
    assert "2 / 5 케이스" in html


def test_event_log_escapes_values_and_shows_states():
    html = build_event_log_html(
        [
            {
                "time": "12:34:56",
                "case_id": "<TC-1>",
                "step": "규칙 & 검증",
                "state": "완료",
            }
        ]
    )

    assert "&lt;TC-1&gt;" in html
    assert "규칙 &amp; 검증" in html
    assert "완료" in html
    assert "class='done'" in html


def test_result_summary_contains_all_key_counts():
    html = build_result_summary_html(
        {
            "execution_id": "RUN-1",
            "total_count": 10,
            "passed_count": 7,
            "failed_count": 3,
            "rule_passed_count": 8,
            "api_passed_count": 7,
            "duration_seconds": 1.25,
        }
    )

    assert "RUN-1" in html
    assert "최종 PASS" in html
    assert "미통과" in html
    assert "1.25초" in html
