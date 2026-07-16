"""_should_auto_complete date logic (backend/app/routers/plans.py, task 4).

A confirmed plan flips to 'complete' once its cook week (week_start + 7 days)
is fully over.
"""

from datetime import date

from app.routers.plans import _should_auto_complete


class TestShouldAutoComplete:
    def test_true_when_more_than_a_week_has_passed(self):
        assert _should_auto_complete("2026-07-01", date(2026, 7, 16)) is True

    def test_false_within_the_cook_week(self):
        assert _should_auto_complete("2026-07-13", date(2026, 7, 16)) is False

    def test_false_exactly_on_the_boundary_day(self):
        # week_start + 7 days == today -> not yet "<", so still active
        assert _should_auto_complete("2026-07-09", date(2026, 7, 16)) is False

    def test_true_the_day_after_the_boundary(self):
        assert _should_auto_complete("2026-07-09", date(2026, 7, 17)) is True

    def test_invalid_date_string_returns_false(self):
        assert _should_auto_complete("not-a-date", date(2026, 7, 16)) is False
