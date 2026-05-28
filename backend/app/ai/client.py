"""OpenRouter HTTP client — retry + model fallback."""

import json
import logging
from typing import Any

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MAX_RETRIES = 2


async def chat_completion(
    messages: list[dict],
    *,
    purpose: str = "general",
    response_format: dict | None = None,
) -> tuple[str, str, dict]:
    """Call OpenRouter with retry + model fallback.

    Returns (content_str, model_used, usage_dict).
    Raises RuntimeError if all attempts fail.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set")

    models = settings.model_chain
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.public_frontend_url,
        "X-Title": "Aristeus Kochapp",
    }

    last_exc: Exception | None = None

    for model in models:
        for attempt in range(_MAX_RETRIES):
            body: dict[str, Any] = {
                "model": model,
                "messages": messages,
            }
            if response_format:
                body["response_format"] = response_format

            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.post(OPENROUTER_URL, headers=headers, json=body)
                    resp.raise_for_status()
                    data = resp.json()

                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                logger.info(
                    "OpenRouter %s OK (attempt %d/%d, purpose=%s, tokens=%s)",
                    model, attempt + 1, _MAX_RETRIES, purpose, usage,
                )
                return content, model, usage

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "OpenRouter %s attempt %d failed: %s", model, attempt + 1, exc
                )

    raise RuntimeError(f"All OpenRouter attempts failed: {last_exc}") from last_exc


async def chat_completion_json(
    messages: list[dict],
    *,
    purpose: str = "general",
) -> tuple[dict, str, dict]:
    """Like chat_completion but parses JSON from the response content.

    Uses response_format={"type":"json_object"} and strips markdown fences.
    Returns (parsed_dict, model_used, usage_dict).
    """
    content, model, usage = await chat_completion(
        messages,
        purpose=purpose,
        response_format={"type": "json_object"},
    )
    # Strip markdown code fences if present
    stripped = content.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove first and last fence lines
        inner = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
        stripped = "\n".join(inner)
    return json.loads(stripped), model, usage
