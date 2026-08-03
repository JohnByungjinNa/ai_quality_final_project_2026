from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard.components.integration_status import AI_PROVIDER_ICONS, OPS_CARD_ICONS


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
