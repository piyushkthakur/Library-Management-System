"""Unit tests for DashboardService with mocked repositories (Volume 3,
Chapter 34.2) — no database required. Deterministic: the module-level
``date`` is frozen via a date subclass (Volume 3, Chapter 9.4).

Run: python -m unittest discover -s tests
"""

import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from app.services.dashboard_service import (
    OVERDUE_WIDGET_LIMIT,
    TREND_DAYS,
    DashboardService,
)

TODAY = date(2026, 8, 1)


class FakeDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 1)


class FakeSession:
    pass


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        yield self.session


class FakeBookRepository:
    def __init__(self, active_books=4, available=37):
        self._books = active_books
        self._available = available

    def count_active_books(self, session):
        return self._books

    def total_available_copies(self, session):
        return self._available


class FakeTransactionRepository:
    def __init__(self, active=6, overdue=2, trend=None, overdue_items=None):
        self._active = active
        self._overdue = overdue
        self._trend = trend if trend is not None else []
        self._overdue_items = overdue_items if overdue_items is not None else []
        self.last_trend_days = None
        self.last_overdue_limit = None

    def count_active(self, session):
        return self._active

    def count_overdue(self, session):
        return self._overdue

    def circulation_trend(self, session, days):
        self.last_trend_days = days
        return self._trend

    def get_overdue(self, session, limit):
        self.last_overdue_limit = limit
        return self._overdue_items


class FakeCategoryRepository:
    def __init__(self, categories=None):
        self._categories = categories if categories is not None else []

    def list_all(self, session):
        return self._categories

    def count_books_in_category(self, session, category_id):
        return self._categories[category_id - 1].count


def make_trend():
    return [
        {"date": TODAY - timedelta(days=1), "issued": 2, "returned": 1},
        {"date": TODAY - timedelta(days=2), "issued": 0, "returned": 3},
    ]


def make_categories():
    return [
        SimpleNamespace(id=1, name="Fiction", count=5),
        SimpleNamespace(id=2, name="Science", count=2),
    ]


def make_overdue_items():
    return [
        SimpleNamespace(
            id=11,
            student_name="Alice",
            due_date=TODAY - timedelta(days=3),
            book=SimpleNamespace(title="Clean Code"),
        ),
        SimpleNamespace(
            id=12,
            student_name="Bob",
            due_date=TODAY - timedelta(days=1),
            book=SimpleNamespace(title="Refactoring"),
        ),
    ]


def make_service(txn=None, book=None, cat=None):
    return DashboardService(
        FakeDatabase(),
        txn or FakeTransactionRepository(),
        book or FakeBookRepository(),
        cat or FakeCategoryRepository(),
    )


class DashboardKpiTest(unittest.TestCase):
    def test_kpis_mapped(self):
        dto = make_service().get_dashboard()
        self.assertEqual(dto.total_books, 4)
        self.assertEqual(dto.total_available_copies, 37)
        self.assertEqual(dto.active_transactions, 6)
        self.assertEqual(dto.overdue_transactions, 2)

    def test_empty_catalog_yields_zero_kpis(self):
        service = make_service(
            FakeTransactionRepository(active=0, overdue=0),
            FakeBookRepository(active_books=0, available=0),
        )
        dto = service.get_dashboard()
        self.assertEqual(
            (
                dto.total_books,
                dto.total_available_copies,
                dto.active_transactions,
                dto.overdue_transactions,
            ),
            (0, 0, 0, 0),
        )
        self.assertEqual(dto.trend, ())
        self.assertEqual(dto.category_distribution, ())
        self.assertEqual(dto.overdue_items, ())


class DashboardTrendTest(unittest.TestCase):
    def test_trend_requests_30_days_and_maps_points(self):
        service = make_service(txn=FakeTransactionRepository(trend=make_trend()))
        dto = service.get_dashboard()
        self.assertEqual(service._txn_repo.last_trend_days, TREND_DAYS)
        self.assertEqual(len(dto.trend), 2)
        first = dto.trend[0]
        self.assertEqual(first.date, TODAY - timedelta(days=1))
        self.assertEqual((first.issued, first.returned), (2, 1))
        self.assertTrue(all(p.returned >= 0 for p in dto.trend))


class DashboardDistributionTest(unittest.TestCase):
    def test_distribution_counts_per_category_in_list_order(self):
        dto = make_service(
            cat=FakeCategoryRepository(make_categories())
        ).get_dashboard()
        self.assertEqual(len(dto.category_distribution), 2)
        self.assertEqual(dto.category_distribution[0].category_name, "Fiction")
        self.assertEqual(dto.category_distribution[0].book_count, 5)
        self.assertEqual(dto.category_distribution[1].book_count, 2)

    def test_empty_categories_yield_empty_distribution(self):
        dto = make_service(cat=FakeCategoryRepository([])).get_dashboard()
        self.assertEqual(dto.category_distribution, ())


class DashboardOverdueWidgetTest(unittest.TestCase):
    @mock.patch("app.services.dashboard_service.date", FakeDate)
    def test_widget_limits_to_ten_and_computes_days_overdue(self):
        service = make_service(
            txn=FakeTransactionRepository(overdue_items=make_overdue_items())
        )
        dto = service.get_dashboard()
        self.assertEqual(service._txn_repo.last_overdue_limit, OVERDUE_WIDGET_LIMIT)
        self.assertEqual(len(dto.overdue_items), 2)
        first, second = dto.overdue_items
        self.assertEqual(first.transaction_id, 11)
        self.assertEqual(first.book_title, "Clean Code")
        self.assertEqual(first.student_name, "Alice")
        self.assertEqual(first.days_overdue, 3)
        self.assertEqual(second.days_overdue, 1)

    def test_no_overdue_items_yields_empty_widget(self):
        dto = make_service(
            txn=FakeTransactionRepository(overdue_items=[])
        ).get_dashboard()
        self.assertEqual(dto.overdue_items, ())


if __name__ == "__main__":
    unittest.main()
