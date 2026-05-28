"""Kaufda scraper: brochure discovery via shelf page + offer extraction via content API.

Architecture:
  1. _get_plz_coords()     — PLZ → lat/lng via api.zippopotam.us
  2. discover_brochures()  — fetch seopages.kaufda.de/shelf with location cookie,
                              parse __NEXT_DATA__ JSON → brochure contentIds + metadata;
                              falls back to search-page discovery for stores like Aldi/Kaufland
                              that don't appear on the shelf page
  3. fetch_brochure_offers() — GET /v1/brochures/{contentId}/pages?lat&lng
                                with Bonial-Api-Consumer: web-content-viewer-fe
  4. refresh_plz()           — full pipeline: discover → fetch → write to DB
"""

import json as jsonlib
import logging
import re
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..models import Brochure, Offer
from .keyword_filter import is_cooking_relevant

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHELF_URL = "https://seopages.kaufda.de/shelf"
CONTENT_API = "https://content-viewer-be.kaufda.de"
ZIPPOPOTAMUS_URL = "https://api.zippopotam.us/DE"
KAUFDA_MAIN_URL = "https://www.kaufda.de"

# Aldi and Kaufland only appear on Kaufda via client-side JS ad placements — not accessible
# via any shelf/SSR page.  We discover their brochures directly from the retailers' own
# websites, which embed the same Bonial content viewer UUIDs our content API accepts.
_RETAILER_OWN_PAGES: dict[str, list[str]] = {
    "aldi": [
        "https://www.aldi-sued.de/de/angebote.html",                     # BW, Bayern, Hessen …
        "https://www.aldi-sued.de/de/angebote/angebote-der-woche.html",
        "https://www.aldi-nord.de/angebote.html",                        # Nord/West
        "https://www.aldi-nord.de/angebote/aktuelle-angebote.html",
    ],
    "kaufland": [
        "https://www.kaufland.de/prospekt.html",
        "https://www.kaufland.de/angebote.html",
    ],
}

# Finds Bonial content-viewer UUIDs near brochure-related keywords in HTML.
_BONIAL_ID_RE = re.compile(
    r'(?:contentId|content[-_]id|brochureId|/static/|/brochures/)["\s:\'=/]*'
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
    re.IGNORECASE,
)

# Full Chrome-like headers used for retailer websites that block simple bot requests.
_RETAILER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;"
        "q=0.8,application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="125", "Google Chrome";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "de-DE,de;q=0.9",
    "Referer": "https://www.kaufda.de/",
}

_CONTENT_HEADERS = {
    **_HEADERS,
    "Bonial-Api-Consumer": "web-content-viewer-fe",
}

