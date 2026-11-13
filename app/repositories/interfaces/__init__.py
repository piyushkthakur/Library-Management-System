"""Repository interfaces (Volume 3, Chapter 12.2).

Services depend on these abstractions — never on concrete SQLAlchemy session
logic — so implementations can be swapped or mocked in tests (Dependency
Inversion Principle, Volume 3, Chapter 34).
"""

from abc import ABC, abstractmethod
from datetime import date, datetime

from sqlalchemy.orm import Session


class UserRepositoryInterface(ABC):
    @abstractmethod
    def get_by_email(self, session: Session, email: str):
        """Return the user with the given email, or None."""

    @abstractmethod
    def get_by_id(self, session: Session, user_id: int):
        """Return the user with the given id."""

    @abstractmethod
    def count_admins(self, session: Session) -> int:
        """Return the number of ADMINISTRATOR accounts."""

    @abstractmethod
    def create(
        self,
        session: Session,
        full_name: str,
        email: str,
        password_hash: str,
        role: str,
    ) -> object:
        """Create and return a new user."""

    @abstractmethod
    def update(self, session: Session, user) -> None:
        """Persist changes to an existing user."""

    @abstractmethod
    def list_librarians(
        self, session: Session, page: int, page_size: int
    ) -> tuple[list, int]:
        """Return a paginated list of LIBRARIAN accounts and the total count."""

    @abstractmethod
    def set_active_status(
        self, session: Session, user_id: int, is_active: bool
    ) -> None:
        """Activate or deactivate an account (FR-LIB-02)."""


class CategoryRepositoryInterface(ABC):
    @abstractmethod
    def get_by_id(self, session: Session, category_id: int):
        """Return the category with the given id, or None."""

    @abstractmethod
    def get_by_name(self, session: Session, name: str):
        """Return the category with the given name (case-insensitive), or None."""

    @abstractmethod
    def list_all(self, session: Session) -> list:
        """Return all categories ordered by name."""

    @abstractmethod
    def count_books_in_category(self, session: Session, category_id: int) -> int:
        """Return the number of books assigned to the category (FR-CAT-03)."""

    @abstractmethod
    def count_books_per_category(self, session: Session) -> dict[int, int]:
        """Return {category_id: book_count} for all categories in one query."""

    @abstractmethod
    def create(self, session: Session, name: str, description: str | None) -> object:
        """Create and return a new category."""

    @abstractmethod
    def update(self, session: Session, category) -> None:
        """Persist changes to an existing category."""

    @abstractmethod
    def delete(self, session: Session, category_id: int) -> None:
        """Delete a category row."""


class BookRepositoryInterface(ABC):
    @abstractmethod
    def get_by_isbn(self, session: Session, isbn: str):
        """Return the book with the given ISBN, or None."""

    @abstractmethod
    def search(
        self,
        session: Session,
        search_term: str,
        category_id: int | None,
        page: int,
        page_size: int,
        include_inactive: bool = False,
    ) -> tuple[list, int]:
        """Search books by title/author/ISBN and optional category filter
        (FR-BOOK-05). Returns (rows, total count)."""

    @abstractmethod
    def list_available(
        self, session: Session, search_term: str, page: int, page_size: int
    ) -> tuple[list, int]:
        """List active books with available_copies > 0 for the Issue dialog."""

    @abstractmethod
    def create(self, session: Session, book_data: dict) -> object:
        """Create and return a new book."""

    @abstractmethod
    def update(self, session: Session, book) -> None:
        """Persist changes to an existing book."""

    @abstractmethod
    def delete(self, session: Session, book) -> None:
        """Hard-delete a book row (FR-BOOK-04, history-free path)."""

    @abstractmethod
    def adjust_available_copies(
        self, session: Session, isbn: str, delta: int
    ) -> None:
        """Adjust available_copies by delta (FR-BOOK-06). Sole write path is
        the Issue/Return flow orchestrated by TransactionService (Volume 4,
        Chapter 25)."""

    @abstractmethod
    def has_any_transactions(self, session: Session, isbn: str) -> bool:
        """Return True when any transaction references the book."""

    @abstractmethod
    def has_active_transactions(self, session: Session, isbn: str) -> bool:
        """Return True when an unreturned transaction references the book
        (Volume 1, Chapter 22 delete-blocking rule)."""

    @abstractmethod
    def count_active_books(self, session: Session) -> int:
        """Return the count of active catalog titles (Dashboard KPI)."""

    @abstractmethod
    def total_available_copies(self, session: Session) -> int:
        """Return the sum of available_copies across active books."""


