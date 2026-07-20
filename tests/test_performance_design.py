from streamlit.testing.v1 import AppTest

from dashboard.components.performance_design import performance_svg_icon, service_icon_name


def _contains_markup(app, text):
    return any(text in item.value for item in app.markdown)


def test_performance_design_icons_cover_each_page_meaning():
    for icon in ["services", "gauge", "database", "docker", "grafana", "prometheus", "fastapi"]:
        assert "<svg" in performance_svg_icon(icon)
    assert service_icon_name("Docker Engine") == "docker"
    assert service_icon_name("Grafana") == "grafana"
    assert service_icon_name("Prometheus") == "prometheus"
    assert service_icon_name("FastAPI") == "fastapi"


def test_service_management_uses_common_performance_design():
    app = AppTest.from_file("tests/fixtures/service_management_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    assert _contains_markup(app, "pfd-hero")
    assert _contains_markup(app, "실행 기반 요약")
    assert _contains_markup(app, "pfd-service-label")


def test_k6_runner_uses_common_performance_design():
    app = AppTest.from_file("tests/fixtures/k6_background_runner_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    assert _contains_markup(app, "pfd-hero")
    assert _contains_markup(app, "실행 설정")
    assert _contains_markup(app, "최근 k6 수행이력")


def test_ops_detail_uses_common_performance_design():
    app = AppTest.from_file("tests/fixtures/ops_detail_design_app.py", default_timeout=15)
    app.run()

    assert not app.exception
    assert _contains_markup(app, "pfd-hero")
    assert _contains_markup(app, "상세 데이터 보기")
    assert _contains_markup(app, "주요 서비스 정보")
    assert app.segmented_control[0].value == "서비스 정보"
