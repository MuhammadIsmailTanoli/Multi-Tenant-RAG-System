"""Provider-agnostic LLM configuration layer for Multi-Tenant RAG System.

Supports seamless switching between leading LLM providers:
- Gemini (Google GenAI) [default]
- Groq (Ultra-fast Llama models)
- Claude (Anthropic)

Configuration is read from environment variables or .env:
- LLM_PROVIDER: 'gemini' (default), 'groq', or 'claude'
- Provider API keys: GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY
- Optional model override: LLM_MODEL
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional
import logging
import os

from dotenv import load_dotenv

# Ensure environment variables from project .env are loaded
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("api.llm_provider")

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODELS: Dict[str, str] = {
    "gemini": "gemini-3.6-flash",
    "groq": "llama-3.3-70b-versatile",
    "claude": "claude-3-5-haiku-20241022",
}


class BaseLLMAdapter(ABC):
    """Abstract interface for multi-provider LLM adapters."""

    @abstractmethod
    def generate_answer(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        """Generate a text answer for the given prompt.

        Args:
            prompt: User or grounded RAG prompt text.
            system_prompt: Optional system instruction context.
            temperature: Sampling temperature (0.0 for deterministic answers).

        Returns:
            Generated response string.
        """
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Active model identifier."""
        pass


class GeminiAdapter(BaseLLMAdapter):
    """Google Gemini adapter using google-genai SDK with HTTP fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._model = model or os.getenv("LLM_MODEL") or DEFAULT_MODELS["gemini"]

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def generate_answer(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        if not self._api_key:
            raise ValueError(
                "Missing Gemini API key. Please set GEMINI_API_KEY (or GOOGLE_API_KEY) in your .env file."
            )

        import time
        import httpx

        max_retries = 3
        last_error = None

        for attempt in range(1, max_retries + 1):
            # 1. Try official google-genai SDK
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(api_key=self._api_key)
                config = types.GenerateContentConfig(
                    temperature=temperature,
                    system_instruction=system_prompt if system_prompt else None,
                )
                response = client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=config,
                )
                if response.text:
                    return response.text.strip()
                return ""
            except ImportError:
                pass
            except Exception as exc:
                last_error = exc
                logger.warning("google.genai SDK attempt %d failed (%s). Trying REST fallback.", attempt, exc)

            # 2. Fallback: Direct REST API via httpx with retry
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"
            contents = [{"role": "user", "parts": [{"text": prompt}]}]
            body = {
                "contents": contents,
                "generationConfig": {"temperature": temperature},
            }
            if system_prompt:
                body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

            try:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(url, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    last_error = RuntimeError(f"Gemini API returned error {resp.status_code}: {resp.text}")
                    if resp.status_code in (503, 429) and attempt < max_retries:
                        sleep_s = attempt * 2
                        logger.warning(
                            "Gemini API returned %d (%s). Retrying in %ds (attempt %d/%d)...",
                            resp.status_code,
                            self._model,
                            sleep_s,
                            attempt,
                            max_retries,
                        )
                        time.sleep(sleep_s)
                        continue
                    if resp.status_code != 200:
                        raise last_error
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(attempt * 2)
                    continue
                raise last_error

        raise RuntimeError(f"Gemini generation failed after {max_retries} attempts: {last_error}")


class GroqAdapter(BaseLLMAdapter):
    """Groq adapter using official groq SDK with OpenAI-compatible REST fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        self._model = model or os.getenv("LLM_MODEL") or DEFAULT_MODELS["groq"]

    @property
    def provider_name(self) -> str:
        return "groq"

    @property
    def model_name(self) -> str:
        return self._model

    def generate_answer(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        if not self._api_key:
            raise ValueError(
                "Missing Groq API key. Please set GROQ_API_KEY in your .env file."
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        # Primary: Official Groq SDK
        try:
            import groq

            client = groq.Groq(api_key=self._api_key)
            completion = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
            )
            return completion.choices[0].message.content.strip()
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("groq SDK call failed (%s). Falling back to REST API.", exc)

        # Fallback: Direct REST API via httpx
        import httpx

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()


class ClaudeAdapter(BaseLLMAdapter):
    """Anthropic Claude adapter using official anthropic SDK with REST fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        self._model = model or os.getenv("LLM_MODEL") or DEFAULT_MODELS["claude"]

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    def generate_answer(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        if not self._api_key:
            raise ValueError(
                "Missing Claude API key. Please set ANTHROPIC_API_KEY in your .env file."
            )

        # Primary: Official Anthropic SDK
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            kwargs = {
                "model": self._model,
                "max_tokens": 1024,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = client.messages.create(**kwargs)
            return response.content[0].text.strip()
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("anthropic SDK call failed (%s). Falling back to REST API.", exc)

        # Fallback: Direct REST API via httpx
        import httpx

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": self._model,
            "max_tokens": 1024,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt

        with httpx.Client(timeout=60.0) as client:
            resp = client.post("https://api.anthropic.com/v1/messages", headers=headers, json=body)
            if resp.status_code != 200:
                raise RuntimeError(f"Claude API error {resp.status_code}: {resp.text}")
            data = resp.json()
            return data["content"][0]["text"].strip()


class MockLLMAdapter(BaseLLMAdapter):
    """Deterministic mock adapter for automated testing and offline verification."""

    def __init__(self, response_text: str = "Mock answer generated for testing."):
        self._response_text = response_text

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock-model"

    def generate_answer(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
    ) -> str:
        return self._response_text


def get_llm_adapter(
    provider_name: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseLLMAdapter:
    """Factory function returning the configured LLM adapter.

    Reads LLM_PROVIDER from environment if provider_name is not explicitly passed.
    Defaults to 'gemini'.

    Args:
        provider_name: 'gemini', 'groq', 'claude', or 'mock'.
        api_key: Optional explicit API key override.
        model: Optional model identifier override.

    Returns:
        Configured BaseLLMAdapter instance.

    Raises:
        ValueError: If provider is unsupported.
    """
    raw_provider = provider_name or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER
    clean_provider = raw_provider.strip().lower()

    if clean_provider == "gemini":
        return GeminiAdapter(api_key=api_key, model=model)
    elif clean_provider == "groq":
        return GroqAdapter(api_key=api_key, model=model)
    elif clean_provider in ("claude", "anthropic"):
        return ClaudeAdapter(api_key=api_key, model=model)
    elif clean_provider == "mock":
        return MockLLMAdapter()
    else:
        valid_options = ["gemini", "groq", "claude"]
        raise ValueError(
            f"Unsupported LLM provider '{raw_provider}'. Supported providers: {valid_options}"
        )


def generate_answer(
    prompt: str,
    system_prompt: Optional[str] = None,
    provider: Optional[str] = None,
    **kwargs,
) -> str:
    """Provider-agnostic high-level generation function.

    Resolves the configured adapter (defaulting to Gemini) and generates an answer.

    Args:
        prompt: User or grounded RAG prompt text.
        system_prompt: Optional system instruction context.
        provider: Optional provider name override ('gemini', 'groq', 'claude').
        **kwargs: Additional parameters passed to adapter.generate_answer.

    Returns:
        Synthesized answer string.
    """
    adapter = get_llm_adapter(provider_name=provider)
    return adapter.generate_answer(prompt=prompt, system_prompt=system_prompt, **kwargs)
