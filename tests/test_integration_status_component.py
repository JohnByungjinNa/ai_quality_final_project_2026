from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.components.integration_status import (
    AI_PROVIDER_ICONS,
    OPS_CARD_ICONS,
    _decision_label,
    render_aws_evidence_management,
)


def test_ops_integration_cards_compact_ai_summary_and_remove_provider_details():
    app = AppTest.from_file("tests/fixtures/integration_status_ops_app.py", default_timeout=10).run()

    assert not app.exception
    markdown = "\n".join(str(item.value) for item in app.markdown)
    for label, icon in OPS_CARD_ICONS.items():
        assert f"{icon} {label}" in markdown

    assert "2/3" in markdown
    assert "2 / 3 설정" not in markdown
    assert f":green-badge[{AI_PROVIDER_ICONS['OpenAI']}]" in markdown
    assert f":gray-badge[{AI_PROVIDER_ICONS['Anthropic']}]" in markdown
    assert f":green-badge[{AI_PROVIDER_ICONS['Gemini']}]" in markdown
    assert "OpenAI, Anthropic, Gemini" not in markdown
    assert not app.dataframe


def test_non_ops_context_keeps_existing_metric_cards_without_provider_badges():
    source = Path("dashboard/components/integration_status.py").read_text(encoding="utf-8")

    assert 'if context == "ops":' in source
    assert "_render_ops_integration_cards" in source


def test_formal_deployment_decision_is_localized():
    assert _decision_label("FORMAL_QUALITY_APPROVED") == "정식 품질 승인"


def test_overview_keeps_aws_summary_without_mutating_actions():
    app = AppTest.from_file("tests/fixtures/integration_status_overview_app.py", default_timeout=10).run()

    assert not app.exception
    markdown = "\n".join(str(item.value) for item in app.markdown)
    assert "정식 품질 승인" in markdown
    assert "파일 2개" in markdown
    assert not any(button.label == "S3 증적 업로드" for button in app.button)
    assert not any(selectbox.label == "업로드 대상 Run" for selectbox in app.selectbox)


def test_aws_evidence_management_is_a_reusable_acceptance_component():
    assert callable(render_aws_evidence_management)
    source = Path("dashboard/pages_top/voc_quality_view.py").read_text(encoding="utf-8")
    assert "AWS S3 최종 인수 증적" in source
    assert 'key_prefix="acceptance"' in source
