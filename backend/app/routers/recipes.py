"""Recipes router — "Unser Kochbuch".

The cookbook is a plain read of saved_recipes — every entry has an `origin`:
  - "gekocht": archived from a confirmed PlanDish by archive_recipes_to_cookbook
    (see ../ai/pipeline.py), called at the end of confirm/swap/regenerate and
    plan-into-week. Surviving in its own table means deleting the plan that
    originally produced the recipe no longer removes it from the cookbook.
  - "eigene": a household's own SavedRecipe entries — imported from a URL or
    entered by hand.

GET /api/recipes best-effort-enriches "gekocht" entries with the newest
confirmed PlanDish of the same name (dish_id/plan_id/feedback_thumbs) so the
frontend can still show the thumbs-up/down row; if that plan was since
deleted these stay null and the frontend just hides the row.

Also hosts the URL-import / manual-entry / favorite / delete endpoints for
SavedRecipe (favorite + delete now apply to every entry, not just "eigene"),
and "plan-into-week" which drops any recipe (gekocht or eigene) into the
current or next weekly plan.
"""

import ipaddress
import json
import logging
import re
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..ai.client import chat_completion_json
from ..ai.pipeline import (
    _all_confirmed_recipes,
    archive_recipes_to_cookbook,
    build_shopping_list,
    rebuild_shopping_list_preserving,
)
from ..ai.prompts import build_recipe_import_from_text_prompt, build_recipe_import_ingredients_prompt
from ..ai.schemas import ImportedRecipeResponse, ImportIngredientsResponse, RecipeResponse
from ..db import get_db
from ..models import Household, PlanDish, SavedRecipe, WeeklyPlan
from ..security import get_current_household

router = APIRouter(prefix="/api/recipes", tags=["recipes"])
logger = logging.getLogger(__name__)

_IMPORT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-testable without a DB session)
# ---------------------------------------------------------------------------

def filter_saved(
    saved: list[SavedRecipe], *, q: str | None = None, favorites_only: bool = False
) -> list[SavedRecipe]:
    result = saved
    if q:
        q_lower = q.strip().lower()
        result = [s for s in result if q_lower in s.name.lower()]
    if favorites_only:
        result = [s for s in result if s.is_favorite]
    return result


def _saved_out(saved: SavedRecipe, dish: PlanDish | None = None) -> dict:
    """`dish`, when given, is the newest confirmed PlanDish with the same
    (case-insensitive) name — best-effort enrichment for "gekocht" entries so
    the frontend can show/patch the thumbs-up/down feedback row. None for
    "eigene" entries or once the originating plan has been deleted."""
    recipe = None
    if saved.recipe_json:
        try:
            recipe = json.loads(saved.recipe_json)
        except Exception:
            pass
    return {
        "source": saved.origin,
        "dish_id": dish.id if dish else None,
        "plan_id": dish.plan_id if dish else None,
        "saved_recipe_id": saved.id,
        "name": saved.name,
        "cuisine": saved.cuisine,
        "cook_time_min": saved.cook_time_min,
        "is_favorite": saved.is_favorite,
        "feedback_thumbs": dish.feedback_thumbs if dish else None,
        "image_url": saved.image_url,
        "week_start_date": dish.plan.week_start_date if dish and dish.plan else None,
        "recipe": recipe,
    }


# ---------------------------------------------------------------------------
# GET /api/recipes — saved_recipes only (origin "gekocht" | "eigene")
# ---------------------------------------------------------------------------

