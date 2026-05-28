"""Admin-only endpoints: invite tokens, household list."""

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Household, InviteToken
from ..schemas import HouseholdAdminOut, InviteTokenOut
from ..security import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/households", response_model=list[HouseholdAdminOut])
def list_households(
    _admin: Household = Depends(get_current_admin),
    db: DbSession = Depends(get_db),
) -> list[HouseholdAdminOut]:
    households = db.query(Household).order_by(Household.created_at).all()
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
        )
        for h in households
    ]


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