class TransactionRepositoryInterface(ABC):
    @abstractmethod
    def create(self, session: Session, transaction_data: dict) -> object:
        """Create and return a new transaction."""

    @abstractmethod
    def get_by_id(self, session: Session, transaction_id: int):
        """Return the transaction with the given id, or None."""

    @abstractmethod
    def get_active_by_contact(
        self, session: Session, contact_number: str, book_isbn: str | None = None
    ) -> list:
        """Return active (unreturned) transactions for a contact number,
        optionally narrowed to a single book (Volume 4, Chapter 17.3)."""

    @abstractmethod
    def get_overdue(self, session: Session, limit: int | None = None) -> list:
        """Return issued transactions with due_date passed, most overdue
        first (derived status, Volume 3, Chapter 10.2)."""

    @abstractmethod
    def count_active(self, session: Session) -> int:
        """Return the count of currently issued transactions (Dashboard KPI)."""

    @abstractmethod
    def count_overdue(self, session: Session) -> int:
        """Return the count of overdue transactions (Dashboard KPI)."""

    @abstractmethod
    def list_by_filters(
        self,
        session: Session,
        page: int,
        page_size: int,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        book_search: str | None = None,
        borrower_search: str | None = None,
        user_id: int | None = None,
        include_returned_by: bool = False,
    ) -> tuple[list, int]:
        """Filter transactions by status (ISSUED / RETURNED / OVERDUE,
        derived), date range, book, borrower, and optional acting user
        (FR-TXN-08; Volume 1, Chapter 26)."""

    @abstractmethod
    def update(self, session: Session, transaction) -> None:
        """Persist changes to an existing transaction."""

    @abstractmethod
    def circulation_trend(self, session: Session, days: int) -> list:
        """Return per-day issue/return counts over the rolling window."""

    @abstractmethod
    def aggregate_for_period(
        self,
        session: Session,
        start: date,
        end: date,
        scope_user_id: int | None,
        granularity: str | None = None,
        category_id: int | None = None,
    ) -> dict | list:
        """SQL-level aggregation of issued/returned/overdue/fines for a
        period (Volume 3, Chapter 26.1; Volume 4, Section 35.5), optionally
        scoped to a librarian's own issued activity (FR-RPT-04). All four
        aggregates respect the same scope predicate. ``granularity`` None
        returns the four report totals; 'day'/'week'/'month' return
        per-bucket rows for the Report preview grouping (Volume 2,
        Chapter 19). ``category_id`` restricts all aggregates to one
        category via a books join (optional Category filter, Volume 2,
        Chapter 19)."""


class TeacherRepositoryInterface(ABC):
    @abstractmethod
    def create(self, session: Session, teacher_data: dict) -> object:
        """Create and return a new teacher in the registry."""

    @abstractmethod
    def get_by_id(self, session: Session, teacher_id: int):
        """Return the teacher with the given id, or None."""

    @abstractmethod
    def get_by_contact(self, session: Session, contact_number: str):
        """Return the teacher with the given contact number, or None."""

    @abstractmethod
    def list(
        self,
        session: Session,
        page: int,
        page_size: int,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list, int]:
        """List registry teachers, most recently added last (name order)."""

    @abstractmethod
    def update(self, session: Session, teacher) -> None:
        """Persist changes to an existing teacher."""


class TeacherIssueRepositoryInterface(ABC):
    @abstractmethod
    def create(self, session: Session, issue_data: dict) -> object:
        """Create and return a new teacher book issue."""

    @abstractmethod
    def get_by_id(self, session: Session, issue_id: int):
        """Return the issue with the given id, or None."""

    @abstractmethod
    def get_active_by_teacher(
        self, session: Session, teacher_id: int, book_isbn: str | None = None
    ) -> list:
        """Return active (unreturned) issues for a teacher, optionally
        narrowed to a single book."""

    @abstractmethod
    def get_overdue(self, session: Session, limit: int | None = None) -> list:
        """Return issued teacher loans with due_date passed, most overdue
        first (derived status)."""

    @abstractmethod
    def count_active(self, session: Session) -> int:
        """Return the count of currently issued teacher loans."""

    @abstractmethod
    def list_by_filters(
        self,
        session: Session,
        page: int,
        page_size: int,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        book_search: str | None = None,
        teacher_search: str | None = None,
    ) -> tuple[list, int]:
        """Filter teacher issues by status (ISSUED / RETURNED / OVERDUE,
        derived), date range, book, and teacher."""

    @abstractmethod
    def update(self, session: Session, issue) -> None:
        """Persist changes to an existing teacher issue."""


class OtpRepositoryInterface(ABC):
    @abstractmethod
    def create(
        self, session: Session, user_id: int, otp_code_hash: str, expires_at: datetime
    ) -> object:
        """Create and return a new OTP record."""

    @abstractmethod
    def get_latest_unexpired(self, session: Session, user_id: int):
        """Return the most recent unexpired, unused OTP for a user, or None
        (Volume 4, Chapter 13.2)."""

    @abstractmethod
    def mark_used(self, session: Session, otp_id: int) -> None:
        """Atomically mark an OTP as used (single-use, FR-AUTH-07)."""


class SettingsRepositoryInterface(ABC):
    @abstractmethod
    def get_value(self, session: Session, key: str) -> str | None:
        """Return a setting value, or None when unset."""

    @abstractmethod
    def set_value(self, session: Session, key: str, value: str) -> None:
        """Upsert a setting key-value pair (FR-SET-02)."""

    @abstractmethod
    def get_all(self, session: Session) -> dict:
        """Return all settings as a key-value dict."""
