"""Chefkoch.de recipe scraper — fills the local recipe catalog.

Usage (CLI):
    python -m app.services.chefkoch_scraper [--max N] [--delay SECS]

Scraping strategy:
  1. Fetch the Rezeptsammlungen hub page, collect collection links.
  2. For each collection page, collect individual recipe page links.
  3. For each recipe page, extract the JSON-LD <script type="application/ld+json">
     block with @type "Recipe" and persist to DB.

All HTTP calls respect a configurable per-request delay and retry on 429/5xx.
The scraper is idempotent: existing source_url rows are only touch-updated.
"""

import asyncio
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session as DbSession

from ..db import SessionLocal
from ..models import Recipe, RecipeIngredient

logger = logging.getLogger(__name__)

_BASE = "https://www.chefkoch.de"
_COLLECTIONS_URL = "https://www.chefkoch.de/rezeptsammlungen/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "de-DE,de;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ---------------------------------------------------------------------------
# Diet / allergen detection keyword maps
# ---------------------------------------------------------------------------

_MEAT_KINDS: dict[str, list[str]] = {
    "chicken": ["hähnchen", "huhn", "hühnchen", "chicken", "poularde"],
    "turkey": ["pute", "truthahn", "turkey"],
    "beef": ["rind", "beef", "steak", "hackfleisch", "ochsen", "kalb"],
    "pork": ["schwein", "pork", "speck", "bacon", "wurst", "schinken", "ham", "salami"],
    "fish": ["fisch", "lachs", "thunfisch", "forelle", "garnele", "shrimp",
             "meeresfrüchte", "hering", "makrele", "sardine", "tintenfisch"],
}

_VEGAN_BLOCKED = [
    "ei", "eier", "milch", "käse", "butter", "sahne", "joghurt",
    "quark", "honig", "fleisch", "fisch", "lachs", "wurst", "speck",
    "hähnchen", "huhn", "rind", "schwein", "gelatine", "schmalz",
]
_VEGETARIAN_BLOCKED = [
    "fleisch", "hackfleisch", "hähnchen", "huhn", "rind", "schwein",
    "wurst", "speck", "thunfisch", "lachs", "garnele", "pute", "truthahn",
    "gelatine", "schmalz", "fisch",
]
_ALLERGEN_MAP: dict[str, list[str]] = {
    "gluten": ["mehl", "weizen", "dinkel", "gerste", "roggen", "brot", "nudel", "pasta"],
    "laktose": ["milch", "butter", "sahne", "joghurt", "käse", "quark"],
    "ei": ["ei", "eier"],
    "nuss": ["nuss", "nüsse", "mandel", "haselnuss", "walnuss", "cashew", "pistaz"],
    "soja": ["soja", "tofu", "edamame"],
    "erdnuss": ["erdnuss"],
    "sesam": ["sesam"],
    "fisch": ["fisch", "lachs", "thunfisch", "sardine"],
    "schalentiere": ["garnele", "shrimp", "krebs", "hummer", "tintenfisch"],
}

_DESSERT_CATS = {
    "Kuchen", "Dessert", "Frucht", "Cremes", "Torten", "Süßspeisen",
    "Kekse & Plätzchen", "Mehlspeisen", "Backen",
}
_DRINK_CATS = {"Longdrink", "Liköre", "Alkoholfrei"}
_GRUNDREZEPT_CATS = {
    "Saucen & Dips", "Grundrezepte", "Saucen", "Salatdressing",
    "Aufstrich", "Brot und Brötchen", "Fingerfood", "Marinieren",
}


# Unambiguous dessert-only keywords — never appear in savory main dishes.
# Intentionally conservative: "kuchen", "waffel", "muffin", "pudding" excluded
# because they have common savory variants (Zwiebelkuchen, herzhafter Waffel, etc.).
_DESSERT_NAME_KW = {
    "frosting", "buttercreme",
    "mousse",
    "brownie", "cupcake", "cheesecake", "tiramisu",
    "zimtschnecken", "kanelbullar", "cinnabon",
    "macarons",
    "panna cotta",
    "parfait",
    "nougat",
    "crumble",
}