@router.get("")
def list_recipes(
    q: str | None = None,
    favorites_only: bool = False,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> list[dict]:
    saved = db.scalars(
        select(SavedRecipe)
        .where(SavedRecipe.household_id == household.id)
        .order_by(SavedRecipe.created_at.desc())
    ).all()
    filtered = filter_saved(saved, q=q, favorites_only=favorites_only)
    ordered = sorted(filtered, key=lambda s: (0 if s.is_favorite else 1, s.name.strip().lower()))

    # Newest confirmed PlanDish per case-insensitive name — drives the thumbs
    # row for "gekocht" entries. Fetched once for the whole household rather
    # than per-entry.
    dish_by_name: dict[str, PlanDish] = {}
    if any(s.origin == "gekocht" for s in ordered):
        dishes = db.scalars(
            select(PlanDish)
            .join(WeeklyPlan, PlanDish.plan_id == WeeklyPlan.id)
            .where(
                WeeklyPlan.household_id == household.id,
                PlanDish.dish_status == "confirmed",
            )
            .order_by(WeeklyPlan.week_start_date.desc(), PlanDish.id.desc())
        ).all()
        for d in dishes:
            key = d.name.strip().lower()
            if key not in dish_by_name:
                dish_by_name[key] = d

    return [_saved_out(s, dish_by_name.get(s.name.strip().lower())) for s in ordered]


# ---------------------------------------------------------------------------
# URL import
# ---------------------------------------------------------------------------

class ImportRecipeRequest(BaseModel):
    url: str


def _validate_import_url(url: str) -> None:
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(400, "Ungültige URL") from None

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "Nur http/https-URLs sind erlaubt")

    host = parsed.hostname
    if not host:
        raise HTTPException(400, "Ungültige URL")
    if host.lower() in ("localhost", "0.0.0.0"):
        raise HTTPException(400, "Diese Adresse ist nicht erlaubt")

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        raise HTTPException(400, "Host konnte nicht aufgelöst werden") from None

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "Diese Adresse ist nicht erlaubt")


async def _fetch_page(url: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _IMPORT_USER_AGENT})
            resp.raise_for_status()
            return resp.text
    except Exception as exc:
        logger.warning("Recipe import fetch failed for %s: %s", url, exc)
        return None


def _extract_jsonld_recipe(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            # Some sites wrap the Recipe in a @graph array
            if item.get("@type") == "Recipe":
                return item
            for node in item.get("@graph", []) or []:
                if isinstance(node, dict) and node.get("@type") == "Recipe":
                    return node
    return None


def _extract_jsonld_steps(instructions) -> list[str]:
    steps: list[str] = []
    if isinstance(instructions, str):
        steps = [s.strip() for s in instructions.split("\n") if s.strip()]
    elif isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str):
                if item.strip():
                    steps.append(item.strip())
            elif isinstance(item, dict):
                if item.get("@type") == "HowToSection":
                    for step in item.get("itemListElement", []) or []:
                        if isinstance(step, dict):
                            text = (step.get("text") or "").strip()
                            if text:
                                steps.append(text)
                else:
                    text = (item.get("text") or "").strip()
                    if text:
                        steps.append(text)
    return steps


def _parse_iso_duration(iso: str | None) -> int | None:
    """Parse ISO 8601 durations: PT30M, PT1H30M, P0DT0H30M, P1DT2H30M."""
    if not iso:
        return None
    hours = int(m.group(1)) if (m := re.search(r"(\d+)H", iso)) else 0
    minutes = int(m.group(1)) if (m := re.search(r"(\d+)M", iso)) else 0
    days = int(m.group(1)) if (m := re.search(r"(\d+)D", iso)) else 0
    total = days * 24 * 60 + hours * 60 + minutes
    return total if total > 0 else None


async def _structure_ingredients(raw_ingredients: list[str]) -> list[dict]:
    """LLM call: raw ingredient lines -> structured zutaten list. Falls back to
    name-only entries (no menge/einheit) if the call or parse fails."""
    fallback = [
        {"name": r, "menge": None, "einheit": None, "ist_angebot": False, "laden": None}
        for r in raw_ingredients
    ]
    if not raw_ingredients:
        return []
    try:
        messages = build_recipe_import_ingredients_prompt(raw_ingredients=raw_ingredients)
        raw, _model, _usage = await chat_completion_json(messages, purpose="recipe_import", max_tokens=3000)
        parsed = ImportIngredientsResponse.model_validate(raw)
    except Exception as exc:
        logger.warning("Ingredient structuring failed: %s", exc)
        return fallback
    if not parsed.zutaten:
        return fallback
    return [
        {"name": z.name, "menge": z.menge, "einheit": z.einheit, "ist_angebot": False, "laden": None}
        for z in parsed.zutaten
    ]


