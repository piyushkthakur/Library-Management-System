"""Transaction model — transactions table (Volume 4, Chapter 12).

Overdue is derived, never persisted (Volume 3, Chapter 10.2).
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.models.base import Base


class Stream(str, enum.Enum):
    """Stream enum for classes XI-XII (Volume 1, Chapter 17.2)."""

    Science = "Science"
    Commerce = "Commerce"
    Humanities = "Humanities"


class CaseInsensitiveEnum(TypeDecorator):
    """TypeDecorator that stores enum values as strings but reads them case-insensitively."""

    impl = String
    cache_ok = True

    def __init__(self, enum_class, **kwargs):
        self.enum_class = enum_class
        super().__init__(**kwargs)

    def _find_member(self, value):
        for member in self.enum_class:
            if member.value.lower() == str(value).lower():
                return member
        return None

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, self.enum_class):
            return value.value
        member = self._find_member(value)
        return member.value if member else str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return self._find_member(value) or value


class TransactionStatus(str, enum.Enum):
    """Only ISSUED and RETURNED are persisted (Volume 3, Chapter 10.2)."""

    ISSUED = "ISSUED"
    RETURNED = "RETURNED"


class Transaction(Base):
    """Maps to the transactions table (Volume 4, Chapter 12)."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("due_date >= issue_date", name="chk_txn_due_after_issue"),
        CheckConstraint(
            "return_date IS NULL OR return_date >= issue_date",
            name="chk_txn_return_after_issue",
        ),
        UniqueConstraint(
            "book_isbn", "active_contact_lock", name="uq_txn_active_contact"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_isbn: Mapped[str] = mapped_column(
        ForeignKey("books.isbn", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    student_name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    class_name: Mapped[str] = mapped_column("class", String(20), nullable=False)
    stream: Mapped[Stream] = mapped_column(CaseInsensitiveEnum(Stream), nullable=False)
    section: Mapped[str] = mapped_column(String(10), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus),
        default=TransactionStatus.ISSUED,
        nullable=False,
        index=True,
    )
    fine_amount: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    issued_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    returned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT")
    )
    active_contact_lock: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    book: Mapped["Book"] = relationship(  # noqa: F821
        back_populates="transactions", lazy="joined"
    )
    issued_by: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys="Transaction.issued_by_user_id", lazy="joined"
    )
    returned_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys="Transaction.returned_by_user_id", lazy="joined"
    )