def _classify_meal_type(category: str | None, name: str = "") -> str:
    # Category-based (primary signal)
    if category in _DESSERT_CATS:
        return "dessert"
    if category in _DRINK_CATS:
        return "getraenk"
    if category in _GRUNDREZEPT_CATS:
        return "grundrezept"

    # Name-based fallback — only for unambiguous dessert terms.
    # Sauce/dip detection intentionally omitted: "Spaghetti mit Tomatensauce"
    # is a complete dish; detecting standalone sauces reliably requires context.
    name_lower = name.lower()
    if any(kw in name_lower for kw in _DESSERT_NAME_KW):
        return "dessert"

    return "hauptgericht"


_STOP_WORDS = {
    "frisch", "frische", "frisches", "frischem", "tiefgekühlt", "tk",
    "bio", "getrocknet", "geräuchert", "gehackt", "gewürfelt", "geschnitten",
    "klein", "groß", "mittel", "fein", "grob", "nach", "geschmack",
    "optional", "ca", "etwa", "etwas", "beliebig", "je", "nach", "bedarf",
}

# ---------------------------------------------------------------------------
# Ingredient text parser
# ---------------------------------------------------------------------------

_UNIT_PATTERN = re.compile(
    r"^([\d]+(?:[.,]\d+)?)\s*"
    r"(kg|g|mg|l|ml|cl|dl|el|tl|tasse|tassen|stück|stk|prise|prisen|"
    r"bund|bunde|zehe|zehen|scheibe|scheiben|dose|dosen|glas|pkg|pck|paket|"
    r"handvoll|msp|mssp|becher|beutel|flasche|fl)\s+(.*)",
    re.IGNORECASE,
)


def _parse_ingredient(text: str) -> tuple[float | None, str | None, str]:
    """Parse '500 g Hähnchenbrustfilet, frisch' → (500.0, 'g', 'Hähnchenbrustfilet, frisch')."""
    text = text.strip()
    m = _UNIT_PATTERN.match(text)
    if m:
        qty_str, unit, rest = m.group(1), m.group(2), m.group(3)
        qty = float(qty_str.replace(",", "."))
        return qty, unit.lower(), rest.strip()
    # Try bare number prefix (e.g. "3 Zwiebeln")
    m2 = re.match(r"^([\d]+(?:[.,]\d+)?)\s+(.*)", text)
    if m2:
        qty = float(m2.group(1).replace(",", "."))
        return qty, None, m2.group(2).strip()
    return None, None, text


def _normalize_for_match(raw: str) -> str:
    """Strip stop-words, commas, parenthetical notes → short lowercase match key."""
    # Remove parenthetical notes e.g. "(oder Crème fraîche)"
    raw = re.sub(r"\(.*?\)", "", raw)
    # Remove comma-separated qualifiers: "Hähnchenbrustfilet, frisch" → "Hähnchenbrustfilet"
    raw = raw.split(",")[0]
    words = raw.lower().split()
    kept = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    return " ".join(kept).strip()


# ---------------------------------------------------------------------------
# Diet / allergen flag deriver
# ---------------------------------------------------------------------------

