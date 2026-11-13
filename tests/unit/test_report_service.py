"""Unit tests for ReportService with mocked repositories and exporters
(Volume 3, Chapter 34.2) — no database required. Deterministic: the
module-level ``date`` is frozen via a date subclass.

Run: python -m unittest discover -s tests
"""

import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from types import SimpleNamespace
from unittest import mock

from app.core.exceptions import LmsError, ValidationError
from app.reporting import ExportResultDto
from app.services.report_service import REPORT_GRANULARITY, ReportService

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


class FakeTransactionRepository:
    def __init__(self, rows=None):
        self._rows = rows if rows is not None else []
        self.last_call = None

    def aggregate_for_period(
        self, session, start, end, scope_user_id, granularity=None, category_id=None
    ):
        self.last_call = {
            "start": start,
            "end": end,
            "scope_user_id": scope_user_id,
            "granularity": granularity,
            "category_id": category_id,
        }
        return self._rows


class FakeSettingsRepository:
    def __init__(self, fine_enabled="true"):
        self._fine_enabled = fine_enabled

    def get_value(self, session, key):
        return self._fine_enabled


class FakeExporter:
    def __init__(self, failure=None):
        self.reports = []
        self._failure = failure

    def generate(self, report):
        self.reports.append(report)
        if self._failure is not None:
            raise self._failure
        return ExportResultDto(file_name="out", file_bytes=b"bytes")


ADMIN = SimpleNamespace(user_id=1, role="ADMINISTRATOR", full_name="Admin User")
LIBRARIAN = SimpleNamespace(user_id=2, role="LIBRARIAN", full_name="Librarian User")


def make_rows():
    return [
        {
            "date": TODAY - timedelta(days=1),
            "issued": 3,
            "returned": 1,
            "overdue": 0,
            "fines": 4.5,
        },
        {
            "date": TODAY - timedelta(days=2),
            "issued": 2,
            "returned": 4,
            "overdue": 2,
            "fines": 1.25,
        },
    ]


def make_service(txn=None, settings=None, pdf=None, excel=None):
    return ReportService(
        FakeDatabase(),
        txn or FakeTransactionRepository(),
        settings or FakeSettingsRepository(),
        pdf if pdf is not None else FakeExporter(),
        excel if excel is not None else FakeExporter(),
    )


class RoleScopingTest(unittest.TestCase):
    def test_librarian_sees_all_transactions_by_default(self):
        service = make_service()
        service.generate_report(LIBRARIAN, "MONTHLY", librarian_id=99)
        self.assertEqual(service._txn_repo.last_call["scope_user_id"], 99)

    def test_librarian_unfiltered_sees_everything(self):
        service = make_service()
        service.generate_report(LIBRARIAN, "MONTHLY")
        self.assertIsNone(service._txn_repo.last_call["scope_user_id"])

    def test_admin_institution_wide_by_default(self):
        service = make_service()
        service.generate_report(ADMIN, "MONTHLY")
        self.assertIsNone(service._txn_repo.last_call["scope_user_id"])

    def test_admin_can_scope_to_a_librarian(self):
        service = make_service()
        service.generate_report(ADMIN, "MONTHLY", librarian_id=7)
        self.assertEqual(service._txn_repo.last_call["scope_user_id"], 7)

    def test_category_passthrough(self):
        service = make_service()
        service.generate_report(ADMIN, "MONTHLY", category_id=4)
        self.assertEqual(service._txn_repo.last_call["category_id"], 4)


