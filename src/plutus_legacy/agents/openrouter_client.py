# plutus/agents/openrouter_client.py
from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx
import structlog

from plutus.config import settings

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
_MAX_429_RETRIES = 5
_MAX_5XX_RETRIES = 2
_BASE_BACKOFF_SEC = 1.0
_MAX_BACKOFF_SEC = 16.0


class OpenRouterError(RuntimeError):
    """Raised when OpenRouter returns a non-recoverable error."""


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/plutus-trading",
        "X-Title": "Plutus Trading Engine",
    }


def call_llm(
    messages: list,
    model: str,
    response_format: Optional[dict] = None,
    temperature: float = 0.2,
) -> str:
    """
    Send a chat completion request to OpenRouter and return the assistant's
    text content. Retries on 429 (rate limit) with exponential backoff.

    Args:
        messages: list of {"role": ..., "content": ...} dicts.
        model: OpenRouter model identifier, e.g. "deepseek/deepseek-v4-flash".
        response_format: optional, e.g. {"type": "json_object"}.
        temperature: sampling temperature (default 0.2 — deterministic).

    Returns:
        The assistant message content as a string.
    """
    url = f"{settings.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    backoff = _BASE_BACKOFF_SEC
    attempts_429 = 0
    attempts_5xx = 0

    with httpx.Client(timeout=_TIMEOUT) as client:
        while True:
            try:
                resp = client.post(url, headers=_headers(), json=payload)
            except httpx.RequestError as e:
                if attempts_5xx >= _MAX_5XX_RETRIES:
                    raise OpenRouterError(f"network error: {e}") from e
                attempts_5xx += 1
                logger.warning(
                    "openrouter_network_retry", attempt=attempts_5xx, err=str(e)
                )
                time.sleep(min(backoff, _MAX_BACKOFF_SEC))
                backoff *= 2
                continue

            if resp.status_code == 429:
                if attempts_429 >= _MAX_429_RETRIES:
                    raise OpenRouterError(
                        f"OpenRouter 429 after {attempts_429} retries"
                    )
                attempts_429 += 1
                wait = min(backoff, _MAX_BACKOFF_SEC)
                logger.warning(
                    "openrouter_rate_limited", attempt=attempts_429, sleep=wait
                )
                time.sleep(wait)
                backoff *= 2
                continue

            if 500 <= resp.status_code < 600:
                if attempts_5xx >= _MAX_5XX_RETRIES:
                    raise OpenRouterError(
                        f"OpenRouter {resp.status_code}: {resp.text[:200]}"
                    )
                attempts_5xx += 1
                wait = min(backoff, _MAX_BACKOFF_SEC)
                logger.warning(
                    "openrouter_5xx_retry", code=resp.status_code, attempt=attempts_5xx
                )
                time.sleep(wait)
                backoff *= 2
                continue

            if resp.status_code >= 400:
                raise OpenRouterError(
                    f"OpenRouter {resp.status_code}: {resp.text[:500]}"
                )

            data = resp.json()
            try:
                content = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError) as e:
                raise OpenRouterError(f"malformed response: {data}") from e

            usage = data.get("usage", {})
            logger.debug(
                "llm_call",
                model=model,
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
            return content


def _parse_llm_json(response: str) -> dict:
    """Parse LLM JSON response, stripping markdown fences if present."""
    if not response:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.MULTILINE)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
