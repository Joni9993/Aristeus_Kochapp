"""OpenRouter HTTP client — retry + model fallback."""

import asyncio
import json
import logging
import re
import time
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 2
_RATE_LIMIT_WAIT = 35  # seconds to wait after a 429 before retrying


def _make_headers(settings) -> dict:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_frontend_url,
        "X-Title": "Aristeus Kochapp",
    }


def _is_rate_limit(exc: Exception) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


async def _call_once(
    model: str,
    messages: list[dict],
    headers: dict,
    response_format: dict | None = None,
) -> tuple[str, dict, float]:
    """Single HTTP call to OpenRouter. Returns (content, usage, elapsed_s). Raises on any failure."""
    body: dict[str, Any] = {"model": model, "messages": messages}
    if response_format:
        body["response_format"] = response_format

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    elapsed = time.monotonic() - t0

    content = data["choices"][0]["message"].get("content")
    if not content:
        raise ValueError(
            f"Empty/null content — finish_reason={data['choices'][0].get('finish_reason')}"
        )
    return content, data.get("usage", {}), elapsed


def _parse_json_content(content: str, model: str, purpose: str) -> dict:
    """Strip markdown fences, parse JSON, repair trailing commas. Raises ValueError on failure."""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        stripped = "\n".join(inner)

    # Direct parse
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Repair trailing commas — common LLM mistake: {"a": 1,} or [1, 2,]
    repaired = re.sub(r',\s*([}\]])', r'\1', stripped)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as exc:
        logger.warning(
            "JSON parse failed for %s (purpose=%s): %s | content[:300]: %s",
            model, purpose, exc, stripped[:300],
        )
        raise ValueError(f"Invalid JSON from {model}: {exc}") from exc


async def chat_completion(
    messages: list[dict],
    *,
    purpose: str = "general",
    response_format: dict | None = None,
) -> tuple[str, str, dict]:
    """Call OpenRouter with retry + model fallback. Returns (content_str, model, usage)."""
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    headers = _make_headers(settings)
    last_exc: Exception | None = None

    for model in settings.model_chain:
        for attempt in range(1, _MAX_RETRIES + 1):
            logger.info("OpenRouter → %s (attempt %d/%d, purpose=%s) …", model, attempt, _MAX_RETRIES, purpose)
            try:
                content, usage, elapsed = await _call_once(model, messages, headers, response_format)
                logger.info(
                    "OpenRouter ✓ %s — %.1fs (attempt %d/%d, purpose=%s, tokens=%s)",
                    model, elapsed, attempt, _MAX_RETRIES, purpose, usage,
                )
                return content, model, usage
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc) and attempt < _MAX_RETRIES:
                    logger.warning(
                        "OpenRouter ✗ %s attempt %d: rate limited — waiting %ds before retry…",
                        model, attempt, _RATE_LIMIT_WAIT,
                    )
                    await asyncio.sleep(_RATE_LIMIT_WAIT)
                else:
                    logger.warning("OpenRouter ✗ %s attempt %d failed: %s", model, attempt, exc)

    raise RuntimeError(f"All OpenRouter attempts failed: {last_exc}") from last_exc


async def chat_completion_json(
    messages: list[dict],
    *,
    purpose: str = "general",
) -> tuple[dict, str, dict]:
    """Like chat_completion but parses + validates JSON.

    Retries across models on JSON parse errors too (not just HTTP failures),
    so a model returning garbled JSON automatically falls back to the next one.
    Returns (parsed_dict, model_used, usage_dict).
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    headers = _make_headers(settings)
    last_exc: Exception | None = None

    for model in settings.model_chain:
        for attempt in range(1, _MAX_RETRIES + 1):
            logger.info("OpenRouter → %s (attempt %d/%d, purpose=%s) …", model, attempt, _MAX_RETRIES, purpose)
            try:
                content, usage, elapsed = await _call_once(
                    model, messages, headers,
                    response_format={"type": "json_object"},
                )
                parsed = _parse_json_content(content, model, purpose)
                logger.info(
                    "OpenRouter ✓ %s — %.1fs (attempt %d/%d, purpose=%s, tokens=%s)",
                    model, elapsed, attempt, _MAX_RETRIES, purpose, usage,
                )
                return parsed, model, usage
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc) and attempt < _MAX_RETRIES:
                    logger.warning(
                        "OpenRouter ✗ %s attempt %d: rate limited — waiting %ds before retry…",
                        model, attempt, _RATE_LIMIT_WAIT,
                    )
                    await asyncio.sleep(_RATE_LIMIT_WAIT)
                else:
                    logger.warning(
                        "OpenRouter ✗ %s attempt %d failed (purpose=%s): %s",
                        model, attempt, purpose, exc,
                    )

    raise RuntimeError(f"All OpenRouter JSON attempts failed: {last_exc}") from last_exc
