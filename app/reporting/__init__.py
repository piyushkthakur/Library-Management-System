"""Reporting package — export generators and the shared report DTO layer
(Volume 3, Chapters 7.1, 26; Volume 2, Chapter 19).

Consumed exclusively by ReportService. The DTOs live here rather than in
app.services so that both ReportService (which constructs them) and the
generators (which consume them) share one contract without any
services -> reporting -> services cycle. The package imports only stdlib,
ReportLab, and OpenPyXL — never repositories or models, so an exporter
cannot reach a database or ORM object by construction.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReportTotalsDto:
    """Summary Strip totals for the selected period (Volume 2, Chapter 19)."""

    issued: int
    returned: int
    overdue: int
    fines: float


@dataclass(frozen=True)
class ReportRowDto:
    """One grouped Report Preview row (Volume 2, Chapter 19)."""

    date: date
    issued: int
    returned: int
    overdue: int
    fines: float


@dataclass(frozen=True)
class ReportPreviewDto:
    """The complete generated report, shared verbatim by the on-screen
    preview and both export formats (Volume 3, Chapter 26.2)."""

    report_type: str
    start_date: date
    end_date: date
    totals: ReportTotalsDto
    rows: tuple[ReportRowDto, ...]
    include_fines: bool
    generated_by: str = ""
    academic_year: str = ""


@dataclass(frozen=True)
class ExportResultDto:
    """Generated file content; the Presentation layer writes it to the
    user-selected location via the native save dialog (Volume 3, 27.1)."""

    file_name: str
    file_bytes: bytes


class ReportExporter(ABC):
    """Common export contract (Strategy Pattern, Volume 3, Chapter 32):
    both generators accept the same Report Preview DTO and return file
    bytes — pure format transformation, no business logic."""

    @abstractmethod
    def generate(self, report: ReportPreviewDto) -> ExportResultDto:
        """Render the report into this exporter's format and return the
        generated file."""


from app.reporting.excel_exporter import ExcelExporter
from app.reporting.pdf_exporter import PdfExporter

__all__ = [
    "ExcelExporter",
    "ExportResultDto",
    "PdfExporter",
    "ReportExporter",
    "ReportPreviewDto",
    "ReportRowDto",
    "ReportTotalsDto",
]
