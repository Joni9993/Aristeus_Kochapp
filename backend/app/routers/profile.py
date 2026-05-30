"""Profile + /me endpoints."""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Household, LearnedPreferences, Profile, WeeklyPlan
from ..schemas import HouseholdOut, ProfileIn, ProfileOut
from ..security import SESSION_COOKIE, get_current_household

router = APIRouter(prefix="/api", tags=["profile"])


@router.get("/me", response_model=HouseholdOut)
def get_me(household: Household = Depends(get_current_household)) -> HouseholdOut:
    return HouseholdOut(
        id=household.id,
        username=household.username,
        email=household.email,
        is_admin=household.is_admin,
        has_profile=household.profile is not None,
        onboarding_complete=(
            household.profile is not None and household.profile.onboarding_complete
        ),
    )


@router.get("/me/profile", response_model=ProfileOut)
def get_profile(household: Household = Depends(get_current_household)) -> ProfileOut:
    p = household.profile
    if not p:
        raise HTTPException(404, "Profil noch nicht angelegt")
    return _profile_to_out(p)


@router.put("/me/profile", response_model=ProfileOut)
def upsert_profile(
    data: ProfileIn,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> ProfileOut:
    p = household.profile
    if not p:
        p = Profile(household_id=household.id)
        db.add(p)

    p.adults = data.adults
    p.kids = data.kids
    p.diet = data.diet
    p.allergies_json = json.dumps(data.allergies, ensure_ascii=False)
    p.allowed_meats_json = json.dumps(data.allowed_meats, ensure_ascii=False)
    p.max_cook_time_min = data.max_cook_time_min
    p.preferred_cuisines_json = json.dumps(data.preferred_cuisines, ensure_ascii=False)
    p.no_gos_json = json.dumps(data.no_gos, ensure_ascii=False)
    p.budget_sensitivity = data.budget_sensitivity
    p.postal_code = data.postal_code
    p.selected_stores_json = json.dumps(data.selected_stores, ensure_ascii=False)
    p.monday_only_offers = data.monday_only_offers
    p.include_desserts = data.include_desserts
    p.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(p)
    return _profile_to_out(p)


@router.post("/me/onboarding/complete")
def complete_onboarding(
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    p = household.profile
    if not p:
        raise HTTPException(400, "Profil muss zuerst angelegt werden")
    p.onboarding_complete = True
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.get("/me/export")
def export_data(
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> Response:
    """Download all personal data as a JSON file."""
    p = household.profile
    prefs = db.scalar(
        select(LearnedPreferences).where(LearnedPreferences.household_id == household.id)
    )
    plans = db.scalars(
        select(WeeklyPlan).where(WeeklyPlan.household_id == household.id)
    ).all()

    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "household": {
            "username": household.username,
            "email": household.email,
            "created_at": household.created_at.isoformat(),
        },
        "profile": (
            {
                "adults": p.adults, "kids": p.kids, "diet": p.diet,
                "allergies": json.loads(p.allergies_json),
                "allowed_meats": json.loads(p.allowed_meats_json),
                "max_cook_time_min": p.max_cook_time_min,
                "preferred_cuisines": json.loads(p.preferred_cuisines_json),
                "no_gos": json.loads(p.no_gos_json),
                "budget_sensitivity": p.budget_sensitivity,
                "postal_code": p.postal_code,
                "selected_stores": json.loads(p.selected_stores_json),
            }
            if p else None
        ),
        "learned_preferences": (
            {
                "loved_dishes": json.loads(prefs.loved_dishes_json),
                "disliked_dishes": json.loads(prefs.disliked_dishes_json),
                "portion_adjustments": json.loads(prefs.portion_adjustments_json),
                "recurring_notes": prefs.recurring_notes,
            }
            if prefs else None
        ),
        "plans": [
            {
                "week_start_date": plan.week_start_date,
                "status": plan.status,
                "created_at": plan.created_at.isoformat(),
                "dishes": [
                    {
                        "name": d.name,
                        "cook_day": d.cook_day,
                        "dish_status": d.dish_status,
                        "is_favorite": d.is_favorite,
                        "feedback_thumbs": d.feedback_thumbs,
                        "feedback_portion_note": d.feedback_portion_note,
                        "feedback_free_text": d.feedback_free_text,
                    }
                    for d in plan.dishes
                ],
            }
            for plan in plans
        ],
    }

    content = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"aristeus-export-{household.username}.json"
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/me", status_code=204)
def delete_account(
    response: Response,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> None:
    """Permanently delete the account and all associated data."""
    db.delete(household)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


def _profile_to_out(p: Profile) -> ProfileOut:
    return ProfileOut(
        adults=p.adults,
        kids=p.kids,
        diet=p.diet,  # type: ignore[arg-type]
        allergies=json.loads(p.allergies_json),
        allowed_meats=json.loads(p.allowed_meats_json),
        max_cook_time_min=p.max_cook_time_min,
        preferred_cuisines=json.loads(p.preferred_cuisines_json),
        no_gos=json.loads(p.no_gos_json),
        budget_sensitivity=p.budget_sensitivity,
        postal_code=p.postal_code,
        selected_stores=json.loads(p.selected_stores_json),
        monday_only_offers=p.monday_only_offers,
        include_desserts=p.include_desserts,
        onboarding_complete=p.onboarding_complete,
        updated_at=p.updated_at,
    )
