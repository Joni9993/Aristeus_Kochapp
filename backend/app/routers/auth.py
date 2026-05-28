"""Auth endpoints: register, login, logout, password-reset."""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.orm import Session as DbSession

from ..db import get_db
from ..models import Household, InviteToken, PasswordReset, UserSession
from ..schemas import (
    LoginIn,
    PasswordChangeIn,
    PasswordResetConfirmIn,
    PasswordResetRequestIn,
    RegisterIn,
)
from ..security import (
    SESSION_COOKIE,
    create_session,
    get_current_household,
    hash_password,
    set_session_cookie,
    verify_password,
)
from ..services.email import send_password_reset_email

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=201)
def register(data: RegisterIn, db: DbSession = Depends(get_db)) -> dict:
    invite = db.get(InviteToken, data.invite_token)
    if not invite or invite.used_by is not None:
        raise HTTPException(400, "Ungültiger oder bereits verwendeter Einladungs-Token")

    exists = db.query(Household).filter(
        or_(Household.username == data.username, Household.email == str(data.email))
    ).first()
    if exists:
        raise HTTPException(400, "Benutzername oder E-Mail bereits vergeben")

    household = Household(
        username=data.username,
        email=str(data.email),
        password_hash=hash_password(data.password),
    )
    db.add(household)
    db.flush()

    invite.used_by = household.id
    invite.used_at = datetime.now(timezone.utc)
    db.commit()

    return {"ok": True, "message": "Konto erstellt – bitte anmelden"}


@router.post("/login")
def login(
    data: LoginIn,
    response: Response,
    request: Request,
    db: DbSession = Depends(get_db),
) -> dict:
    household = db.query(Household).filter(
        or_(
            Household.username == data.username_or_email,
            Household.email == data.username_or_email,
        )
    ).first()

    if not household or not verify_password(data.password, household.password_hash):
        raise HTTPException(401, "Benutzername oder Passwort falsch")

    token = create_session(db, household.id, request.headers.get("user-agent"))
    household.last_login_at = datetime.now(timezone.utc)
    db.commit()

    set_session_cookie(response, token)
    return {
        "ok": True,
        "onboarding_complete": household.profile is not None and household.profile.onboarding_complete,
    }


@router.post("/logout")
def logout(
    response: Response,
    aristeus_session: str | None = Cookie(default=None),
    _household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    if aristeus_session:
        sess = db.get(UserSession, aristeus_session)
        if sess:
            db.delete(sess)
            db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.post("/password-reset/request")
def password_reset_request(
    data: PasswordResetRequestIn, db: DbSession = Depends(get_db)
) -> dict:
    household = db.query(Household).filter(Household.email == str(data.email)).first()
    if household:
        token = secrets.token_hex(32)
        reset = PasswordReset(
            token=token,
            household_id=household.id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        db.add(reset)
        db.commit()
        send_password_reset_email(household.email, household.username, token)
    # Always return ok – don't leak whether the email is registered
    return {"ok": True, "message": "Falls die E-Mail bekannt ist, wurde ein Link gesendet"}


@router.post("/password-reset/confirm")
def password_reset_confirm(
    data: PasswordResetConfirmIn, db: DbSession = Depends(get_db)
) -> dict:
    reset = db.get(PasswordReset, data.token)
    if (
        not reset
        or reset.used
        or reset.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
    ):
        raise HTTPException(400, "Ungültiger oder abgelaufener Token")

    household = db.get(Household, reset.household_id)
    if not household:
        raise HTTPException(400, "Konto nicht gefunden")

    household.password_hash = hash_password(data.new_password)
    reset.used = True
    db.commit()
    return {"ok": True, "message": "Passwort erfolgreich geändert"}


@router.put("/password")
def change_password(
    data: PasswordChangeIn,
    household: Household = Depends(get_current_household),
    db: DbSession = Depends(get_db),
) -> dict:
    if not verify_password(data.current_password, household.password_hash):
        raise HTTPException(400, "Aktuelles Passwort falsch")
    household.password_hash = hash_password(data.new_password)
    db.commit()
    return {"ok": True}