async def _recipe_from_jsonld(data: dict) -> tuple[dict, str, str | None, int | None, str | None]:
    """Returns (recipe_dict, name, cuisine, cook_time_min, image_url)."""
    name = (data.get("name") or "").strip()[:300] or "Importiertes Rezept"

    raw_ingredients = [str(i).strip() for i in (data.get("recipeIngredient") or []) if str(i).strip()]
    steps = _extract_jsonld_steps(data.get("recipeInstructions"))

    cook_min = _parse_iso_duration(data.get("cookTime"))
    prep_min = _parse_iso_duration(data.get("prepTime"))
    total_min = _parse_iso_duration(data.get("totalTime"))
    if total_min is None:
        summed = (cook_min or 0) + (prep_min or 0)
        total_min = summed or None

    cuisine = data.get("recipeCuisine")
    if isinstance(cuisine, list):
        cuisine = cuisine[0] if cuisine else None
    cuisine = str(cuisine)[:100] if cuisine else None

    image = data.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    image_url = str(image)[:500] if image else None

    zutaten = await _structure_ingredients(raw_ingredients)
    recipe = {
        "zutaten": zutaten,
        "schritte": steps or ["Keine Zubereitungsschritte gefunden — bitte manuell ergänzen."],
        "geschaetzte_zeit_min": total_min or 30,
        "tipps": [],
    }
    return recipe, name, cuisine, total_min, image_url


def _extract_page_text(html: str) -> tuple[str, str | None, str | None]:
    """Returns (visible_text_capped_8000, og_title, og_image)."""
    soup = BeautifulSoup(html, "html.parser")
    og_title: str | None = None
    og_image: str | None = None
    og_desc: str | None = None
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if not content:
            continue
        if prop == "og:title":
            og_title = content
        elif prop == "og:image":
            og_image = content
        elif prop == "og:description":
            og_desc = content

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    body_text = soup.get_text(separator=" ", strip=True)

    parts = [p for p in (og_title, og_desc, body_text) if p]
    text = re.sub(r"\s+", " ", " ".join(parts)).strip()[:8000]
    return text, og_title, og_image


async def _recipe_from_page_text(
    html: str, url: str
) -> tuple[dict, str, str | None, int | None, str | None] | None:
    """Fallback path for pages without JSON-LD (Instagram/Pinterest/blogs).
    Returns None if the LLM found no recipe on the page."""
    text, og_title, og_image = _extract_page_text(html)
    if not text:
        return None

    try:
        messages = build_recipe_import_from_text_prompt(page_text=text, url=url)
        raw, _model, _usage = await chat_completion_json(messages, purpose="recipe_import", max_tokens=4000)
        parsed = ImportedRecipeResponse.model_validate(raw)
    except Exception as exc:
        logger.warning("Recipe extraction from page text failed for %s: %s", url, exc)
        return None

    if not parsed.erkannt or not parsed.schritte:
        return None

    name = (parsed.name or og_title or "Importiertes Rezept").strip()[:300]
    zutaten = [
        {"name": z.name, "menge": z.menge, "einheit": z.einheit, "ist_angebot": False, "laden": None}
        for z in parsed.zutaten
    ]
    recipe = {
        "zutaten": zutaten,
        "schritte": parsed.schritte,
        "geschaetzte_zeit_min": parsed.geschaetzte_zeit_min or 30,
        "tipps": parsed.tipps,
    }
    image_url = str(og_image)[:500] if og_image else None
    return recipe, name, parsed.kategorie, parsed.geschaetzte_zeit_min, image_url


