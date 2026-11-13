import importlib
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta
from unittest.mock import patch

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.exceptions import UnauthorizedOperationError, ValidationError
from app.core.security import SessionContext
from app.models import Base, Book, Category, Notification, Stream, Transaction, TransactionStatus
from app.models.user import User, UserRole
from app.services.notification_service import NotificationDto, NotificationService

TODAY = date(2026, 9, 17)
STAFF = SessionContext(1, UserRole.LIBRARIAN.value, "Staff", "staff@example.test")
ADMIN = SessionContext(2, UserRole.ADMINISTRATOR.value, "Admin", "admin@example.test")


class NotificationServiceTest(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", self._foreign_keys)
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine)
        self.service = NotificationService(self.factory)
        with self.factory.begin() as session:
            session.add_all([
                User(id=ctx.user_id, full_name=ctx.full_name, email=ctx.email,
                     password_hash="unused", role=ctx.role)
                for ctx in (STAFF, ADMIN)
            ])
            session.add(Category(id=1, name="General"))
            session.flush()
            session.add(Book(isbn="9780306406157", title="A book", author="Author",
                             category_id=1, total_copies=100, available_copies=100))
        clock = patch("app.services.notification_service.date")
        self.clock = clock.start()
        self.clock.today.return_value = TODAY
        self.addCleanup(clock.stop)

    @staticmethod
    def _foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    def transaction(self, user=STAFF, issue=TODAY, due=None, returned=None, returned_by=None):
        with self.factory.begin() as session:
            row = Transaction(
                book_isbn="9780306406157", student_name="Student", contact_number="1234567890",
                class_name="12", stream=Stream.Science, section="A", issue_date=issue,
                due_date=due or issue + timedelta(days=14), return_date=returned,
                status=TransactionStatus.RETURNED if returned else TransactionStatus.ISSUED,
                issued_by_user_id=user.user_id, returned_by_user_id=returned_by,
            )
            session.add(row)
            session.flush()
            return row.id

    def keys(self, context=STAFF):
        with self.factory() as session:
            return set(session.scalars(select(Notification.event_key).where(
                Notification.user_id == context.user_id
            )))

    def test_refresh_generates_owned_events_and_dtos_only(self):
        issued = self.transaction()
        returned = self.transaction(returned=TODAY, returned_by=ADMIN.user_id)
        overdue = self.transaction(issue=TODAY - timedelta(days=20),
                                   due=TODAY - timedelta(days=1))
        self.transaction(user=ADMIN, returned=TODAY, returned_by=STAFF.user_id)
        self.assertEqual(self.service.list_notifications(STAFF), [])
        self.assertEqual(self.service.unread_count(STAFF), 0)
        self.assertIsNone(self.service.refresh(STAFF))
        self.assertEqual(self.keys(), {
            f"transaction:{issued}:issued", f"transaction:{returned}:issued",
            f"transaction:{returned}:returned", f"transaction:{overdue}:overdue",
        })
        rows = self.service.list_notifications(STAFF)
        self.assertEqual(len(rows), 4)
        self.assertEqual(self.service.unread_count(STAFF), 4)
        self.assertEqual(self.service.list_notifications(ADMIN), [])
        self.assertTrue(all(isinstance(row, NotificationDto) for row in rows))
        self.assertTrue(all(isinstance(row.created_at, datetime) for row in rows))
        self.assertTrue(all("A book" in row.message for row in rows))
        with self.assertRaises(FrozenInstanceError):
            rows[0].is_read = True

    def test_refresh_is_stable_after_read_dismiss_and_service_recreation(self):
        self.transaction()
        self.transaction()
        self.service.refresh(STAFF)
        first, second = self.service.list_notifications(STAFF)
        self.service.mark_read(STAFF, first.id)
        self.service.dismiss(STAFF, second.id)
        self.service = NotificationService(self.factory)
        self.service.refresh(STAFF)
        self.service.refresh(STAFF)
        self.assertEqual(self.service.list_notifications(STAFF), [replace(first, is_read=True)])
        self.assertEqual(self.service.unread_count(STAFF), 0)
        self.assertEqual(len(self.keys()), 2)
        with self.factory() as session:
            self.assertTrue(session.get(Notification, second.id).is_dismissed)

    def test_all_reads_and_writes_are_owner_scoped_including_admin(self):
        self.transaction()
        self.transaction(user=ADMIN)
        for context in (STAFF, ADMIN):
            self.service.refresh(context)
        staff_row = self.service.list_notifications(STAFF)[0]
        admin_row = self.service.list_notifications(ADMIN)[0]
        for actor, foreign in ((STAFF, admin_row), (ADMIN, staff_row)):
            self.service.mark_read(actor, foreign.id)
            self.service.dismiss(actor, foreign.id)
        self.assertEqual(self.service.list_notifications(STAFF), [staff_row])
        self.assertEqual(self.service.list_notifications(ADMIN), [admin_row])
        self.service.mark_all_read(ADMIN)
        self.assertEqual(self.service.unread_count(ADMIN), 0)
        self.assertEqual(self.service.unread_count(STAFF), 1)
        self.service.dismiss(ADMIN, admin_row.id)
        self.assertEqual(self.service.list_notifications(ADMIN), [])
        self.assertEqual(self.service.list_notifications(STAFF), [staff_row])

    def test_missing_and_dismissed_ids_are_noops(self):
        self.transaction()
        self.service.refresh(STAFF)
        row = self.service.list_notifications(STAFF)[0]
        for id in (row.id, row.id, 999999):
            self.assertIsNone(self.service.dismiss(STAFF, id))
            self.assertIsNone(self.service.mark_read(STAFF, id))
        self.assertEqual(self.service.list_notifications(STAFF), [])
        self.assertEqual(self.service.unread_count(STAFF), 0)

    def test_invalid_ids_are_rejected(self):
        for method in (self.service.mark_read, self.service.dismiss):
            for id in (None, True, 0, -1, "1", 1.5):
                with (self.subTest(method=method.__name__, id=id),
                      self.assertRaises(ValidationError)):
                    method(STAFF, id)

    def test_unauthorized_contexts_rejected_by_every_operation(self):
        contexts = [replace(STAFF, role="UNKNOWN"), replace(STAFF, user_id=999),
                    replace(STAFF, role=UserRole.ADMINISTRATOR.value)]
        with self.factory.begin() as session:
            session.get(User, ADMIN.user_id).is_active = False
        contexts.append(ADMIN)
        for context in contexts:
            for name, args in (
                ("list_notifications", ()), ("unread_count", ()), ("mark_read", (1,)),
                ("mark_all_read", ()), ("dismiss", (1,)), ("refresh", ()),
            ):
                with (self.subTest(context=context, method=name),
                      self.assertRaises(UnauthorizedOperationError)):
                    getattr(self.service, name)(context, *args)

    def test_history_window_and_overdue_boundaries(self):
        boundary = self.transaction(issue=TODAY - timedelta(days=6))
        self.transaction(issue=TODAY - timedelta(days=7))
        self.transaction(issue=TODAY - timedelta(days=30),
                         returned=TODAY - timedelta(days=7))
        recent_return = self.transaction(issue=TODAY - timedelta(days=30),
                                         returned=TODAY - timedelta(days=6))
        old_overdue = self.transaction(issue=TODAY - timedelta(days=90))
        due_today = self.transaction(due=TODAY)
        self.transaction(issue=TODAY + timedelta(days=1))
        self.service.refresh(STAFF)
        self.assertEqual(self.keys(), {
            f"transaction:{boundary}:issued", f"transaction:{recent_return}:returned",
            f"transaction:{old_overdue}:overdue", f"transaction:{due_today}:issued",
        })
        self.clock.today.return_value = TODAY + timedelta(days=1)
        self.service.refresh(STAFF)
        self.assertIn(f"transaction:{due_today}:overdue", self.keys())

    def test_return_after_refresh_adds_one_event_without_resetting_read_state(self):
        id = self.transaction(issue=TODAY - timedelta(days=20))
        self.service.refresh(STAFF)
        overdue = self.service.list_notifications(STAFF)[0]
        self.service.mark_read(STAFF, overdue.id)
        with self.factory.begin() as session:
            row = session.get(Transaction, id)
            row.status = TransactionStatus.RETURNED
            row.return_date = TODAY
            row.returned_by_user_id = ADMIN.user_id
        self.service.refresh(STAFF)
        self.service.refresh(STAFF)
        self.assertEqual(self.keys(), {f"transaction:{id}:overdue", f"transaction:{id}:returned"})
        self.assertEqual(self.service.unread_count(STAFF), 1)
        self.assertIn(replace(overdue, is_read=True), self.service.list_notifications(STAFF))

    def test_list_is_bounded_and_ordered_but_count_and_mark_all_cover_all(self):
        created = datetime(2026, 9, 17, 12)
        with self.factory.begin() as session:
            session.add_all([
                Notification(user_id=STAFF.user_id, event_key=f"event:{i}", message=str(i),
                             created_at=created)
                for i in range(60)
            ])
        rows = self.service.list_notifications(STAFF)
        self.assertEqual([row.message for row in rows], [str(i) for i in range(59, 9, -1)])
        self.assertEqual(self.service.unread_count(STAFF), 60)
        self.service.mark_all_read(STAFF)
        self.assertEqual(self.service.unread_count(STAFF), 0)

    def test_unique_user_event_constraint_and_foreign_key(self):
        self.transaction()
        self.service.refresh(STAFF)
        key = next(iter(self.keys()))
        with self.assertRaises(IntegrityError), self.factory.begin() as session:
            session.add(Notification(user_id=STAFF.user_id, event_key=key, message="duplicate"))
        with self.factory.begin() as session:
            session.add(Notification(user_id=ADMIN.user_id, event_key=key, message="different user"))
        with self.assertRaises(IntegrityError), self.factory.begin() as session:
            session.add(Notification(user_id=999, event_key=key, message="missing user"))
        self.assertEqual(self.service.unread_count(STAFF), 1)

    def test_migration_upgrade_matches_metadata_and_downgrade_preserves_existing_data(self):
        migration = importlib.import_module("migrations.versions.0003_notifications")
        self.assertEqual(migration.down_revision, "0002_stream_enum")
        self.transaction()
        Notification.__table__.drop(self.engine)
        with self.engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            with patch.object(migration, "op", operations):
                migration.upgrade()
                self.assertEqual(compare_metadata(
                    MigrationContext.configure(connection), Base.metadata
                ), [])
        self.service.refresh(STAFF)
        self.assertEqual(self.service.unread_count(STAFF), 1)
        with self.engine.begin() as connection:
            with patch.object(migration, "op", Operations(MigrationContext.configure(connection))):
                migration.downgrade()
            self.assertNotIn("notifications", inspect(connection).get_table_names())
            self.assertEqual(connection.scalar(select(func.count()).select_from(Transaction)), 1)
            self.assertEqual(connection.scalar(select(func.count()).select_from(User)), 2)


if __name__ == "__main__":
    unittest.main()
