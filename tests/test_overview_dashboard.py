from streamlit.testing.v1 import AppTest

from dashboard.navigation import MENU_OPTIONS, SIDEBAR_MENU_OPTIONS
from dashboard.services.overview_dashboard import (
    build_overview,
    build_quality_run_trend,
    evaluate_overall_status,
)
from dashboard.pages_top.overview_dashboard import (
    KPI_TOOLTIPS,
    PRIMARY_CHART_HEIGHT,
    PRIMARY_PANEL_COLUMNS,
    TEST_RESULT_COLORS,
    _build_quality_trend_chart,
    _open_test_history_from_dialog,
)


def test_new_overview_menu_is_separate_from_existing_performance_dashboard():
    assert MENU_OPTIONS[0] == "종합 현황"
    assert "성능관리" in MENU_OPTIONS
    assert SIDEBAR_MENU_OPTIONS["종합 현황"] == ["AI QA 종합 현황"]
    assert "운영 모니터링" in SIDEBAR_MENU_OPTIONS["성능관리"]


def test_primary_panels_use_equal_width_and_blue_test_palette():
    assert PRIMARY_PANEL_COLUMNS == (1, 1, 1)
    assert PRIMARY_CHART_HEIGHT == 220
    assert TEST_RESULT_COLORS == {
        "Pass": "#155A96",
        "Fail": "#5599D2",
        "Error": "#A9CAE7",
    }


def test_primary_kpis_explain_meaning_formula_thresholds_and_current_value():
    assert set(KPI_TOOLTIPS) == {
        "전체 품질점수",
        "테스트 통과율",
        "p95 응답시간",
        "오류율",
        "안전성 위반",
        "LLM 토큰 / API 비용",
    }
    assert all("의미:" in text and "산정:" in text and "기준:" in text for text in KPI_TOOLTIPS.values())


def test_safety_dialog_navigation_requests_full_app_rerun(monkeypatch):
    state = type("SessionState", (), {})()
    reruns = []
    monkeypatch.setattr("dashboard.pages_top.overview_dashboard.st.session_state", state)
    monkeypatch.setattr(
        "dashboard.pages_top.overview_dashboard.st.rerun",
        lambda *, scope: reruns.append(scope),
    )

    _open_test_history_from_dialog("RUN-20260714142734", "TC-017")

    assert state.qa_safety_focus_run_id == "RUN-20260714142734"
    assert state.qa_safety_focus_case_id == "TC-017"
    assert state.current_menu == "테스트 관리"
    assert state.current_sub_menu == "테스트 수행 이력"
    assert reruns == ["app"]


def test_quality_trend_uses_latest_seven_test_runs():
    records = []
    for index in range(1, 9):
        records.append(
            {
                "event": {
                    "occurred_at": f"2026-07-14T{index:02d}:00:00Z",
                    "event_type": "quality.evaluation.completed",
                    "context": {"run_id": f"RUN-20260714{index:02d}0000", "case_id": f"TC-{index:03d}"},
                    "payload": {"scores": {"accuracy": {"evaluated": True, "score": 4}}},
                }
            }
        )

    trend = build_quality_run_trend(records)

    assert len(trend) == 7
    assert trend.iloc[0]["Run ID"] == "RUN-20260714020000"
    assert trend.iloc[-1]["Run ID"] == "RUN-20260714080000"


def test_quality_score_trend_uses_a_smooth_project_tone_line():
    records = [
        {
            "event": {
                "occurred_at": f"2026-07-14T0{index}:00:00Z",
                "event_type": "quality.evaluation.completed",
                "context": {"run_id": f"RUN-{index}", "case_id": f"TC-{index:03d}"},
                "payload": {"scores": {"accuracy": {"evaluated": True, "score": score}}},
            }
        }
        for index, score in ((1, 4), (2, 5))
    ]

    spec = _build_quality_trend_chart(build_quality_run_trend(records)).to_dict()

    assert spec["mark"]["type"] == "line"
    assert spec["mark"]["interpolate"] == "monotone"
    assert spec["mark"]["color"] == "#2563EB"
    assert spec["mark"]["point"]["filled"] is True
    assert "params" not in spec


