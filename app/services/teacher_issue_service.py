"""TeacherIssueService — book loans to registry teachers.

Mirrors the student issue/return flow (availability precondition, loan
period from Settings, active-loan lock, derived Overdue status) with one
deliberate difference: teachers are never fined, so there is no fine
computation anywhere in this module and fine previews always read zero.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.config import SETTING_LOAN_PERIOD_DAYS
from app.core.database import Database
from app.core.exceptions import (
    DuplicateResourceError,
    InsufficientAvailabilityError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.teacher import TeacherIssueStatus
from app.repositories.interfaces import (
    BookRepositoryInterface,
    SettingsRepositoryInterface,
    TeacherIssueRepositoryInterface,
    TeacherRepositoryInterface,
)
from app.services.interfaces import TeacherIssueServiceInterface
from app.utils.validators import normalize_isbn

logger = logging.getLogger(__name__)

_PAGE_MIN = 1
_PAGE_SIZE_MIN = 1

_DEFAULT_LOAN_PERIOD_DAYS = 14

STATUS_ISSUED = "Issued"
STATUS_RETURNED = "Returned"
STATUS_OVERDUE = "Overdue"


@dataclass(frozen=True)
class TeacherIssueInput:
    """Presentation-layer input for Issue Book (teacher flow)."""

    book_isbn: str
    teacher_id: int


@dataclass(frozen=True)
class TeacherIssueDto:
    """Domain result DTO — never a raw ORM instance. ``status`` is the
    derived display value (Issued/Returned/Overdue)."""

    id: int
    book_isbn: str
    book_title: str
    teacher_id: int
    teacher_name: str
    teacher_contact: str
    issue_date: date
    due_date: date
    return_date: date | None
    status: str
    issued_by_user_id: int
    returned_by_user_id: int | None


@dataclass(frozen=True)
class TeacherReturnResult:
    """Result of a processed teacher return (never carries a fine)."""

    issue_id: int
    status: str


class TeacherIssueService(TeacherIssueServiceInterface):
    def __init__(
        self,
        database: Database,
        teacher_issue_repository: TeacherIssueRepositoryInterface,
        teacher_repository: TeacherRepositoryInterface,
        book_repository: BookRepositoryInterface,
        settings_repository: SettingsRepositoryInterface,
    ) -> None:
        self._database = database
        self._issue_repo = teacher_issue_repository
        self._teacher_repo = teacher_repository
        self._book_repo = book_repository
        self._settings_repo = settings_repository

    def issue_book(
        self, issue_input: TeacherIssueInput, context: SessionContext
    ) -> TeacherIssueDto:
        """Issue a book to a registry teacher. Atomically creates the issue
        record and decrements available_copies."""
        with self._database.session_scope() as session:
            teacher = self._teacher_repo.get_by_id(session, issue_input.teacher_id)
            if teacher is None:
                raise RecordNotFoundError("The requested teacher was not found.")
            if not teacher.is_active:
                raise ValidationError("This teacher is deactivated.")
            book = self._book_repo.get_by_isbn(session, normalize_isbn(issue_input.book_isbn))
            if book is None:
                raise RecordNotFoundError("The requested book was not found.")
            if book.available_copies <= 0:
                raise InsufficientAvailabilityError(
                    "This book has no available copies."
                )
            if self._issue_repo.get_active_by_teacher(
                session, teacher.id, book_isbn=book.isbn
            ):
                raise DuplicateResourceError(
                    "This teacher already has an active loan for this book."
                )
            value = self._settings_repo.get_value(session, SETTING_LOAN_PERIOD_DAYS)
            try:
                loan_days = int(value) if value is not None else _DEFAULT_LOAN_PERIOD_DAYS
            except (TypeError, ValueError):
                loan_days = _DEFAULT_LOAN_PERIOD_DAYS
            today = date.today()
            try:
                issue = self._issue_repo.create(
                    session,
                    {
                        "book_isbn": book.isbn,
                        "teacher_id": teacher.id,
                        "issue_date": today,
                        "due_date": today + timedelta(days=loan_days),
                        "issued_by_user_id": context.user_id,
                    },
                )
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "This teacher already has an active loan for this book."
                ) from error
            try:
                self._book_repo.adjust_available_copies(session, book.isbn, -1)
            except IntegrityConstraintError as error:
                raise InsufficientAvailabilityError(
                    "This book has no available copies."
                ) from error
            logger.info(
                "Book issued to teacher (issue_id=%s, book_isbn=%s, teacher_id=%s)",
                issue.id,
                book.isbn,
                teacher.id,
            )
            return self._to_dto(issue)

    def return_book(
        self, issue_id: int, context: SessionContext
    ) -> TeacherReturnResult:
        """Process a teacher book return: sets status, return date and
        returning-librarian attribution, clears the active-teacher lock —
        all atomically with the available_copies increment. No fine."""
        with self._database.session_scope() as session:
            issue = self._issue_repo.get_by_id(session, issue_id)
            if issue is None:
                raise RecordNotFoundError("The requested issue was not found.")
            if issue.status == TeacherIssueStatus.RETURNED:
                raise ValidationError("This book has already been returned.")
            issue.status = TeacherIssueStatus.RETURNED
            issue.return_date = date.today()
            issue.returned_by_user_id = context.user_id
            issue.active_teacher_lock = None
            self._issue_repo.update(session, issue)
            self._book_repo.adjust_available_copies(session, issue.book_isbn, +1)
            logger.info(
                "Teacher book returned (issue_id=%s, book_isbn=%s, user_id=%s)",
                issue.id,
                issue.book_isbn,
                context.user_id,
            )
            return TeacherReturnResult(issue_id=issue.id, status=STATUS_RETURNED)

    def list_issues(
        self,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        book_search: str | None = None,
        teacher_search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[TeacherIssueDto], int]:
        """Search and filter teacher issues by status, date range, book, and
        teacher. Status accepts Issued/Returned/Overdue in any casing."""
        self._validate_pagination(page, page_size)
        normalized = status.strip().upper() if status and status.strip() else None
        with self._database.session_scope() as session:
            rows, total = self._issue_repo.list_by_filters(
                session,
                page,
                page_size,
                status=normalized,
                start_date=start_date,
                end_date=end_date,
                book_search=book_search,
                teacher_search=teacher_search,
            )
            return [self._to_dto(row) for row in rows], total

    def _to_dto(self, issue) -> TeacherIssueDto:
        if issue.status == TeacherIssueStatus.RETURNED:
            status = STATUS_RETURNED
        elif issue.due_date < date.today():
            status = STATUS_OVERDUE
        else:
            status = STATUS_ISSUED
        return TeacherIssueDto(
            id=issue.id,
            book_isbn=issue.book_isbn,
            book_title=issue.book.title,
            teacher_id=issue.teacher_id,
            teacher_name=issue.teacher.name,
            teacher_contact=issue.teacher.contact_number,
            issue_date=issue.issue_date,
            due_date=issue.due_date,
            return_date=issue.return_date,
            status=status,
            issued_by_user_id=issue.issued_by_user_id,
            returned_by_user_id=issue.returned_by_user_id,
        )

    @staticmethod
    def _validate_pagination(page: int, page_size: int) -> None:
        if page < _PAGE_MIN or page_size < _PAGE_SIZE_MIN:
            raise ValidationError("Invalid page or page size.")
