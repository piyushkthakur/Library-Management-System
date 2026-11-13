"""UserRepository — users aggregate root (Volume 3, Chapter 12; Volume 4,
Chapter 9)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.repositories.base import BaseRepository
from app.repositories.interfaces import UserRepositoryInterface


class UserRepository(BaseRepository, UserRepositoryInterface):
    """Data access for the users table."""

    def get_by_email(self, session: Session, email: str) -> User | None:
        try:
            return session.scalar(
                select(User).where(func.lower(User.email) == email.strip().lower())
            )
        except Exception as error:
            raise self._translate(error)

    def get_by_id(self, session: Session, user_id: int) -> User | None:
        try:
            return session.get(User, user_id)
        except Exception as error:
            raise self._translate(error)

    def count_admins(self, session: Session) -> int:
        try:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == UserRole.ADMINISTRATOR)
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)

    def create(
        self,
        session: Session,
        full_name: str,
        email: str,
        password_hash: str,
        role: str,
    ) -> User:
        try:
            user = User(
                full_name=full_name.strip(),
                email=email.strip(),
                password_hash=password_hash,
                role=UserRole(role),
            )
            session.add(user)
            session.flush()
            return user
        except Exception as error:
            raise self._translate(error)

    def update(self, session: Session, user: User) -> None:
        try:
            session.flush()
        except Exception as error:
            raise self._translate(error)

    def list_librarians(
        self, session: Session, page: int, page_size: int
    ) -> tuple[list[User], int]:
        try:
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(User)
                    .where(User.role == UserRole.LIBRARIAN)
                )
                or 0
            )
            rows = (
                session.scalars(
                    select(User)
                    .where(User.role == UserRole.LIBRARIAN)
                    .order_by(User.created_at.desc(), User.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .unique()
                .all()
            )
            return list(rows), total
        except Exception as error:
            raise self._translate(error)

    def set_active_status(
        self, session: Session, user_id: int, is_active: bool
    ) -> None:
        try:
            user = session.get(User, user_id)
            if user is not None:
                user.is_active = is_active
                session.flush()
        except Exception as error:
            raise self._translate(error)