def test_status_priority_and_no_data_are_explicit():
    assert evaluate_overall_status({"data_status": "no_data"})["level"] == "no_data"
    status = evaluate_overall_status(
        {
            "data_status": "fresh",
            "safety_violation_count": 1,
            "quality_score": 100,
            "test_pass_rate": 100,
            "api_error_rate": 0,
            "api_p95_duration_ms": 1,
        }
    )
    assert status["level"] == "danger"
    assert "안전성" in status["reason"]
    rag_status = evaluate_overall_status(
        {"data_status": "fresh", "rag_no_result_rate": 6}
    )
    assert rag_status["level"] == "warning"
    assert "RAG" in rag_status["reason"]


def test_stale_business_events_do_not_mean_collector_failure():
    health = {
        "status": "healthy",
        "storage": {"writable": True},
        "scheduler": {"running": True, "last_error_type": None, "interval_seconds": 30},
    }
    summary = {
        "data_status": "stale",
        "quality_score": 100,
        "test_pass_rate": 100,
        "api_error_rate": 0,
        "api_p95_duration_ms": 10,
        "safety_violation_count": 0,
    }

    view = build_overview(summary, [], [], health)

    assert view["status"]["level"] == "normal"
    assert view["collection"]["healthy"] is True
    assert view["collection"]["event_data_status"] == "stale"


def test_safety_incident_contains_actionable_run_and_case_ids():
    records = [
        {
            "event": {
                "occurred_at": "2026-07-14T04:23:51Z",
                "event_type": "safety.violation.detected",
                "context": {"run_id": "RUN-1", "case_id": "TC-017"},
                "payload": {
                    "severity": "critical",
                    "category": "llm_judge_safety_score",
                    "action": "review_required",
                    "blocked": False,
                },
            }
        },
    ]

    view = build_overview({"data_status": "fresh", "safety_violation_count": 1}, [], records)

    assert view["safety_incidents"].iloc[0]["Run ID"] == "RUN-1"
    assert view["safety_incidents"].iloc[0]["Case ID"] == "TC-017"
    assert view["safety_incidents"].iloc[0]["심각도"] == "CRITICAL"


def test_dedicated_safety_events_are_not_lost_when_general_events_are_limited():
    safety_records = [
        {
            "event": {
                "occurred_at": "2026-07-14T04:23:51Z",
                "event_type": "safety.violation.detected",
                "context": {"run_id": "RUN-SAFETY", "case_id": "TC-SAFETY"},
                "payload": {"severity": "high", "category": "policy"},
            }
        }
    ]

    view = build_overview(
        {"data_status": "fresh", "safety_violation_count": 1},
        [],
        [],
        safety_event_records=safety_records,
    )

    assert view["safety_incidents"].iloc[0]["Run ID"] == "RUN-SAFETY"
    assert view["safety_incidents"].iloc[0]["Case ID"] == "TC-SAFETY"