STORE_RETAILER_ALIASES: dict[str, list[str]] = {
    "rewe": ["rewe"],
    "lidl": ["lidl"],
    "aldi": ["aldi nord", "aldi süd", "aldi sued", "aldi"],
    "edeka": ["edeka"],
    "penny": ["penny"],
    "netto": ["netto marken", "netto ohne hund", "netto"],
    "kaufland": ["kaufland"],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BrochureInfo:
    content_id: str        # UUID used by content API
    legacy_id: int         # numeric id from shelf
    store: str             # our store key (e.g. "rewe")
    retailer_name: str     # display name from shelf data
    valid_from: str | None # ISO date string "YYYY-MM-DD"
    valid_to: str | None
    lat: float
    lng: float


@dataclass
class OfferRow:
    product_name: str
    price_text: str | None
    quantity_text: str | None
    base_price: str | None
    hint: str | None
    store: str
    live_from_date: str | None
    category: str | None
    is_cooking_relevant: bool
    page_no: int | None


# ---------------------------------------------------------------------------
# PLZ → coordinates
# ---------------------------------------------------------------------------

async def _get_plz_coords(plz: str) -> tuple[float, float]:
    """Look up approximate lat/lng for a German PLZ via zippopotamus.us.
    Returns (49.0, 9.5) as fallback (central Baden-Württemberg) on error.
    """
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{ZIPPOPOTAMUS_URL}/{plz}",
                headers={"User-Agent": "Aristeus-Kochapp/1.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            place = data["places"][0]
            return float(place["latitude"]), float(place["longitude"])
    except Exception as exc:
        logger.warning("PLZ coord lookup failed for %s: %s", plz, exc)
        return 51.1657, 10.4515  # geographic centre of Germany


# ---------------------------------------------------------------------------
# Discovery via shelf page HTML
# ---------------------------------------------------------------------------

def _match_store(retailer_name: str) -> str | None:
    """Return our store ID if the retailer name matches, else None."""
    normalized = retailer_name.lower()
    for store_id, aliases in STORE_RETAILER_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return store_id
    return None


def _coerce_dict(val) -> dict:
    """Coerce a value that might be a list or None into a plain dict."""
    if isinstance(val, list):
        return val[0] if val else {}
    return val if isinstance(val, dict) else {}


def _get_content(item: dict) -> dict:
    """Extract the brochure content dict from a shelf item.

    The API sometimes puts content fields at the top level (no 'content' key),
    sometimes wraps them in a 'content' dict, and occasionally makes 'content' a list.
    """
    raw = item.get("content")
    if raw is None:
        return item
    if isinstance(raw, list):
        return raw[0] if raw else {}
    if isinstance(raw, dict):
        return raw
    return item


def _parse_iso_date(ts: str | None) -> str | None:
    """Extract YYYY-MM-DD from ISO timestamp like 2026-05-25T22:00:00.000+0000."""
    if not ts:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", ts)
    return m.group(1) if m else None


def _extract_from_json_api(
    data: dict | list,
    store_id: str,
    fallback_lat: float,
    fallback_lng: float,
) -> BrochureInfo | None:
    """Extract a BrochureInfo from a Bonial/Kaufda JSON API response.

    Handles both list responses (Bonial v4 leaflets) and dict responses with
    various wrapper keys.  Logs what retailer names were present for diagnosis.
    """
    # Normalise to a flat list of item dicts.
    # Handles multiple response shapes:
    #   - flat list
    #   - {"searchResults": {"contents": {"brochures": [...]}}}  ← Kaufda /api/search
    #   - {"leaflets": [...]} / {"brochures": [...]}              ← Bonial v4
    #   - {"items": [...]} / {"results": [...]}
    def _unwrap(d: dict) -> list:
        for key in ("leaflets", "brochures", "items", "results", "contents"):
            val = d.get(key)
            if isinstance(val, list):
                return val
            if isinstance(val, dict):
                return _unwrap(val)
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        sr = data.get("searchResults")
        if isinstance(sr, dict):
            # searchResults → {"contents": {"brochures": [...]}, ...}
            contents = sr.get("contents")
            if isinstance(contents, dict):
                items = contents.get("brochures") or contents.get("items") or []
            elif isinstance(contents, list):
                items = contents
            else:
                items = _unwrap(sr)
        elif isinstance(sr, list):
            items = sr
        else:
            items = _unwrap(data)
    else:
        items = []

    retailer_names_seen: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        # Each item may wrap its data inside a "content" key (Kaufda search API)
        # or have fields at the top level (Bonial v4 leaflets).
        content = _get_content(item)

        # Retailer name: try content.publisher.name first (Kaufda search),
        # then common Bonial v4 paths.
        publisher = _coerce_dict(content.get("publisher") or {})
        company = _coerce_dict(
            item.get("company") or item.get("retailer") or content.get("company") or {}
        )
        retailer_name = (
            publisher.get("name")
            or company.get("name")
            or content.get("retailerName")
            or item.get("retailerName")
            or item.get("brandName")
            or ""
        )
        retailer_names_seen.append(retailer_name)

        matched = _match_store(retailer_name)
        if matched != store_id:
            continue

        # ContentId: content.id (Kaufda search) or various Bonial v4 field names
        content_id = (
            content.get("id")
            or content.get("contentId")
            or item.get("contentId")
            or item.get("uuid")
            or item.get("id")
            or ""
        )
        if not content_id:
            continue

        store_data = _coerce_dict(
            content.get("closestStore") or item.get("closestStore") or item.get("store") or {}
        )
        return BrochureInfo(
            content_id=str(content_id),
            legacy_id=content.get("legacyId") or item.get("legacyId") or 0,
            store=store_id,
            retailer_name=retailer_name,
            valid_from=_parse_iso_date(
                content.get("validFrom") or item.get("validFrom") or item.get("startDate")
            ),
            valid_to=_parse_iso_date(
                content.get("validUntil") or item.get("validUntil") or item.get("endDate")
            ),
            lat=store_data.get("latitude") or fallback_lat,
            lng=store_data.get("longitude") or fallback_lng,
        )

    logger.info("  [diag:json] retailer names seen: %s", retailer_names_seen[:20])
    return None


def _collect_brochures_from_next_data(
    next_data: dict,
    stores: list[str],
    fallback_lat: float,
    fallback_lng: float,
    *,
    source_label: str = "?",
) -> list[BrochureInfo]:
    """Scan all known JSON paths in a __NEXT_DATA__ blob for matching brochures."""
    results: list[BrochureInfo] = []
    seen_stores: set[str] = set()

    page_info = (
        next_data.get("props", {})
        .get("pageProps", {})
        .get("pageInformation", {})
    )

    logger.info("  [diag:%s] page_info keys: %s", source_label, list(page_info.keys()))

    # Collect items from all known section keys
    all_items: list[dict] = []
    for section_key in ("shelfContents", "searchResults", "brochures", "contents", "items"):
        section = page_info.get(section_key)
        if isinstance(section, dict):
            all_items.extend(section.get("contents") or section.get("items") or [])
        elif isinstance(section, list):
            all_items.extend(section)

    # Diagnostic: log every contentType + retailer name present (regardless of filter)
    seen_combos = [
        (
            item.get("contentType", "—"),
            _coerce_dict(_get_content(item).get("closestStore")).get("name")
            or _get_content(item).get("retailerName", "?"),
        )
        for item in all_items
        if isinstance(item, dict)
    ]
    logger.info("  [diag:%s] all items (contentType, retailer): %s", source_label, seen_combos)

    for item in all_items:
        if not isinstance(item, dict):
            continue
        # Accept "brochure", "handzettel", and items without a contentType field
        content_type = item.get("contentType")
        if content_type is not None and content_type not in ("brochure", "handzettel", "leaflet"):
            continue
        content = _get_content(item)
        content_id = content.get("contentId")
        if not content_id:
            continue

        legacy_id = content.get("id", 0)
        closest_store = _coerce_dict(content.get("closestStore"))
        retailer_name = closest_store.get("name", "") or content.get("retailerName", "")

        store_id = _match_store(retailer_name)
        if not store_id or store_id not in stores or store_id in seen_stores:
            continue
        seen_stores.add(store_id)

        results.append(BrochureInfo(
            content_id=content_id,
            legacy_id=legacy_id,
            store=store_id,
            retailer_name=retailer_name,
            valid_from=_parse_iso_date(content.get("validFrom")),
            valid_to=_parse_iso_date(content.get("validUntil")),
            lat=closest_store.get("latitude", fallback_lat),
            lng=closest_store.get("longitude", fallback_lng),
        ))

    return results


_ANY_UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE,
)


async def _try_uuid_as_brochure(content_id: str, store_id: str, lat: float, lng: float) -> bool:
    """Return True if the content API returns at least one offer for this UUID."""
    try:
        offers = await fetch_brochure_offers(content_id, store_id, lat, lng)
        return bool(offers)
    except Exception:
        return False


async def _discover_via_retailer_page(
    store_id: str,
    lat: float,
    lng: float,
) -> BrochureInfo | None:
    """Fetch the retailer's own brochure page and find a valid Bonial content UUID.

    Strategy:
      1. Look for UUIDs near known Bonial keywords (contentId, /static/, …).
      2. If none found, fall back to searching ALL UUIDs in the HTML (the page may use
         different field names) and test each against the content API.
    """
    pages = _RETAILER_OWN_PAGES.get(store_id, [])
    if not pages:
        return None

    for url in pages:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(url, headers=_RETAILER_HEADERS)
                resp.raise_for_status()
                html = resp.text
        except Exception as exc:
            logger.info("Retailer page %s failed: %s", url, exc)
            continue

        # Pass 1: contextual search (fast, precise)
        content_ids = list(dict.fromkeys(m.group(1) for m in _BONIAL_ID_RE.finditer(html)))

        if not content_ids:
            # Pass 2: search ALL UUIDs in the page
            all_uuids = list(dict.fromkeys(_ANY_UUID_RE.findall(html)))
            logger.info(
                "Retailer page %s: %d chars, 0 contextual UUIDs, %d raw UUIDs: %s",
                url, len(html), len(all_uuids), all_uuids[:10],
            )
            content_ids = all_uuids
        else:
            logger.info("Retailer page %s: %d contextual candidate(s): %s", url, len(content_ids), content_ids[:5])

        for content_id in content_ids[:12]:
            if await _try_uuid_as_brochure(content_id, store_id, lat, lng):
                logger.info("Retailer page %s: contentId %s is valid — using for %s", url, content_id, store_id)
                return BrochureInfo(
                    content_id=content_id,
                    legacy_id=0,
                    store=store_id,
                    retailer_name=store_id.title(),
                    valid_from=None,
                    valid_to=None,
                    lat=lat,
                    lng=lng,
                )

        logger.info("Retailer page %s: no valid contentId found", url)

    logger.warning("Retailer-page discovery failed for store=%s", store_id)
    return None


async def _discover_via_kaufda_api(
    store_id: str,
    plz: str,
    lat: float,
    lng: float,
) -> BrochureInfo | None:
    """Try the Kaufda /api/search endpoint (returned 400 on GET — try POST with JSON body)."""
    queries = {"aldi": ["aldi", "aldi sued", "ALDI SÜD"], "kaufland": ["kaufland", "Kaufland"]}
    search_terms = queries.get(store_id, [store_id])

    for term in search_terms:
        for method in ("post", "get"):
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    kwargs: dict = dict(
                        url="https://www.kaufda.de/api/search",
                        headers={
                            **_HEADERS,
                            "Content-Type": "application/json",
                            "Referer": "https://www.kaufda.de/",
                            "Origin": "https://www.kaufda.de",
                        },
                    )
                    if method == "post":
                        kwargs["json"] = {"query": term, "lat": lat, "lng": lng, "zip": plz, "postalCode": plz}
                        resp = await client.post(**kwargs)
                    else:
                        kwargs["params"] = {"query": term, "lat": lat, "lng": lng, "zip": plz}
                        resp = await client.get(**kwargs)

                    logger.info(
                        "Kaufda /api/search %s query=%r → HTTP %d",
                        method.upper(), term, resp.status_code,
                    )
                    if resp.status_code >= 400:
                        continue
                    data = resp.json()
                    sr = data.get("searchResults") if isinstance(data, dict) else data
                    logger.info(
                        "Kaufda /api/search response: keys=%s  searchResults type=%s len=%s  sample=%s",
                        list(data.keys()) if isinstance(data, dict) else "—",
                        type(sr).__name__,
                        len(sr) if isinstance(sr, (list, dict)) else "—",
                        str(sr)[:300] if sr else "empty",
                    )
                    found = _extract_from_json_api(data, store_id, lat, lng)
                    if found:
                        logger.info("Kaufda /api/search found %s (contentId=%s)", store_id, found.content_id)
                        return found
            except Exception as exc:
                logger.info("Kaufda /api/search %s query=%r failed: %s", method.upper(), term, exc)

    return None


async def discover_brochures(plz: str, stores: list[str]) -> list[BrochureInfo]:
    """Return current brochures for the given PLZ, filtered to requested stores.

    Primary: kaufda shelf page (fast, covers most stores).
    Fallback: store-specific search pages for Aldi/Kaufland which don't appear on shelf.
    """
    lat, lng = await _get_plz_coords(plz)

    location_payload = jsonlib.dumps({
        "city": plz,
        "cityDisplayName": plz,
        "countryCode": "DE",
        "lat": lat,
        "lng": lng,
        "zip": plz,
    }, separators=(",", ":"))
    location_cookie = urllib.parse.quote(location_payload)

    shelf_headers = {
        **_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cookie": f"location={location_cookie}",
    }

    # --- Primary: shelf page ---
    results: list[BrochureInfo] = []
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(
                SHELF_URL,
                params={"postalCode": plz},
                headers=shelf_headers,
            )
            resp.raise_for_status()
            html = resp.text

        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            next_data = jsonlib.loads(m.group(1))
            results = _collect_brochures_from_next_data(
                next_data, stores, lat, lng, source_label="shelf"
            )
        else:
            logger.error("No __NEXT_DATA__ found in shelf page for PLZ %s", plz)
    except Exception as exc:
        logger.error("Shelf page fetch/parse failed for PLZ %s: %s", plz, exc)

    logger.info(
        "Discovery via shelf page: found %d matching brochures for PLZ %s (stores: %s)",
        len(results), plz, [r.store for r in results],
    )

    # --- Fallback: scrape retailer's own website for stores missing from shelf ---
    found_store_ids = {r.store for r in results}
    missing = [s for s in stores if s not in found_store_ids and s in _RETAILER_OWN_PAGES]

    for store_id in missing:
        logger.info("Store %s not on shelf page for PLZ %s — trying fallbacks", store_id, plz)
        brochure = (
            await _discover_via_kaufda_api(store_id, plz, lat, lng)
            or await _discover_via_retailer_page(store_id, lat, lng)
        )
        if brochure:
            results.append(brochure)

    return results


# ---------------------------------------------------------------------------
# Offer extraction via content viewer API
# ---------------------------------------------------------------------------

async def fetch_brochure_offers(content_id: str, store: str, lat: float, lng: float) -> list[OfferRow]:
    """Download all pages of a brochure and extract offer rows."""
    rows: list[OfferRow] = []
    seen: set[str] = set()

    url = f"{CONTENT_API}/v1/brochures/{content_id}/pages"
    params = {"lat": lat, "lng": lng}

    try:
        async with httpx.AsyncClient(headers=_CONTENT_HEADERS, timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.error("Failed to fetch pages for brochure %s: %s", content_id, exc)
        return rows

    pages = data.get("contents") or []
    for page in pages:
        page_no = page.get("number")
        for offer_block in page.get("offers") or []:
            extracted = _extract_offer(offer_block, store, page_no)
            for row in extracted:
                key = f"{row.product_name}|{row.price_text}"
                if key not in seen:
                    seen.add(key)
                    rows.append(row)

    logger.info("Extracted %d offers from brochure %s (%s)", len(rows), content_id, store)
    return rows


def _extract_offer(offer_block: dict, store: str, page_no) -> list[OfferRow]:
    """Extract OfferRow(s) from a single offer block in the new API format."""
    rows: list[OfferRow] = []
    content = offer_block.get("content", {})

    products = content.get("products") or []
    deals = content.get("deals") or []
    profiles = content.get("publicationProfiles") or []

    if not products:
        return rows

    # Determine best price (prefer deal without loyalty conditions)
    price_text = _best_price(deals)
    base_price = _base_price(deals)
    hint = _build_hint(deals, profiles)
    live_from = _live_from(profiles)

    for prod in products:
        name = _build_name(prod)
        if not name:
            continue

        quantity = None
        desc_list = prod.get("description") or []
        if desc_list and isinstance(desc_list[0], dict):
            quantity = desc_list[0].get("paragraph")

        category = None
        cat_paths = prod.get("categoryPaths") or []
        if cat_paths:
            category = cat_paths[0].get("name")

        rows.append(OfferRow(
            product_name=name,
            price_text=price_text,
            quantity_text=str(quantity)[:200] if quantity else None,
            base_price=str(base_price)[:80] if base_price else None,
            hint=str(hint)[:300] if hint else None,
            store=store,
            live_from_date=live_from,
            category=str(category)[:200] if category else None,
            is_cooking_relevant=is_cooking_relevant(name, str(quantity) if quantity else None),
            page_no=int(page_no) if page_no is not None else None,
        ))

    return rows


def _build_name(prod: dict) -> str:
    brand = (prod.get("brandName") or "").strip()
    name = (prod.get("name") or "").strip()
    if brand and name and not name.lower().startswith(brand.lower()):
        return f"{brand} {name}"
    return name or brand


def _best_price(deals: list[dict]) -> str | None:
    """Return price text, preferring deals without loyalty card conditions."""
    if not deals:
        return None
    # Prefer deal with no conditions (regular price)
    plain = next((d for d in deals if not d.get("conditions")), None)
    deal = plain or deals[0]
    min_p = deal.get("min")
    max_p = deal.get("max")
    if min_p is None:
        return None
    if min_p == max_p or max_p is None:
        return f"{float(min_p):.2f} €"
    return f"{float(min_p):.2f}–{float(max_p):.2f} €"


def _base_price(deals: list[dict]) -> str | None:
    for d in deals:
        if v := d.get("priceByBaseUnit"):
            return str(v)
    return None


def _build_hint(deals: list[dict], profiles: list[dict]) -> str | None:
    parts = []
    # Loyalty conditions (e.g. "Mit Lidl Plus")
    for d in deals:
        for cond in d.get("conditions") or []:
            if v := cond.get("other"):
                parts.append(str(v))
                break
    # Validity
    if profiles:
        end = _parse_iso_date((profiles[0].get("validity") or {}).get("endDate"))
        if end:
            parts.append(f"gültig bis {end}")
    return " | ".join(parts) if parts else None


def _live_from(profiles: list[dict]) -> str | None:
    if profiles:
        return _parse_iso_date((profiles[0].get("validity") or {}).get("startDate"))
    return None


# ---------------------------------------------------------------------------
# Full pipeline: refresh one PLZ
# ---------------------------------------------------------------------------

async def refresh_plz(plz: str, stores: list[str], db: DbSession) -> dict:
    """Discover + fetch all brochures for a PLZ and persist to DB."""
    summary: dict[str, int] = {}
    now = datetime.now(timezone.utc)

    brochures = await discover_brochures(plz, stores)

    if not brochures:
        logger.warning("No brochures found for PLZ %s stores %s", plz, stores)
        return {"plz": plz, "brochures_found": 0, "offers": {}}

    for bi in brochures:
        existing = db.scalar(
            select(Brochure).where(
                Brochure.brochure_id_kaufda == bi.content_id,
                Brochure.postal_code == plz,
                Brochure.store == bi.store,
            )
        )
        if existing:
            logger.debug("Brochure %s already in DB, skipping", bi.content_id)
            summary[bi.store] = len(existing.offers)
            continue

        # Mark older brochures for this store+plz as stale
        for old in db.scalars(
            select(Brochure).where(
                Brochure.store == bi.store,
                Brochure.postal_code == plz,
                Brochure.brochure_id_kaufda != bi.content_id,
            )
        ):
            old.status = "stale"

        rows = await fetch_brochure_offers(bi.content_id, bi.store, bi.lat, bi.lng)

        brochure = Brochure(
            store=bi.store,
            postal_code=plz,
            brochure_id_kaufda=bi.content_id,
            retailer_name=bi.retailer_name,
            valid_from=bi.valid_from,
            valid_to=bi.valid_to,
            fetched_at=now,
            status="active",
        )
        db.add(brochure)
        db.flush()

        for row in rows:
            db.add(Offer(
                brochure_id=brochure.id,
                product_name=row.product_name,
                price_text=row.price_text,
                quantity_text=row.quantity_text,
                base_price=row.base_price,
                hint=row.hint,
                store=row.store,
                live_from_date=row.live_from_date,
                category=row.category,
                is_cooking_relevant=row.is_cooking_relevant,
                page_no=row.page_no,
            ))

        db.commit()
        summary[bi.store] = len(rows)
        logger.info("Stored %d offers for %s (PLZ %s)", len(rows), bi.store, plz)

    return {"plz": plz, "brochures_found": len(brochures), "offers": summary}
