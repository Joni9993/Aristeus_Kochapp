"""Pydantic v2 I/O schemas."""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,50}$")


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    invite_token: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not _USERNAME_RE.match(v):
            raise ValueError("Nur Buchstaben, Zahlen und _ erlaubt (3–50 Zeichen)")
        return v


class LoginIn(BaseModel):
    username_or_email: str
    password: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordResetConfirmIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)


# ---------------------------------------------------------------------------
# Household / Me
# ---------------------------------------------------------------------------

class HouseholdOut(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    has_profile: bool
    onboarding_complete: bool


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

DietType = Literal["vegetarian", "vegan", "flexitarian", "omnivore"]
MeatType = Literal["chicken", "turkey", "beef", "pork", "fish"]
StoreType = Literal["rewe", "lidl", "aldi", "edeka", "penny", "netto", "kaufland"]


class ProfileIn(BaseModel):
    adults: int = Field(default=2, ge=1, le=20)
    kids: int = Field(default=0, ge=0, le=20)
    diet: DietType = "omnivore"
    allergies: list[str] = Field(default_factory=list)
    allowed_meats: list[MeatType] = Field(
        default_factory=lambda: ["chicken", "turkey", "beef", "pork", "fish"]
    )
    max_cook_time_min: int = Field(default=50, ge=10, le=120)
    preferred_cuisines: list[str] = Field(default_factory=list)
    no_gos: list[str] = Field(default_factory=list)
    budget_sensitivity: int = Field(default=3, ge=1, le=5)
    postal_code: str = Field(default="", max_length=10)
    selected_stores: list[StoreType] = Field(
        default_factory=lambda: ["rewe", "lidl", "aldi", "edeka", "penny", "netto", "kaufland"]
    )
    monday_only_offers: bool = True


class ProfileOut(ProfileIn):
    onboarding_complete: bool
    updated_at: datetime


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class InviteTokenOut(BaseModel):
    token: str
    created_at: datetime
    used_by: int | None
    used_at: datetime | None


class HouseholdAdminOut(BaseModel):
    id: int
    username: str
    email: str
    is_admin: bool
    created_at: datetime
    last_login_at: datetime | None
    has_profile: bool
    onboarding_complete: bool
    api_calls_count: int = 0
    total_tokens: int = 0
