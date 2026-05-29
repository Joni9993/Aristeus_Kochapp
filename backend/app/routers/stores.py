"""Stores + freshness endpoints."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Brochure, Household
from ..security import get_current_household
from ..services.kaufda import refresh_plz

router = APIRouter(prefix="/api/stores", tags=["stores"])

_ALL_STORES = ["rewe", "lidl", "aldi", "edeka", "penny", "netto", "kaufland"]
_STORE_LABELS = {
    "rewe": "Rewe", "lidl": "Lidl", "aldi": "Aldi", "edeka": "Edeka",
    "penny": "Penny", "netto": "Netto", "kaufland": "Kaufland",
}


@router.get("/freshness")
def get_freshness(
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Return per-store freshness info for the current household's PLZ."""
    profile = household.profile
    if not profile or not profile.postal_code:
        raise HTTPException(400, "Profil oder PLZ fehlt")

    plz = profile.postal_code
    selected = json.loads(profile.selected_stores_json)
    result: dict[str, dict] = {}

    for store in selected:
        # Find newest active brochure for this store+plz
        brochure = db.scalar(
            select(Brochure)
            .where(Brochure.store == store, Brochure.postal_code == plz)
            .order_by(Brochure.fetched_at.desc())
            .limit(1)
        )
        if not brochure:
            result[store] = {
                "label": _STORE_LABELS.get(store, store),
                "status": "not_fetched",
                "offer_count": 0,
                "fetched_at": None,
                "valid_from": None,
                "valid_to": None,
            }
            continue

        now = datetime.now(timezone.utc)
        fetched_at = brochure.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        age_hours = (now - fetched_at).total_seconds() / 3600
        status = "fresh" if age_hours < 30 else ("stale" if age_hours < 168 else "outdated")
        if brochure.status == "stale":
            status = "stale"

        result[store] = {
            "label": _STORE_LABELS.get(store, store),
            "status": status,
            "offer_count": len(brochure.offers),
            "cooking_relevant_count": sum(1 for o in brochure.offers if o.is_cooking_relevant),
            "fetched_at": fetched_at.isoformat(),
            "valid_from": brochure.valid_from,
            "valid_to": brochure.valid_to,
        }

    return {"plz": plz, "stores": result}


@router.post("/refresh")
async def trigger_refresh(
    background_tasks: BackgroundTasks,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Manually trigger a Kaufda refresh for the current household's PLZ."""
    profile = household.profile
    if not profile or not profile.postal_code:
        raise HTTPException(400, "Profil oder PLZ fehlt")

    plz = profile.postal_code
    stores = json.loads(profile.selected_stores_json)

    # Run in background so the response returns immediately
    background_tasks.add_task(_bg_refresh, plz, stores)
    return {"ok": True, "message": f"Refresh für PLZ {plz} gestartet"}


@router.get("/{store_id}/offers")
def get_store_offers(
    store_id: str,
    cooking_only: bool = True,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    """Return offers for a specific store for the current household's PLZ."""
    profile = household.profile
    if not profile or not profile.postal_code:
        raise HTTPException(400, "Profil oder PLZ fehlt")

    plz = profile.postal_code
    brochure = db.scalar(
        select(Brochure)
        .where(Brochure.store == store_id, Brochure.postal_code == plz)
        .order_by(Brochure.fetched_at.desc())
        .limit(1)
    )
    if not brochure:
        raise HTTPException(404, "Keine Angebote gefunden")

    offers = [o for o in brochure.offers if (not cooking_only or o.is_cooking_relevant)]
    # Sort by category, then product name
    offers.sort(key=lambda o: (o.category or "", o.product_name))

    return {
        "store": store_id,
        "label": _STORE_LABELS.get(store_id, store_id),
        "brochure_url": brochure.web_url or "https://www.kaufda.de/",
        "valid_from": brochure.valid_from,
        "valid_to": brochure.valid_to,
        "total_count": len(brochure.offers),
        "cooking_relevant_count": sum(1 for o in brochure.offers if o.is_cooking_relevant),
        "offers": [
            {
                "id": o.id,
                "product_name": o.product_name,
                "price_text": o.price_text,
                "quantity_text": o.quantity_text,
                "base_price": o.base_price,
                "hint": o.hint,
                "category": o.category,
                "is_cooking_relevant": o.is_cooking_relevant,
            }
            for o in offers
        ],
    }


async def _bg_refresh(plz: str, stores: list[str]) -> None:
    db = DbSession.__new__(DbSession)  # will be created properly below
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        await refresh_plz(plz, stores, db)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Background refresh failed: %s", exc)
    finally:
        db.close()
