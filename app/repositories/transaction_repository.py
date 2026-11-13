"""TransactionRepository — transactions aggregate root (Volume 3, Chapter 12;
Volume 4, Chapter 12).

Overdue is a derived state computed at query time (Volume 3, Chapter 10.2):
status = 'ISSUED' AND due_date < CURDATE().
"""

from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.book import Book
from app.models.transaction import Transaction, TransactionStatus
from app.repositories.base import BaseRepository
from app.repositories.interfaces import TransactionRepositoryInterface
from app.utils.validators import normalize_isbn


class TransactionRepository(BaseRepository, TransactionRepositoryInterface):
    """Data access for the transactions table."""

    def create(self, session: Session, transaction_data: dict) -> Transaction:
        try:
            transaction = Transaction(
                book_isbn=transaction_data["book_isbn"],
                student_name=transaction_data["student_name"],
                contact_number=transaction_data["contact_number"],
                class_name=transaction_data["class"],
                stream=transaction_data["stream"],
                section=transaction_data["section"],
                issue_date=transaction_data["issue_date"],
                due_date=transaction_data["due_date"],
                status=TransactionStatus.ISSUED,
                issued_by_user_id=transaction_data["issued_by_user_id"],
                active_contact_lock=transaction_data["contact_number"],
            )
            session.add(transaction)
            session.flush()
            return transaction
        except Exception as error:
            raise self._translate(error)

    def get_by_id(self, session: Session, transaction_id: int) -> Transaction | None:
        try:
            return session.get(Transaction, transaction_id)
        except Exception as error:
            raise self._translate(error)

    def get_active_by_contact(
        self,
        session: Session,
        contact_number: str,
        book_isbn: str | None = None,
    ) -> list[Transaction]:
        """Active (unreturned) transactions for a contact number, optionally
        narrowed to a single book — the Contact Number uniqueness rule
        (Volume 1, Section 24.6; Volume 4, Chapter 17.3)."""
        try:
            query = select(Transaction).where(
                Transaction.status == TransactionStatus.ISSUED,
                Transaction.contact_number == contact_number,
            )
            if book_isbn is not None:
                query = query.where(Transaction.book_isbn == book_isbn)
            return list(session.scalars(query))
        except Exception as error:
            raise self._translate(error)

    def get_overdue(
        self, session: Session, limit: int | None = None
    ) -> list[Transaction]:
        try:
            query = (
                select(Transaction)
                .where(
                    Transaction.status == TransactionStatus.ISSUED,
                    Transaction.due_date < func.curdate(),
                )
                .order_by(Transaction.due_date.asc())
            )
            if limit is not None:
                query = query.limit(limit)
            return list(session.scalars(query))
        except Exception as error:
            raise self._translate(error)

    def count_active(self, session: Session) -> int:
        try:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(Transaction)
                    .where(Transaction.status == TransactionStatus.ISSUED)
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)

    def count_overdue(self, session: Session) -> int:
        try:
            return (
                session.scalar(
                    select(func.count())
                    .select_from(Transaction)
                    .where(
                        Transaction.status == TransactionStatus.ISSUED,
                        Transaction.due_date < func.curdate(),
                    )
                )
                or 0
            )
        except Exception as error:
            raise self._translate(error)

    def list_by_filters(
        self,
        session: Session,
        page: int,
        page_size: int,
        status: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        book_search: str | None = None,
        borrower_search: str | None = None,
        user_id: int | None = None,
        include_returned_by: bool = False,
    ) -> tuple[list[Transaction], int]:
        try:
            query = select(Transaction)
            if status:
                normalized = status.upper()
                if normalized == "OVERDUE":
                    query = query.where(
                        Transaction.status == TransactionStatus.ISSUED,
                        Transaction.due_date < func.curdate(),
                    )
                else:
                    query = query.where(Transaction.status == normalized)
            if start_date is not None:
                query = query.where(Transaction.issue_date >= start_date)
            if end_date is not None:
                query = query.where(Transaction.issue_date <= end_date)
            if book_search:
                term = f"%{book_search.strip()}%"
                query = query.join(Book).where(
                    or_(Book.title.like(term), Book.isbn == normalize_isbn(book_search))
                )
            if borrower_search:
                term = f"%{borrower_search.strip()}%"
                query = query.where(
                    or_(
                        Transaction.student_name.like(term),
                        Transaction.contact_number.like(term),
                    )
                )
            if user_id is not None:
                if include_returned_by:
                    query = query.where(
                        or_(
                            Transaction.issued_by_user_id == user_id,
                            Transaction.returned_by_user_id == user_id,
                        )
                    )
                else:
                    query = query.where(Transaction.issued_by_user_id == user_id)
            total = (
                session.scalar(select(func.count()).select_from(query.subquery())) or 0
            )
            rows = (
                session.scalars(
                    query.order_by(Transaction.issue_date.desc(), Transaction.id.desc())
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
                .unique()
                .all()
            )
            return list(rows), total
        except Exception as error:
            raise self._translate(error)

    def update(self, session: Session, transaction: Transaction) -> None:
        try:
            session.flush()
        except Exception as error:
            raise self._translate(error)

    def circulation_trend(self, session: Session, days: int) -> list[dict]:
        """Per-day issue/return counts over the rolling window, covering every
        calendar day in the window (Volume 2, Chapter 14)."""
        start = date.today() - timedelta(days=days - 1)
        try:
            issued_rows = session.execute(
                select(Transaction.issue_date, func.count())
                .where(Transaction.issue_date >= start)
                .group_by(Transaction.issue_date)
            ).all()
            returned_rows = session.execute(
                select(Transaction.return_date, func.count())
                .where(Transaction.return_date >= start)
                .group_by(Transaction.return_date)
            ).all()
        except Exception as error:
            raise self._translate(error)
        issued_map = {day: count for day, count in issued_rows}
        returned_map = {day: count for day, count in returned_rows}
        return [
            {
                "date": start + timedelta(days=offset),
                "issued": issued_map.get(start + timedelta(days=offset), 0),
                "returned": returned_map.get(start + timedelta(days=offset), 0),
            }
            for offset in range(days)
        ]

    def _bucket_expression(self, column, granularity: str):
        """SQL expression bucketing a DATE column into its report period —
        day (the date), week (Monday of its week), month (first of the
        month), or year (Jan 1) — for the Report preview grouping
        (Volume 2, Chapter 19). Buckets use day-number arithmetic
        (to_days/from_days) so every bucket is a real DATE and the four
        modes share one code shape."""
        if granularity == "day":
            return func.date(column)
        if granularity == "week":
            return func.from_days(
                func.to_days(func.date(column)) - func.weekday(func.date(column))
            )
        if granularity == "month":
            return func.from_days(
                func.to_days(func.date(column)) - func.dayofmonth(column) + 1
            )
        if granularity == "year":
            return func.date(
                func.concat(func.year(column), "-01-01")
            )
        raise ValueError(f"Unsupported granularity: {granularity}")

    def aggregate_for_period(
        self,
        session: Session,
        start: date,
        end: date,
        scope_user_id: int | None,
        granularity: str | None = None,
        category_id: int | None = None,
    ) -> dict | list:
        """SQL-level aggregation for a period (Volume 3, Chapter 26.1;
        Volume 4, Section 35.5), optionally scoped to a librarian's own
        issued activity (FR-RPT-04). All four aggregates respect the same
        scope predicate, and overdue counts only transactions issued within
        the period. ``granularity`` None returns the four report totals;
        'day'/'week'/'month' return per-bucket rows (one row per non-empty
        bucket, ordered by bucket date) for the Report preview grouping
        (Volume 2, Chapter 19). ``category_id`` restricts every aggregate to
        books of one category (optional Category filter, Volume 2,
        Chapter 19), applied at SQL level via a books join."""
        if granularity not in (None, "day", "week", "month", "year"):
            raise ValueError(f"Unsupported granularity: {granularity}")
        scope = (
            Transaction.issued_by_user_id == scope_user_id
            if scope_user_id is not None
            else True
        )
        category_pred = (
            (Book.category_id == category_id,) if category_id is not None else ()
        )
        issued_period = (
            Transaction.issue_date >= start,
            Transaction.issue_date <= end,
        )
        returned_period = (
            Transaction.return_date >= start,
            Transaction.return_date <= end,
        )
        overdue_where = (
            scope,
            Transaction.status == TransactionStatus.ISSUED,
            *issued_period,
            Transaction.due_date < func.curdate(),
        )

        def base(*columns):
            query = select(*columns).select_from(Transaction)
            if category_id is not None:
                query = query.join(Book)
            return query

        try:
            if granularity is None:
                issued = (
                    session.scalar(
                        base(func.count()).where(scope, *issued_period, *category_pred)
                    )
                    or 0
                )
                returned = (
                    session.scalar(
                        base(func.count()).where(
                            scope, *returned_period, *category_pred
                        )
                    )
                    or 0
                )
                overdue = (
                    session.scalar(
                        base(func.count()).where(*overdue_where, *category_pred)
                    )
                    or 0
                )
                fines = float(
                    session.scalar(
                        base(func.coalesce(func.sum(Transaction.fine_amount), 0)).where(
                            scope, *returned_period, *category_pred
                        )
                    )
                    or 0
                )
                return {
                    "issued": issued,
                    "returned": returned,
                    "overdue": overdue,
                    "fines": fines,
                }

            issue_bucket = self._bucket_expression(Transaction.issue_date, granularity)
            return_bucket = self._bucket_expression(
                Transaction.return_date, granularity
            )
            issued_rows = session.execute(
                base(issue_bucket, func.count())
                .where(scope, *issued_period, *category_pred)
                .group_by(issue_bucket)
                .order_by(issue_bucket)
            ).all()
            returned_rows = session.execute(
                base(return_bucket, func.count())
                .where(scope, *returned_period, *category_pred)
                .group_by(return_bucket)
                .order_by(return_bucket)
            ).all()
            overdue_rows = session.execute(
                base(issue_bucket, func.count())
                .where(*overdue_where, *category_pred)
                .group_by(issue_bucket)
                .order_by(issue_bucket)
            ).all()
            fines_rows = session.execute(
                base(return_bucket, func.coalesce(func.sum(Transaction.fine_amount), 0))
                .where(scope, *returned_period, *category_pred)
                .group_by(return_bucket)
                .order_by(return_bucket)
            ).all()
            groups: dict = {}
            for bucket_date, count in issued_rows:
                groups.setdefault(
                    bucket_date,
                    {
                        "date": bucket_date,
                        "issued": 0,
                        "returned": 0,
                        "overdue": 0,
                        "fines": 0.0,
                    },
                )["issued"] = count
            for bucket_date, count in returned_rows:
                groups.setdefault(
                    bucket_date,
                    {
                        "date": bucket_date,
                        "issued": 0,
                        "returned": 0,
                        "overdue": 0,
                        "fines": 0.0,
                    },
                )["returned"] = count
            for bucket_date, count in overdue_rows:
                groups.setdefault(
                    bucket_date,
                    {
                        "date": bucket_date,
                        "issued": 0,
                        "returned": 0,
                        "overdue": 0,
                        "fines": 0.0,
                    },
                )["overdue"] = count
            for bucket_date, total in fines_rows:
                groups.setdefault(
                    bucket_date,
                    {
                        "date": bucket_date,
                        "issued": 0,
                        "returned": 0,
                        "overdue": 0,
                        "fines": 0.0,
                    },
                )["fines"] = float(total)
            return [groups[key] for key in sorted(groups)]
        except Exception as error:
            raise self._translate(error)
