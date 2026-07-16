"""_round_quantity and _format_quantity (backend/app/ai/pipeline.py)."""

from app.ai.pipeline import _format_quantity, _round_quantity


class TestRoundQuantity:
    def test_grams_small_min_one(self):
        assert _round_quantity(3, "g") == 3

    def test_grams_under_50_rounds_to_5(self):
        assert _round_quantity(23, "g") == 25

    def test_grams_over_50_rounds_to_10(self):
        assert _round_quantity(1500, "g") == 1500

    def test_kg_rounds_to_one_decimal(self):
        # The exact bug report from the task: 0.5 kg used to become 0.
        assert _round_quantity(0.5, "kg") == 0.5

    def test_liters_rounds_to_one_decimal(self):
        # The exact bug report from the task: 1.5 l used to become 2.
        assert _round_quantity(1.5, "l") == 1.5

    def test_countable_unit_rounds_up_to_at_least_one(self):
        assert _round_quantity(0.2, "") == 1

    def test_spoon_measure_rounds_to_quarter(self):
        assert _round_quantity(0.6, "el") == 0.5

    def test_pinch_rounds_to_half(self):
        assert _round_quantity(0.3, "prise") == 0.5


class TestFormatQuantity:
    def test_whole_number_has_no_decimal(self):
        assert _format_quantity(2.0) == "2"

    def test_half_keeps_decimal(self):
        assert _format_quantity(0.5) == "0.5"

    def test_quarter_keeps_decimal(self):
        assert _format_quantity(0.25) == "0.25"

    def test_one_point_five_keeps_decimal(self):
        assert _format_quantity(1.5) == "1.5"

    def test_large_whole_number(self):
        assert _format_quantity(1500.0) == "1500"
