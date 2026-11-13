"""Import preview/commit tests against real SQLite (Volume 3, Chapter 34):
same-ISBN rows merge their copies (summed, conflicts error out), catalog
repeats add copies to the cataloged book, and one bad row must never
poison the rest of the commit (savepoint per row)."""

import unittest
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import SessionContext
from app.models import Base
from app.models.book import Book
from app.models.category import Category
from app.models.user import UserRole
from app.repositories import BookRepository, CategoryRepository
from app.services.import_service import (
    BookImportService,
    ImportPreviewDto,
    ImportRowDto,
)

ISBN_A = "9780306406157"
ISBN_B = "9780132350884"

STAFF = SessionContext(
    user_id=1, role=UserRole.LIBRARIAN.value, full_name="Staff",
    email="staff@example.test",
)


class StubDatabase:
    """session_scope over SQLite (Database hardcodes MySQL pool args)."""

    def __init__(self):
        self.engine = create_engine("sqlite://")
        self._factory = sessionmaker(bind=self.engine)

    @contextmanager
    def session_scope(self):
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def make_service(db):
    return BookImportService(db, BookRepository(), CategoryRepository())


def csv_bytes(*rows):
    lines = ["Title,Author,ISBN,Category,TotalCopies,ShelfLocation"]
    for i, (title, isbn, copies, *rest) in enumerate(rows, start=1):
        shelf = rest[0] if rest else "A-1"
        lines.append(f"{title},Author,{isbn},Fiction,{copies},{shelf}")
    return "\n".join(lines).encode()


def valid_row(i, isbn):
    return ImportRowDto(
        row_number=i, title=f"Book {i}", author="Author", isbn=isbn,
        category_name="Fiction", total_copies=2, shelf_location=None,
        status="valid",
    )


class ImportServiceTest(unittest.TestCase):
    def setUp(self):
        self.db = StubDatabase()
        Base.metadata.create_all(self.db.engine)
        with self.db.session_scope() as session:
            session.add(Category(name="Fiction"))

    def _seed_book(self, isbn, title="Seeded", copies=3):
        with self.db.session_scope() as session:
            cat_id = session.query(Category).first().id
            session.add(Book(
                title=title, author="Author", isbn=isbn, category_id=cat_id,
                total_copies=copies, available_copies=copies,
            ))
            session.flush()

    def _totals(self, isbn):
        with self.db.session_scope() as session:
            row = session.execute(
                Book.__table__.select().where(Book.__table__.c.isbn == isbn)
            ).first()
            return row.total_copies, row.available_copies

    def test_preview_merges_within_file_repeat_and_sums_copies(self):
        service = make_service(self.db)
        preview = service.preview(
            csv_bytes(("T", ISBN_A, 2), ("T", ISBN_B, 2), ("T", ISBN_B, 3)),
            ".csv",
        )
        self.assertEqual(
            [r.status for r in preview.rows], ["valid", "valid", "merged"]
        )
        self.assertIn("Merged into row 2", preview.rows[2].error_message)
        self.assertEqual(preview.rows[1].total_copies, 5)
        self.assertEqual(
            (preview.valid_count, preview.merged_count, preview.error_count),
            (2, 1, 0),
        )

    def test_preview_conflicting_repeat_is_error(self):
        service = make_service(self.db)
        preview = service.preview(
            csv_bytes(("Title One", ISBN_A, 2), ("Other Title", ISBN_A, 2)),
            ".csv",
        )
        self.assertEqual([r.status for r in preview.rows], ["valid", "error"])
        self.assertIn("Conflicts with row 1", preview.rows[1].error_message)
        self.assertEqual(preview.rows[0].total_copies, 2)

    def test_preview_shelf_conflict_is_error(self):
        service = make_service(self.db)
        preview = service.preview(
            csv_bytes(("T", ISBN_A, 2, "A-1"), ("T", ISBN_A, 2, "B-9")),
            ".csv",
        )
        self.assertEqual([r.status for r in preview.rows], ["valid", "error"])
        self.assertIn("shelf location", preview.rows[1].error_message)

    def test_preview_empty_shelf_defers(self):
        service = make_service(self.db)
        preview = service.preview(
            csv_bytes(("T", ISBN_A, 2, "A-1"), ("T", ISBN_A, 3, "")),
            ".csv",
        )
        self.assertEqual([r.status for r in preview.rows], ["valid", "merged"])
        self.assertEqual(preview.rows[0].total_copies, 5)

    def test_commit_imports_merged_totals(self):
        service = make_service(self.db)
        preview = service.preview(
            csv_bytes(("T", ISBN_A, 2), ("T", ISBN_B, 2), ("T", ISBN_B, 3)),
            ".csv",
        )
        result = service.commit(preview, STAFF)
        self.assertEqual((result.imported, result.merged, result.errors), (2, 0, 0))
        self.assertEqual(self._totals(ISBN_A), (2, 2))
        self.assertEqual(self._totals(ISBN_B), (5, 5))

    def test_commit_adds_copies_to_cataloged_book(self):
        self._seed_book(ISBN_A, title="Seeded", copies=3)
        service = make_service(self.db)
        preview = service.preview(
            csv_bytes(("Seeded", ISBN_A, 2), ("Seeded", ISBN_A, 4)), ".csv"
        )
        self.assertEqual([r.status for r in preview.rows], ["merged", "merged"])
        self.assertIn("Exists in catalog", preview.rows[0].error_message)
        result = service.commit(preview, STAFF)
        self.assertEqual((result.imported, result.merged, result.errors), (0, 1, 0))
        self.assertEqual(self._totals(ISBN_A), (9, 9))

    def test_commit_rejects_repeat_conflicting_with_catalog(self):
        self._seed_book(ISBN_A, title="Seeded", copies=3)
        service = make_service(self.db)
        preview = service.preview(csv_bytes(("Wrong Title", ISBN_A, 2)), ".csv")
        self.assertEqual([r.status for r in preview.rows], ["error"])
        self.assertIn("Differs from cataloged book", preview.rows[0].error_message)
        result = service.commit(preview, STAFF)
        self.assertEqual((result.imported, result.merged, result.errors), (0, 0, 1))
        self.assertEqual(self._totals(ISBN_A), (3, 3))

    def test_commit_survives_unexpected_row_failure(self):
        # Hand-built colliding "valid" rows (e.g. a race preview missed):
        # the failure must count as one error, not abort the batch.
        service = make_service(self.db)
        preview = ImportPreviewDto(
            rows=(valid_row(1, ISBN_A), valid_row(2, ISBN_A)),
            valid_count=2, merged_count=0, error_count=0,
        )
        result = service.commit(preview, STAFF)
        self.assertEqual((result.imported, result.merged, result.errors), (1, 0, 1))
        with self.db.session_scope() as session:
            self.assertEqual(session.query(Book).count(), 1)


if __name__ == "__main__":
    unittest.main()
