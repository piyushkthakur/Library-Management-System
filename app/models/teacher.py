"""Teacher registry + teacher book issues (teachers, teacher_issues tables).

Teachers are staff borrowers recorded in their own registry (chosen over
reusing the student transactions table). Teacher loans accrue no fines —
overdue is tracked, fine stays zero.
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TeacherIssueStatus(str, enum.Enum):
    """Only ISSUED and RETURNED are persisted; Overdue is derived at read."""

    ISSUED = "ISSUED"
    RETURNED = "RETURNED"


class Teacher(Base):
    """Staff borrower in the teacher registry."""

    __tablename__ = "teachers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    contact_number: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    issues: Mapped[list["TeacherIssue"]] = relationship(  # noqa: F821
        back_populates="teacher", lazy="selectin"
    )


class TeacherIssue(Base):
    """One book loan to a teacher. No fine column — teachers are never fined."""

    __tablename__ = "teacher_issues"
    __table_args__ = (
        CheckConstraint("due_date >= issue_date", name="chk_tissue_due_after_issue"),
        CheckConstraint(
            "return_date IS NULL OR return_date >= issue_date",
            name="chk_tissue_return_after_issue",
        ),
        UniqueConstraint(
            "book_isbn", "active_teacher_lock", name="uq_tissue_active_teacher"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    book_isbn: Mapped[str] = mapped_column(
        ForeignKey("books.isbn", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    teacher_id: Mapped[int] = mapped_column(
        ForeignKey("teachers.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    return_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[TeacherIssueStatus] = mapped_column(
        Enum(TeacherIssueStatus),
        default=TeacherIssueStatus.ISSUED,
        nullable=False,
        index=True,
    )
    issued_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    returned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT")
    )
    active_teacher_lock: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    teacher: Mapped["Teacher"] = relationship(  # noqa: F821
        back_populates="issues", lazy="joined"
    )
    book: Mapped["Book"] = relationship(  # noqa: F821
        lazy="joined"
    )
    issued_by: Mapped["User"] = relationship(  # noqa: F821
        foreign_keys="TeacherIssue.issued_by_user_id", lazy="joined"
    )
    returned_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys="TeacherIssue.returned_by_user_id", lazy="joined"
    )
