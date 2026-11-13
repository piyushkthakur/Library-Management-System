"""Unit tests for TransactionRepository.aggregate_for_period (Volume 4,
Section 35.5; Volume 3, Chapter 26.1) using a scripted FakeSession — the
method's SQL-level aggregation is verified against real MySQL in the live
smoke; these tests pin the default contract, the scope predicate, the
overdue bounds, and the grouped-row assembly without a database.

Run: python -m unittest discover -s tests
"""

import unittest
from datetime import date
from types import SimpleNamespace

from app.repositories.transaction_repository import TransactionRepository

TODAY = date(2026, 8, 1)
WINDOW = (date(2026, 6, 1), date(2026, 7, 31))


class FakeSession:
    """Records every statement; returns scripted scalar/row results."""

    def __init__(self, scalar_results=(), execute_results=()):
        self._scalar_results = list(scalar_results)
        self._execute_results = list(execute_results)
        self.scalar_calls = []
        self.execute_calls = []

    def scalar(self, stmt):
        self.scalar_calls.append(stmt)
        return self._scalar_results.pop(0)

    def execute(self, stmt):
        self.execute_calls.append(stmt)
        return SimpleNamespace(all=lambda: self._execute_results.pop(0))


def make_repo():
    return TransactionRepository()


class DefaultContractTest(unittest.TestCase):
    def test_totals_dict_structure_preserved(self):
        session = FakeSession(scalar_results=[5, 3, 2, 12.5])
        result = make_repo().aggregate_for_period(session, *WINDOW, None)
        self.assertEqual(
            result, {"issued": 5, "returned": 3, "overdue": 2, "fines": 12.5}
        )
        self.assertEqual(len(session.scalar_calls), 4)

    def test_null_totals_coerce_to_zero(self):
        session = FakeSession(scalar_results=[None, None, None, None])
        result = make_repo().aggregate_for_period(session, *WINDOW, None)
        self.assertEqual(
            result, {"issued": 0, "returned": 0, "overdue": 0, "fines": 0.0}
        )


class ScopeTest(unittest.TestCase):
    def sql(self, stmt):
        return str(stmt)

    def test_scope_applied_to_all_four_aggregates(self):
        """F1 — the documented scope predicate must gate issued, returned,
        overdue, and fines identically (Volume 4, Section 35.5)."""
        session = FakeSession(scalar_results=[1, 1, 1, 1.0])
        make_repo().aggregate_for_period(session, *WINDOW, scope_user_id=7)
        self.assertEqual(len(session.scalar_calls), 4)
        for stmt in session.scalar_calls:
            self.assertIn("issued_by_user_id", self.sql(stmt), stmt)

    def test_unscoped_has_no_user_predicate(self):
        session = FakeSession(scalar_results=[1, 1, 1, 1.0])
        make_repo().aggregate_for_period(session, *WINDOW, None)
        for stmt in session.scalar_calls:
            self.assertNotIn("issued_by_user_id", self.sql(stmt))

    def test_grouped_scope_applied_to_all_four(self):
        session = FakeSession(execute_results=[[], [], [], []])
        make_repo().aggregate_for_period(session, *WINDOW, 7, "day")
        self.assertEqual(len(session.execute_calls), 4)
        for stmt in session.execute_calls:
            self.assertIn("issued_by_user_id", self.sql(stmt))


class OverdueBoundsTest(unittest.TestCase):
    def test_overdue_query_has_both_period_bounds(self):
        """F2 — overdue counts only transactions issued within the period
        (Volume 4, Section 35.5 WHERE clause), plus derived-overdue
        predicate (Volume 3, Chapter 10.2)."""
        session = FakeSession(scalar_results=[1, 1, 1, 1.0])
        make_repo().aggregate_for_period(session, *WINDOW, None)
        overdue_stmt = self.stmt_with(session, "due_date < curdate()")
        sql = str(overdue_stmt)
        self.assertIn("issue_date >= :issue_date_1", sql)
        self.assertIn("issue_date <= :issue_date_2", sql)

    def stmt_with(self, session, fragment):
        for stmt in session.scalar_calls:
            if fragment in str(stmt):
                return stmt
        self.fail(f"no statement containing {fragment}")


class GranularityTest(unittest.TestCase):
    def test_unknown_granularity_rejected(self):
        session = FakeSession()
        with self.assertRaises(ValueError):
            make_repo().aggregate_for_period(session, *WINDOW, None, "year")

    def test_bucket_expressions_compile(self):
        repo = make_repo()
        col = __import__(
            "app.models.transaction", fromlist=["Transaction"]
        ).Transaction.issue_date
        for granularity, fragment in (
            ("day", "date("),
            ("week", "from_days("),
            ("month", "from_days("),
        ):
            sql = str(repo._bucket_expression(col, granularity))
            self.assertIn(fragment, sql)
        with self.assertRaises(ValueError):
            repo._bucket_expression(col, "year")

    def test_grouped_rows_merge_in_order(self):
        rows = [
            [(date(2026, 6, 2), 3)],  # issued
            [(date(2026, 6, 3), 1)],  # returned
            [(date(2026, 6, 4), 2)],  # overdue
            [(date(2026, 6, 3), 10.0)],  # fines
        ]
        session = FakeSession(execute_results=rows)
        result = make_repo().aggregate_for_period(session, *WINDOW, None, "day")
        self.assertEqual(len(result), 3)
        by_date = {row["date"]: row for row in result}
        self.assertEqual(by_date[date(2026, 6, 2)]["issued"], 3)
        self.assertEqual(by_date[date(2026, 6, 3)]["returned"], 1)
        self.assertEqual(by_date[date(2026, 6, 3)]["fines"], 10.0)
        self.assertEqual(by_date[date(2026, 6, 4)]["overdue"], 2)
        self.assertEqual(
            list(by_date), sorted(by_date), "rows must be ordered by bucket date"
        )
        for row in result:
            self.assertEqual(
                set(row),
                {"date", "issued", "returned", "overdue", "fines"},
            )

    def test_grouped_empty_period(self):
        session = FakeSession(execute_results=[[], [], [], []])
        result = make_repo().aggregate_for_period(session, *WINDOW, None, "month")
        self.assertEqual(result, [])


class CategoryFilterTest(unittest.TestCase):
    """Optional Category filter (Volume 2, Chapter 19) must join books and
    filter on category_id in every aggregate, both modes, at SQL level."""

    def test_totals_join_and_filter_all_four(self):
        session = FakeSession(scalar_results=[1, 1, 1, 1.0])
        make_repo().aggregate_for_period(session, *WINDOW, None, category_id=3)
        self.assertEqual(len(session.scalar_calls), 4)
        for stmt in session.scalar_calls:
            sql = str(stmt)
            self.assertIn("JOIN books", sql, stmt)
            self.assertIn("category_id", sql, stmt)

    def test_grouped_join_and_filter_all_four(self):
        session = FakeSession(execute_results=[[], [], [], []])
        make_repo().aggregate_for_period(session, *WINDOW, 7, "day", category_id=3)
        self.assertEqual(len(session.execute_calls), 4)
        for stmt in session.execute_calls:
            sql = str(stmt)
            self.assertIn("JOIN books", sql, stmt)
            self.assertIn("category_id", sql, stmt)

    def test_no_join_when_unfiltered(self):
        session = FakeSession(scalar_results=[1, 1, 1, 1.0])
        make_repo().aggregate_for_period(session, *WINDOW, None)
        for stmt in session.scalar_calls:
            self.assertNotIn("JOIN books", str(stmt))


if __name__ == "__main__":
    unittest.main()
