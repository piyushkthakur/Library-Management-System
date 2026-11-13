"""User model — users table (Volume 4, Chapter 9)."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserRole(str, enum.Enum):
    """Exactly two roles (Volume 1, Chapter 19)."""

    ADMINISTRATOR = "ADMINISTRATOR"
    LIBRARIAN = "LIBRARIAN"


class User(Base):
    """Maps to the users table (Volume 4, Chapter 9)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    issued_transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        back_populates="issued_by",
        foreign_keys="Transaction.issued_by_user_id",
        lazy="raise",
    )
    returned_transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        back_populates="returned_by",
        foreign_keys="Transaction.returned_by_user_id",
        lazy="raise",
    )
    password_reset_otps: Mapped[list["PasswordResetOtp"]] = relationship(  # noqa: F821
        back_populates="user", lazy="raise"
    )