def _derive_flags(normalized_names: list[str]) -> dict[str, Any]:
    combined = " ".join(normalized_names)

    def _hit(kws: list[str]) -> bool:
        return any(kw in combined for kw in kws)

    meat_kinds: list[str] = []
    for kind, kws in _MEAT_KINDS.items():
        if _hit(kws):
            meat_kinds.append(kind)

    is_fish = "fish" in meat_kinds
    is_meat = bool(set(meat_kinds) - {"fish"})

    is_vegan = not _hit(_VEGAN_BLOCKED) and not is_meat and not is_fish
    is_vegetarian = is_vegan or (not _hit(_VEGETARIAN_BLOCKED) and not is_meat)

    allergens: list[str] = []
    for allergen, kws in _ALLERGEN_MAP.items():
        if _hit(kws):
            allergens.append(allergen)

    return {
        "is_vegetarian": is_vegetarian,
        "is_vegan": is_vegan,
        "is_meat": is_meat,
        "is_fish": is_fish,
        "contains_pork": "pork" in meat_kinds,
        "contains_beef": "beef" in meat_kinds,
        "contains_chicken": "chicken" in meat_kinds,
        "contains_turkey": "turkey" in meat_kinds,
        "allergen_flags_json": json.dumps(allergens, ensure_ascii=False),
        "meat_kinds_json": json.dumps(meat_kinds, ensure_ascii=False),
    }


# ---------------------------------------------------------------------------
# Name cleaner (strips " von <author>" suffix chefkoch appends)
# ---------------------------------------------------------------------------

def _clean_name(name: str) -> str:
    return re.sub(r"\s+von\s+\S+$", "", name).strip()


# ---------------------------------------------------------------------------
# ISO 8601 duration parser (PT30M, PT1H30M)
# ---------------------------------------------------------------------------

def _parse_duration_min(iso: str | None) -> int | None:
    """Parse ISO 8601 durations: PT30M, PT1H30M, P0DT0H30M, P1DT2H30M."""
    if not iso:
        return None
    # Extract hours and minutes anywhere in the string
    hours = int(m.group(1)) if (m := re.search(r"(\d+)H", iso)) else 0
    minutes = int(m.group(1)) if (m := re.search(r"(\d+)M", iso)) else 0
    days = int(m.group(1)) if (m := re.search(r"(\d+)D", iso)) else 0
    total = days * 24 * 60 + hours * 60 + minutes
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

