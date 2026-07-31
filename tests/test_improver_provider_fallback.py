import asyncio
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_DIR / "voc_quality_runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from agents import improver  # noqa: E402


def test_policy_provider_order_env_normalizes_aliases(monkeypatch):
    monkeypatch.setenv("A2A_POLICY_PROVIDER_ORDER", "google, gpt, claude")

    assert improver._provider_order_from_env() == ["gemini", "openai", "anthropic"]


def test_improver_agent_starts_without_anthropic_for_healthcheck(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    agent = improver.PolicyImproverAgent()
    result = asyncio.run(agent.improve("healthcheck"))

    assert "Improver Agent" in result.policy


def test_policy_llm_skips_placeholder_keys(monkeypatch):
    monkeypatch.setenv("A2A_POLICY_PROVIDER_ORDER", "anthropic,openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    async def fake_call_provider(provider, prompt, *, model, max_tokens):
        assert provider == "openai"
        return "OpenAI fallback policy improvement"

    monkeypatch.setattr(improver, "_call_policy_provider", fake_call_provider)

    router = improver.PolicyLLMFallback()
    text = asyncio.run(router("VOC summary", max_tokens=64))

    assert text == "OpenAI fallback policy improvement"
    assert router.last_provider == "openai"
    assert [item["status"] for item in router.last_attempts] == ["SKIPPED", "SUCCESS"]


def test_policy_llm_fallback_uses_next_provider_after_failure(monkeypatch):
    monkeypatch.setenv("A2A_POLICY_PROVIDER_ORDER", "anthropic,gemini,openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")

    async def fake_call_provider(provider, prompt, *, model, max_tokens):
        if provider == "anthropic":
            raise RuntimeError("credit balance too low")
        if provider == "gemini":
            return "Gemini fallback policy improvement"
        raise AssertionError("OpenAI should not be called after Gemini succeeds")

    monkeypatch.setattr(improver, "_call_policy_provider", fake_call_provider)

    router = improver.PolicyLLMFallback()
    text = asyncio.run(router("VOC summary", max_tokens=64))

    assert text == "Gemini fallback policy improvement"
    assert router.last_provider == "gemini"
    assert [item["status"] for item in router.last_attempts] == ["ERROR", "SUCCESS"]
