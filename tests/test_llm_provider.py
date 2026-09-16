"""Unit tests for the provider-agnostic LLM layer in api/llm_provider.py.

Verifies:
1. Default provider is 'gemini'.
2. Factory instantiates GeminiAdapter, GroqAdapter, ClaudeAdapter, and MockLLMAdapter.
3. Unsupported provider names raise ValueError.
4. Missing API keys raise ValueError with descriptive instructions.
5. High-level generate_answer interface routes correctly.
"""

import os
import pytest

from api.llm_provider import (
    get_llm_adapter,
    generate_answer,
    GeminiAdapter,
    GroqAdapter,
    ClaudeAdapter,
    MockLLMAdapter,
)


def test_default_provider_is_gemini(monkeypatch):
    """Verify that when LLM_PROVIDER is unset, it defaults to Gemini."""
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    adapter = get_llm_adapter()
    assert isinstance(adapter, GeminiAdapter)
    assert adapter.provider_name == "gemini"


def test_factory_resolves_groq(monkeypatch):
    """Verify that LLM_PROVIDER='groq' instantiates GroqAdapter."""
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    adapter = get_llm_adapter()
    assert isinstance(adapter, GroqAdapter)
    assert adapter.provider_name == "groq"


def test_factory_resolves_claude(monkeypatch):
    """Verify that LLM_PROVIDER='claude' instantiates ClaudeAdapter."""
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    adapter = get_llm_adapter()
    assert isinstance(adapter, ClaudeAdapter)
    assert adapter.provider_name == "claude"


def test_unsupported_provider_raises_error():
    """Verify that unsupported provider names raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported LLM provider 'unsupported_ai'"):
        get_llm_adapter("unsupported_ai")


def test_missing_api_keys_raise_error(monkeypatch):
    """Verify clear error message when required API keys are missing."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    gemini = GeminiAdapter(api_key=None)
    with pytest.raises(ValueError, match="Missing Gemini API key"):
        gemini.generate_answer("hello")

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    groq = GroqAdapter(api_key=None)
    with pytest.raises(ValueError, match="Missing Groq API key"):
        groq.generate_answer("hello")

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
    claude = ClaudeAdapter(api_key=None)
    with pytest.raises(ValueError, match="Missing Claude API key"):
        claude.generate_answer("hello")


def test_mock_adapter_generation():
    """Verify mock adapter produces expected test responses."""
    mock_adapter = MockLLMAdapter(response_text="Test response 123")
    answer = mock_adapter.generate_answer("What is the company policy?")
    assert answer == "Test response 123"


def test_high_level_generate_answer():
    """Verify top-level generate_answer helper with mock provider."""
    answer = generate_answer("Hello", provider="mock")
    assert "Mock answer" in answer
