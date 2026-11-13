"""TeacherRepository — teachers aggregate root (teacher registry)."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.teacher import Teacher
from app.repositories.base import BaseRepository
from app.repositories.interfaces import TeacherRepositoryInterface


class TeacherRepository(BaseRepository, TeacherRepositoryInterface):
    """Data access for the teachers table."""

    def create(self, session: Session, teacher_data: dict) -> Teacher:
        try:
            teacher = Teacher(
                name=teacher_data["name"],
                contact_number=teacher_data["contact_number"],
                subject=teacher_data.get("subject"),
                is_active=True,
            )
            session.add(teacher)
            session.flush()
            return teacher
        except Exception as error:
            raise self._translate(error)

    def get_by_id(self, session: Session, teacher_id: int) -> Teacher | None:
        try:
            return session.get(Teacher, teacher_id)
        except Exception as error:
            raise self._translate(error)

    def get_by_contact(self, session: Session, contact_number: str) -> Teacher | None:
        try:
            return session.scalar(
                select(Teacher).where(Teacher.contact_number == contact_number)
            )
        except Exception as error:
            raise self._translate(error)

    def list(
        self,
        session: Session,
        page: int,
        page_size: int,
        search: str | None = None,
        active_only: bool = False,
    ) -> tuple[list[Teacher], int]:
        try:
            query = select(Teacher)
            if active_only:
                query = query.where(Teacher.is_active.is_(True))
            if search:
                term = f"%{search.strip()}%"
                query = query.where(
                    or_(
                        Teacher.name.like(term),
                        Teacher.contact_number.like(term),
                        Teacher.subject.like(term),
                    )
                )
            total = (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = (
                session.scalars(
                    query.order_by(Teacher.name.asc(), Teacher.id.asc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            return list(rows), total
        except Exception as error:
            raise self._translate(error)

    def update(self, session: Session, teacher: Teacher) -> None:
        try:
            session.flush()
        except Exception as error:
            raise self._translate(error)
