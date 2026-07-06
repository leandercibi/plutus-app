"""Minimal OpenRouter chat client used for the dashboard AI summaries.

Uses ``requests`` (already a project dependency) rather than the OpenAI SDK to
keep the dependency surface small. The endpoint is OpenAI-compatible, so any
OpenRouter-hosted model works by setting ``LLM_MODEL`` in the environment
(e.g. ``deepseek/deepseek-chat``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from plutus.config.settings import Settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the LLM call fails or returns an unusable response."""


@dataclass
class OpenRouterClient:
    api_key: str
    model: str
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.4
    max_tokens: int = 800
    timeout_seconds: int = 45

    def chat(self, system: str, user: str) -> str:
        """Single-turn completion. Returns the assistant message content."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers recognised by OpenRouter.
            "HTTP-Referer": "https://github.com/leandercibi/plutus-app",
            "X-Title": "Plutus Dashboard",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
        except requests.RequestException as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc

        if resp.status_code != 200:
            raise LLMError(f"LLM returned {resp.status_code}: {resp.text[:300]}")

        try:
            data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {exc}") from exc

        text = (content or "").strip()
        if not text:
            # Reasoning models can consume the whole budget on hidden reasoning
            # tokens and return empty visible content when finish_reason=length.
            finish = choice.get("finish_reason")
            if finish == "length":
                raise LLMError(
                    "LLM output truncated before any content (finish_reason=length); "
                    "increase LLM_MAX_TOKENS — reasoning models need extra headroom"
                )
            raise LLMError(f"LLM returned empty content (finish_reason={finish})")
        return text


def build_llm_client(settings: Settings) -> OpenRouterClient | None:
    """Return a configured client, or None when no API key is set."""
    if settings.openrouter_api_key is None:
        return None
    return OpenRouterClient(
        api_key=settings.openrouter_api_key.get_secret_value(),
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout_seconds=settings.llm_timeout_seconds,
    )
