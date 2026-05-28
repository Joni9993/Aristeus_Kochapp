"""SQLAlchemy 2.0 ORM models."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Household(Base):
    __tablename__ = "households"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(72), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["Profile | None"] = relationship(
        "Profile", back_populates="household", uselist=False, cascade="all, delete-orphan"
    )
    user_sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession",
        foreign_keys="UserSession.household_id",
        back_populates="household",
        cascade="all, delete-orphan",
    )


class Profile(Base):
    __tablename__ = "profiles"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), primary_key=True
    )
    adults: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    kids: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # vegetarian | vegan | flexitarian | omnivore
    diet: Mapped[str] = mapped_column(String(20), default="omnivore", nullable=False)
    allergies_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    allowed_meats_json: Mapped[str] = mapped_column(
        Text, default='["chicken","turkey","beef","pork","fish"]', nullable=False
    )
    max_cook_time_min: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    preferred_cuisines_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    no_gos_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # 1 = günstig egal, 5 = max. Angebotsnutzung
    budget_sensitivity: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    postal_code: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    selected_stores_json: Mapped[str] = mapped_column(
        Text,
        default='["rewe","lidl","aldi","edeka","penny","netto","kaufland"]',
        nullable=False,
    )
    # True = nur Angebote, die ab Montag gelten (für einmaliges Einkaufen)
    monday_only_offers: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    household: Mapped["Household"] = relationship("Household", back_populates="profile")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)

    household: Mapped["Household"] = relationship(
        "Household", foreign_keys=[household_id], back_populates="user_sessions"
    )


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    used_by: Mapped[int | None] = mapped_column(
        ForeignKey("households.id", ondelete="SET NULL"), nullable=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PasswordReset(Base):
    __tablename__ = "password_resets"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Brochure(Base):
    __tablename__ = "brochures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    postal_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    brochure_id_kaufda: Mapped[str] = mapped_column(String(200), nullable=False)
    retailer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valid_from: Mapped[str | None] = mapped_column(String(20), nullable=True)   # ISO date string
    valid_to: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # active | stale | error
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    offers: Mapped[list["Offer"]] = relationship(
        "Offer", back_populates="brochure", cascade="all, delete-orphan"
    )


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brochure_id: Mapped[int] = mapped_column(
        ForeignKey("brochures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_name: Mapped[str] = mapped_column(String(300), nullable=False)
    price_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    quantity_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_price: Mapped[str | None] = mapped_column(String(80), nullable=True)
    hint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    store: Mapped[str] = mapped_column(String(20), nullable=False)
    # "live ab Mo. 11.5." — ISO date when the offer becomes valid
    live_from_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    category: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_cooking_relevant: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    brochure: Mapped["Brochure"] = relationship("Brochure", back_populates="offers")


class HealthPing(Base):
    """Kept from Phase 0."""

    __tablename__ = "health_pings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
