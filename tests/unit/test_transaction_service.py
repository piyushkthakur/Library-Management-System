"""Unit tests for TransactionService with mocked repositories (Volume 3,
Chapter 34.2) — no database required. Deterministic: the module-level
``date`` is frozen via a date subclass (Volume 3, Chapter 9.4).

Run: python -m unittest discover -s tests
"""

import unittest
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from app.core.exceptions import (
    DuplicateResourceError,
    InsufficientAvailabilityError,
    IntegrityConstraintError,
    RecordNotFoundError,
    UnauthorizedOperationError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.transaction import Stream, TransactionStatus
from app.services.transaction_service import (
    STATUS_ISSUED,
    STATUS_OVERDUE,
    STATUS_RETURNED,
    IssueInput,
    TransactionService,
)

STAFF = SessionContext(
    user_id=1, role="Librarian", full_name="Grace", email="grace@lms.local"
)
TODAY = date(2026, 8, 1)
LOAN_DAYS = 14
BOOK_ISBN = "9780306406157"
BOOK_ISBN_2 = "9780132350884"


class FakeDate(date):
    """Date subclass with a frozen ``today()`` — still comparable with and
    subtractable from real dates (deterministic timing, Volume 3, Ch. 9.4)."""

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


def make_book(isbn=BOOK_ISBN, available=3, total=5):
    return SimpleNamespace(
        isbn=isbn,
        title="Clean Code",
        available_copies=available,
        total_copies=total,
    )


def make_txn(
    txn_id=1,
    book=None,
    due_days_from_today=LOAN_DAYS - 1,
    returned=False,
    fine=None,
):
    """A transaction issued LOAN_DAYS before its due date; due date is
    ``due_days_from_today`` days after TODAY (negative = already overdue)."""
    book = book or make_book()
    due_date = TODAY + timedelta(days=due_days_from_today)
    return SimpleNamespace(
        id=txn_id,
        book_isbn=book.isbn,
        book=book,
        student_name="Aarav Sharma",
        contact_number="9876543210",
        class_name="12",
        stream=Stream.Science,
        section="A",
        issue_date=due_date - timedelta(days=LOAN_DAYS),
        due_date=due_date,
        return_date=TODAY if returned else None,
        status=TransactionStatus.RETURNED if returned else TransactionStatus.ISSUED,
        fine_amount=fine,
        issued_by_user_id=1,
        returned_by_user_id=1 if returned else None,
        active_contact_lock=None if returned else "9876543210",
    )


class FakeTransactionRepository:
    def __init__(self):
        self.transactions = {}
        self.next_id = 1
        self.created = []
        self.last_filters = None

    def create(self, session, transaction_data):
        self.created.append(transaction_data)
        txn = SimpleNamespace(
            id=self.next_id,
            book_isbn=transaction_data["book_isbn"],
            book=make_book(transaction_data["book_isbn"]),
            student_name=transaction_data["student_name"],
            contact_number=transaction_data["contact_number"],
            class_name=transaction_data["class"],
            stream=transaction_data["stream"],
            section=transaction_data["section"],
            issue_date=transaction_data["issue_date"],
            due_date=transaction_data["due_date"],
            return_date=None,
            status=TransactionStatus.ISSUED,
            fine_amount=None,
            issued_by_user_id=transaction_data["issued_by_user_id"],
            returned_by_user_id=None,
            active_contact_lock=transaction_data["contact_number"],
        )
        self.transactions[txn.id] = txn
        self.next_id += 1
        return txn

    def get_by_id(self, session, transaction_id):
        return self.transactions.get(transaction_id)

    def get_active_by_contact(self, session, contact_number, book_isbn=None):
        return [
            txn
            for txn in self.transactions.values()
            if txn.status == TransactionStatus.ISSUED
            and txn.contact_number == contact_number
            and (book_isbn is None or txn.book_isbn == book_isbn)
        ]

    def update(self, session, transaction):
        self.transactions[transaction.id] = transaction

    def list_by_filters(
        self,
        session,
        page,
        page_size,
        status=None,
        start_date=None,
        end_date=None,
        book_search=None,
        borrower_search=None,
        user_id=None,
        include_returned_by=False,
    ):
        self.last_filters = {
            "page": page,
            "page_size": page_size,
            "status": status,
            "start_date": start_date,
            "end_date": end_date,
            "book_search": book_search,
            "borrower_search": borrower_search,
            "user_id": user_id,
            "include_returned_by": include_returned_by,
        }
        return [], 0


class FakeBookRepository:
    def __init__(self, books=None):
        self.books = {b.isbn: b for b in (books or [])}
        self.adjustments = []
        self.raise_on_adjust = None

    def get_by_isbn(self, session, isbn):
        return self.books.get(isbn)

    def adjust_available_copies(self, session, isbn, delta):
        if self.raise_on_adjust:
            raise self.raise_on_adjust
        self.adjustments.append((isbn, delta))


class FakeSettingsRepository:
    def __init__(self, values=None):
        self.values = values or {
            "loan_period_days": "14",
            "fine_enabled": "false",
            "fine_rate_per_day": "0.00",
        }

    def get_value(self, session, key):
        return self.values.get(key)


def make_service(books=None, txn_repo=None, settings=None):
    txn_repo = txn_repo or FakeTransactionRepository()
    return (
        TransactionService(
            FakeDatabase(),
            txn_repo,
            FakeBookRepository(books),
            FakeSettingsRepository(settings),
        ),
        txn_repo,
    )


def issue_input(book_isbn=BOOK_ISBN, contact="9876543210", stream="Science", student="Aarav Sharma"):
    return IssueInput(
        book_isbn=book_isbn,
        student_name=student,
        contact_number=contact,
        class_name="12",
        stream=stream,
        section="A",
    )


@mock.patch("app.services.transaction_service.date", FakeDate)
class IssueBookTests(unittest.TestCase):
    def test_issue_success(self):
        service, txn_repo = make_service(books=[make_book(available=3)])
        dto = service.issue_book(issue_input(), STAFF)
        self.assertEqual(dto.status, STATUS_ISSUED)
        self.assertEqual(dto.book_title, "Clean Code")
        self.assertEqual(dto.issue_date, TODAY)
        self.assertEqual(dto.due_date, TODAY + timedelta(days=14))
        created = txn_repo.created[0]
        self.assertEqual(created["issued_by_user_id"], 1)
        self.assertEqual(created["class"], "12")
        self.assertEqual(created["contact_number"], "9876543210")

    def test_issue_empty_section_allowed(self):
        # ponytail: empty Section reaches the service as None — must store
        # "" instead of raising AttributeError.
        service, txn_repo = make_service(books=[make_book(available=3)])
        payload = IssueInput(
            book_isbn=BOOK_ISBN,
            student_name="Aarav Sharma",
            contact_number="9876543210",
            class_name="10",
            stream="",
            section=None,
        )
        dto = service.issue_book(payload, STAFF)
        self.assertEqual(dto.status, STATUS_ISSUED)
        self.assertEqual(txn_repo.created[0]["section"], "")

    def test_issue_decrements_available_copies(self):
        service, _ = make_service(books=[make_book(available=3)])
        service.issue_book(issue_input(), STAFF)
        self.assertEqual(service._book_repo.adjustments, [(BOOK_ISBN, -1)])

    def test_issue_book_not_found(self):
        service, txn_repo = make_service(books=[])
        with self.assertRaises(RecordNotFoundError):
            service.issue_book(issue_input(book_isbn="0000000000"), STAFF)
        self.assertEqual(txn_repo.created, [])

    def test_issue_zero_available_rejected(self):
        service, txn_repo = make_service(books=[make_book(available=0)])
        with self.assertRaises(InsufficientAvailabilityError):
            service.issue_book(issue_input(), STAFF)
        self.assertEqual(txn_repo.created, [])
        self.assertEqual(service._book_repo.adjustments, [])

    def test_issue_duplicate_active_contact_same_book(self):
        book = make_book()
        service, _ = make_service(books=[book])
        service._txn_repo.transactions[1] = make_txn(book=book)
        with self.assertRaises(DuplicateResourceError):
            service.issue_book(issue_input(), STAFF)
        self.assertEqual(service._book_repo.adjustments, [])

    def test_issue_same_contact_different_book_allowed(self):
        book = make_book(isbn=BOOK_ISBN)
        other = make_book(isbn=BOOK_ISBN_2)
        service, _ = make_service(books=[book, other])
        service._txn_repo.transactions[1] = make_txn(book=book)
        dto = service.issue_book(issue_input(book_isbn=BOOK_ISBN_2), STAFF)
        self.assertEqual(dto.book_isbn, BOOK_ISBN_2)

    def test_issue_historical_returned_loan_does_not_block(self):
        book = make_book()
        service, _ = make_service(books=[book])
        service._txn_repo.transactions[1] = make_txn(book=book, returned=True)
        dto = service.issue_book(issue_input(), STAFF)
        self.assertEqual(dto.status, STATUS_ISSUED)

    def test_issue_missing_student_name(self):
        service, _ = make_service(books=[make_book()])
        with self.assertRaises(ValidationError):
            service.issue_book(issue_input(student="   "), STAFF)

    def test_issue_invalid_contact(self):
        service, _ = make_service(books=[make_book()])
        with self.assertRaises(ValidationError):
            service.issue_book(issue_input(contact="abc"), STAFF)

    def test_issue_missing_class(self):
        service, _ = make_service(books=[make_book()])
        with self.assertRaises(ValidationError):
            service.issue_book(
                IssueInput(
                    book_isbn=BOOK_ISBN,
                    student_name="A",
                    contact_number="9876543210",
                    class_name=" ",
                    stream="Science",
                    section="A",
                ),
                STAFF,
            )

    def test_issue_empty_section_stored_empty(self):
        # Section is optional (see test_issue_empty_section_allowed) — an
        # empty value issues fine and stores "".
        service, txn_repo = make_service(books=[make_book()])
        dto = service.issue_book(
            IssueInput(
                book_isbn=BOOK_ISBN,
                student_name="A",
                contact_number="9876543210",
                class_name="12",
                stream="Science",
                section="",
            ),
            STAFF,
        )
        self.assertEqual(dto.status, STATUS_ISSUED)
        self.assertEqual(txn_repo.created[0]["section"], "")

    def test_issue_invalid_stream(self):
        service, _ = make_service(books=[make_book()])
        with self.assertRaises(ValidationError):
            service.issue_book(issue_input(stream="IX"), STAFF)

    def test_issue_stream_stored_as_selected(self):
        service, txn_repo = make_service(books=[make_book()])
        dto = service.issue_book(issue_input(stream="Science"), STAFF)
        self.assertEqual(dto.stream, "Science")
        self.assertEqual(txn_repo.created[0]["stream"], "Science")

    def test_issue_custom_loan_period(self):
        service, _ = make_service(
            books=[make_book()], settings={"loan_period_days": "21"}
        )
        dto = service.issue_book(issue_input(), STAFF)
        self.assertEqual(dto.due_date, TODAY + timedelta(days=21))

    def test_issue_missing_loan_setting_uses_seed_default(self):
        service, _ = make_service(books=[make_book()], settings={})
        dto = service.issue_book(issue_input(), STAFF)
        self.assertEqual(dto.due_date, TODAY + timedelta(days=14))

    def test_issue_availability_race_translated(self):
        service, _ = make_service(books=[make_book(available=1)])
        service._book_repo.raise_on_adjust = IntegrityConstraintError("race")
        with self.assertRaises(InsufficientAvailabilityError):
            service.issue_book(issue_input(), STAFF)

    def test_issue_create_unique_violation_translated(self):
        class RacingTxnRepo(FakeTransactionRepository):
            def create(self, session, transaction_data):
                raise IntegrityConstraintError("duplicate")

        service, _ = make_service(books=[make_book()], txn_repo=RacingTxnRepo())
        with self.assertRaises(DuplicateResourceError):
            service.issue_book(issue_input(), STAFF)


@mock.patch("app.services.transaction_service.date", FakeDate)
class ReturnBookTests(unittest.TestCase):
    def test_return_on_time_success(self):
        service, _ = make_service(books=[make_book(available=3)])
        txn = make_txn(due_days_from_today=5)
        service._txn_repo.transactions[1] = txn
        result = service.return_book(1, STAFF)
        self.assertEqual(result.status, STATUS_RETURNED)
        self.assertIsNone(result.fine_amount)
        self.assertEqual(txn.status, TransactionStatus.RETURNED)
        self.assertEqual(txn.return_date, TODAY)
        self.assertEqual(txn.returned_by_user_id, 1)
        self.assertIsNone(txn.active_contact_lock)
        self.assertEqual(service._book_repo.adjustments, [(BOOK_ISBN, +1)])

    def test_return_overdue_fine_calculated(self):
        service, _ = make_service(
            books=[make_book()],
            settings={"fine_enabled": "true", "fine_rate_per_day": "2.50"},
        )
        txn = make_txn(due_days_from_today=-3)  # returned 3 days late
        service._txn_repo.transactions[1] = txn
        result = service.return_book(1, STAFF)
        self.assertEqual(result.fine_amount, Decimal("7.50"))
        self.assertEqual(txn.fine_amount, Decimal("7.50"))

    def test_return_overdue_fines_disabled(self):
        service, _ = make_service(
            books=[make_book()], settings={"fine_enabled": "false"}
        )
        txn = make_txn(due_days_from_today=-5)
        service._txn_repo.transactions[1] = txn
        result = service.return_book(1, STAFF)
        self.assertIsNone(result.fine_amount)

    def test_return_overdue_zero_rate(self):
        service, _ = make_service(
            books=[make_book()],
            settings={"fine_enabled": "true", "fine_rate_per_day": "0.00"},
        )
        txn = make_txn(due_days_from_today=-1)
        service._txn_repo.transactions[1] = txn
        result = service.return_book(1, STAFF)
        self.assertEqual(result.fine_amount, Decimal("0.00"))

    def test_return_not_found(self):
        service, _ = make_service(books=[])
        with self.assertRaises(RecordNotFoundError):
            service.return_book(999, STAFF)

    def test_return_already_returned(self):
        service, _ = make_service(books=[make_book()])
        service._txn_repo.transactions[1] = make_txn(returned=True)
        with self.assertRaises(ValidationError):
            service.return_book(1, STAFF)
        self.assertEqual(service._book_repo.adjustments, [])

    def test_return_does_not_require_available_copies(self):
        service, _ = make_service(books=[make_book(available=0)])
        service._txn_repo.transactions[1] = make_txn()
        result = service.return_book(1, STAFF)
        self.assertEqual(result.status, STATUS_RETURNED)
        self.assertEqual(service._book_repo.adjustments, [(BOOK_ISBN, +1)])


@mock.patch("app.services.transaction_service.date", FakeDate)
class ListTransactionTests(unittest.TestCase):
    def test_dto_derived_overdue(self):
        service, _ = make_service()
        rows = [make_txn(txn_id=1, due_days_from_today=-1)]
        service._txn_repo.list_by_filters = lambda session, page, page_size, **kw: (
            rows,
            1,
        )
        dtos, total = service.list_transactions()
        self.assertEqual(total, 1)
        self.assertEqual(dtos[0].status, STATUS_OVERDUE)

    def test_dto_issued_when_due_not_passed(self):
        service, _ = make_service()
        rows = [make_txn(txn_id=1, due_days_from_today=1)]
        service._txn_repo.list_by_filters = lambda session, page, page_size, **kw: (
            rows,
            1,
        )
        dtos, _ = service.list_transactions()
        self.assertEqual(dtos[0].status, STATUS_ISSUED)
        self.assertIsNone(dtos[0].fine_amount)

    def test_dto_returned_status(self):
        service, _ = make_service()
        rows = [make_txn(txn_id=1, returned=True, fine=Decimal("4.00"))]
        service._txn_repo.list_by_filters = lambda session, page, page_size, **kw: (
            rows,
            1,
        )
        dtos, _ = service.list_transactions()
        self.assertEqual(dtos[0].status, STATUS_RETURNED)
        self.assertEqual(dtos[0].fine_amount, Decimal("4.00"))
        self.assertEqual(dtos[0].return_date, TODAY)

    def test_dto_overdue_preview_fine_when_enabled(self):
        service, _ = make_service(
            settings={"fine_enabled": "true", "fine_rate_per_day": "1.00"}
        )
        rows = [make_txn(txn_id=1, due_days_from_today=-1)]
        service._txn_repo.list_by_filters = lambda session, page, page_size, **kw: (
            rows,
            1,
        )
        dtos, _ = service.list_transactions()
        self.assertEqual(dtos[0].fine_amount, Decimal("1.00"))

    def test_dto_overdue_preview_fine_when_disabled(self):
        service, _ = make_service(settings={"fine_enabled": "false"})
        rows = [make_txn(txn_id=1, due_days_from_today=-1)]
        service._txn_repo.list_by_filters = lambda session, page, page_size, **kw: (
            rows,
            1,
        )
        dtos, _ = service.list_transactions()
        self.assertIsNone(dtos[0].fine_amount)

    def test_status_normalized_to_uppercase(self):
        service, txn_repo = make_service()
        service.list_transactions(status="overdue", page=1, page_size=5)
        self.assertEqual(txn_repo.last_filters["status"], "OVERDUE")

    def test_filters_passed_through(self):
        service, txn_repo = make_service()
        service.list_transactions(
            status="Issued",
            start_date=TODAY,
            end_date=TODAY + timedelta(days=1),
            book_search="Clean",
            borrower_search="9876",
            page=2,
            page_size=20,
        )
        self.assertEqual(
            txn_repo.last_filters,
            {
                "page": 2,
                "page_size": 20,
                "status": "ISSUED",
                "start_date": TODAY,
                "end_date": TODAY + timedelta(days=1),
                "book_search": "Clean",
                "borrower_search": "9876",
                "user_id": None,
                "include_returned_by": False,
            },
        )

    def test_invalid_pagination_rejected(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.list_transactions(page=0)
        with self.assertRaises(ValidationError):
            service.list_active(page_size=0)

    def test_list_active_filters_issued_and_borrower(self):
        service, txn_repo = make_service()
        service.list_active(search_term="Aarav", page=1, page_size=10)
        self.assertEqual(txn_repo.last_filters["status"], "ISSUED")
        self.assertEqual(txn_repo.last_filters["borrower_search"], "Aarav")


class MyActivityTest(unittest.TestCase):
    """list_own_activity (Volume 1, Chapter 26; Volume 4, Section 35.6):
    Librarian-only guard, self-scoped issued-or-returned-by query."""

    LIBRARIAN_CTX = SessionContext(
        user_id=2, role="LIBRARIAN", full_name="Grace", email="grace@lms.local"
    )
    ADMIN_CTX = SessionContext(
        user_id=1, role="ADMINISTRATOR", full_name="Admin", email="admin@lms.local"
    )

    def test_librarian_only(self):
        service, _ = make_service()
        with self.assertRaises(UnauthorizedOperationError):
            service.list_own_activity(self.ADMIN_CTX)

    def test_scoped_to_acting_user_issued_or_returned(self):
        service, txn_repo = make_service()
        service.list_own_activity(self.LIBRARIAN_CTX)
        self.assertEqual(txn_repo.last_filters["user_id"], 2)
        self.assertTrue(txn_repo.last_filters["include_returned_by"])

    def test_filters_passed_through(self):
        service, txn_repo = make_service()
        service.list_own_activity(
            self.LIBRARIAN_CTX,
            start_date=TODAY,
            end_date=TODAY + timedelta(days=1),
            status="Returned",
            page=3,
            page_size=25,
        )
        self.assertEqual(txn_repo.last_filters["status"], "RETURNED")
        self.assertEqual(txn_repo.last_filters["start_date"], TODAY)
        self.assertEqual(txn_repo.last_filters["end_date"], TODAY + timedelta(days=1))
        self.assertEqual(txn_repo.last_filters["page"], 3)
        self.assertEqual(txn_repo.last_filters["page_size"], 25)

    def test_invalid_pagination_rejected(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.list_own_activity(self.LIBRARIAN_CTX, page=0)

    def test_status_normalized(self):
        service, txn_repo = make_service()
        service.list_own_activity(self.LIBRARIAN_CTX, status="overdue")
        self.assertEqual(txn_repo.last_filters["status"], "OVERDUE")


if __name__ == "__main__":
    unittest.main()
