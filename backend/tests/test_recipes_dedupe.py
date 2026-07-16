"""dedupe_by_name / sort_dishes / filter_dishes — cookbook list logic
(backend/app/routers/recipes.py, GET /api/recipes)."""

from app.models import PlanDish
from app.routers.recipes import dedupe_by_name, filter_dishes, sort_dishes


def _dish(id_, name, is_favorite=False):
    return PlanDish(
        id=id_,
        plan_id=1,
        name=name,
        dish_status="confirmed",
        is_favorite=is_favorite,
        used_offer_ids_json="[]",
    )


class TestDedupeByName:
    def test_keeps_first_occurrence_per_case_insensitive_name(self):
        newest = _dish(2, "Lasagne")
        older = _dish(1, "lasagne")
        result = dedupe_by_name([newest, older])
        assert result == [newest]

    def test_keeps_distinct_names(self):
        a = _dish(1, "Lasagne")
        b = _dish(2, "Chili con Carne")
        result = dedupe_by_name([a, b])
        assert result == [a, b]

    def test_strips_whitespace_when_comparing(self):
        a = _dish(1, "  Lasagne ")
        b = _dish(2, "Lasagne")
        result = dedupe_by_name([a, b])
        assert result == [a]

    def test_empty_list(self):
        assert dedupe_by_name([]) == []


class TestSortDishes:
    def test_favorites_come_first(self):
        fav = _dish(1, "Zucchini-Auflauf", is_favorite=True)
        other = _dish(2, "Auflauf", is_favorite=False)
        result = sort_dishes([other, fav])
        assert result == [fav, other]

    def test_alphabetical_within_group(self):
        b = _dish(1, "Bolognese")
        a = _dish(2, "Auflauf")
        result = sort_dishes([b, a])
        assert result == [a, b]


class TestFilterDishes:
    def test_query_matches_substring_case_insensitive(self):
        a = _dish(1, "Käsespätzle")
        b = _dish(2, "Chili con Carne")
        result = filter_dishes([a, b], q="spätzle")
        assert result == [a]

    def test_favorites_only(self):
        fav = _dish(1, "A", is_favorite=True)
        other = _dish(2, "B", is_favorite=False)
        result = filter_dishes([fav, other], favorites_only=True)
        assert result == [fav]

    def test_no_filters_returns_all(self):
        a = _dish(1, "A")
        b = _dish(2, "B")
        assert filter_dishes([a, b]) == [a, b]
