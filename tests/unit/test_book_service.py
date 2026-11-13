"""Unit tests for BookService with mocked repositories (Volume 3,
Chapter 34.2) — no database required.

Run: python -m unittest discover -s tests
"""

import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from app.core.exceptions import (
    DuplicateResourceError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ResourceInUseError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.user import UserRole
from app.services.book_service import BookInput, BookService

STAFF = SessionContext(
    user_id=1, role=UserRole.LIBRARIAN.value, full_name="Grace", email="grace@lms.local"
)

VALID_ISBN_10 = "0306406152"
VALID_ISBN_13 = "9780306406157"


class FakeSession:
    pass


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        yield self.session


def make_book(
    title="Clean Code",
    author="Robert Martin",
    isbn=VALID_ISBN_10,
    category_id=1,
    total=5,
    available=5,
    is_active=True,
    shelf_location="A-1",
):
    return SimpleNamespace(
        title=title,
        author=author,
        isbn=isbn,
        category_id=category_id,
        category=SimpleNamespace(name="Fiction"),
        total_copies=total,
        available_copies=available,
        shelf_location=shelf_location,
        is_active=is_active,
    )


class FakeBookRepository:
    def __init__(self, books=None):
        self.books = {b.isbn: b for b in (books or [])}
        self.deleted = set()
        self.deactivated = set()

    def search(
        self, session, search_term, category_id, page, page_size, include_inactive=False
    ):
        rows = [b for b in self.books.values() if b.is_active or include_inactive]
        return rows, len(rows)

    def list_available(self, session, search_term, page, page_size):
        rows = [
            b for b in self.books.values() if b.is_active and b.available_copies > 0
        ]
        return rows, len(rows)

    def get_by_isbn(self, session, isbn):
        return self.books.get(isbn)

    def create(self, session, book_data):
        if any(b.isbn == book_data["isbn"] for b in self.books.values()):
            raise IntegrityConstraintError("duplicate isbn")
        book = make_book(
            title=book_data["title"],
            author=book_data["author"],
            isbn=book_data["isbn"],
            category_id=book_data["category_id"],
            total=book_data["total_copies"],
            available=book_data["available_copies"],
            shelf_location=book_data.get("shelf_location"),
        )
        self.books[book.isbn] = book
        return book

    def update(self, session, book):
        pass

    def delete(self, session, book):
        self.deleted.add(book.isbn)
        self.books.pop(book.isbn, None)

    def adjust_available_copies(self, session, isbn, delta):
        pass

    def has_any_transactions(self, session, isbn):
        return isbn in self.books and getattr(self.books[isbn], "_history", False)

    def has_active_transactions(self, session, isbn):
        return isbn in self.books and getattr(self.books[isbn], "_active", False)

    def count_active_books(self, session):
        return sum(1 for b in self.books.values() if b.is_active)

    def total_available_copies(self, session):
        return sum(b.available_copies for b in self.books.values() if b.is_active)


class FakeCategoryRepository:
    def __init__(self, category_ids):
        self.category_ids = set(category_ids)

    def get_by_id(self, session, category_id):
        return (
            SimpleNamespace(id=category_id)
            if category_id in self.category_ids
            else None
        )

    def get_by_name(self, session, name):
        return None

    def list_all(self, session):
        return []

    def count_books_in_category(self, session, category_id):
        return 0

    def create(self, session, name, description):
        return SimpleNamespace(id=1)

    def update(self, session, category):
        pass

    def delete(self, session, category_id):
        pass


def make_service(books=None, category_ids=(1,)):
    return BookService(
        FakeDatabase(),
        FakeBookRepository(books),
        FakeCategoryRepository(category_ids),
    )


def valid_input(**overrides):
    data = {
        "title": "Clean Code",
        "author": "Robert Martin",
        "isbn": VALID_ISBN_10,
        "category_id": 1,
        "total_copies": "5",
        "shelf_location": "A-1",
    }
    data.update(overrides)
    return BookInput(**data)


class BookServiceTest(unittest.TestCase):
    def test_search_returns_dtos(self):
        service = make_service([make_book()])
        items, total = service.search("", None, 1, 25)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].category_name, "Fiction")

    def test_get_by_isbn_returns_dto(self):
        service = make_service([make_book()])
        dto = service.get_by_isbn(VALID_ISBN_10)
        self.assertEqual(dto.title, "Clean Code")

    def test_get_by_isbn_missing_raises(self):
        service = make_service()
        with self.assertRaises(RecordNotFoundError):
            service.get_by_isbn("0000000000")

    def test_get_by_isbn_normalizes_input(self):
        service = make_service([make_book()])
        dto = service.get_by_isbn("0-306-40615-2")
        self.assertEqual(dto.title, "Clean Code")

    def test_list_available_filters(self):
        issued = make_book(isbn=VALID_ISBN_13, title="Borrowed", available=0)
        service = make_service([make_book(), issued])
        items, total = service.list_available("", 1, 25)
        self.assertEqual(total, 1)
        self.assertEqual(items[0].title, "Clean Code")

    def test_create_success_sets_available_to_total(self):
        service = make_service()
        dto = service.create(valid_input(), STAFF)
        self.assertEqual(dto.total_copies, 5)
        self.assertEqual(dto.available_copies, 5)

    def test_create_normalizes_isbn_on_write(self):
        service = make_service()
        dto = service.create(valid_input(isbn="978-0-306-40615-7"), STAFF)
        self.assertEqual(dto.isbn, VALID_ISBN_13)

    def test_create_blank_title_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.create(valid_input(title="   "), STAFF)

    def test_create_blank_author_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.create(valid_input(author=""), STAFF)

    def test_create_invalid_isbn_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.create(valid_input(isbn="123456789"), STAFF)

    def test_create_non_positive_total_rejected(self):
        service = make_service()
        for bad in ("0", "-3", "abc"):
            with self.assertRaises(ValidationError, msg=str(bad)):
                service.create(valid_input(total_copies=bad), STAFF)

    def test_create_missing_category_rejected(self):
        service = make_service(category_ids=(2,))
        with self.assertRaises(ValidationError):
            service.create(valid_input(category_id=1), STAFF)

    def test_create_duplicate_isbn_rejected(self):
        service = make_service([make_book()])
        with self.assertRaises(DuplicateResourceError):
            service.create(valid_input(isbn=VALID_ISBN_10), STAFF)

    def test_update_success(self):
        service = make_service([make_book()])
        dto = service.update(VALID_ISBN_10, valid_input(title="Clean Code 2"), STAFF)
        self.assertEqual(dto.title, "Clean Code 2")

    def test_update_missing_raises(self):
        service = make_service()
        with self.assertRaises(RecordNotFoundError):
            service.update("0000000000", valid_input(), STAFF)

    def test_update_isbn_change_rejected(self):
        service = make_service([make_book()])
        with self.assertRaises(ValidationError):
            service.update(VALID_ISBN_10, valid_input(isbn=VALID_ISBN_13), STAFF)

    def test_update_total_below_issued_rejected(self):
        book = make_book(available=2)  # 3 issued
        service = make_service([book])
        with self.assertRaises(ValidationError):
            service.update(VALID_ISBN_10, valid_input(total_copies="2"), STAFF)

    def test_update_total_at_issued_accepted(self):
        book = make_book(available=2)  # 3 issued
        service = make_service([book])
        dto = service.update(VALID_ISBN_10, valid_input(total_copies="3"), STAFF)
        self.assertEqual(dto.total_copies, 3)

    def test_delete_with_active_transactions_rejected(self):
        book = make_book()
        book._active = True
        service = make_service([book])
        with self.assertRaises(ResourceInUseError):
            service.delete(VALID_ISBN_10, STAFF)

    def test_delete_with_history_deactivates(self):
        book = make_book()
        book._history = True
        service = make_service([book])
        service.delete(VALID_ISBN_10, STAFF)
        self.assertFalse(book.is_active)
        self.assertNotIn(VALID_ISBN_10, service._book_repo.deleted)

    def test_delete_without_history_hard_deletes(self):
        service = make_service([make_book()])
        service.delete(VALID_ISBN_10, STAFF)
        self.assertIn(VALID_ISBN_10, service._book_repo.deleted)

    def test_delete_missing_raises(self):
        service = make_service()
        with self.assertRaises(RecordNotFoundError):
            service.delete("0000000000", STAFF)

    def test_search_invalid_pagination_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.search("", None, 0, 25)


if __name__ == "__main__":
    unittest.main()