async def _fetch(client: httpx.AsyncClient, url: str, delay: float) -> str | None:
    await asyncio.sleep(delay + random.uniform(0, 0.5))
    for attempt in range(4):
        try:
            r = await client.get(url, follow_redirects=True, timeout=20)
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503, 502):
                wait = (2 ** attempt) * 5
                logger.warning("HTTP %d for %s — waiting %ds", r.status_code, url, wait)
                await asyncio.sleep(wait)
            else:
                logger.debug("HTTP %d for %s — skipping", r.status_code, url)
                return None
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning("Request error %s for %s (attempt %d)", exc, url, attempt + 1)
            await asyncio.sleep(3 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Link collectors
# ---------------------------------------------------------------------------

def _is_recipe_url(url: str) -> bool:
    # Recipe URLs: /rezepte/<numeric_id>/<Slug>.html
    parsed = urlparse(url)
    parts = [p for p in parsed.path.rstrip("/").split("/") if p]
    return (
        parsed.netloc == "www.chefkoch.de"
        and len(parts) >= 3
        and parts[0] == "rezepte"
        and parts[1].isdigit()
        and parsed.path.endswith(".html")
    )


def _is_pagination_url(url: str) -> bool:
    """Hub pagination: /rezeptsammlungen/2 (plural path + bare page number)."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.rstrip("/").split("/") if p]
    return len(parts) == 2 and parts[0] == "rezeptsammlungen" and parts[1].isdigit()


def _is_collection_detail_url(url: str) -> bool:
    """Individual collection page: /rezeptsammlung/<id> (singular, numeric id only)."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.rstrip("/").split("/") if p]
    if not parts:
        return False
    # Singular "rezeptsammlung" with a numeric id
    return len(parts) == 2 and parts[0] == "rezeptsammlung" and parts[1].isdigit()


def _extract_links_from_page(html: str, base_url: str) -> tuple[list[str], list[str], list[str]]:
    """Return (recipe_urls, collection_urls, pagination_urls) from a page."""
    soup = BeautifulSoup(html, "html.parser")
    recipes, collections, paginations = [], [], []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?")[0].split("#")[0]  # strip query/fragment
        if not href:
            continue
        href = urljoin(base_url, href)
        if href in seen:
            continue
        seen.add(href)
        if _is_recipe_url(href):
            recipes.append(href)
        elif _is_collection_detail_url(href):
            collections.append(href)
        elif _is_pagination_url(href) and href != _COLLECTIONS_URL:
            paginations.append(href)
    return recipes, collections, paginations


# ---------------------------------------------------------------------------
# JSON-LD extractor
# ---------------------------------------------------------------------------

def _extract_jsonld_recipe(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Recipe":
                    return item
        elif isinstance(data, dict):
            if data.get("@type") == "Recipe":
                return data
    return None


# ---------------------------------------------------------------------------
# DB persistence
# ---------------------------------------------------------------------------

def _upsert_recipe(data: dict, source_url: str, db: DbSession) -> bool:
    """Insert or touch-update a recipe. Returns True if newly inserted."""
    now = datetime.now(timezone.utc)

    existing = db.query(Recipe).filter(Recipe.source_url == source_url).first()
    if existing:
        existing.last_seen_at = now
        return False

    # Parse ingredients
    raw_ingredients: list[str] = []
    if isinstance(data.get("recipeIngredient"), list):
        raw_ingredients = [str(i).strip() for i in data["recipeIngredient"] if i]

    parsed_ings: list[dict] = []
    normalized_names: list[str] = []
    for idx, raw in enumerate(raw_ingredients):
        qty, unit, name_part = _parse_ingredient(raw)
        norm = _normalize_for_match(name_part)
        normalized_names.append(norm)
        parsed_ings.append({
            "raw_name": name_part[:300],
            "normalized_name": norm[:200],
            "quantity": qty,
            "unit": unit,
            "is_main": idx < 5,
            "optional": "optional" in raw.lower(),
        })

    flags = _derive_flags(normalized_names)

    # Parse instructions — chefkoch uses HowToSection > itemListElement > HowToStep
    steps: list[str] = []
    instructions = data.get("recipeInstructions", [])
    if isinstance(instructions, str):
        steps = [s.strip() for s in instructions.split("\n") if s.strip()]
    elif isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str):
                if item.strip():
                    steps.append(item.strip())
            elif isinstance(item, dict):
                if item.get("@type") == "HowToSection":
                    for step in item.get("itemListElement", []):
                        if isinstance(step, dict):
                            text = step.get("text", "").strip()
                            if text:
                                steps.append(text)
                else:
                    text = item.get("text", "").strip()
                    if text:
                        steps.append(text)

    # Times — chefkoch often puts total in prepTime, cookTime may be None
    cook_min = _parse_duration_min(data.get("cookTime"))
    prep_min = _parse_duration_min(data.get("prepTime"))
    total_min = _parse_duration_min(data.get("totalTime"))
    if total_min is None:
        if cook_min is not None and prep_min is not None:
            total_min = cook_min + prep_min
        elif prep_min is not None:
            total_min = prep_min
        elif cook_min is not None:
            total_min = cook_min

    # Servings
    yield_raw = data.get("recipeYield", "4")
    if isinstance(yield_raw, list):
        yield_raw = yield_raw[0] if yield_raw else "4"
    servings_match = re.search(r"\d+", str(yield_raw))
    base_servings = int(servings_match.group()) if servings_match else 4

    # Rating
    rating = data.get("aggregateRating", {}) or {}
    rating_avg = None
    rating_count = None
    if isinstance(rating, dict):
        try:
            rating_avg = float(rating.get("ratingValue", 0)) or None
            rating_count = int(rating.get("ratingCount", 0)) or None
        except (ValueError, TypeError):
            pass

    # Image
    image = data.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")

    # Source ID from URL slug
    slug_match = re.search(r"/rezepte/(\d+)", source_url)
    source_id = slug_match.group(1) if slug_match else None

    recipe = Recipe(
        source="chefkoch",
        source_url=source_url,
        source_id=source_id,
        name=_clean_name(data.get("name") or "")[:300],
        description=(data.get("description") or "")[:2000] or None,
        cuisine=(data.get("recipeCuisine") or None),
        category=(data.get("recipeCategory") or None),
        cook_time_min=total_min,   # use total as the relevant planning time
        total_time_min=total_min,
        difficulty=None,
        base_servings=base_servings,
        instructions_json=json.dumps(steps, ensure_ascii=False),
        tips_json="[]",
        image_url=str(image)[:500] if image else None,
        rating_avg=rating_avg,
        rating_count=rating_count,
        tags_json="[]",
        meal_type=_classify_meal_type(data.get("recipeCategory"), data.get("name", "")),
        scraped_at=now,
        last_seen_at=now,
        **flags,
    )
    db.add(recipe)
    db.flush()

    for idx, ing in enumerate(parsed_ings):
        db.add(RecipeIngredient(
            recipe_id=recipe.id,
            **ing,
        ))

    return True


# ---------------------------------------------------------------------------
# Search-result URL collector
# ---------------------------------------------------------------------------

_SEARCH_BASE = "https://www.chefkoch.de/rs/s{page}/{category}/Rezepte.html"


async def _collect_search_recipe_urls(
    client: httpx.AsyncClient,
    category: str,
    target: int,
    delay: float,
    seen: set[str],
) -> list[str]:
    """Paginate /rs/s{N}/{category}/Rezepte.html and collect recipe URLs."""
    collected: list[str] = []
    page = 1
    consecutive_empty = 0

    while len(collected) < target:
        url = _SEARCH_BASE.format(page=page, category=category)
        html = await _fetch(client, url, delay * 0.6)
        if not html:
            break

        new_links, _, _ = _extract_links_from_page(html, url)
        added = 0
        for link in new_links:
            if link not in seen:
                seen.add(link)
                collected.append(link)
                added += 1

        if added == 0:
            consecutive_empty += 1
            if consecutive_empty >= 3:
                logger.info("Category '%s': no new recipes on page %d — stopping", category, page)
                break
        else:
            consecutive_empty = 0

        logger.debug("Category '%s' page %d: +%d recipes (total %d)", category, page, added, len(collected))
        page += 1

    logger.info("Category '%s': collected %d recipe URLs across %d pages", category, len(collected), page - 1)
    return collected


# ---------------------------------------------------------------------------
# Shared recipe scraping loop
# ---------------------------------------------------------------------------

async def _scrape_recipe_urls(
    client: httpx.AsyncClient,
    recipe_urls: list[str],
    max_recipes: int,
    delay: float,
    db: DbSession,
) -> tuple[int, int, int]:
    """Fetch + persist each recipe URL. Returns (scraped, skipped, errors)."""
    scraped = skipped = errors = 0
    for url in recipe_urls:
        if scraped >= max_recipes:
            break
        try:
            html = await _fetch(client, url, delay)
            if not html:
                errors += 1
                continue
            ld = _extract_jsonld_recipe(html)
            if not ld:
                skipped += 1
                continue
            inserted = _upsert_recipe(ld, url, db)
            if inserted:
                scraped += 1
                if scraped % 10 == 0:
                    db.commit()
                    logger.info("Progress: %d scraped / %d skipped / %d errors", scraped, skipped, errors)
            else:
                skipped += 1
        except Exception as exc:
            logger.error("Error processing %s: %s", url, exc)
            db.rollback()
            errors += 1
    return scraped, skipped, errors


# ---------------------------------------------------------------------------
# Main scraper — search mode (Mittagessen + Abendessen)
# ---------------------------------------------------------------------------

async def run_scraper(
    max_recipes: int = 500,
    delay: float = 1.2,
    categories: list[str] | None = None,
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    if categories is None:
        categories = ["mittagessen", "abendessen"]

    db: DbSession = SessionLocal()
    total_scraped = total_skipped = total_errors = 0

    try:
        async with httpx.AsyncClient(headers=_HEADERS) as client:
            seen_recipe_urls: set[str] = set()
            all_recipe_urls: list[str] = []

            # Phase 1: collect recipe URLs from all categories
            per_category = max_recipes // len(categories) + 50  # overshoot a bit
            for cat in categories:
                logger.info("Collecting recipe URLs for category: %s", cat)
                urls = await _collect_search_recipe_urls(
                    client, cat, per_category, delay, seen_recipe_urls
                )
                all_recipe_urls.extend(urls)

            logger.info("Total recipe URLs collected: %d", len(all_recipe_urls))

            # Phase 2: scrape each recipe
            scraped, skipped, errors = await _scrape_recipe_urls(
                client, all_recipe_urls, max_recipes, delay, db
            )
            total_scraped += scraped
            total_skipped += skipped
            total_errors += errors

            db.commit()

    finally:
        db.close()

    logger.info(
        "Scrape complete — scraped: %d | skipped/known: %d | errors: %d",
        total_scraped, total_skipped, total_errors,
    )


async def fix_instructions(delay: float = 1.0) -> None:
    """Re-fetch all existing recipes and update their instructions_json."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    db: DbSession = SessionLocal()
    fixed = skipped = errors = 0

    try:
        recipes = db.query(Recipe).all()
        logger.info("Fixing instructions for %d recipes…", len(recipes))

        async with httpx.AsyncClient(headers=_HEADERS) as client:
            for i, recipe in enumerate(recipes):
                try:
                    html = await _fetch(client, recipe.source_url, delay)
                    if not html:
                        errors += 1
                        continue
                    ld = _extract_jsonld_recipe(html)
                    if not ld:
                        skipped += 1
                        continue

                    # Re-parse instructions with the fixed parser
                    steps: list[str] = []
                    instructions = ld.get("recipeInstructions", [])
                    if isinstance(instructions, str):
                        steps = [s.strip() for s in instructions.split("\n") if s.strip()]
                    elif isinstance(instructions, list):
                        for item in instructions:
                            if isinstance(item, str):
                                if item.strip():
                                    steps.append(item.strip())
                            elif isinstance(item, dict):
                                if item.get("@type") == "HowToSection":
                                    for step in item.get("itemListElement", []):
                                        if isinstance(step, dict):
                                            text = step.get("text", "").strip()
                                            if text:
                                                steps.append(text)
                                else:
                                    text = item.get("text", "").strip()
                                    if text:
                                        steps.append(text)

                    recipe.instructions_json = json.dumps(steps, ensure_ascii=False)
                    fixed += 1

                    if fixed % 20 == 0:
                        db.commit()
                        logger.info("Progress: %d fixed / %d skipped / %d errors", fixed, skipped, errors)

                except Exception as exc:
                    logger.error("Error fixing %s: %s", recipe.source_url, exc)
                    db.rollback()
                    errors += 1

        db.commit()
    finally:
        db.close()

    logger.info("Fix complete — fixed: %d | skipped: %d | errors: %d", fixed, skipped, errors)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Chefkoch recipe scraper (Mittagessen + Abendessen)")
    parser.add_argument("--max", type=int, default=500, help="Max new recipes to scrape")
    parser.add_argument("--delay", type=float, default=1.2, help="Base delay between requests (seconds)")
    parser.add_argument(
        "--categories", type=str, default="mittagessen,abendessen",
        help="Comma-separated chefkoch search categories"
    )
    parser.add_argument("--fix-instructions", action="store_true", help="Re-fetch and fix instructions for all existing recipes")
    args = parser.parse_args()

    if args.fix_instructions:
        asyncio.run(fix_instructions(delay=args.delay))
    else:
        cats = [c.strip() for c in args.categories.split(",") if c.strip()]
        asyncio.run(run_scraper(max_recipes=args.max, delay=args.delay, categories=cats))
