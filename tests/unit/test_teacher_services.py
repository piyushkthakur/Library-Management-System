"""Unit tests for TeacherService + TeacherIssueService with mocked
repositories — no database required."""

import unittest
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from app.core.exceptions import (
    DuplicateResourceError,
    InsufficientAvailabilityError,
    RecordNotFoundError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.teacher import TeacherIssueStatus
from app.services.teacher_issue_service import (
    STATUS_ISSUED,
    STATUS_OVERDUE,
    STATUS_RETURNED,
    TeacherIssueInput,
    TeacherIssueService,
)
from app.services.teacher_service import TeacherInput, TeacherService

STAFF = SessionContext(
    user_id=1, role="Librarian", full_name="Grace", email="grace@lms.local"
)

BOOK_ISBN = "9780306406157"


class FakeSession:
    pass


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        yield self.session


def make_teacher(teacher_id=7, active=True):
    return SimpleNamespace(
        id=teacher_id,
        name="Ada Teacher",
        contact_number="9876543210",
        subject="Physics",
        is_active=active,
        created_at=datetime(2026, 8, 1, 10, 0, 0),
    )


def make_book(available=3):
    return SimpleNamespace(
        isbn=BOOK_ISBN, title="Clean Code", available_copies=available
    )


def make_issue(due_offset_days=13, returned=False):
    today = date.today()
    return SimpleNamespace(
        id=11,
        book_isbn=BOOK_ISBN,
        teacher_id=7,
        issue_date=today - timedelta(days=1),
        due_date=today + timedelta(days=due_offset_days),
        return_date=today if returned else None,
        status=TeacherIssueStatus.RETURNED if returned else TeacherIssueStatus.ISSUED,
        issued_by_user_id=1,
        returned_by_user_id=1 if returned else None,
        active_teacher_lock=None if returned else "7",
        book=SimpleNamespace(title="Clean Code"),
        teacher=SimpleNamespace(name="Ada Teacher", contact_number="9876543210"),
    )


class TeacherRegistryTests(unittest.TestCase):
    def setUp(self):
        self.repo = mock.Mock()
        self.service = TeacherService(FakeDatabase(), self.repo)

    def test_create_registers_active_teacher(self):
        self.repo.get_by_contact.return_value = None
        self.repo.create.return_value = make_teacher()
        dto = self.service.create(
            STAFF, TeacherInput("Ada Teacher", "9876543210", "Physics")
        )
        self.assertEqual(dto.name, "Ada Teacher")
        self.assertTrue(dto.is_active)

    def test_create_rejects_duplicate_contact(self):
        self.repo.get_by_contact.return_value = make_teacher()
        with self.assertRaises(DuplicateResourceError):
            self.service.create(
                STAFF, TeacherInput("Other", "9876543210", None)
            )

    def test_create_rejects_bad_phone(self):
        with self.assertRaises(ValidationError):
            self.service.create(STAFF, TeacherInput("Ada", "abc", None))

    def test_update_missing_teacher(self):
        self.repo.get_by_id.return_value = None
        with self.assertRaises(RecordNotFoundError):
            self.service.update(STAFF, 99, TeacherInput("Ada", "9876543210", None))

    def test_set_active_status_persists(self):
        teacher = make_teacher()
        self.repo.get_by_id.return_value = teacher
        self.service.set_active_status(STAFF, 7, False)
        self.assertFalse(teacher.is_active)
        self.repo.update.assert_called_once()


class TeacherIssueTests(unittest.TestCase):
    def setUp(self):
        self.issues = mock.Mock()
        self.teachers = mock.Mock()
        self.books = mock.Mock()
        self.settings = mock.Mock()
        self.settings.get_value.return_value = "14"
        self.service = TeacherIssueService(
            FakeDatabase(), self.issues, self.teachers, self.books, self.settings
        )

    def _prime_issue(self, teacher=None, book=None):
        teacher = teacher or make_teacher()
        book = book or make_book()
        self.teachers.get_by_id.return_value = teacher
        self.books.get_by_isbn.return_value = book
        self.issues.get_active_by_teacher.return_value = []
        return teacher, book

    def test_issue_happy_path_sets_two_week_due(self):
        self._prime_issue()
        self.issues.create.return_value = make_issue(due_offset_days=14)
        dto = self.service.issue_book(TeacherIssueInput(book_isbn=BOOK_ISBN, teacher_id=7), STAFF)
        self.assertEqual(dto.status, STATUS_ISSUED)
        self.assertEqual(dto.due_date, date.today() + timedelta(days=14))
        self.books.adjust_available_copies.assert_called_once_with(mock.ANY, BOOK_ISBN, -1)

    def test_issue_rejects_deactivated_teacher(self):
        self._prime_issue(teacher=make_teacher(active=False))
        with self.assertRaises(ValidationError):
            self.service.issue_book(TeacherIssueInput(BOOK_ISBN, 7), STAFF)

    def test_issue_rejects_no_copies(self):
        self._prime_issue(book=make_book(available=0))
        with self.assertRaises(InsufficientAvailabilityError):
            self.service.issue_book(TeacherIssueInput(BOOK_ISBN, 7), STAFF)

    def test_issue_rejects_duplicate_active_loan(self):
        self._prime_issue()
        self.issues.get_active_by_teacher.return_value = [make_issue()]
        with self.assertRaises(DuplicateResourceError):
            self.service.issue_book(TeacherIssueInput(BOOK_ISBN, 7), STAFF)

    def test_return_closes_without_fine(self):
        issue = make_issue()
        self.issues.get_by_id.return_value = issue
        result = self.service.return_book(11, STAFF)
        self.assertEqual(result.status, STATUS_RETURNED)
        self.assertIsNone(issue.active_teacher_lock)
        self.books.adjust_available_copies.assert_called_once_with(mock.ANY, BOOK_ISBN, +1)

    def test_return_twice_rejected(self):
        self.issues.get_by_id.return_value = make_issue(returned=True)
        with self.assertRaises(ValidationError):
            self.service.return_book(11, STAFF)

    def test_overdue_derived_at_read(self):
        self.issues.list_by_filters.return_value = ([make_issue(due_offset_days=-3)], 1)
        rows, total = self.service.list_issues(status="Overdue")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0].status, STATUS_OVERDUE)


if __name__ == "__main__":
    unittest.main()
