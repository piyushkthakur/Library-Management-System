"""BookRepository — books aggregate root (Volume 3, Chapter 12; Volume 4,
Chapter 11)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.transaction import Transaction, TransactionStatus
from app.repositories.base import BaseRepository
from app.repositories.interfaces import BookRepositoryInterface
from app.utils.validators import normalize_isbn


class BookRepository(BaseRepository, BookRepositoryInterface):
    """Data access for the books table."""

    def get_by_isbn(self, session: Session, isbn: str) -> Book | None:
        try:
            return session.get(Book, normalize_isbn(isbn))
        except Exception as error:
            raise self._translate(error)

    def search(
        self,
        session: Session,
        search_term: str,
        category_id: int | None,
        page: int,
        page_size: int,
        include_inactive: bool = False,
    ) -> tuple[list[Book], int]:
        try:
            query = select(Book)
            if not include_inactive:
                query = query.where(Book.is_active.is_(True))
            if category_id is not None:
                query = query.where(Book.category_id == category_id)
            if search_term:
                term = f"%{search_term.strip()}%"
                query = query.where(
                    or_(
                        Book.title.like(term),
                        Book.author.like(term),
                        Book.isbn == normalize_isbn(search_term),
                    )
                )
            total = (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = (
                session.scalars(
                    query.order_by(Book.title)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .unique()
                .all()
            )
            return list(rows), total
        except Exception as error:
            raise self._translate(error)

    def list_available(
        self,
        session: Session,
        search_term: str,
        page: int,
        page_size: int,
    ) -> tuple[list[Book], int]:
        try:
            query = select(Book).where(
                Book.is_active.is_(True), Book.available_copies > 0
            )
            if search_term:
                term = f"%{search_term.strip()}%"
                query = query.where(
                    or_(Book.title.like(term), Book.isbn == normalize_isbn(search_term))
                )
            total = (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = (
                session.scalars(
                    query.order_by(Book.title)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .unique()
                .all()
            )
            return list(rows), total
        except Exception as error:
            raise self._translate(error)

    def create(self, session: Session, book_data: dict) -> Book:
        try:
            book = Book(
                title=book_data["title"].strip(),
                author=book_data["author"].strip(),
                isbn=normalize_isbn(book_data["isbn"]),
                category_id=book_data["category_id"],
                total_copies=book_data["total_copies"],
                available_copies=book_data["available_copies"],
                shelf_location=book_data.get("shelf_location"),
            )
            session.add(book)
            session.flush()
            return book
        except Exception as error:
            raise self._translate(error)

    def update(self, session: Session, book: Book) -> None:
        try:
            session.flush()
        except Exception as error:
            raise self._translate(error)

    def delete(self, session: Session, book: Book) -> None:
        """Hard-delete a book row (FR-BOOK-04) — only reached when the
        Service Layer has confirmed the book has no transaction history."""
        try:
            session.delete(book)
            session.flush()
        except Exception as error:
            raise self._translate(error)

    def adjust_available_copies(
        self, session: Session, isbn: str, delta: int
    ) -> None:
        """Adjust available_copies transactionally (FR-BOOK-06). Sole write
        path is the Issue/Return flow orchestrated by TransactionService
        (Volume 4, Chapter 25)."""
        try:
            book = session.get(Book, normalize_isbn(isbn))
            if book is not None:
                book.available_copies += delta
                session.flush()
        except Exception as error:
            raise self._translate(error)

    def has_any_transactions(self, session: Session, isbn: str) -> bool:
        try:
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(Transaction)
                    .where(Transaction.book_isbn == normalize_isbn(isbn))
                )
                or 0
            )
            return count > 0
        except Exception as error:
            raise self._translate(error)

    def has_active_transactions(self, session: Session, isbn: str) -> bool:
        try:
            count = (
                session.scalar(
                    select(func.count())
                    .select_from(Transaction)
                    .where(
                        Transaction.book_isbn == normalize_isbn(isbn),
                        Transaction.status == TransactionStatus.ISSUED,
                    )
                )
                or 0
            )
            return count > 0
        except Exception as error:
            raise self._translate(error)

    def count_active_books(self, session: Session) -> int:
        try:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(Book)
                    .where(Book.is_active.is_(True))
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)

    def total_available_copies(self, session: Session) -> int:
        try:
            return (
                session.scalar(
                    select(func.coalesce(func.sum(Book.available_copies), 0)).where(
                        Book.is_active.is_(True)
                    )
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)
