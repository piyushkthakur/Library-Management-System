"""Service implementations, one class per module (Volume 3, Chapter 11).

Services open one session per business operation (Volume 3, Chapter 13.2),
enforce authorization and business rules, and return domain DTOs — never
raw ORM instances (Volume 3, Chapter 11.1).
"""

from app.reporting import (
    ExportResultDto,
    ReportPreviewDto,
    ReportRowDto,
    ReportTotalsDto,
)
from app.services.auth_service import AuthService
from app.services.book_service import (
    AvailableBookDto,
    BookDto,
    BookInput,
    BookService,
)
from app.services.category_service import CategoryDto, CategoryInput, CategoryService
from app.services.dashboard_service import (
    CategoryDistributionDto,
    DashboardDto,
    DashboardService,
    OverdueItemDto,
    TrendPointDto,
)
from app.services.librarian_service import (
    LibrarianDto,
    LibrarianInput,
    LibrarianService,
)
from app.services.report_service import ReportService
from app.services.settings_service import SettingsService
from app.services.teacher_issue_service import (
    TeacherIssueDto,
    TeacherIssueInput,
    TeacherIssueService,
    TeacherReturnResult,
)
from app.services.teacher_service import TeacherDto, TeacherInput, TeacherService
from app.services.transaction_service import (
    IssueInput,
    ReturnResult,
    TransactionDto,
    TransactionService,
)

__all__ = [
    "AuthService",
    "AvailableBookDto",
    "BookDto",
    "BookInput",
    "BookService",
    "CategoryDistributionDto",
    "CategoryDto",
    "CategoryInput",
    "CategoryService",
    "DashboardDto",
    "DashboardService",
    "ExportResultDto",
    "IssueInput",
    "LibrarianDto",
    "LibrarianInput",
    "LibrarianService",
    "OverdueItemDto",
    "ReportPreviewDto",
    "ReportRowDto",
    "ReportService",
    "ReportTotalsDto",
    "ReturnResult",
    "SettingsService",
    "TeacherDto",
    "TeacherInput",
    "TeacherIssueDto",
    "TeacherIssueInput",
    "TeacherIssueService",
    "TeacherReturnResult",
    "TeacherService",
    "TransactionDto",
    "TransactionService",
    "TrendPointDto",
]
