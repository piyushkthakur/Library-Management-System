"""Unit tests for LibrarianService with mocked repositories (Volume 3,
Chapter 34.2) — no database required. Deterministic; no timing-sensitive
behaviour exists in this service.

Run: python -m unittest discover -s tests
"""

import unittest
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace

from app.core.exceptions import (
    DuplicateResourceError,
    IntegrityConstraintError,
    RecordNotFoundError,
    UnauthorizedOperationError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.user import UserRole
from app.services.librarian_service import LibrarianInput, LibrarianService

ADMIN = SessionContext(
    user_id=1,
    role=UserRole.ADMINISTRATOR.value,
    full_name="Admin",
    email="admin@lms.local",
)
LIBRARIAN = SessionContext(
    user_id=2,
    role=UserRole.LIBRARIAN.value,
    full_name="Grace",
    email="grace@lms.local",
)


class FakeSession:
    pass


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        yield self.session


def make_user(
    user_id=10,
    name="Rohan Mehta",
    email="rohan@lms.local",
    is_active=True,
    created_at=None,
):
    return SimpleNamespace(
        id=user_id,
        full_name=name,
        email=email,
        role=UserRole.LIBRARIAN,
        is_active=is_active,
        created_at=created_at or datetime(2026, 8, 1, 9, 30, 0),
    )


class FakeUserRepository:
    def __init__(self, users=None):
        self.users = {u.id: u for u in (users or [])}
        self.next_id = max(self.users, default=0) + 1
        self.created = []

    def get_by_email(self, session, email):
        for user in self.users.values():
            if user.email.lower() == email.strip().lower():
                return user
        return None

    def get_by_id(self, session, user_id):
        return self.users.get(user_id)

    def create(self, session, full_name, email, password_hash, role):
        self.created.append((full_name, email, password_hash, role))
        user = make_user(self.next_id, name=full_name, email=email)
        self.users[user.id] = user
        self.next_id += 1
        return user

    def update(self, session, user):
        self.users[user.id] = user

    def list_librarians(self, session, page, page_size):
        rows = [u for u in self.users.values() if u.role == UserRole.LIBRARIAN]
        return rows, len(rows)


class FakeSettingsRepository:
    def __init__(self, values=None):
        self.values = values or {"password_min_length": "8"}

    def get_value(self, session, key):
        return self.values.get(key)


def make_service(users=None, settings=None):
    repo = FakeUserRepository(users)
    return (
        LibrarianService(FakeDatabase(), repo, FakeSettingsRepository(settings)),
        repo,
    )


def librarian_input(name="Rohan Mehta", email="rohan@lms.local", password="TempPass1"):
    return LibrarianInput(full_name=name, email=email, temporary_password=password)


class LibrarianServiceTests(unittest.TestCase):
    def test_create_success(self):
        service, repo = make_service()
        dto = service.create(ADMIN, librarian_input())
        self.assertEqual(dto.full_name, "Rohan Mehta")
        self.assertEqual(dto.email, "rohan@lms.local")
        self.assertTrue(dto.is_active)
        self.assertIsNotNone(dto.created_at)
        _, _, password_hash, role = repo.created[0]
        self.assertEqual(role, UserRole.LIBRARIAN.value)
        self.assertNotEqual(password_hash, "TempPass1")
        self.assertTrue(password_hash.startswith("$2"))

    def test_create_duplicate_email(self):
        existing = make_user(email="rohan@lms.local")
        service, _ = make_service(users=[existing])
        with self.assertRaises(DuplicateResourceError):
            service.create(ADMIN, librarian_input())

    def test_create_duplicate_email_case_insensitive(self):
        existing = make_user(email="Rohan@LMS.Local")
        service, _ = make_service(users=[existing])
        with self.assertRaises(DuplicateResourceError):
            service.create(ADMIN, librarian_input())

    def test_create_unique_violation_race_translated(self):
        class RacingRepo(FakeUserRepository):
            def create(self, session, full_name, email, password_hash, role):
                raise IntegrityConstraintError("duplicate")

        service, _ = make_service()
        service._user_repo = RacingRepo()
        with self.assertRaises(DuplicateResourceError):
            service.create(ADMIN, librarian_input())

    def test_create_missing_full_name(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.create(ADMIN, librarian_input(name="   "))

    def test_create_invalid_email(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.create(ADMIN, librarian_input(email="not-an-email"))

    def test_create_missing_password(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.create(ADMIN, LibrarianInput(full_name="A", email="a@lms.local"))

    def test_create_weak_password_rejected(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.create(ADMIN, librarian_input(password="short1"))

    def test_create_password_policy_uses_settings_min_length(self):
        service, _ = make_service(settings={"password_min_length": "12"})
        with self.assertRaises(ValidationError):
            service.create(ADMIN, librarian_input(password="ShortPass1"))
        dto = service.create(ADMIN, librarian_input(password="LongPass1234"))
        self.assertEqual(dto.email, "rohan@lms.local")

    def test_update_success(self):
        user = make_user()
        service, _ = make_service(users=[user])
        dto = service.update(
            ADMIN, user.id, librarian_input(name="R. Mehta", email="r.mehta@lms.local")
        )
        self.assertEqual(dto.full_name, "R. Mehta")
        self.assertEqual(dto.email, "r.mehta@lms.local")
        self.assertEqual(user.full_name, "R. Mehta")

    def test_update_preserves_password_hash_and_status(self):
        user = make_user()
        original_hash = "keep-me"
        user.password_hash = original_hash
        service, _ = make_service(users=[user])
        dto = service.update(
            ADMIN, user.id, librarian_input(name="Renamed", email="renamed@lms.local")
        )
        self.assertEqual(user.password_hash, original_hash)
        self.assertTrue(dto.is_active)

    def test_update_duplicate_email(self):
        other = make_user(user_id=11, email="other@lms.local")
        user = make_user(user_id=10, email="rohan@lms.local")
        service, _ = make_service(users=[other, user])
        with self.assertRaises(DuplicateResourceError):
            service.update(ADMIN, user.id, librarian_input(email="other@lms.local"))

    def test_update_own_email_unchanged_allowed(self):
        user = make_user(email="rohan@lms.local")
        service, _ = make_service(users=[user])
        dto = service.update(ADMIN, user.id, librarian_input(email="rohan@lms.local"))
        self.assertEqual(dto.email, "rohan@lms.local")

    def test_update_not_found(self):
        service, _ = make_service(users=[])
        with self.assertRaises(RecordNotFoundError):
            service.update(ADMIN, 99, librarian_input())

    def test_update_only_accepts_librarian_accounts(self):
        admin_user = SimpleNamespace(
            id=5,
            full_name="Boss",
            email="boss@lms.local",
            role=UserRole.ADMINISTRATOR,
            is_active=True,
            created_at=datetime(2026, 8, 1),
        )
        service, _ = make_service(users=[admin_user])
        with self.assertRaises(RecordNotFoundError):
            service.update(ADMIN, 5, librarian_input())

    def test_update_invalid_email(self):
        user = make_user()
        service, _ = make_service(users=[user])
        with self.assertRaises(ValidationError):
            service.update(ADMIN, user.id, librarian_input(email="bad"))

    def test_deactivate(self):
        user = make_user()
        service, _ = make_service(users=[user])
        service.set_active_status(ADMIN, user.id, False)
        self.assertFalse(user.is_active)

    def test_reactivate(self):
        user = make_user(is_active=False)
        service, _ = make_service(users=[user])
        service.set_active_status(ADMIN, user.id, True)
        self.assertTrue(user.is_active)

    def test_set_active_status_not_found(self):
        service, _ = make_service(users=[])
        with self.assertRaises(RecordNotFoundError):
            service.set_active_status(ADMIN, 99, False)

    def test_list_returns_dtos_and_total(self):
        service, _ = make_service(
            users=[make_user(user_id=10), make_user(user_id=11, email="b@lms.local")]
        )
        dtos, total = service.list_librarians(ADMIN)
        self.assertEqual(total, 2)
        self.assertEqual([d.email for d in dtos], ["rohan@lms.local", "b@lms.local"])

    def test_list_empty(self):
        service, _ = make_service(users=[])
        dtos, total = service.list_librarians(ADMIN)
        self.assertEqual((dtos, total), ([], 0))

    def test_list_invalid_pagination(self):
        service, _ = make_service(users=[])
        with self.assertRaises(ValidationError):
            service.list_librarians(ADMIN, page=0)
        with self.assertRaises(ValidationError):
            service.list_librarians(ADMIN, page_size=0)

    def test_librarian_cannot_list(self):
        service, _ = make_service(users=[])
        with self.assertRaises(UnauthorizedOperationError):
            service.list_librarians(LIBRARIAN)

    def test_librarian_cannot_create(self):
        service, _ = make_service(users=[])
        with self.assertRaises(UnauthorizedOperationError):
            service.create(LIBRARIAN, librarian_input())

    def test_librarian_cannot_update(self):
        service, _ = make_service(users=[])
        with self.assertRaises(UnauthorizedOperationError):
            service.update(LIBRARIAN, 1, librarian_input())

    def test_librarian_cannot_toggle_status(self):
        service, _ = make_service(users=[])
        with self.assertRaises(UnauthorizedOperationError):
            service.set_active_status(LIBRARIAN, 1, False)


if __name__ == "__main__":
    unittest.main()
