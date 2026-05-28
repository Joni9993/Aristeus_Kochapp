"""Admin-only endpoints: invite tokens, household list."""

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import ApiCall, Household, InviteToken, LearnedPreferences
from ..schemas import HouseholdAdminOut, InviteTokenOut
from ..security import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/households", response_model=list[HouseholdAdminOut])
def list_households(
    _admin: Household = Depends(get_current_admin),
    db: DbSession = Depends(get_db),
) -> list[HouseholdAdminOut]:
    households = db.query(Household).order_by(Household.created_at).all()

    usage_rows = db.execute(
        select(
            ApiCall.household_id,
            func.count(ApiCall.id).label("cnt"),
            func.coalesce(func.sum(ApiCall.input_tokens + ApiCall.output_tokens), 0).label("tokens"),
        )
        .where(ApiCall.household_id.isnot(None))
        .group_by(ApiCall.household_id)
    ).all()
    usage: dict[int, tuple[int, int]] = {row.household_id: (row.cnt, row.tokens) for row in usage_rows}

    return [
        HouseholdAdminOut(
            id=h.id,
            username=h.username,
            email=h.email,
            is_admin=h.is_admin,
            created_at=h.created_at,
            last_login_at=h.last_login_at,
            has_profile=h.profile is not None,
            onboarding_complete=(h.profile is not None and h.profile.onboarding_complete),
            api_calls_count=usage.get(h.id, (0, 0))[0],
            total_tokens=usage.get(h.id, (0, 0))[1],
        )
        for h in households
    ]


@router.get("/households/{household_id}/details")
def household_details(
    household_id: int,
    _admin: Household = Depends(get_current_admin),
    db: DbSession = Depends(get_db),
) -> dict:
    """Return profile settings and learned preferences for one household."""
    h = db.get(Household, household_id)
    if not h:
        raise HTTPException(404, "Haushalt nicht gefunden")

    p = h.profile
    profile_data = None
    if p:
        profile_data = {
            "postal_code": p.postal_code,
            "adults": p.adults,
            "kids": p.kids,
            "diet": p.diet,
            "allergies": json.loads(p.allergies_json),
            "no_gos": json.loads(p.no_gos_json),
            "preferred_cuisines": json.loads(p.preferred_cuisines_json),
            "allowed_meats": json.loads(p.allowed_meats_json),
            "max_cook_time_min": p.max_cook_time_min,
            "selected_stores": json.loads(p.selected_stores_json),
            "budget_sensitivity": p.budget_sensitivity,
        }

    prefs = db.scalar(
        select(LearnedPreferences).where(LearnedPreferences.household_id == household_id)
    )
    prefs_data = None
    if prefs:
        prefs_data = {
            "loved_dishes": json.loads(prefs.loved_dishes_json),
            "disliked_dishes": json.loads(prefs.disliked_dishes_json),
            "portion_adjustments": json.loads(prefs.portion_adjustments_json),
            "recurring_notes": prefs.recurring_notes,
        }

    return {"profile": profile_data, "learned_preferences": prefs_data}


@router.get("/invite-tokens", response_model=list[InviteTokenOut])
def list_invite_tokens(
    admin: Household = Depends(get_current_admin),
    db: DbSession = Depends(get_db),
) -> list[InviteTokenOut]:
    tokens = (
        db.query(InviteToken)
        .filter(InviteToken.created_by == admin.id)
        .order_by(InviteToken.created_at.desc())
        .all()
    )
    return [
        InviteTokenOut(
            token=t.token,
            created_at=t.created_at,
            used_by=t.used_by,
            used_at=t.used_at,
        )
        for t in tokens
    ]


@router.post("/invite-tokens", response_model=InviteTokenOut, status_code=201)
def create_invite_token(
    admin: Household = Depends(get_current_admin),
    db: DbSession = Depends(get_db),
) -> InviteTokenOut:
    token = InviteToken(
        token=secrets.token_hex(24),
        created_by=admin.id,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return InviteTokenOut(
        token=token.token,
        created_at=token.created_at,
        used_by=token.used_by,
        used_at=token.used_at,
    )


@router.delete("/invite-tokens/{token}", status_code=204)
def revoke_invite_token(
    token: str,
    admin: Household = Depends(get_current_admin),
    db: DbSession = Depends(get_db),
) -> None:
    t = db.get(InviteToken, token)
    if t and t.created_by == admin.id and t.used_by is None:
        db.delete(t)
        db.commit()
