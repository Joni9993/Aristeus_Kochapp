"""Kaufda scraper: brochure discovery via shelf page + offer extraction via content API.

Architecture:
  1. _get_plz_coords()     — PLZ → lat/lng via api.zippopotam.us
  2. discover_brochures()  — fetch seopages.kaufda.de/shelf with location cookie,
                              parse __NEXT_DATA__ JSON → brochure contentIds + metadata
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


def _parse_iso_date(ts: str | None) -> str | None:
    """Extract YYYY-MM-DD from ISO timestamp like 2026-05-25T22:00:00.000+0000."""
    if not ts:
        return None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", ts)
    return m.group(1) if m else None


async def discover_brochures(plz: str, stores: list[str]) -> list[BrochureInfo]:
    """Return current brochures for the given PLZ, filtered to requested stores.

    Fetches the kaufda shelf page with a location cookie and parses the
    embedded __NEXT_DATA__ JSON to extract brochure contentIds.
    """
    lat, lng = await _get_plz_coords(plz)

    # Build location cookie with PLZ coordinates
    location_payload = jsonlib.dumps({
        "city": plz,
        "cityDisplayName": plz,
        "countryCode": "DE",
        "lat": lat,
        "lng": lng,
        "zip": plz,
    }, separators=(",", ":"))
    location_cookie = urllib.parse.quote(location_payload)

    headers = {
        **_HEADERS,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Cookie": f"location={location_cookie}",
    }

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(
                SHELF_URL,
                params={"postalCode": plz},
                headers=headers,
            )
            resp.raise_for_status()
            html = resp.text
    except Exception as exc:
        logger.error("Shelf page fetch failed for PLZ %s: %s", plz, exc)
        return []

    # Extract __NEXT_DATA__ JSON
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        logger.error("No __NEXT_DATA__ found in shelf page for PLZ %s", plz)
        return []

    try:
        next_data = jsonlib.loads(m.group(1))
        page_info = (
            next_data
            .get("props", {})
            .get("pageProps", {})
            .get("pageInformation", {})
        )
        shelf_contents = page_info.get("shelfContents", {}).get("contents", [])
    except Exception as exc:
        logger.error("Failed to parse __NEXT_DATA__ for PLZ %s: %s", plz, exc)
        return []

    seen_stores: set[str] = set()
    results: list[BrochureInfo] = []

    for item in shelf_contents:
        if item.get("contentType") != "brochure":
            continue

        content = item.get("content", {})
        content_id = content.get("contentId")
        legacy_id = content.get("id", 0)
        closest_store = content.get("closestStore", {})
        retailer_name = closest_store.get("name", "")

        store_id = _match_store(retailer_name)
        if not store_id or store_id not in stores:
            continue
        # One brochure per store
        if store_id in seen_stores:
            continue
        seen_stores.add(store_id)

        store_lat = closest_store.get("latitude", lat)
        store_lng = closest_store.get("longitude", lng)

        results.append(BrochureInfo(
            content_id=content_id,
            legacy_id=legacy_id,
            store=store_id,
            retailer_name=retailer_name,
            valid_from=_parse_iso_date(content.get("validFrom")),
            valid_to=_parse_iso_date(content.get("validUntil")),
            lat=store_lat,
            lng=store_lng,
        ))

    logger.info(
        "Discovery via shelf page: found %d matching brochures for PLZ %s (stores: %s)",
        len(results), plz, [r.store for r in results],
    )
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
