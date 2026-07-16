"""build_shopping_list quantity aggregation/formatting (backend/app/ai/pipeline.py).

Covers the fix for task 2: round(entry["total"]) used to destroy decimal
quantities (0.5 kg -> 0 -> quantity disappeared; 1.5 l -> 2). The fixed
version uses _round_quantity + _format_quantity and only reports
quantity=None when nothing was ever aggregated (total == 0).
"""

from datetime import datetime, timezone

from app.ai.pipeline import build_shopping_list
from app.ai.schemas import RecipeIngredient as SchemaIngredient
from app.ai.schemas import RecipeResponse
from app.models import Brochure, Household, Offer, PlanDish, Profile, WeeklyPlan


def _make_household(db):
    household = Household(username="tester", email="tester@example.com", password_hash="x")
    db.add(household)
    db.flush()
    profile = Profile(household_id=household.id, postal_code="", selected_stores_json="[]")
    db.add(profile)
    db.flush()
    db.refresh(household)
    return household


def _make_confirmed_dish(db, plan):
    dish = PlanDish(
        plan_id=plan.id,
        name="Testgericht",
        dish_status="confirmed",
        used_offer_ids_json="[]",
    )
    db.add(dish)
    db.flush()
    return dish


class TestBuildShoppingListQuantities:
    def test_decimal_quantities_are_preserved(self, db_session):
        household = _make_household(db_session)
        plan = WeeklyPlan(household_id=household.id, week_start_date="2026-07-20", status="confirmed")
        db_session.add(plan)
        db_session.flush()
        dish = _make_confirmed_dish(db_session, plan)

        recipe = RecipeResponse(
            zutaten=[
                SchemaIngredient(name="Butter", menge=0.5, einheit="kg"),
                SchemaIngredient(name="Milch", menge=1.5, einheit="l"),
                SchemaIngredient(name="Mehl", menge=1500, einheit="g"),
                SchemaIngredient(name="Salz", menge=None, einheit=None),
            ],
            schritte=["Schritt 1"],
            geschaetzte_zeit_min=20,
            tipps=[],
        )

        items = build_shopping_list(plan, {dish.id: recipe}, household, db_session)
        by_name = {i.ingredient: i for i in items}

        assert by_name["Butter"].quantity == "0.5"  # used to become "0" / disappear
        assert by_name["Milch"].quantity == "1.5"    # used to become "2"
        assert by_name["Mehl"].quantity == "1500"    # no spurious ".0"
        assert by_name["Salz"].quantity is None      # nothing ever aggregated

    def test_aggregates_same_ingredient_across_dishes(self, db_session):
        household = _make_household(db_session)
        plan = WeeklyPlan(household_id=household.id, week_start_date="2026-07-20", status="confirmed")
        db_session.add(plan)
        db_session.flush()
        dish1 = _make_confirmed_dish(db_session, plan)
        dish2 = PlanDish(
            plan_id=plan.id, name="Zweites Gericht", dish_status="confirmed", used_offer_ids_json="[]",
        )
        db_session.add(dish2)
        db_session.flush()

        recipe1 = RecipeResponse(
            zutaten=[SchemaIngredient(name="Zwiebel", menge=0.3, einheit="kg")],
            schritte=["..."], geschaetzte_zeit_min=10, tipps=[],
        )
        recipe2 = RecipeResponse(
            zutaten=[SchemaIngredient(name="Zwiebel", menge=0.3, einheit="kg")],
            schritte=["..."], geschaetzte_zeit_min=10, tipps=[],
        )

        items = build_shopping_list(
            plan, {dish1.id: recipe1, dish2.id: recipe2}, household, db_session
        )
        assert len(items) == 1
        assert items[0].quantity == "0.6"

    def test_unconfirmed_dishes_are_ignored(self, db_session):
        household = _make_household(db_session)
        plan = WeeklyPlan(household_id=household.id, week_start_date="2026-07-20", status="confirmed")
        db_session.add(plan)
        db_session.flush()
        dish = PlanDish(
            plan_id=plan.id, name="Verworfen", dish_status="rejected", used_offer_ids_json="[]",
        )
        db_session.add(dish)
        db_session.flush()

        recipe = RecipeResponse(
            zutaten=[SchemaIngredient(name="Karotte", menge=200, einheit="g")],
            schritte=["..."], geschaetzte_zeit_min=10, tipps=[],
        )
        items = build_shopping_list(plan, {dish.id: recipe}, household, db_session)
        assert items == []


class TestBuildShoppingListOfferMatching:
    def test_matches_active_offer_even_when_ist_angebot_is_false(self, db_session):
        """Task 5: ALL ingredients get matched against active offers, not just
        the ones the LLM flagged ist_angebot=true at generation time — this is
        what gives imported/older recipes fresh offer pricing when planned in."""
        household = Household(username="offers", email="offers@example.com", password_hash="x")
        db_session.add(household)
        db_session.flush()
        profile = Profile(household_id=household.id, postal_code="12345", selected_stores_json='["rewe"]')
        db_session.add(profile)
        db_session.flush()
        db_session.refresh(household)

        brochure = Brochure(
            store="rewe",
            postal_code="12345",
            brochure_id_kaufda="b1",
            fetched_at=datetime.now(timezone.utc),
            status="active",
        )
        db_session.add(brochure)
        db_session.flush()
        offer = Offer(
            brochure_id=brochure.id,
            product_name="Hähnchenbrust",
            store="rewe",
            is_cooking_relevant=True,
            price_text="3,99 €",
        )
        db_session.add(offer)
        db_session.flush()

        plan = WeeklyPlan(household_id=household.id, week_start_date="2026-07-20", status="confirmed")
        db_session.add(plan)
        db_session.flush()
        dish = _make_confirmed_dish(db_session, plan)

        recipe = RecipeResponse(
            zutaten=[
                SchemaIngredient(name="Hähnchenbrust", menge=400, einheit="g", ist_angebot=False, laden=None),
            ],
            schritte=["..."],
            geschaetzte_zeit_min=20,
            tipps=[],
        )
        items = build_shopping_list(plan, {dish.id: recipe}, household, db_session)
        assert len(items) == 1
        assert items[0].offer_id == offer.id
        assert items[0].price_text == "3,99 €"
        assert items[0].store == "rewe"
