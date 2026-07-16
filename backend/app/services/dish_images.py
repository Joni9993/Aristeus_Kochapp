"""Dish photo lookup via the Pexels Search API.

Env-gated: with no PEXELS_API_KEY set, find_dish_image() is a no-op that
always returns None so image search stays fully optional. Results are cached
in-process (dish name -> URL) so the same dish name isn't looked up twice
within a process lifetime — cheap insurance against Pexels' rate limit
(200 req/h on the free tier) when many households suggest the same dish.
"""

import logging

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"

# In-memory cache: lowercased dish name -> image URL (or None for "looked up,
# nothing found"). Cleared on process restart — fine, it's just an optimization.
_image_cache: dict[str, str | None] = {}


async def find_dish_image(name: str, kategorie: str | None = None) -> str | None:
    """Look up a landscape photo for a dish name via Pexels. Never raises.

    Returns None when no API key is configured, the lookup fails, or nothing
    is found.
    """
    settings = get_settings()
    if not settings.pexels_api_key:
        return None

    cache_key = (name or "").strip().lower()
    if not cache_key:
        return None
    if cache_key in _image_cache:
        return _image_cache[cache_key]

    query = f"{name} essen gericht"
    headers = {"Authorization": settings.pexels_api_key}
    params = {
        "query": query,
        "locale": "de-DE",
        "orientation": "landscape",
        "per_page": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(PEXELS_SEARCH_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        photos = data.get("photos") or []
        url = photos[0]["src"]["large"] if photos else None
    except Exception as exc:
        logger.warning("Pexels image lookup failed for '%s': %s", name, exc)
        url = None

    _image_cache[cache_key] = url
    return url
