"""TransactionService — Transactions module (Volume 1, Chapter 24; Volume 2,
Chapter 18; Volume 3, Chapters 11, 15.1; Volume 4, Chapters 12, 17).

Owns: issue precondition available_copies > 0 (FR-TXN-06); Stream restricted
to XI/XII; automatic due-date from the loan period in Settings (FR-TXN-03);
automatic overdue-fine calculation at return (FR-TXN-05); Contact Number
uniqueness among active transactions per book (Volume 1, Section 24.6;
Volume 4, Chapter 17.3); active_contact_lock maintenance (mirrored at issue,
cleared at return, within the same database transaction). Overdue is a
derived state computed at read time (Volume 3, Chapter 10.2). Both roles
have full issue/return access (Volume 3, Chapter 15.1), so no role guard is
required; the session context carries issuing/returning-librarian
attribution (FR-TXN-07).
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.core.config import (
    SETTING_FINE_ENABLED,
    SETTING_FINE_RATE_PER_DAY,
    SETTING_LOAN_PERIOD_DAYS,
)
from app.core.database import Database
from app.core.exceptions import (
    DuplicateResourceError,
    InsufficientAvailabilityError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.transaction import Stream, TransactionStatus
from app.models.user import UserRole
from app.repositories.interfaces import (
    BookRepositoryInterface,
    SettingsRepositoryInterface,
    TransactionRepositoryInterface,
)
from app.services.authorization import require_role
from app.services.interfaces import TransactionServiceInterface
from app.utils.validators import is_valid_phone, is_valid_stream, normalize_isbn

logger = logging.getLogger(__name__)

_PAGE_MIN = 1
_PAGE_SIZE_MIN = 1
_PENNY = Decimal("0.01")

# Documented seed defaults (Volume 4, Chapter 14.2) — used only when a
# settings row is absent, so issue/return never hard-codes operational values.
_DEFAULT_LOAN_PERIOD_DAYS = 14
_DEFAULT_FINE_ENABLED = False
_DEFAULT_FINE_RATE = Decimal("0.00")

STATUS_ISSUED = "Issued"
STATUS_RETURNED = "Returned"
STATUS_OVERDUE = "Overdue"


@dataclass(frozen=True)
class IssueInput:
    """Presentation-layer input for Issue Book (Volume 2, Chapter 18).
    ``class_name`` maps to the database column ``class`` (a reserved word)."""

    book_isbn: str
    student_name: str
    contact_number: str
    class_name: str
    stream: str
    section: str


@dataclass(frozen=True)
class TransactionDto:
    """Domain result DTO — never a raw ORM instance (Volume 3, Chapter 11.1).
    ``status`` is the derived display value (Issued/Returned/Overdue);
    ``fine_amount`` is the persisted fine for returned transactions or the
    computed preview for overdue ones, enabling the Return dialog's fine
    display (Volume 2, Chapter 18)."""

    id: int
    book_isbn: str
    book_title: str
    student_name: str
    contact_number: str
    class_name: str
    stream: str
    section: str
    issue_date: date
    due_date: date
    return_date: date | None
    status: str
    fine_amount: Decimal | None
    issued_by_user_id: int
    returned_by_user_id: int | None


@dataclass(frozen=True)
class ReturnResult:
    """Result of a processed return (FR-TXN-04/05)."""

    transaction_id: int
    status: str
    fine_amount: Decimal | None


class TransactionService(TransactionServiceInterface):
    def __init__(
        self,
        database: Database,
        transaction_repository: TransactionRepositoryInterface,
        book_repository: BookRepositoryInterface,
        settings_repository: SettingsRepositoryInterface,
    ) -> None:
        self._database = database
        self._txn_repo = transaction_repository
        self._book_repo = book_repository
        self._settings_repo = settings_repository

    def issue_book(
        self, issue_input: IssueInput, context: SessionContext
    ) -> TransactionDto:
        """Issue a book to a borrower (FR-TXN-01). Atomically creates the
        transaction and decrements available_copies (Volume 3, Chapter 11.2;
        Volume 4, Chapter 28.2)."""
        self._validate(issue_input)
        isbn = normalize_isbn(issue_input.book_isbn)
        with self._database.session_scope() as session:
            book = self._book_repo.get_by_isbn(session, isbn)
            if book is None:
                raise RecordNotFoundError("The requested book was not found.")
            if book.available_copies <= 0:
                raise InsufficientAvailabilityError(
                    "This book has no available copies."
                )
            if self._txn_repo.get_active_by_contact(
                session, issue_input.contact_number, book_isbn=book.isbn
            ):
                raise DuplicateResourceError(
                    "This contact number already has an active loan for this book."
                )
            loan_days = self._setting_int(
                session, SETTING_LOAN_PERIOD_DAYS, _DEFAULT_LOAN_PERIOD_DAYS
            )
            today = date.today()
            try:
                transaction = self._txn_repo.create(
                    session,
                    {
                        "book_isbn": book.isbn,
                        "student_name": issue_input.student_name.strip(),
                        "contact_number": issue_input.contact_number.strip(),
                        "class": issue_input.class_name.strip(),
                        "stream": issue_input.stream.strip(),
                        "section": (issue_input.section or "").strip(),
                        "issue_date": today,
                        "due_date": today + timedelta(days=loan_days),
                        "issued_by_user_id": context.user_id,
                    },
                )
            except IntegrityConstraintError as error:
                # Race: another session issued the same book to the same
                # contact between the pre-check and the insert.
                raise DuplicateResourceError(
                    "This contact number already has an active loan for this book."
                ) from error
            try:
                self._book_repo.adjust_available_copies(session, book.isbn, -1)
            except IntegrityConstraintError as error:
                # Race: the last available copy was issued by another session
                # (Volume 2, Chapter 18 — non-blocking error + refresh).
                raise InsufficientAvailabilityError(
                    "This book has no available copies."
                ) from error
            logger.info(
                "Book issued (txn_id=%s, book_isbn=%s, user_id=%s)",
                transaction.id,
                book.isbn,
                context.user_id,
            )
            return self._to_dto(transaction, book.title, session)

    def return_book(self, transaction_id: int, context: SessionContext) -> ReturnResult:
        """Process a book return (FR-TXN-04): sets status, return date, the
        computed overdue fine (FR-TXN-05), returning-librarian attribution,
        and clears the active-contact lock — all atomically with the
        available_copies increment (Volume 4, Chapters 17.3, 28.2)."""
        with self._database.session_scope() as session:
            transaction = self._txn_repo.get_by_id(session, transaction_id)
            if transaction is None:
                raise RecordNotFoundError("The requested transaction was not found.")
            if transaction.status == TransactionStatus.RETURNED:
                raise ValidationError("This transaction has already been returned.")
            today = date.today()
            fine = self._compute_fine(
                today,
                transaction.due_date,
                self._setting_bool(
                    session, SETTING_FINE_ENABLED, _DEFAULT_FINE_ENABLED
                ),
                self._setting_decimal(
                    session, SETTING_FINE_RATE_PER_DAY, _DEFAULT_FINE_RATE
                ),
            )
            transaction.status = TransactionStatus.RETURNED
            transaction.return_date = today
            transaction.fine_amount = fine
            transaction.returned_by_user_id = context.user_id
            transaction.active_contact_lock = None
            self._txn_repo.update(session, transaction)
            self._book_repo.adjust_available_copies(session, transaction.book_isbn, +1)
            logger.info(
                "Book returned (txn_id=%s, book_isbn=%s, user_id=%s, fine_amount=%s)",
                transaction.id,
                transaction.book_isbn,
                context.user_id,
                fine,
            )
            return ReturnResult(
                transaction_id=transaction.id,
                status=STATUS_RETURNED,
                fine_amount=fine,
            )

    def list_transactions(
        self,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        book_search: str | None = None,
        borrower_search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[TransactionDto], int]:
        """Search and filter transactions by status, date range, book, and
        borrower (FR-TXN-08). Status accepts Issued/Returned/Overdue in any
        casing; Overdue is derived at query time (Volume 3, Chapter 10.2)."""
        self._validate_pagination(page, page_size)
        normalized = status.strip().upper() if status and status.strip() else None
        with self._database.session_scope() as session:
            rows, total = self._txn_repo.list_by_filters(
                session,
                page,
                page_size,
                status=normalized,
                start_date=start_date,
                end_date=end_date,
                book_search=book_search,
                borrower_search=borrower_search,
            )
            return [self._to_dto(row, row.book.title, session) for row in rows], total

    def list_active(
        self, search_term: str | None = None, page: int = 1, page_size: int = 10
    ) -> tuple[list[TransactionDto], int]:
        """List currently issued transactions for the Return Book lookup
        (Volume 2, Chapter 18), optionally filtered by borrower name or
        contact number."""
        self._validate_pagination(page, page_size)
        with self._database.session_scope() as session:
            rows, total = self._txn_repo.list_by_filters(
                session,
                page,
                page_size,
                status="ISSUED",
                borrower_search=search_term,
            )
            return [self._to_dto(row, row.book.title, session) for row in rows], total

    def list_own_activity(
        self,
        context: SessionContext,
        start_date: date | None = None,
        end_date: date | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[TransactionDto], int]:
        """Read-only, self-scoped activity list (Volume 1, Chapter 26;
        Volume 2, Chapter 20; Volume 4, Section 35.6): transactions the
        acting Librarian issued or returned, most recent first. Librarians
        only — Administrators review cross-librarian data through Reports
        (Volume 1, Chapter 26)."""
        require_role(context, {UserRole.LIBRARIAN})
        self._validate_pagination(page, page_size)
        normalized = status.strip().upper() if status and status.strip() else None
        with self._database.session_scope() as session:
            rows, total = self._txn_repo.list_by_filters(
                session,
                page,
                page_size,
                status=normalized,
                start_date=start_date,
                end_date=end_date,
                user_id=context.user_id,
                include_returned_by=True,
            )
            return [self._to_dto(row, row.book.title, session) for row in rows], total

    def _validate(self, issue_input: IssueInput) -> None:
        if not issue_input.student_name.strip():
            raise ValidationError("Student Name is required.")
        if not is_valid_phone(issue_input.contact_number):
            raise ValidationError("Enter a valid phone number.")
        if not issue_input.class_name.strip():
            raise ValidationError("Class is required.")
        if issue_input.class_name in ("11", "12") and not is_valid_stream(issue_input.stream):
            raise ValidationError("Stream must be Science, Commerce, or Humanities.")

    def _compute_fine(
        self,
        return_date: date,
        due_date: date,
        fine_enabled: bool,
        rate_per_day: Decimal,
    ) -> Decimal | None:
        """Overdue fine = days late x configured rate; only when fines are
        enabled and the return is after the due date (FR-TXN-05)."""
        if not fine_enabled:
            return None
        days = (return_date - due_date).days
        if days <= 0:
            return None
        return (Decimal(days) * rate_per_day).quantize(_PENNY)

    def _to_dto(self, transaction, book_title: str, session) -> TransactionDto:
        today = date.today()
        if transaction.status == TransactionStatus.RETURNED:
            status = STATUS_RETURNED
            fine = transaction.fine_amount
        elif transaction.due_date < today:
            status = STATUS_OVERDUE
            fine = self._compute_fine(
                today,
                transaction.due_date,
                self._setting_bool(
                    session, SETTING_FINE_ENABLED, _DEFAULT_FINE_ENABLED
                ),
                self._setting_decimal(
                    session, SETTING_FINE_RATE_PER_DAY, _DEFAULT_FINE_RATE
                ),
            )
        else:
            status = STATUS_ISSUED
            fine = None
        return TransactionDto(
            id=transaction.id,
            book_isbn=transaction.book_isbn,
            book_title=book_title,
            student_name=transaction.student_name,
            contact_number=transaction.contact_number,
            class_name=transaction.class_name,
            stream=transaction.stream.value
            if isinstance(transaction.stream, Stream)
            else str(transaction.stream),
            section=transaction.section,
            issue_date=transaction.issue_date,
            due_date=transaction.due_date,
            return_date=transaction.return_date,
            status=status,
            fine_amount=fine,
            issued_by_user_id=transaction.issued_by_user_id,
            returned_by_user_id=transaction.returned_by_user_id,
        )

    def _setting_int(self, session, key: str, default: int) -> int:
        value = self._settings_repo.get_value(session, key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("Setting %s has a non-integer value; using default", key)
            return default

    def _setting_bool(self, session, key: str, default: bool) -> bool:
        value = self._settings_repo.get_value(session, key)
        if value is None:
            return default
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _setting_decimal(self, session, key: str, default: Decimal) -> Decimal:
        value = self._settings_repo.get_value(session, key)
        if value is None:
            return default
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            logger.warning("Setting %s has a non-numeric value; using default", key)
            return default

    @staticmethod
    def _validate_pagination(page: int, page_size: int) -> None:
        if page < _PAGE_MIN or page_size < _PAGE_SIZE_MIN:
            raise ValidationError("Invalid page or page size.")
