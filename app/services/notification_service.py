from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedOperationError, ValidationError
from app.core.security import SessionContext
from app.models.book import Book
from app.models.notification import Notification
from app.models.transaction import Transaction, TransactionStatus
from app.models.user import User, UserRole
from app.services.authorization import require_role


@dataclass(frozen=True)
class NotificationDto:
    id: int
    message: str
    is_read: bool
    created_at: datetime


class NotificationService:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def _session(self, context: SessionContext) -> Iterator[Session]:
        require_role(context, {UserRole.ADMINISTRATOR, UserRole.LIBRARIAN})
        with self._session_factory() as session, session.begin():
            user = session.get(User, context.user_id)
            if user is None or not user.is_active or user.role != context.role:
                raise UnauthorizedOperationError(
                    "You do not have permission to perform this action."
                )
            yield session

    @staticmethod
    def _visible(context: SessionContext):
        return and_(
            Notification.user_id == context.user_id,
            Notification.is_dismissed.is_(False),
        )

    def list_notifications(self, context: SessionContext) -> list[NotificationDto]:
        with self._session(context) as session:
            rows = session.scalars(
                select(Notification)
                .where(self._visible(context))
                .order_by(Notification.created_at.desc(), Notification.id.desc())
                .limit(50)
            )
            return [NotificationDto(row.id, row.message, row.is_read, row.created_at) for row in rows]

    def unread_count(self, context: SessionContext) -> int:
        with self._session(context) as session:
            return session.scalar(
                select(func.count()).select_from(Notification).where(
                    self._visible(context), Notification.is_read.is_(False)
                )
            ) or 0

    def mark_read(self, context: SessionContext, id: int) -> None:
        with self._session(context) as session:
            self._validate_id(id)
            session.execute(
                update(Notification)
                .where(self._visible(context), Notification.id == id)
                .values(is_read=True)
            )

    def mark_all_read(self, context: SessionContext) -> None:
        with self._session(context) as session:
            session.execute(
                update(Notification).where(self._visible(context)).values(is_read=True)
            )

    def dismiss(self, context: SessionContext, id: int) -> None:
        with self._session(context) as session:
            self._validate_id(id)
            session.execute(
                update(Notification)
                .where(self._visible(context), Notification.id == id)
                .values(is_dismissed=True)
            )

    @staticmethod
    def _validate_id(id: int) -> None:
        if type(id) is not int or id < 1:
            raise ValidationError("Notification ID must be a positive integer.")

    def refresh(self, context: SessionContext) -> None:
        today = date.today()
        start = today - timedelta(days=6)
        with self._session(context) as session:
            rows = session.execute(
                select(
                    Transaction.id, Book.title, Transaction.issue_date,
                    Transaction.return_date, Transaction.due_date, Transaction.status,
                )
                .join(Book, Book.isbn == Transaction.book_isbn)
                .where(
                    Transaction.issued_by_user_id == context.user_id,
                    or_(
                        Transaction.issue_date.between(start, today),
                        and_(
                            Transaction.status == TransactionStatus.RETURNED,
                            Transaction.return_date.between(start, today),
                        ),
                        and_(
                            Transaction.status == TransactionStatus.ISSUED,
                            Transaction.due_date < today,
                        ),
                    ),
                )
            ).all()
            for row in rows:
                events = []
                if start <= row.issue_date <= today:
                    events.append(("issued", f'Issued "{row.title}" on {row.issue_date}.'))
                if (
                    row.status == TransactionStatus.RETURNED
                    and row.return_date is not None
                    and start <= row.return_date <= today
                ):
                    events.append(("returned", f'Returned "{row.title}" on {row.return_date}.'))
                if row.status == TransactionStatus.ISSUED and row.due_date < today:
                    events.append(("overdue", f'Overdue: "{row.title}" was due {row.due_date}.'))
                for event, message in events:
                    key = f"transaction:{row.id}:{event}"
                    existing = select(Notification.id).where(
                        Notification.user_id == context.user_id,
                        Notification.event_key == key,
                    )
                    if session.scalar(existing) is not None:
                        continue
                    try:
                        with session.begin_nested():
                            session.add(Notification(
                                user_id=context.user_id, event_key=key, message=message
                            ))
                            session.flush()
                    except IntegrityError:
                        if session.scalar(existing.with_for_update()) is None:
                            raise