@router.post("/import", status_code=201)
async def import_recipe(
    body: ImportRecipeRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    url = body.url.strip()
    if not url:
        raise HTTPException(400, "URL fehlt")
    _validate_import_url(url)

    html = await _fetch_page(url)
    if html is None:
        raise HTTPException(422, "Seite konnte nicht geladen werden.")

    jsonld = _extract_jsonld_recipe(html)
    if jsonld:
        recipe_data, name, cuisine, cook_time, image_url = await _recipe_from_jsonld(jsonld)
    else:
        result = await _recipe_from_page_text(html, url)
        if result is None:
            raise HTTPException(
                422, "Konnte kein Rezept auf der Seite erkennen — bitte manuell eintragen."
            )
        recipe_data, name, cuisine, cook_time, image_url = result

    if not image_url:
        try:
            from ..services.dish_images import find_dish_image
            image_url = await find_dish_image(name, cuisine)
        except Exception:
            image_url = None

    saved = SavedRecipe(
        household_id=household.id,
        name=name,
        cuisine=cuisine,
        cook_time_min=cook_time,
        image_url=image_url,
        recipe_json=json.dumps(recipe_data, ensure_ascii=False),
        source_url=url[:1000],
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return _saved_out(saved)


# ---------------------------------------------------------------------------
# Manual entry
# ---------------------------------------------------------------------------

class ManualIngredient(BaseModel):
    name: str
    menge: float | None = None
    einheit: str | None = None


class ManualRecipeRequest(BaseModel):
    name: str
    cuisine: str | None = None
    cook_time_min: int | None = None
    zutaten: list[ManualIngredient]
    schritte: list[str]
    tipps: list[str] | None = None


@router.post("/manual", status_code=201)
async def create_manual_recipe(
    body: ManualRecipeRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name fehlt")
    schritte = [s.strip() for s in body.schritte if s.strip()]
    if not schritte:
        raise HTTPException(400, "Mindestens ein Zubereitungsschritt nötig")

    zutaten = [
        {
            "name": z.name.strip(),
            "menge": z.menge,
            "einheit": z.einheit,
            "ist_angebot": False,
            "laden": None,
        }
        for z in body.zutaten
        if z.name.strip()
    ]

    recipe_data = {
        "zutaten": zutaten,
        "schritte": schritte,
        "geschaetzte_zeit_min": body.cook_time_min or 30,
        "tipps": [t.strip() for t in (body.tipps or []) if t.strip()],
    }

    image_url = None
    try:
        from ..services.dish_images import find_dish_image
        image_url = await find_dish_image(name, body.cuisine)
    except Exception:
        image_url = None

    saved = SavedRecipe(
        household_id=household.id,
        name=name[:300],
        cuisine=body.cuisine,
        cook_time_min=body.cook_time_min,
        image_url=image_url,
        recipe_json=json.dumps(recipe_data, ensure_ascii=False),
        source_url=None,
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return _saved_out(saved)


# ---------------------------------------------------------------------------
# Saved recipe favorite / delete
# ---------------------------------------------------------------------------

class SavedRecipePatchRequest(BaseModel):
    is_favorite: bool


def _get_saved_or_404(saved_id: int, household_id: int, db: DbSession) -> SavedRecipe:
    saved = db.get(SavedRecipe, saved_id)
    if not saved or saved.household_id != household_id:
        raise HTTPException(404, "Rezept nicht gefunden")
    return saved


@router.patch("/saved/{saved_id}")
def update_saved_recipe(
    saved_id: int,
    body: SavedRecipePatchRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    saved = _get_saved_or_404(saved_id, household.id, db)
    saved.is_favorite = body.is_favorite
    db.commit()
    return _saved_out(saved)


@router.delete("/saved/{saved_id}", status_code=204)
def delete_saved_recipe(
    saved_id: int,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> None:
    saved = _get_saved_or_404(saved_id, household.id, db)
    db.delete(saved)
    db.commit()


# ---------------------------------------------------------------------------
# Plan into week
# ---------------------------------------------------------------------------

class PlanIntoWeekRequest(BaseModel):
    dish_id: int | None = None
    saved_recipe_id: int | None = None
    week: str  # "current" | "next"
    cook_day: str | None = None


@router.post("/plan-into-week")
def plan_into_week(
    body: PlanIntoWeekRequest,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    from ..services.scheduler import _next_monday, _this_monday

    if not body.dish_id and not body.saved_recipe_id:
        raise HTTPException(400, "dish_id oder saved_recipe_id erforderlich")
    if body.week not in ("current", "next"):
        raise HTTPException(400, "week muss 'current' oder 'next' sein")

    if body.saved_recipe_id:
        source = _get_saved_or_404(body.saved_recipe_id, household.id, db)
        name, cuisine, cook_time = source.name, source.cuisine, source.cook_time_min
        image_url, recipe_json = source.image_url, source.recipe_json
    else:
        source_dish = db.get(PlanDish, body.dish_id)
        if not source_dish or not source_dish.recipe_json:
            raise HTTPException(404, "Rezept nicht gefunden")
        if not source_dish.plan or source_dish.plan.household_id != household.id:
            raise HTTPException(404, "Rezept nicht gefunden")
        name, cuisine, cook_time = source_dish.name, source_dish.cuisine, source_dish.cook_time_min
        image_url = source_dish.image_url or (source_dish.recipe.image_url if source_dish.recipe else None)
        recipe_json = source_dish.recipe_json

    try:
        recipe_obj = RecipeResponse.model_validate_json(recipe_json)
    except Exception:
        raise HTTPException(422, "Rezeptdaten sind beschädigt") from None

    week_start = _this_monday() if body.week == "current" else _next_monday()

    target = db.scalar(
        select(WeeklyPlan)
        .where(WeeklyPlan.household_id == household.id, WeeklyPlan.week_start_date == week_start)
        .order_by(WeeklyPlan.id.desc())
    )

    if target and target.status == "confirming":
        raise HTTPException(409, "Plan wird gerade aktualisiert — kurz warten.")

    if target and target.status in ("confirmed", "complete"):
        new_dish = PlanDish(
            plan_id=target.id,
            name=name,
            cuisine=cuisine,
            cook_time_min=cook_time,
            cook_day=body.cook_day,
            dish_status="confirmed",
            used_offer_ids_json="[]",
            recipe_json=recipe_json,
            image_url=image_url,
        )
        db.add(new_dish)
        db.flush()

        all_recipes = _all_confirmed_recipes(target, {new_dish.id: recipe_obj})
        rebuild_shopping_list_preserving(target, all_recipes, household, db)

        target.status = "confirmed"
        archive_recipes_to_cookbook(target, db)
        db.commit()
        return {
            "plan_id": target.id,
            "message": f"'{name}' wurde in den Plan für die Woche ab {week_start} eingeplant.",
        }

    if target and target.status in ("suggestions_ready", "pending"):
        new_dish = PlanDish(
            plan_id=target.id,
            name=name,
            cuisine=cuisine,
            cook_time_min=cook_time,
            cook_day=body.cook_day,
            dish_status="suggestion",
            used_offer_ids_json="[]",
            recipe_json=recipe_json,
            image_url=image_url,
        )
        db.add(new_dish)
        db.commit()
        return {
            "plan_id": target.id,
            "message": (
                f"'{name}' wurde als Vorschlag zum Plan für die Woche ab {week_start} hinzugefügt — "
                "wähle ihn dort noch aus."
            ),
        }

    # No usable plan for that week yet — create a fresh confirmed one with just this dish.
    new_plan = WeeklyPlan(
        household_id=household.id,
        week_start_date=week_start,
        status="confirmed",
    )
    db.add(new_plan)
    db.flush()

    new_dish = PlanDish(
        plan_id=new_plan.id,
        name=name,
        cuisine=cuisine,
        cook_time_min=cook_time,
        cook_day=body.cook_day,
        dish_status="confirmed",
        used_offer_ids_json="[]",
        recipe_json=recipe_json,
        image_url=image_url,
    )
    db.add(new_dish)
    db.flush()

    build_shopping_list(new_plan, {new_dish.id: recipe_obj}, household, db)
    archive_recipes_to_cookbook(new_plan, db)
    db.commit()
    return {
        "plan_id": new_plan.id,
        "message": f"Neuer Plan für die Woche ab {week_start} mit '{name}' erstellt.",
    }
