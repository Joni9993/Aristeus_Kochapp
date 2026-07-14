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

# Safety net appended to the configured chain: free-model slugs get removed from
# OpenRouter regularly (gpt-oss-120b:free and gemini-2.0-flash-exp:free both
# started returning 404), and a stale .env would otherwise take the app down.
# Verified available 2026-07-14.
_LAST_RESORT_MODELS = [
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "google/gemma-4-31b-it:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]


def _effective_chain(settings) -> list[str]:
    chain = list(settings.model_chain)
    chain += [m for m in _LAST_RESORT_MODELS if m not in chain]
    return chain


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
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
) -> tuple[str, dict, float]:
    """Single HTTP call to OpenRouter. Returns (content, usage, elapsed_s). Raises on any failure."""
    body: dict[str, Any] = {"model": model, "messages": messages}
    if response_format:
        body["response_format"] = response_format
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if reasoning_effort is not None:
        # Reasoning models (Nemotron & Co.) otherwise burn 4000+ tokens thinking
        # about a simple JSON task — that's latency and truncation risk
        body["reasoning"] = {"effort": reasoning_effort}

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
    elapsed = time.monotonic() - t0

    # OpenRouter can return HTTP 200 with an error body instead of choices
    # (e.g. provider errors, free-tier daily cap)
    if not data.get("choices"):
        err = data.get("error") or {}
        raise ValueError(f"No choices in response: {err.get('message') or str(data)[:200]}")

    content = data["choices"][0]["message"].get("content")
    if not content:
        raise ValueError(
            f"Empty/null content — finish_reason={data['choices'][0].get('finish_reason')}"
        )
    return content, data.get("usage", {}), elapsed


def _parse_json_content(content: str, model: str, purpose: str) -> dict:
    """Strip markdown fences, parse JSON, repair common LLM mistakes. Raises ValueError on failure."""
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        stripped = "\n".join(inner)

    # strict=False: allow raw control characters (e.g. newlines) inside strings —
    # frequent with free models and otherwise a hard parse failure
    try:
        return json.loads(stripped, strict=False)
    except json.JSONDecodeError:
        pass

    # Repair trailing commas — common LLM mistake: {"a": 1,} or [1, 2,]
    repaired = re.sub(r',\s*([}\]])', r'\1', stripped)
    try:
        return json.loads(repaired, strict=False)
    except json.JSONDecodeError:
        pass

    # Extract embedded JSON — reasoning models sometimes leak thinking prose
    # around (or before) the JSON object. Try each '{' as a candidate start;
    # raw_decode stops at the end of the first valid object.
    decoder = json.JSONDecoder(strict=False)
    pos = repaired.find("{")
    attempts = 0
    while pos != -1 and attempts < 20:
        try:
            obj, _ = decoder.raw_decode(repaired[pos:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        pos = repaired.find("{", pos + 1)
        attempts += 1

    logger.warning(
        "JSON parse failed for %s (purpose=%s) | content[:300]: %s",
        model, purpose, stripped[:300],
    )
    raise ValueError(f"Invalid JSON from {model}")


async def _run_chain(
    messages: list[dict],
    *,
    purpose: str,
    response_format: dict | None,
    temperature: float | None,
    max_tokens: int | None,
    reasoning_effort: str | None,
    parse_json: bool,
) -> tuple[Any, str, dict]:
    """Try every model in the chain (fast failover, no per-model sleep).

    A 429 or a garbled response moves straight to the next model. Only when the
    whole chain failed AND at least one failure was a rate limit do we wait once
    and run a second pass. This keeps the happy path fast even when the first
    free models are congested.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    headers = _make_headers(settings)
    chain = _effective_chain(settings)
    last_exc: Exception | None = None

    for round_no in range(1, _MAX_RETRIES + 1):
        saw_rate_limit = False
        for model in chain:
            logger.info("OpenRouter → %s (round %d/%d, purpose=%s) …", model, round_no, _MAX_RETRIES, purpose)
            try:
                content, usage, elapsed = await _call_once(
                    model, messages, headers, response_format, temperature, max_tokens,
                    reasoning_effort,
                )
                result = _parse_json_content(content, model, purpose) if parse_json else content
                logger.info(
                    "OpenRouter ✓ %s — %.1fs (round %d/%d, purpose=%s, tokens=%s)",
                    model, elapsed, round_no, _MAX_RETRIES, purpose, usage,
                )
                return result, model, usage
            except Exception as exc:
                last_exc = exc
                if _is_rate_limit(exc):
                    saw_rate_limit = True
                logger.warning(
                    "OpenRouter ✗ %s round %d failed (purpose=%s): %s",
                    model, round_no, purpose, exc,
                )

        if round_no < _MAX_RETRIES and saw_rate_limit:
            logger.warning(
                "OpenRouter: full chain rate-limited — waiting %ds before round %d…",
                _RATE_LIMIT_WAIT, round_no + 1,
            )
            await asyncio.sleep(_RATE_LIMIT_WAIT)
        elif not saw_rate_limit:
            break  # hard failures everywhere — a second pass won't help

    raise RuntimeError(f"All OpenRouter attempts failed: {last_exc}") from last_exc


async def chat_completion(
    messages: list[dict],
    *,
    purpose: str = "general",
    response_format: dict | None = None,
    max_tokens: int | None = None,
) -> tuple[str, str, dict]:
    """Call OpenRouter with model fallback. Returns (content_str, model, usage)."""
    return await _run_chain(
        messages,
        purpose=purpose,
        response_format=response_format,
        temperature=None,
        max_tokens=max_tokens,
        reasoning_effort=None,
        parse_json=False,
    )


async def chat_completion_json(
    messages: list[dict],
    *,
    purpose: str = "general",
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = "low",
) -> tuple[dict, str, dict]:
    """Like chat_completion but enforces + parses JSON output.

    Falls through to the next model on JSON parse errors too (not just HTTP
    failures). Returns (parsed_dict, model_used, usage_dict).

    max_tokens must leave headroom for reasoning models — Nemotron & Co. spend
    1000+ completion tokens on reasoning before the JSON starts.
    """
    return await _run_chain(
        messages,
        purpose=purpose,
        response_format={"type": "json_object"},
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        parse_json=True,
    )
