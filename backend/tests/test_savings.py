"""_parse_price / estimate_item_savings — robust German offer-price parsing
for the savings summary (backend/app/routers/plans.py, task 5)."""

from app.routers.plans import _parse_price, estimate_item_savings


class TestParsePrice:
    def test_comma_decimal_with_euro_sign(self):
        assert _parse_price("1,99 €") == 1.99

    def test_dot_decimal(self):
        assert _parse_price("2.49") == 2.49

    def test_bare_cents_with_leading_dash_dot(self):
        assert _parse_price("-.99") == 0.99

    def test_none_input(self):
        assert _parse_price(None) is None

    def test_empty_string(self):
        assert _parse_price("") is None

    def test_no_digits_is_unparsable(self):
        assert _parse_price("Angebot") is None

    def test_price_with_surrounding_text(self):
        assert _parse_price("nur 3,49 € statt 4,99 €") == 3.49


class TestEstimateItemSavings:
    def test_statt_reference_price_in_price_text(self):
        assert estimate_item_savings("1,99 € statt 2,99 €", None) == 1.00

    def test_uvp_reference_price_in_hint(self):
        assert estimate_item_savings("1,99 €", "UVP 2,49 €") == 0.50

    def test_statt_with_dot_decimal(self):
        assert estimate_item_savings("1.99", "statt 2.99") == 1.00

    def test_minus_percent_discount(self):
        # 3,00 € at -25% off => original was 4,00 €, savings 1,00 €
        assert estimate_item_savings("3,00 €", "-25%") == 1.00

    def test_percent_guenstiger_word_form(self):
        assert estimate_item_savings("3,00 €", "25 % günstiger") == 1.00

    def test_percent_without_discount_keyword_is_ignored(self):
        # "25% mehr Inhalt" is a quantity claim, not a price discount.
        assert estimate_item_savings("3,00 €", "25% mehr Inhalt") == 0.0

    def test_reference_price_lower_than_current_is_ignored(self):
        # Malformed/irrelevant "statt" match — never a *negative* saving.
        assert estimate_item_savings("3,00 €", "statt 2,00 €") == 0.0

    def test_no_price_text_returns_zero(self):
        assert estimate_item_savings(None, "statt 2,99 €") == 0.0

    def test_no_pattern_found_returns_zero(self):
        assert estimate_item_savings("1,99 €", "Je 500 g | gültig bis 2026-05-30") == 0.0

    def test_percent_out_of_range_is_ignored(self):
        assert estimate_item_savings("3,00 €", "-150%") == 0.0
