"""Service interfaces for Dependency Inversion (Volume 3, Chapter 34).

Every Service class is consumed through its abstract interface so that
concrete implementations can be swapped or mocked in tests without
modifying Presentation-layer code.
"""

from abc import ABC, abstractmethod

from app.core.security import SessionContext


class AuthServiceInterface(ABC):
    @abstractmethod
    def admin_exists(self) -> bool:
        """Return True when an Administrator account already exists
        (FR-AUTH-01/02; startup check, Volume 3, Chapter 16.1)."""

    @abstractmethod
    def register_administrator(
        self, full_name: str, email: str, password: str
    ) -> SessionContext:
        """Create the first-run Administrator account and return its session
        context (FR-AUTH-01). Rejected when one already exists (FR-AUTH-02)."""

    @abstractmethod
    def login(self, email: str, password: str) -> SessionContext:
        """Authenticate by email and bcrypt hash (FR-AUTH-04), enforcing
        account-active status and the login lockout window (FR-AUTH-09).
        Returns a SessionContext on success."""

    @abstractmethod
    def request_otp(self, email: str) -> None:
        """Generate, persist, and email a single-use 6-digit OTP with an
        expiry derived from the configured window (FR-AUTH-05/06). Returns
        the same success response for unknown accounts (no OTP, no email —
        anti-enumeration); raises a dedicated error for inactive accounts."""

    @abstractmethod
    def reset_password(self, email: str, otp_code: str, new_password: str) -> None:
        """Verify the latest unexpired, unused OTP and set a new password,
        marking the OTP used immediately (FR-AUTH-07; Volume 3, Chapter 14.3)."""


class SettingsServiceInterface(ABC):
    @abstractmethod
    def get_all(self, context: SessionContext) -> dict:
        """Return all settings as a key-value dict (FR-SET-02)."""

    @abstractmethod
    def update(self, context: SessionContext, changes: dict) -> None:
        """Validate and persist operational setting values (FR-SET-01/02)."""

    @abstractmethod
    def update_smtp_credentials(
        self, context: SessionContext, gmail_account: str, app_password: str
    ) -> None:
        """Persist SMTP credentials via environment-variable-backed
        configuration (Volume 2, Chapter 22); never in plaintext storage
        or logs."""

    @abstractmethod
    def send_test_email(self, context: SessionContext) -> None:
        """Verify SMTP configuration with a test message (Volume 2,
        Chapter 22)."""


