"""Auth helpers: password hashing, session cookies, FastAPI dependencies."""

import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from .config import get_settings
from .db import get_db
from .models import Household, UserSession

SESSION_COOKIE = "aristeus_session"
_SESSION_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_session(db: DbSession, household_id: int, user_agent: str | None) -> str:
    token = secrets.token_hex(32)
    expires = datetime.now(timezone.utc) + timedelta(days=_SESSION_EXPIRE_DAYS)
    session = UserSession(
        id=token,
        household_id=household_id,
        expires_at=expires,
        user_agent=user_agent[:300] if user_agent else None,
    )
    db.add(session)
    db.commit()
    return token


def _load_household(session_token: str | None, db: DbSession) -> Household:
    if not session_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")

    sess = db.get(UserSession, session_token)
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sitzung ungültig")

    if sess.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        db.delete(sess)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sitzung abgelaufen")

    return sess.household


def get_current_household(
    aristeus_session: str | None = Cookie(default=None),
    db: DbSession = Depends(get_db),
) -> Household:
    return _load_household(aristeus_session, db)


def get_current_admin(
    household: Household = Depends(get_current_household),
) -> Household:
    if not household.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Nur Admins erlaubt")
    return household


def set_session_cookie(response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=(settings.app_env != "development"),
        samesite="lax",
        max_age=60 * 60 * 24 * _SESSION_EXPIRE_DAYS,
        path="/",
    )
