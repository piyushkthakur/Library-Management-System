"""TeacherIssueRepository — teacher_issues aggregate root.

Overdue is derived at query time (status ISSUED and due_date passed), mirroring
the student transactions table.
"""

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.teacher import Teacher, TeacherIssue, TeacherIssueStatus
from app.repositories.base import BaseRepository
from app.repositories.interfaces import TeacherIssueRepositoryInterface
from app.utils.validators import normalize_isbn


class TeacherIssueRepository(BaseRepository, TeacherIssueRepositoryInterface):
    """Data access for the teacher_issues table."""

    def create(self, session: Session, issue_data: dict) -> TeacherIssue:
        try:
            issue = TeacherIssue(
                book_isbn=issue_data["book_isbn"],
                teacher_id=issue_data["teacher_id"],
                issue_date=issue_data["issue_date"],
                due_date=issue_data["due_date"],
                status=TeacherIssueStatus.ISSUED,
                issued_by_user_id=issue_data["issued_by_user_id"],
                active_teacher_lock=str(issue_data["teacher_id"]),
            )
            session.add(issue)
            session.flush()
            return issue
        except Exception as error:
            raise self._translate(error)

    def get_by_id(self, session: Session, issue_id: int) -> TeacherIssue | None:
        try:
            return session.get(TeacherIssue, issue_id)
        except Exception as error:
            raise self._translate(error)

    def get_active_by_teacher(
        self,
        session: Session,
        teacher_id: int,
        book_isbn: str | None = None,
    ) -> list[TeacherIssue]:
        """Active (unreturned) issues for a teacher, optionally narrowed to
        one book — one active loan per teacher per book."""
        try:
            query = select(TeacherIssue).where(
                TeacherIssue.status == TeacherIssueStatus.ISSUED,
                TeacherIssue.teacher_id == teacher_id,
            )
            if book_isbn is not None:
                query = query.where(TeacherIssue.book_isbn == book_isbn)
            return list(session.scalars(query))
        except Exception as error:
            raise self._translate(error)

    def get_overdue(
        self, session: Session, limit: int | None = None
    ) -> list[TeacherIssue]:
        try:
            query = (
                select(TeacherIssue)
                .where(
                    TeacherIssue.status == TeacherIssueStatus.ISSUED,
                    TeacherIssue.due_date < func.curdate(),
                )
                .order_by(TeacherIssue.due_date.asc())
            )
            if limit is not None:
                query = query.limit(limit)
            return list(session.scalars(query))
        except Exception as error:
            raise self._translate(error)

    def count_active(self, session: Session) -> int:
        try:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(TeacherIssue)
                    .where(TeacherIssue.status == TeacherIssueStatus.ISSUED)
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)

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
    ) -> tuple[list[TeacherIssue], int]:
        try:
            query = select(TeacherIssue)
            if status:
                normalized = status.upper()
                if normalized == "OVERDUE":
                    query = query.where(
                        TeacherIssue.status == TeacherIssueStatus.ISSUED,
                        TeacherIssue.due_date < func.curdate(),
                    )
                else:
                    query = query.where(TeacherIssue.status == normalized)
            if start_date is not None:
                query = query.where(TeacherIssue.issue_date >= start_date)
            if end_date is not None:
                query = query.where(TeacherIssue.issue_date <= end_date)
            if book_search:
                term = f"%{book_search.strip()}%"
                query = query.join(Book).where(
                    or_(Book.title.like(term), Book.isbn == normalize_isbn(book_search))
                )
            if teacher_search:
                term = f"%{teacher_search.strip()}%"
                query = query.join(Teacher).where(
                    or_(
                        Teacher.name.like(term),
                        Teacher.contact_number.like(term),
                    )
                )
            total = (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = (
                session.scalars(
                    query.order_by(
                        TeacherIssue.issue_date.desc(), TeacherIssue.id.desc()
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .unique()
                .all()
            )
            return list(rows), total
        except Exception as error:
            raise self._translate(error)

    def update(self, session: Session, issue: TeacherIssue) -> None:
        try:
            session.flush()
        except Exception as error:
            raise self._translate(error)
