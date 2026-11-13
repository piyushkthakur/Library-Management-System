"""Unit tests for CategoryService with mocked repositories (Volume 3,
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
from app.services.category_service import CategoryInput, CategoryService

STAFF = SessionContext(
    user_id=1, role=UserRole.LIBRARIAN.value, full_name="Grace", email="grace@lms.local"
)


class FakeSession:
    pass


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        yield self.session


def make_category(category_id=1, name="Fiction", description="Novels", book_count=0):
    return SimpleNamespace(
        id=category_id, name=name, description=description, book_count=book_count
    )


class FakeCategoryRepository:
    def __init__(self, categories=None):
        self.categories = {c.id: c for c in (categories or [])}
        self.next_id = max(self.categories, default=0) + 1
        self.deleted = set()

    def get_by_id(self, session, category_id):
        return self.categories.get(category_id)

    def get_by_name(self, session, name):
        lower = name.strip().lower()
        return next(
            (c for c in self.categories.values() if c.name.lower() == lower), None
        )

    def list_all(self, session):
        return sorted(self.categories.values(), key=lambda c: c.name)

    def count_books_in_category(self, session, category_id):
        return self.categories[category_id].book_count

    def create(self, session, name, description):
        if self.get_by_name(session, name) is not None:
            raise IntegrityConstraintError("duplicate name")
        category = make_category(self.next_id, name.strip(), description)
        self.next_id += 1
        self.categories[category.id] = category
        return category

    def update(self, session, category):
        pass

    def delete(self, session, category_id):
        self.deleted.add(category_id)
        self.categories.pop(category_id, None)


def make_service(categories=None):
    return CategoryService(FakeDatabase(), FakeCategoryRepository(categories))


def valid_input(**overrides):
    data = {"name": "Fiction", "description": "Novels and stories"}
    data.update(overrides)
    return CategoryInput(**data)


class CategoryServiceTest(unittest.TestCase):
    def test_list_all_returns_dtos_with_counts(self):
        service = make_service(
            [make_category(book_count=3), make_category(2, "Science", None)]
        )
        dtos = service.list_all(STAFF)
        self.assertEqual(len(dtos), 2)
        self.assertEqual(dtos[0].name, "Fiction")
        self.assertEqual(dtos[0].book_count, 3)

    def test_list_all_ordered_by_name_ascending(self):
        service = make_service(
            [
                make_category(3, "Zulu", None),
                make_category(1, "Alpha", None),
                make_category(2, "Bravo", None),
            ]
        )
        first = service.list_all(STAFF)
        second = service.list_all(STAFF)
        self.assertEqual([d.name for d in first], ["Alpha", "Bravo", "Zulu"])
        self.assertEqual([d.name for d in second], ["Alpha", "Bravo", "Zulu"])

    def test_get_by_id_returns_dto(self):
        service = make_service([make_category()])
        dto = service.get_by_id(1)
        self.assertEqual(dto.name, "Fiction")

    def test_get_by_id_missing_raises(self):
        service = make_service()
        with self.assertRaises(RecordNotFoundError):
            service.get_by_id(99)

    def test_create_success(self):
        service = make_service()
        dto = service.create(valid_input(), STAFF)
        self.assertEqual(dto.name, "Fiction")
        self.assertEqual(dto.book_count, 0)

    def test_create_normalizes_whitespace(self):
        service = make_service()
        dto = service.create(valid_input(name="  Science   "), STAFF)
        self.assertEqual(dto.name, "Science")

    def test_create_collapses_internal_spaces(self):
        service = make_service()
        dto = service.create(valid_input(name="Computer   Science"), STAFF)
        self.assertEqual(dto.name, "Computer Science")

    def test_duplicate_detection_normalizes_whitespace(self):
        service = make_service([make_category()])
        with self.assertRaises(DuplicateResourceError):
            service.create(valid_input(name="  Fiction  "), STAFF)

    def test_duplicate_detection_ignores_case(self):
        service = make_service([make_category()])
        with self.assertRaises(DuplicateResourceError):
            service.create(valid_input(name="FICTION"), STAFF)

    def test_update_normalizes_whitespace(self):
        service = make_service([make_category()])
        dto = service.update(1, valid_input(name="  Sci-Fi  "), STAFF)
        self.assertEqual(dto.name, "Sci-Fi")

    def test_create_blank_name_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.create(valid_input(name="   "), STAFF)

    def test_create_name_too_long_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.create(valid_input(name="x" * 101), STAFF)

    def test_create_description_too_long_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.create(valid_input(description="x" * 501), STAFF)

    def test_create_duplicate_name_case_insensitive_rejected(self):
        service = make_service([make_category()])
        with self.assertRaises(DuplicateResourceError):
            service.create(valid_input(name="fiction"), STAFF)

    def test_update_success_clears_description(self):
        service = make_service([make_category()])
        dto = service.update(1, valid_input(name="Sci-Fi", description="  "), STAFF)
        self.assertEqual(dto.name, "Sci-Fi")
        self.assertIsNone(dto.description)

    def test_update_missing_raises(self):
        service = make_service()
        with self.assertRaises(RecordNotFoundError):
            service.update(99, valid_input(), STAFF)

    def test_update_to_duplicate_name_rejected(self):
        service = make_service(
            [make_category(1, "Fiction"), make_category(2, "Science")]
        )
        with self.assertRaises(DuplicateResourceError):
            service.update(1, valid_input(name="science"), STAFF)

    def test_update_keeping_own_name_allowed(self):
        service = make_service([make_category()])
        dto = service.update(1, valid_input(name="Fiction"), STAFF)
        self.assertEqual(dto.name, "Fiction")

    def test_delete_with_assigned_books_rejected(self):
        service = make_service([make_category(book_count=2)])
        with self.assertRaises(ResourceInUseError):
            service.delete(1, STAFF)

    def test_delete_success(self):
        service = make_service([make_category()])
        service.delete(1, STAFF)
        self.assertIn(1, service._category_repo.deleted)

    def test_delete_missing_raises(self):
        service = make_service()
        with self.assertRaises(RecordNotFoundError):
            service.delete(99, STAFF)


if __name__ == "__main__":
    unittest.main()
