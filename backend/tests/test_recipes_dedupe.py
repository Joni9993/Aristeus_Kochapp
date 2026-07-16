"""archive_recipes_to_cookbook — upserts confirmed plan dishes into
saved_recipes (backend/app/ai/pipeline.py, task 1 of the cookbook refactor).

Replaces the old GET-time dedupe tests: the cookbook is now a plain read of
saved_recipes (backend/app/routers/recipes.py), so the dedupe/skip-existing
logic that used to run per-request now runs once, here, when a plan is
confirmed/swapped/regenerated or planned into a week."""

import json

from app.ai.pipeline import archive_recipes_to_cookbook
from app.models import Household, PlanDish, SavedRecipe, WeeklyPlan

_RECIPE_JSON = json.dumps({
    "zutaten": [{"name": "Nudeln", "menge": 400, "einheit": "g", "ist_angebot": False, "laden": None}],
    "schritte": ["Kochen"],
    "geschaetzte_zeit_min": 20,
    "tipps": [],
})


def _make_household(db):
    household = Household(username="cook", email="cook@example.com", password_hash="x")
    db.add(household)
    db.flush()
    return household


def _make_plan(db, household, status="confirmed"):
    plan = WeeklyPlan(household_id=household.id, week_start_date="2026-07-20", status=status)
    db.add(plan)
    db.flush()
    return plan


def _dish(db, plan, name, *, dish_status="confirmed", recipe_json=_RECIPE_JSON, **kwargs):
    dish = PlanDish(
        plan_id=plan.id,
        name=name,
        dish_status=dish_status,
        used_offer_ids_json="[]",
        recipe_json=recipe_json,
        **kwargs,
    )
    db.add(dish)
    db.flush()
    return dish


class TestArchiveRecipesToCookbook:
    def test_archives_confirmed_dish_with_recipe(self, db_session):
        household = _make_household(db_session)
        plan = _make_plan(db_session, household)
        _dish(db_session, plan, "Lasagne", cuisine="Fleisch", cook_time_min=45, is_favorite=True)

        added = archive_recipes_to_cookbook(plan, db_session)

        assert added == 1
        saved = db_session.query(SavedRecipe).filter_by(household_id=household.id).all()
        assert len(saved) == 1
        assert saved[0].name == "Lasagne"
        assert saved[0].origin == "gekocht"
        assert saved[0].cuisine == "Fleisch"
        assert saved[0].cook_time_min == 45
        assert saved[0].is_favorite is True
        assert saved[0].recipe_json == _RECIPE_JSON

    def test_skips_dish_without_recipe_json(self, db_session):
        household = _make_household(db_session)
        plan = _make_plan(db_session, household)
        _dish(db_session, plan, "Ohne Rezept", recipe_json=None)

        added = archive_recipes_to_cookbook(plan, db_session)

        assert added == 0
        assert db_session.query(SavedRecipe).count() == 0

    def test_skips_non_confirmed_dish(self, db_session):
        household = _make_household(db_session)
        plan = _make_plan(db_session, household)
        _dish(db_session, plan, "Vorschlag", dish_status="suggestion")

        added = archive_recipes_to_cookbook(plan, db_session)

        assert added == 0
        assert db_session.query(SavedRecipe).count() == 0

    def test_skips_name_already_saved_case_insensitive(self, db_session):
        household = _make_household(db_session)
        db_session.add(SavedRecipe(
            household_id=household.id, name="lasagne", recipe_json=_RECIPE_JSON, origin="eigene",
        ))
        db_session.flush()
        plan = _make_plan(db_session, household)
        _dish(db_session, plan, "Lasagne")

        added = archive_recipes_to_cookbook(plan, db_session)

        assert added == 0
        assert db_session.query(SavedRecipe).count() == 1
        assert db_session.query(SavedRecipe).first().origin == "eigene"

    def test_idempotent_on_repeated_calls(self, db_session):
        household = _make_household(db_session)
        plan = _make_plan(db_session, household)
        _dish(db_session, plan, "Chili con Carne")
        _dish(db_session, plan, "Gemüsecurry")

        first = archive_recipes_to_cookbook(plan, db_session)
        second = archive_recipes_to_cookbook(plan, db_session)

        assert first == 2
        assert second == 0
        assert db_session.query(SavedRecipe).count() == 2

    def test_different_households_do_not_collide(self, db_session):
        household_a = _make_household(db_session)
        household_b = Household(username="cook2", email="cook2@example.com", password_hash="x")
        db_session.add(household_b)
        db_session.flush()

        plan_a = _make_plan(db_session, household_a)
        _dish(db_session, plan_a, "Lasagne")
        plan_b = _make_plan(db_session, household_b)
        _dish(db_session, plan_b, "Lasagne")

        archive_recipes_to_cookbook(plan_a, db_session)
        archive_recipes_to_cookbook(plan_b, db_session)

        assert db_session.query(SavedRecipe).count() == 2
