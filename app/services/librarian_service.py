"""LibrarianService — Librarian Management (Volume 1, Chapters 14.5, 19, 27;
Volume 2, Chapter 21; Volume 3, Chapters 11, 15.1, 22; Volume 4, Chapters 9,
17.1).

Owns: Administrator-only account creation (FR-AUTH-03); Administrator-only
viewing of the librarian list (FR-LIB-01); create, edit, activate, and
deactivate of librarian accounts (FR-LIB-02). Login prevention for a
deactivated librarian (FR-LIB-03) is enforced by AuthService at login
(Volume 3, Chapter 14.1); this service provides the activation-state
control that makes it effective. No delete workflow exists for user
accounts, and no password reset exists in this module — resetting a
password uses the Forgot Password flow (FR-AUTH-05/07); the password is
captured only at creation as the Temporary Password (Volume 2, Chapter 21)
and is never edited here.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from app.core.config import SETTING_PASSWORD_MIN_LENGTH
from app.core.database import Database
from app.core.exceptions import (
    DuplicateResourceError,
    IntegrityConstraintError,
    RecordNotFoundError,
    ValidationError,
)
from app.core.security import SessionContext, hasher
from app.models.user import User, UserRole
from app.repositories.interfaces import (
    SettingsRepositoryInterface,
    UserRepositoryInterface,
)
from app.services.authorization import require_role
from app.services.interfaces import LibrarianServiceInterface
from app.utils.validators import is_valid_email, password_error

logger = logging.getLogger(__name__)

_PAGE_MIN = 1
_PAGE_SIZE_MIN = 1
_DEFAULT_PASSWORD_MIN_LENGTH = 8

_ADMIN_ONLY = {UserRole.ADMINISTRATOR}


@dataclass(frozen=True)
class LibrarianInput:
    """Presentation-layer input for the Librarian Form Dialog
    (Volume 2, Chapter 21). ``temporary_password`` is required on creation
    only; edit mode carries no password field."""

    full_name: str
    email: str
    temporary_password: str | None = None


@dataclass(frozen=True)
class LibrarianDto:
    """Domain result DTO — never a raw ORM instance (Volume 3, Chapter 11.1)."""

    id: int
    full_name: str
    email: str
    is_active: bool
    created_at: datetime


class LibrarianService(LibrarianServiceInterface):
    def __init__(
        self,
        database: Database,
        user_repository: UserRepositoryInterface,
        settings_repository: SettingsRepositoryInterface,
    ) -> None:
        self._database = database
        self._user_repo = user_repository
        self._settings_repo = settings_repository

    def list_librarians(
        self, context: SessionContext, page: int = 1, page_size: int = 10
    ) -> tuple[list[LibrarianDto], int]:
        """List every librarian account, most recently added first
        (FR-LIB-01; Volume 2, Chapter 21 Data Table)."""
        require_role(context, _ADMIN_ONLY)
        self._validate_pagination(page, page_size)
        with self._database.session_scope() as session:
            rows, total = self._user_repo.list_librarians(session, page, page_size)
            return [self._to_dto(user) for user in rows], total

    def create(
        self, context: SessionContext, librarian_input: LibrarianInput
    ) -> LibrarianDto:
        """Create a librarian account with Active status and a bcrypt-hashed
        temporary password (FR-AUTH-03, FR-LIB-02; Volume 2, Chapter 21)."""
        require_role(context, _ADMIN_ONLY)
        with self._database.session_scope() as session:
            self._validate(session, librarian_input)
            self._ensure_email_available(session, librarian_input.email)
            try:
                user = self._user_repo.create(
                    session,
                    full_name=librarian_input.full_name,
                    email=librarian_input.email,
                    password_hash=hasher.hash(librarian_input.temporary_password),
                    role=UserRole.LIBRARIAN.value,
                )
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "An account with this email already exists."
                ) from error
            logger.info(
                "Librarian account created (user_id=%s, admin_id=%s)",
                user.id,
                context.user_id,
            )
            return self._to_dto(user)

    def update(
        self,
        context: SessionContext,
        user_id: int,
        librarian_input: LibrarianInput,
    ) -> LibrarianDto:
        """Edit a librarian's full name and email (FR-LIB-02; Volume 2,
        Chapter 21). The password is not editable here; activation state is
        changed via set_active_status."""
        require_role(context, _ADMIN_ONLY)
        with self._database.session_scope() as session:
            self._validate(session, librarian_input, require_password=False)
            user = self._user_repo.get_by_id(session, user_id)
            if user is None or user.role != UserRole.LIBRARIAN:
                raise RecordNotFoundError(
                    "The requested librarian account was not found."
                )
            self._ensure_email_available(session, librarian_input.email, user_id)
            try:
                user.full_name = librarian_input.full_name.strip()
                user.email = librarian_input.email.strip()
                self._user_repo.update(session, user)
            except IntegrityConstraintError as error:
                raise DuplicateResourceError(
                    "An account with this email already exists."
                ) from error
            logger.info(
                "Librarian account updated (user_id=%s, admin_id=%s)",
                user.id,
                context.user_id,
            )
            return self._to_dto(user)

    def set_active_status(
        self, context: SessionContext, user_id: int, is_active: bool
    ) -> None:
        """Activate or deactivate a librarian account (FR-LIB-02); a
        deactivated account is immediately prevented from logging in
        (FR-LIB-03, enforced at login by AuthService)."""
        require_role(context, _ADMIN_ONLY)
        with self._database.session_scope() as session:
            user = self._user_repo.get_by_id(session, user_id)
            if user is None or user.role != UserRole.LIBRARIAN:
                raise RecordNotFoundError(
                    "The requested librarian account was not found."
                )
            user.is_active = is_active
            self._user_repo.update(session, user)
            state = "activated" if is_active else "deactivated"
            logger.info(
                "Librarian account %s (user_id=%s, admin_id=%s)",
                state,
                user.id,
                context.user_id,
            )

    def _validate(
        self,
        session,
        librarian_input: LibrarianInput,
        require_password: bool = True,
    ) -> None:
        if not librarian_input.full_name.strip():
            raise ValidationError("Full Name is required.")
        if not librarian_input.email.strip():
            raise ValidationError("Email is required.")
        if not is_valid_email(librarian_input.email):
            raise ValidationError("Enter a valid email address.")
        if require_password:
            if not librarian_input.temporary_password:
                raise ValidationError("Temporary Password is required.")
            min_length = self._setting_int(
                session, SETTING_PASSWORD_MIN_LENGTH, _DEFAULT_PASSWORD_MIN_LENGTH
            )
            policy_error = password_error(
                librarian_input.temporary_password, min_length
            )
            if policy_error:
                raise ValidationError(policy_error)

    def _ensure_email_available(
        self, session, email: str, exclude_user_id: int | None = None
    ) -> None:
        existing = self._user_repo.get_by_email(session, email)
        if existing is not None and existing.id != exclude_user_id:
            raise DuplicateResourceError("An account with this email already exists.")

    def _setting_int(self, session, key: str, default: int) -> int:
        value = self._settings_repo.get_value(session, key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("Setting %s has a non-integer value; using default", key)
            return default

    @staticmethod
    def _validate_pagination(page: int, page_size: int) -> None:
        if page < _PAGE_MIN or page_size < _PAGE_SIZE_MIN:
            raise ValidationError("Invalid page or page size.")

    @staticmethod
    def _to_dto(user: User) -> LibrarianDto:
        return LibrarianDto(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            is_active=user.is_active,
            created_at=user.created_at,
        )