class PeriodDerivationTest(unittest.TestCase):
    @mock.patch("app.services.report_service.date", FakeDate)
    def test_daily_is_today(self):
        service = make_service()
        service.generate_report(ADMIN, "DAILY")
        self.assertEqual(
            (service._txn_repo.last_call["start"], service._txn_repo.last_call["end"]),
            (TODAY, TODAY),
        )

    @mock.patch("app.services.report_service.date", FakeDate)
    def test_weekly_anchors_monday_of_current_week(self):
        service = make_service()
        service.generate_report(ADMIN, "WEEKLY")
        self.assertEqual(
            service._txn_repo.last_call["start"], TODAY - timedelta(days=5)
        )

    @mock.patch("app.services.report_service.date", FakeDate)
    def test_monthly_anchors_first_of_month(self):
        service = make_service()
        service.generate_report(ADMIN, "MONTHLY")
        self.assertEqual(service._txn_repo.last_call["start"], date(2026, 8, 1))

    @mock.patch("app.services.report_service.date", FakeDate)
    def test_yearly_anchors_first_of_year(self):
        service = make_service()
        service.generate_report(ADMIN, "YEARLY")
        self.assertEqual(service._txn_repo.last_call["start"], date(2026, 1, 1))

    def test_custom_passes_dates_through(self):
        service = make_service()
        start, end = date(2026, 5, 1), date(2026, 5, 31)
        service.generate_report(ADMIN, "CUSTOM", start_date=start, end_date=end)
        self.assertEqual(
            (service._txn_repo.last_call["start"], service._txn_repo.last_call["end"]),
            (start, end),
        )

    def test_custom_requires_both_dates(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.generate_report(ADMIN, "CUSTOM", start_date=TODAY)

    def test_custom_rejects_start_after_end(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.generate_report(
                ADMIN, "CUSTOM", start_date=TODAY, end_date=TODAY - timedelta(days=1)
            )

    def test_unknown_report_type_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.generate_report(ADMIN, "QUARTERLY")


class AggregationTest(unittest.TestCase):
    def test_totals_derived_from_grouped_rows(self):
        dto = make_service(txn=FakeTransactionRepository(make_rows())).generate_report(
            ADMIN, "MONTHLY"
        )
        self.assertEqual(
            (dto.totals.issued, dto.totals.returned, dto.totals.overdue),
            (5, 5, 2),
        )
        self.assertEqual(dto.totals.fines, 5.75)

    def test_rows_mapped_to_dto(self):
        dto = make_service(txn=FakeTransactionRepository(make_rows())).generate_report(
            ADMIN, "MONTHLY"
        )
        self.assertEqual(len(dto.rows), 2)
        self.assertEqual(dto.rows[0].issued, 3)
        self.assertEqual(dto.rows[0].fines, 4.5)
        self.assertEqual(dto.report_type, "MONTHLY")

    def test_empty_report_yields_zero_totals(self):
        dto = make_service(txn=FakeTransactionRepository([])).generate_report(
            ADMIN, "MONTHLY"
        )
        self.assertEqual(
            (
                dto.totals.issued,
                dto.totals.returned,
                dto.totals.overdue,
                dto.totals.fines,
            ),
            (0, 0, 0, 0.0),
        )
        self.assertEqual(dto.rows, ())

    def test_fines_column_follows_setting(self):
        enabled = make_service(settings=FakeSettingsRepository("true")).generate_report(
            ADMIN, "MONTHLY"
        )
        self.assertTrue(enabled.include_fines)
        disabled = make_service(
            settings=FakeSettingsRepository("false")
        ).generate_report(ADMIN, "MONTHLY")
        self.assertFalse(disabled.include_fines)
        unset = make_service(settings=FakeSettingsRepository(None)).generate_report(
            ADMIN, "MONTHLY"
        )
        self.assertFalse(unset.include_fines)

    def test_grouping_follows_report_type(self):
        service = make_service()
        for report_type, granularity in REPORT_GRANULARITY.items():
            service.generate_report(
                ADMIN,
                report_type,
                start_date=TODAY,
                end_date=TODAY,
            )
            self.assertEqual(
                service._txn_repo.last_call["granularity"],
                granularity,
                report_type,
            )


class ExportTest(unittest.TestCase):
    def test_pdf_routes_to_pdf_exporter(self):
        pdf = FakeExporter()
        excel = FakeExporter()
        service = make_service(pdf=pdf, excel=excel)
        report = service.generate_report(ADMIN, "MONTHLY")
        result = service.export(ADMIN, report, "pdf")
        self.assertEqual(len(pdf.reports), 1)
        self.assertEqual(pdf.reports[0], report)
        self.assertEqual(excel.reports, [])
        self.assertEqual(result.file_name, "out")

    def test_excel_routes_to_excel_exporter(self):
        pdf = FakeExporter()
        excel = FakeExporter()
        service = make_service(pdf=pdf, excel=excel)
        report = service.generate_report(ADMIN, "MONTHLY")
        service.export(ADMIN, report, "excel")
        self.assertEqual(excel.reports, [report])
        self.assertEqual(pdf.reports, [])

    def test_unsupported_format_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.export(ADMIN, None, "csv")

    def test_exporter_failure_translated_to_sanitized_lms_error(self):
        service = make_service(pdf=FakeExporter(failure=RuntimeError("boom")))
        report = service.generate_report(ADMIN, "MONTHLY")
        with self.assertRaises(LmsError) as caught:
            service.export(ADMIN, report, "pdf")
        self.assertNotIn("boom", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
