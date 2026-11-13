"""DashboardService — read-only aggregation for the Dashboard screen
(Volume 1, Chapter 21; Volume 2, Chapter 14).

Owned business rules (Volume 3, Chapter 11): KPIs are cached for a short
TTL to avoid re-running expensive queries and Kaleido chart renders on every
tab switch. Overdue status is derived at read time — a transaction is overdue
when due_date has passed and return_date is null (Volume 1, Chapter 21/24;
Volume 3, Chapter 10.2).
Read-only: no writes, no user input, no validation (Volume 1, Chapter 21).
Both roles have identical full access (Volume 1, Chapter 19).
"""

import logging
import time
from dataclasses import dataclass
from datetime import date

from app.core.database import Database
from app.repositories.interfaces import (
    BookRepositoryInterface,
    CategoryRepositoryInterface,
    TransactionRepositoryInterface,
)
from app.services.interfaces import DashboardServiceInterface

logger = logging.getLogger(__name__)

OVERDUE_WIDGET_LIMIT = 10
TREND_DAYS = 30
_CACHE_TTL_SECONDS = 30


@dataclass(frozen=True)
class TrendPointDto:
    """One point of the 30-day circulation trend chart (FR-DASH-02)."""

    date: date
    issued: int
    returned: int


@dataclass(frozen=True)
class CategoryDistributionDto:
    """Catalog composition slice for the donut chart (Volume 2, Chapter 14)."""

    category_name: str
    book_count: int


@dataclass(frozen=True)
class OverdueItemDto:
    """One row of the Overdue Transactions widget (Volume 2, Chapter 14):
    borrower, book title, and days overdue, most overdue first."""

    transaction_id: int
    book_title: str
    student_name: str
    days_overdue: int


@dataclass(frozen=True)
class DashboardDto:
    """Complete read-only Dashboard snapshot (FR-DASH-01/02/03)."""

    total_books: int
    total_available_copies: int
    active_transactions: int
    overdue_transactions: int
    trend: tuple[TrendPointDto, ...]
    category_distribution: tuple[CategoryDistributionDto, ...]
    overdue_items: tuple[OverdueItemDto, ...]


class DashboardService(DashboardServiceInterface):
    def __init__(
        self,
        database: Database,
        transaction_repository: TransactionRepositoryInterface,
        book_repository: BookRepositoryInterface,
        category_repository: CategoryRepositoryInterface,
    ) -> None:
        self._database = database
        self._txn_repo = transaction_repository
        self._book_repo = book_repository
        self._category_repo = category_repository
        self._cache: DashboardDto | None = None
        self._cache_time: float = 0.0

    def get_dashboard(self) -> DashboardDto:
        """Return cached Dashboard snapshot or recompute if stale."""
        now = time.monotonic()
        if self._cache is not None and (now - self._cache_time) < _CACHE_TTL_SECONDS:
            return self._cache

        with self._database.session_scope() as session:
            total_books = self._book_repo.count_active_books(session)
            total_available = self._book_repo.total_available_copies(session)
            active = self._txn_repo.count_active(session)
            overdue = self._txn_repo.count_overdue(session)
            trend = tuple(
                TrendPointDto(
                    date=point["date"],
                    issued=point["issued"],
                    returned=point["returned"],
                )
                for point in self._txn_repo.circulation_trend(session, TREND_DAYS)
            )
            counts = self._category_repo.count_books_per_category(session)
            categories = self._category_repo.list_all(session)
            distribution = tuple(
                CategoryDistributionDto(
                    category_name=category.name,
                    book_count=counts.get(category.id, 0),
                )
                for category in categories
            )
            overdue_items = tuple(
                OverdueItemDto(
                    transaction_id=item.id,
                    book_title=item.book.title,
                    student_name=item.student_name,
                    days_overdue=(date.today() - item.due_date).days,
                )
                for item in self._txn_repo.get_overdue(session, OVERDUE_WIDGET_LIMIT)
            )
        dto = DashboardDto(
            total_books=total_books,
            total_available_copies=total_available,
            active_transactions=active,
            overdue_transactions=overdue,
            trend=trend,
            category_distribution=distribution,
            overdue_items=overdue_items,
        )
        self._cache = dto
        self._cache_time = now
        return dto
