"""BookService — Books module (Volume 1, Chapter 22; Volume 2, Chapter 16;
Volume 3, Chapters 11, 15.1, 22.2; Volume 4, Chapter 11).

Owns: ISBN checksum validation (FR-BOOK-02); available_copies never
exceeding total_copies nor falling below zero; total_copies reduction
below the issued count rejected; delete-blocking while active
transactions exist (FR-BOOK-04); category referential validation
(FR-BOOK-01). Both roles have full CRUD (Volume 3, Chapter 15.1), so no
role guard is required; the session context is still accepted for
auditability attribution (Volume 3, Chapter 24.1).
"""

import logging
from dataclasses import dataclass

from app.core.database import Database
from app.core.exceptions import (
    DuplicateResourceError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ResourceInUseError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.book import Book
from app.repositories.interfaces import (
    BookRepositoryInterface,
    CategoryRepositoryInterface,
)
from app.services.interfaces import BookServiceInterface
from app.utils.validators import is_valid_isbn, normalize_isbn

logger = logging.getLogger(__name__)

_PAGE_MIN = 1
_PAGE_SIZE_MIN = 1


@dataclass(frozen=True)
class BookInput:
    """Presentation-layer input for create/update (Volume 3, Chapter 11.1)."""

    title: str
    author: str
    isbn: str
    category_id: int
    total_copies: int | str
    shelf_location: str | None = None


@dataclass(frozen=True)
class BookDto:
    """Domain result DTO — never a raw ORM instance (Volume 3, Chapter 11.1).
    ISBN is the book primary key; there is no surrogate id."""

    title: str
    author: str
    isbn: str
    category_id: int
    category_name: str
    total_copies: int
    available_copies: int
    shelf_location: str | None
    is_active: bool


@dataclass(frozen=True)
class AvailableBookDto:
    """Compact DTO for the Issue dialog's searchable dropdown (FR-BOOK-07)."""

    title: str
    author: str
    isbn: str
    available_copies: int


class BookService(BookServiceInterface):
    def __init__(
        self,
        database: Database,
        book_repository: BookRepositoryInterface,
        category_repository: CategoryRepositoryInterface,
    ) -> None:
        self._database = database
        self._book_repo = book_repository
        self._category_repo = category_repository

    def search(
        self,
        search_term: str,
        category_id: int | None,
        page: int,
        page_size: int,
    ) -> tuple[list[BookDto], int]:
        self._validate_pagination(page, page_size)
        with self._database.session_scope() as session:
            rows, total = self._book_repo.search(
                session, search_term, category_id, page, page_size
            )
            return [self._to_dto(book) for book in rows], total

    def get_by_isbn(self, isbn: str) -> BookDto:
        with self._database.session_scope() as session:
            book = self._book_repo.get_by_isbn(session, normalize_isbn(isbn))
            if book is None:
                raise RecordNotFoundError("The requested book was not found.")
            return self._to_dto(book)

    def list_available(
        self, search_term: str, page: int, page_size: int
    ) -> tuple[list[AvailableBookDto], int]:
        self._validate_pagination(page, page_size)
        with self._database.session_scope() as session:
            rows, total = self._book_repo.list_available(
                session, search_term, page, page_size
            )
            return [
                AvailableBookDto(
                    title=book.title,
                    author=book.author,
                    isbn=book.isbn,
                    available_copies=book.available_copies,
                )
                for book in rows
            ], total

    def create(self, book_input: BookInput, context: SessionContext) -> BookDto:
        self._validate(book_input)
        isbn = normalize_isbn(book_input.isbn)
        total = self._coerce_positive_int(book_input.total_copies)
        with self._database.session_scope() as session:
            self._require_category(session, book_input.category_id)
            try:
                book = self._book_repo.create(
                    session,
                    {
                        "title": book_input.title,
                        "author": book_input.author,
                        "isbn": isbn,
                        "category_id": book_input.category_id,
                        "total_copies": total,
                        "available_copies": total,
                        "shelf_location": book_input.shelf_location,
                    },
                )
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "A book with this ISBN already exists."
                ) from error
            logger.info(
                "Book created (book_isbn=%s, user_id=%s)", book.isbn, context.user_id
            )
            return self._to_dto(book)

    def update(
        self, isbn: str, book_input: BookInput, context: SessionContext
    ) -> BookDto:
        self._validate(book_input)
        isbn = normalize_isbn(isbn)
        total = self._coerce_positive_int(book_input.total_copies)
        with self._database.session_scope() as session:
            book = self._book_repo.get_by_isbn(session, isbn)
            if book is None:
                raise RecordNotFoundError("The requested book was not found.")
            if normalize_isbn(book_input.isbn) != book.isbn:
                raise ValidationError(
                    "ISBN is the book's identity and cannot be changed."
                )
            self._require_category(session, book_input.category_id)
            issued = book.total_copies - book.available_copies
            if total < issued:
                raise ValidationError(
                    "Total Copies cannot be reduced below the number of "
                    "copies currently issued."
                )
            try:
                book.title = book_input.title.strip()
                book.author = book_input.author.strip()
                book.category_id = book_input.category_id
                book.total_copies = total
                book.shelf_location = (
                    book_input.shelf_location.strip()
                    if book_input.shelf_location
                    else None
                )
                self._book_repo.update(session, book)
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "A book with this ISBN already exists."
                ) from error
            logger.info(
                "Book updated (book_isbn=%s, user_id=%s)", book.isbn, context.user_id
            )
            return self._to_dto(book)

    def delete(self, isbn: str, context: SessionContext) -> None:
        isbn = normalize_isbn(isbn)
        with self._database.session_scope() as session:
            book = self._book_repo.get_by_isbn(session, isbn)
            if book is None:
                raise RecordNotFoundError("The requested book was not found.")
            if self._book_repo.has_active_transactions(session, isbn):
                raise ResourceInUseError(
                    "This book has active transactions and cannot be deleted."
                )
            if self._book_repo.has_any_transactions(session, isbn):
                book.is_active = False
                self._book_repo.update(session, book)
                logger.info(
                    "Book deactivated with transaction history "
                    "(book_isbn=%s, user_id=%s)",
                    book.isbn,
                    context.user_id,
                )
            else:
                self._book_repo.delete(session, book)
                logger.info(
                    "Book deleted (book_isbn=%s, user_id=%s)", isbn, context.user_id
                )

    def _validate(self, book_input: BookInput) -> None:
        if not book_input.title.strip():
            raise ValidationError("Title is required.")
        if not book_input.author.strip():
            raise ValidationError("Author is required.")
        if not is_valid_isbn(book_input.isbn):
            raise ValidationError("Enter a valid ISBN.")

    def _require_category(self, session, category_id: int) -> None:
        if self._category_repo.get_by_id(session, category_id) is None:
            raise ValidationError("Select a valid category.")

    @staticmethod
    def _validate_pagination(page: int, page_size: int) -> None:
        if page < _PAGE_MIN or page_size < _PAGE_SIZE_MIN:
            raise ValidationError("Invalid page or page size.")

    @staticmethod
    def _coerce_positive_int(value: int | str) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValidationError("Total Copies must be a positive integer.")
        if number < 1:
            raise ValidationError("Total Copies must be a positive integer.")
        return number

    @staticmethod
    def _to_dto(book: Book) -> BookDto:
        return BookDto(
            title=book.title,
            author=book.author,
            isbn=book.isbn,
            category_id=book.category_id,
            category_name=book.category.name,
            total_copies=book.total_copies,
            available_copies=book.available_copies,
            shelf_location=book.shelf_location,
            is_active=book.is_active,
        )
