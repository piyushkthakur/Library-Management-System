"""Book model — books table (Volume 4, Chapter 11)."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Book(Base):
    """Maps to the books table (Volume 4, Chapter 11)."""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(
            "available_copies <= total_copies", name="chk_books_copies_range"
        ),
        CheckConstraint("available_copies >= 0", name="chk_books_copies_nonneg"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    author: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    isbn: Mapped[str] = mapped_column(String(20), primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    total_copies: Mapped[int] = mapped_column(Integer, nullable=False)
    available_copies: Mapped[int] = mapped_column(Integer, nullable=False)
    shelf_location: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    category: Mapped["Category"] = relationship(  # noqa: F821
        back_populates="books", lazy="joined"
    )
    transactions: Mapped[list["Transaction"]] = relationship(  # noqa: F821
        back_populates="book", lazy="raise"
    )
