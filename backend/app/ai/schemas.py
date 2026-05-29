"""Pydantic schemas for LLM JSON output validation."""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Step 3 — Dish suggestions
# ---------------------------------------------------------------------------

class AngebotsZutat(BaseModel):
    name: str
    laden: str
    ab_tag: str | None = None


class DishSuggestion(BaseModel):
    name: str
    beschreibung: str
    hauptzutaten: list[str] = Field(default_factory=list)
    angebots_zutaten: list[AngebotsZutat] = Field(default_factory=list)
    kochzeit_min: int = 30
    kategorie: str = "gemischt"
    schwierigkeit: str = "mittel"


class DishSuggestionsResponse(BaseModel):
    vorschlaege: list[DishSuggestion]


# ---------------------------------------------------------------------------
# Step 6 — Recipe
# ---------------------------------------------------------------------------

class RecipeIngredient(BaseModel):
    name: str
    menge: float | None = None
    einheit: str | None = None
    ist_angebot: bool = False
    laden: str | None = None  # exact store key when ist_angebot=True


class RecipeResponse(BaseModel):
    zutaten: list[RecipeIngredient] = Field(default_factory=list)
    schritte: list[str] = Field(default_factory=list)
    geschaetzte_zeit_min: int = 30
    tipps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Step 8 — Feedback aggregation
# ---------------------------------------------------------------------------

class FeedbackSummaryResponse(BaseModel):
    muster: list[str] = Field(default_factory=list)      # extracted patterns
    empfehlungen: list[str] = Field(default_factory=list) # recommendations
