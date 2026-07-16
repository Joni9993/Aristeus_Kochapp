"""_parse_price — robust German offer-price parsing for the savings summary
(backend/app/routers/plans.py, task 8)."""

from app.routers.plans import _parse_price


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