def test_overview_builds_quality_traffic_events_and_actions():
    summary = {
        "data_status": "fresh",
        "safety_violation_count": 0,
        "quality_score": 85,
        "test_pass_rate": 90,
        "api_error_rate": 3,
        "api_p95_duration_ms": 6000,
        "rag_no_result_rate": 8,
        "llm_total_tokens": 100,
        "llm_price_coverage": 0,
    }
    items = [
        {"date": "2026-07-14", "metric": "quality.accuracy.score", "average_value": 4.5, "sum_value": 4.5},
        {"date": "2026-07-14", "metric": "api.requests", "average_value": 1, "sum_value": 10},
        {"date": "2026-07-14", "metric": "api.service_errors", "average_value": 1, "sum_value": 2},
        {"date": "2026-07-14", "metric": "llm.requests", "sum_value": 2},
        {"date": "2026-07-14", "metric": "llm.input_tokens", "sum_value": 80},
        {"date": "2026-07-14", "metric": "llm.output_tokens", "sum_value": 20},
        {"date": "2026-07-14", "metric": "llm.cached_input_tokens", "sum_value": 10},
        {"date": "2026-07-14", "metric": "llm.total_tokens", "sum_value": 100},
        {"date": "2026-07-14", "metric": "test.pass_count", "sum_value": 9},
        {"date": "2026-07-14", "metric": "test.fail_count", "sum_value": 1},
        {"date": "2026-07-14", "metric": "rag.searches", "sum_value": 10},
        {"date": "2026-07-14", "metric": "rag.no_result", "sum_value": 1},
        {"date": "2026-07-14", "metric": "rag.top_k_hit", "sum_value": 8, "sample_count": 10},
    ]
    records = [
        {
            "event": {
                "occurred_at": "2026-07-14T00:00:00Z",
                "event_type": "api.request.completed",
                "context": {"service": "chatbot", "run_id": None, "case_id": None},
                "payload": {"status_code": 503},
            }
        },
        {
            "event": {
                "occurred_at": "2026-07-14T01:00:00Z",
                "event_type": "quality.evaluation.completed",
                "context": {"service": "chatbot", "run_id": "RUN-20260714010000", "case_id": "TC-001"},
                "payload": {
                    "scores": {
                        "accuracy": {"evaluated": True, "score": 4.5},
                        "safety": {"evaluated": True, "score": 4.5},
                    }
                },
            }
        },
    ]

    view = build_overview(summary, items, records)

    assert view["status"]["level"] == "danger"
    assert view["quality_trend"].iloc[0]["품질점수"] == 90
    assert view["quality_trend"].iloc[0]["Run ID"] == "RUN-20260714010000"
    assert view["traffic_trend"].iloc[0]["요청 수"] == 10
    assert view["events"].iloc[0]["상태"] == "503"
    assert view["test_distribution"]["건수"].sum() == 10
    assert view["rag_quality"]["top_k_hit_rate"] == 80
    assert view["llm_usage"] == {
        "request_count": 2,
        "input_tokens": 80,
        "output_tokens": 20,
        "cached_input_tokens": 10,
        "total_tokens": 100,
        "cost_krw": None,
        "price_coverage": 0,
        "daily_budget_krw": None,
        "budget_usage_rate": None,
    }
    assert view["issues"].iloc[0]["유형"] == "API 결함"
    assert view["alerts"]
    assert len(view["actions"]) >= 4


def test_streamlit_overview_page_renders_without_exceptions():
    app = AppTest.from_file("tests/fixtures/overview_dashboard_app.py", default_timeout=10)
    app.run()

    assert not app.exception
    assert app.title[0].value == "AI QA 모니터링 대시보드"
    html = "\n".join(str(item.value) for item in app.markdown)
    assert "aqd-kpi-row" in html
    assert 'class="aqd-kpi-row aqd-integration-row"' in html
    assert html.count("class='aqd-kpi") >= 10
    assert "data-tooltip=" in html
    assert "현재 표시: 92.5점" in html
    assert "evaluated=true인 1~5점 항목의 평균 × 20" in html
    assert "HTTP 5xx 또는 timeout" in html
    assert "92.5점" in html
    assert "₩18,420" in html
    assert "aqd-rag-grid" in html
    assert "최근 위반 RUN-20260714010000 · TC-017" in html
    assert any(button.label == "위반 Case 확인" for button in app.button)
    assert any(item.value.startswith("집계 단계 합계 ") for item in app.caption)
    assert len(app.dataframe) == 1
    filters = {item.label: item.value for item in app.selectbox}
    assert filters["환경"] == "전체"
    assert filters["서비스"] == "전체"
    assert filters["공급자"] == "전체"
    assert filters["모델"] == "전체"


def test_full_app_starts_on_new_overview_page():
    app = AppTest.from_file("dashboard/streamlit_app.py", default_timeout=30)
    app.run()
    assert not app.exception
    assert app.button[0].label == "종합 현황"
    assert app.title[0].value == "AI QA 모니터링 대시보드"
    html = "\n".join(str(item.value) for item in app.markdown)
    assert "aqd-kpi-row" in html
