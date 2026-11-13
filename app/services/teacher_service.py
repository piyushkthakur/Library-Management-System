"""TeacherService — teacher registry (staff borrowers).

Owns: teacher create/edit/activate/deactivate and registry listing. Both
roles share access (mirroring Transactions); the registry exists so book
issues pick a validated teacher instead of free-typed names.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.core.database import Database
from app.core.exceptions import (
    DuplicateResourceError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ValidationError,
)
from app.core.security import SessionContext
from app.repositories.interfaces import TeacherRepositoryInterface
from app.services.interfaces import TeacherServiceInterface
from app.utils.validators import is_valid_phone

logger = logging.getLogger(__name__)

_PAGE_MIN = 1
_PAGE_SIZE_MIN = 1


@dataclass(frozen=True)
class TeacherInput:
    """Presentation-layer input for the Teacher Form Dialog."""

    name: str
    contact_number: str
    subject: str | None = None


@dataclass(frozen=True)
class TeacherDto:
    """Domain result DTO — never a raw ORM instance."""

    id: int
    name: str
    contact_number: str
    subject: str | None
    is_active: bool
    created_at: datetime


class TeacherService(TeacherServiceInterface):
    def __init__(
        self,
        database: Database,
        teacher_repository: TeacherRepositoryInterface,
    ) -> None:
        self._database = database
        self._teacher_repo = teacher_repository

    def list_teachers(
        self,
        context: SessionContext,
        search: str | None = None,
        active_only: bool = False,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[TeacherDto], int]:
        """List registry teachers, name order."""
        self._validate_pagination(page, page_size)
        with self._database.session_scope() as session:
            rows, total = self._teacher_repo.list(
                session, page, page_size, search=search, active_only=active_only
            )
            return [self._to_dto(row) for row in rows], total

    def create(
        self, context: SessionContext, teacher_input: TeacherInput
    ) -> TeacherDto:
        """Add a teacher to the registry with Active status."""
        self._validate(teacher_input)
        with self._database.session_scope() as session:
            if self._teacher_repo.get_by_contact(
                session, teacher_input.contact_number.strip()
            ):
                raise DuplicateResourceError(
                    "A teacher with this contact number already exists."
                )
            try:
                teacher = self._teacher_repo.create(
                    session,
                    {
                        "name": teacher_input.name.strip(),
                        "contact_number": teacher_input.contact_number.strip(),
                        "subject": (teacher_input.subject or "").strip() or None,
                    },
                )
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "A teacher with this contact number already exists."
                ) from error
            logger.info(
                "Teacher registered (teacher_id=%s, user_id=%s)",
                teacher.id,
                context.user_id,
            )
            return self._to_dto(teacher)

    def update(
        self, context: SessionContext, teacher_id: int, teacher_input: TeacherInput
    ) -> TeacherDto:
        """Edit a teacher's name, contact number, and subject."""
        self._validate(teacher_input)
        with self._database.session_scope() as session:
            teacher = self._teacher_repo.get_by_id(session, teacher_id)
            if teacher is None:
                raise RecordNotFoundError("The requested teacher was not found.")
            other = self._teacher_repo.get_by_contact(
                session, teacher_input.contact_number.strip()
            )
            if other is not None and other.id != teacher.id:
                raise DuplicateResourceError(
                    "A teacher with this contact number already exists."
                )
            teacher.name = teacher_input.name.strip()
            teacher.contact_number = teacher_input.contact_number.strip()
            teacher.subject = (teacher_input.subject or "").strip() or None
            self._teacher_repo.update(session, teacher)
            return self._to_dto(teacher)

    def set_active_status(
        self, context: SessionContext, teacher_id: int, is_active: bool
    ) -> None:
        """Activate or deactivate a teacher in the registry."""
        with self._database.session_scope() as session:
            teacher = self._teacher_repo.get_by_id(session, teacher_id)
            if teacher is None:
                raise RecordNotFoundError("The requested teacher was not found.")
            teacher.is_active = is_active
            self._teacher_repo.update(session, teacher)

    def _validate(self, teacher_input: TeacherInput) -> None:
        if not teacher_input.name.strip():
            raise ValidationError("Teacher Name is required.")
        if not is_valid_phone(teacher_input.contact_number):
            raise ValidationError("Enter a valid phone number.")

    def _to_dto(self, teacher) -> TeacherDto:
        return TeacherDto(
            id=teacher.id,
            name=teacher.name,
            contact_number=teacher.contact_number,
            subject=teacher.subject,
            is_active=teacher.is_active,
            created_at=teacher.created_at,
        )

    @staticmethod
    def _validate_pagination(page: int, page_size: int) -> None:
        if page < _PAGE_MIN or page_size < _PAGE_SIZE_MIN:
            raise ValidationError("Invalid page or page size.")
