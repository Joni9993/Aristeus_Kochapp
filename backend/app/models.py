"""SQLAlchemy 2.0 ORM models."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
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
    include_desserts: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
    web_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

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


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    # pending | suggestions_ready | confirmed | complete
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    wish_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional one-off headcount for this week only (guests etc.); NULL = use profile
    portion_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    household: Mapped["Household"] = relationship("Household")
    dishes: Mapped[list["PlanDish"]] = relationship(
        "PlanDish", back_populates="plan", cascade="all, delete-orphan"
    )
    shopping_items: Mapped[list["ShoppingItem"]] = relationship(
        "ShoppingItem", back_populates="plan", cascade="all, delete-orphan"
    )


class PlanDish(Base):
    __tablename__ = "plan_dishes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cook_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cook_day: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "Montag" etc.
    recipe_json: Mapped[str | None] = mapped_column(Text, nullable=True)     # JSON string
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    used_offer_ids_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # confirmed = user selected this dish; suggestion = still a candidate
    dish_status: Mapped[str] = mapped_column(String(20), default="suggestion", nullable=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    feedback_thumbs: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1=up, -1=down
    feedback_portion_note: Mapped[str | None] = mapped_column(String(50), nullable=True)
    feedback_free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NULL for plans created before the recipe catalog was introduced
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )

    plan: Mapped["WeeklyPlan"] = relationship("WeeklyPlan", back_populates="dishes")
    recipe: Mapped["Recipe | None"] = relationship("Recipe")


class ShoppingItem(Base):
    __tablename__ = "shopping_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("weekly_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    store: Mapped[str | None] = mapped_column(String(50), nullable=True)
    live_from_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    offer_id: Mapped[int | None] = mapped_column(
        ForeignKey("offers.id", ondelete="SET NULL"), nullable=True
    )
    price_text: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_already_have: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    plan: Mapped["WeeklyPlan"] = relationship("WeeklyPlan", back_populates="shopping_items")


class LearnedPreferences(Base):
    __tablename__ = "learned_preferences"

    household_id: Mapped[int] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"), primary_key=True
    )
    loved_dishes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    disliked_dishes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    portion_adjustments_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    recurring_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    household: Mapped["Household"] = relationship("Household")


class ApiCall(Base):
    __tablename__ = "api_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    household_id: Mapped[int | None] = mapped_column(
        ForeignKey("households.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_estimate: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cook_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_time_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)
    base_servings: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    instructions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    tips_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rating_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Diet flags derived from ingredients at scrape time
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_meat: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_fish: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contains_pork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contains_beef: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contains_chicken: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contains_turkey: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allergen_flags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    meat_kinds_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # hauptgericht | dessert | getraenk | grundrezept | sonstige
    meal_type: Mapped[str] = mapped_column(String(30), default="hauptgericht", nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        "RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    optional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(200), nullable=True)

    recipe: Mapped["Recipe"] = relationship("Recipe", back_populates="ingredients")


class HealthPing(Base):
    """Kept from Phase 0."""

    __tablename__ = "health_pings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
