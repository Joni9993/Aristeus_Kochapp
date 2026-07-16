"""URL-guard for POST /api/recipes/import (backend/app/routers/recipes.py,
task 4) and POST /api/recipes/plan-into-week (task 5)."""

import json

import pytest
from fastapi import HTTPException

from app.models import Household, PlanDish, Profile, SavedRecipe, WeeklyPlan
from app.routers.recipes import PlanIntoWeekRequest, _validate_import_url, plan_into_week
from app.services.scheduler import _this_monday


def _make_household(db):
    household = Household(username="planner", email="planner@example.com", password_hash="x")
    db.add(household)
    db.flush()
    profile = Profile(household_id=household.id, postal_code="", selected_stores_json="[]")
    db.add(profile)
    db.flush()
    db.refresh(household)
    return household


_RECIPE_JSON = json.dumps({
    "zutaten": [{"name": "Nudeln", "menge": 400, "einheit": "g", "ist_angebot": False, "laden": None}],
    "schritte": ["Kochen"],
    "geschaetzte_zeit_min": 20,
    "tipps": [],
})


# ---------------------------------------------------------------------------
# _validate_import_url
# ---------------------------------------------------------------------------

class TestValidateImportUrl:
    def test_rejects_non_http_scheme(self):
        with pytest.raises(HTTPException) as exc:
            _validate_import_url("ftp://example.com/recipe")
        assert exc.value.status_code == 400

    def test_rejects_localhost(self):
        with pytest.raises(HTTPException) as exc:
            _validate_import_url("http://localhost/recipe")
        assert exc.value.status_code == 400

    def test_rejects_private_ip_literal(self):
        with pytest.raises(HTTPException) as exc:
            _validate_import_url("http://192.168.1.5/recipe")
        assert exc.value.status_code == 400

    def test_rejects_loopback_ip_literal(self):
        with pytest.raises(HTTPException) as exc:
            _validate_import_url("http://127.0.0.1/recipe")
        assert exc.value.status_code == 400

    def test_rejects_missing_host(self):
        with pytest.raises(HTTPException):
            _validate_import_url("http:///recipe")

    def test_allows_public_ip_literal(self):
        # Numeric literal — classified locally, no real DNS lookup needed.
        _validate_import_url("http://93.184.216.34/recipe")


# ---------------------------------------------------------------------------
# plan_into_week
# ---------------------------------------------------------------------------

class TestPlanIntoWeek:
    def test_creates_new_plan_when_none_exists(self, db_session):
        household = _make_household(db_session)
        saved = SavedRecipe(household_id=household.id, name="Pasta", recipe_json=_RECIPE_JSON)
        db_session.add(saved)
        db_session.flush()

        body = PlanIntoWeekRequest(saved_recipe_id=saved.id, week="current")
        result = plan_into_week(body, household=household, db=db_session)

        plan = db_session.get(WeeklyPlan, result["plan_id"])
        assert plan.status == "confirmed"
        assert plan.week_start_date == _this_monday()
        assert len(plan.dishes) == 1
        assert plan.dishes[0].name == "Pasta"
        assert plan.dishes[0].dish_status == "confirmed"
        assert len(plan.shopping_items) == 1

    def test_adds_confirmed_dish_to_existing_confirmed_plan(self, db_session):
        household = _make_household(db_session)
        plan = WeeklyPlan(household_id=household.id, week_start_date=_this_monday(), status="confirmed")
        db_session.add(plan)
        db_session.flush()
        existing_dish = PlanDish(
            plan_id=plan.id, name="Suppe", dish_status="confirmed", used_offer_ids_json="[]",
            recipe_json=_RECIPE_JSON,
        )
        db_session.add(existing_dish)
        db_session.flush()

        saved = SavedRecipe(household_id=household.id, name="Pasta", recipe_json=_RECIPE_JSON)
        db_session.add(saved)
        db_session.flush()

        body = PlanIntoWeekRequest(saved_recipe_id=saved.id, week="current")
        result = plan_into_week(body, household=household, db=db_session)

        assert result["plan_id"] == plan.id
        db_session.refresh(plan)
        confirmed_names = {d.name for d in plan.dishes if d.dish_status == "confirmed"}
        assert confirmed_names == {"Suppe", "Pasta"}
        assert plan.status == "confirmed"

    def test_adds_suggestion_to_suggestions_ready_plan(self, db_session):
        household = _make_household(db_session)
        plan = WeeklyPlan(
            household_id=household.id, week_start_date=_this_monday(), status="suggestions_ready"
        )
        db_session.add(plan)
        db_session.flush()

        saved = SavedRecipe(household_id=household.id, name="Pasta", recipe_json=_RECIPE_JSON)
        db_session.add(saved)
        db_session.flush()

        body = PlanIntoWeekRequest(saved_recipe_id=saved.id, week="current")
        result = plan_into_week(body, household=household, db=db_session)

        assert "Vorschlag" in result["message"]
        db_session.refresh(plan)
        new_dish = next(d for d in plan.dishes if d.name == "Pasta")
        assert new_dish.dish_status == "suggestion"

    def test_confirming_plan_returns_409(self, db_session):
        household = _make_household(db_session)
        plan = WeeklyPlan(household_id=household.id, week_start_date=_this_monday(), status="confirming")
        db_session.add(plan)
        db_session.flush()
        saved = SavedRecipe(household_id=household.id, name="Pasta", recipe_json=_RECIPE_JSON)
        db_session.add(saved)
        db_session.flush()

        body = PlanIntoWeekRequest(saved_recipe_id=saved.id, week="current")
        with pytest.raises(HTTPException) as exc:
            plan_into_week(body, household=household, db=db_session)
        assert exc.value.status_code == 409

    def test_missing_recipe_source_is_404(self, db_session):
        household = _make_household(db_session)
        body = PlanIntoWeekRequest(saved_recipe_id=999, week="current")
        with pytest.raises(HTTPException) as exc:
            plan_into_week(body, household=household, db=db_session)
        assert exc.value.status_code == 404