class BookServiceInterface(ABC):
    @abstractmethod
    def search(
        self,
        search_term: str,
        category_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple:
        """Search books by title/author/ISBN and optional category filter
        (FR-BOOK-05), returning (DTOs, total count)."""

    @abstractmethod
    def get_by_isbn(self, isbn: str) -> object:
        """Return a book DTO, or raise RecordNotFoundError."""

    @abstractmethod
    def list_available(self, search_term: str, page: int, page_size: int) -> tuple:
        """List active books with available_copies > 0 for the Issue dialog
        (FR-BOOK-07)."""

    @abstractmethod
    def create(self, book_input, context: SessionContext) -> object:
        """Create a book (FR-BOOK-01/02); raises ValidationError,
        DuplicateResourceError on duplicate ISBN."""

    @abstractmethod
    def update(self, isbn: str, book_input, context: SessionContext) -> object:
        """Update a book (FR-BOOK-03), enforcing the total-copies reduction
        rule. The ISBN itself is immutable."""

    @abstractmethod
    def delete(self, isbn: str, context: SessionContext) -> None:
        """Delete or deactivate a book (FR-BOOK-04); raises
        ResourceInUseError while active transactions exist."""


class CategoryServiceInterface(ABC):
    @abstractmethod
    def list_all(self, context: SessionContext) -> list:
        """Return all categories ordered by name, with assigned-book counts."""

    @abstractmethod
    def get_by_id(self, category_id: int) -> object:
        """Return a category DTO, or raise RecordNotFoundError."""

    @abstractmethod
    def create(self, category_input, context: SessionContext) -> object:
        """Create a category (FR-CAT-01); raises DuplicateResourceError on
        case-insensitive name duplicates (FR-CAT-02)."""

    @abstractmethod
    def update(
        self, category_id: int, category_input, context: SessionContext
    ) -> object:
        """Update a category, preserving name uniqueness."""

    @abstractmethod
    def delete(self, category_id: int, context: SessionContext) -> None:
        """Delete a category (FR-CAT-03); raises ResourceInUseError while
        books remain assigned."""


class TransactionServiceInterface(ABC):
    @abstractmethod
    def issue_book(self, issue_input, context: SessionContext) -> object:
        """Issue a book to a borrower (FR-TXN-01/06), atomically creating
        the transaction and decrementing available_copies (Volume 3,
        Chapter 11.2)."""

    @abstractmethod
    def return_book(self, transaction_id: int, context: SessionContext) -> object:
        """Process a book return (FR-TXN-04/05), atomically closing the
        transaction and incrementing available_copies."""

    @abstractmethod
    def list_transactions(
        self,
        status: str | None = None,
        start_date=None,
        end_date=None,
        book_search: str | None = None,
        borrower_search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple:
        """Search and filter transactions by status, date range, book, and
        borrower (FR-TXN-08)."""

    @abstractmethod
    def list_active(
        self, search_term: str | None = None, page: int = 1, page_size: int = 10
    ) -> tuple:
        """List currently issued transactions for the Return Book lookup
        (Volume 2, Chapter 18)."""

    @abstractmethod
    def list_own_activity(
        self,
        context: SessionContext,
        start_date=None,
        end_date=None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple:
        """Return the Librarian's own activity — transactions issued or
        returned by the acting user, most recent first, filterable by date
        range and status (Volume 1, Chapter 26; Volume 4, Section 35.6).
        Librarians only."""


class LibrarianServiceInterface(ABC):
    @abstractmethod
    def list_librarians(
        self, context: SessionContext, page: int = 1, page_size: int = 10
    ) -> tuple:
        """List every librarian account (FR-LIB-01); Administrator only."""

    @abstractmethod
    def create(self, context: SessionContext, librarian_input) -> object:
        """Create a librarian account with an Active status and a hashed
        temporary password (FR-AUTH-03, FR-LIB-02); Administrator only."""

    @abstractmethod
    def update(self, context: SessionContext, user_id: int, librarian_input) -> object:
        """Edit a librarian's full name and email (FR-LIB-02); Administrator
        only. Password is not editable here."""

    @abstractmethod
    def set_active_status(
        self, context: SessionContext, user_id: int, is_active: bool
    ) -> None:
        """Activate or deactivate a librarian account (FR-LIB-02);
        Administrator only."""


class TeacherServiceInterface(ABC):
    @abstractmethod
    def list_teachers(
        self,
        context: SessionContext,
        search: str | None = None,
        active_only: bool = False,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple:
        """List registry teachers."""

    @abstractmethod
    def create(self, context: SessionContext, teacher_input) -> object:
        """Add a teacher to the registry with Active status."""

    @abstractmethod
    def update(
        self, context: SessionContext, teacher_id: int, teacher_input
    ) -> object:
        """Edit a teacher's name, contact number, and subject."""

    @abstractmethod
    def set_active_status(
        self, context: SessionContext, teacher_id: int, is_active: bool
    ) -> None:
        """Activate or deactivate a teacher in the registry."""


class TeacherIssueServiceInterface(ABC):
    @abstractmethod
    def issue_book(self, issue_input, context: SessionContext) -> object:
        """Issue a book to a teacher, atomically creating the issue record
        and decrementing available_copies. No fines apply to teachers."""

    @abstractmethod
    def return_book(self, issue_id: int, context: SessionContext) -> object:
        """Process a teacher book return, atomically closing the issue and
        incrementing available_copies."""

    @abstractmethod
    def list_issues(
        self,
        status: str | None = None,
        start_date=None,
        end_date=None,
        book_search: str | None = None,
        teacher_search: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple:
        """Search and filter teacher issues by status, date range, book,
        and teacher."""


class DashboardServiceInterface(ABC):
    @abstractmethod
    def get_dashboard(self) -> object:
        """Return the full read-only Dashboard snapshot — KPIs, 30-day
        circulation trend, category distribution, and top overdue items
        (FR-DASH-01/02/03; Volume 1, Chapter 21)."""


class ReportServiceInterface(ABC):
    @abstractmethod
    def generate_report(
        self,
        context: SessionContext,
        report_type: str,
        start_date=None,
        end_date=None,
        category_id=None,
        librarian_id=None,
        academic_year: str = "",
    ) -> object:
        """Generate a role-scoped report preview — grouped rows plus totals
        for the period (FR-RPT-01/04; Volume 1, Chapter 25)."""

    @abstractmethod
    def export(self, context: SessionContext, report: object, format: str) -> object:
        """Render the generated preview to PDF or Excel bytes
        (FR-RPT-02/03)."""


class ImportServiceInterface(ABC):
    @abstractmethod
    def preview(self, file_bytes: bytes, file_ext: str) -> object:
        """Parse a CSV/Excel/JSON file and return a preview DTO with per-row
        validation status (valid, merged, error)."""

    @abstractmethod
    def commit(self, preview, context: SessionContext) -> object:
        """Insert all valid rows from the preview into the database.
        Returns an ImportResultDto with counts."""
