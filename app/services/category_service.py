"""CategoryService — Categories module (Volume 1, Chapter 23; Volume 2,
Chapter 17; Volume 3, Chapters 11, 15.1, 22.2; Volume 4, Chapter 10).

Owns: case-insensitive category-name uniqueness (FR-CAT-02) and
delete-blocking while books remain assigned (FR-CAT-03). Both roles have
full CRUD (Volume 3, Chapter 15.1); the session context is accepted for
auditability attribution (Volume 3, Chapter 24.1).
"""

import logging
from dataclasses import dataclass

from app.core.database import Database
from app.core.exceptions import (
    DuplicateResourceError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ResourceInUseError,
    ValidationError,
)
from app.core.security import SessionContext
from app.models.category import Category
from app.repositories.interfaces import CategoryRepositoryInterface
from app.services.interfaces import CategoryServiceInterface
from app.utils.validators import normalize_category_name

logger = logging.getLogger(__name__)

_NAME_MAX = 100
_DESCRIPTION_MAX = 500


@dataclass(frozen=True)
class CategoryInput:
    """Presentation-layer input for create/update (Volume 3, Chapter 11.1)."""

    name: str
    description: str | None = None


@dataclass(frozen=True)
class CategoryDto:
    """Domain result DTO — never a raw ORM instance (Volume 3, Chapter 11.1)."""

    id: int
    name: str
    description: str | None
    book_count: int


class CategoryService(CategoryServiceInterface):
    def __init__(
        self,
        database: Database,
        category_repository: CategoryRepositoryInterface,
    ) -> None:
        self._database = database
        self._category_repo = category_repository

    def list_all(self, context: SessionContext) -> list[CategoryDto]:
        with self._database.session_scope() as session:
            return [
                self._to_dto(category, session)
                for category in self._category_repo.list_all(session)
            ]

    def get_by_id(self, category_id: int) -> CategoryDto:
        with self._database.session_scope() as session:
            category = self._category_repo.get_by_id(session, category_id)
            if category is None:
                raise RecordNotFoundError("The requested category was not found.")
            return self._to_dto(category, session)

    def create(
        self, category_input: CategoryInput, context: SessionContext
    ) -> CategoryDto:
        name = normalize_category_name(category_input.name)
        self._validate(name, category_input.description)
        with self._database.session_scope() as session:
            self._ensure_unique(session, name)
            try:
                category = self._category_repo.create(
                    session, name, category_input.description
                )
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "A category with this name already exists."
                ) from error
            logger.info(
                "Category created (category_id=%s, user_id=%s)",
                category.id,
                context.user_id,
            )
            return self._to_dto(category, session)

    def update(
        self, category_id: int, category_input: CategoryInput, context: SessionContext
    ) -> CategoryDto:
        name = normalize_category_name(category_input.name)
        self._validate(name, category_input.description)
        with self._database.session_scope() as session:
            category = self._category_repo.get_by_id(session, category_id)
            if category is None:
                raise RecordNotFoundError("The requested category was not found.")
            self._ensure_unique(session, name, exclude_id=category_id)
            try:
                category.name = name
                description = (category_input.description or "").strip()
                category.description = description or None
                self._category_repo.update(session, category)
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "A category with this name already exists."
                ) from error
            logger.info(
                "Category updated (category_id=%s, user_id=%s)",
                category.id,
                context.user_id,
            )
            return self._to_dto(category, session)

    def delete(self, category_id: int, context: SessionContext) -> None:
        with self._database.session_scope() as session:
            category = self._category_repo.get_by_id(session, category_id)
            if category is None:
                raise RecordNotFoundError("The requested category was not found.")
            if self._category_repo.count_books_in_category(session, category_id) > 0:
                raise ResourceInUseError(
                    "This category has books assigned and cannot be deleted."
                )
            self._category_repo.delete(session, category_id)
            logger.info(
                "Category deleted (category_id=%s, user_id=%s)",
                category_id,
                context.user_id,
            )

    def _validate(self, name: str, description: str | None) -> None:
        if not name:
            raise ValidationError("Category Name is required.")
        if len(name) > _NAME_MAX:
            raise ValidationError(
                f"Category Name must be at most {_NAME_MAX} characters."
            )
        if description and len(description) > _DESCRIPTION_MAX:
            raise ValidationError(
                f"Description must be at most {_DESCRIPTION_MAX} characters."
            )

    def _ensure_unique(self, session, name: str, exclude_id: int | None = None) -> None:
        existing = self._category_repo.get_by_name(session, name)
        if existing is not None and existing.id != exclude_id:
            raise DuplicateResourceError("A category with this name already exists.")

    def _to_dto(self, category: Category, session) -> CategoryDto:
        return CategoryDto(
            id=category.id,
            name=category.name,
            description=category.description,
            book_count=self._category_repo.count_books_in_category(
                session, category.id
            ),
        )
