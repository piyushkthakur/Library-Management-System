"""Reports screen: run report, preview totals + rows, export PDF/Excel."""

from __future__ import annotations

from datetime import timedelta

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.buttons import Button
from app.presentation.shared_components.cards import KpiCard, page_header
from app.presentation.shared_components.data_table import (
    ColumnSpec,
    DataTable,
    TableRow,
)
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import DateField, DropdownField, Field
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import COLOR_BORDER, COLOR_SURFACE, SPACING, styled_text

REPORT_TYPES = ["DAILY", "WEEKLY", "MONTHLY", "YEARLY", "CUSTOM"]


class ReportsScreen:
    def __init__(
        self,
        page: ft.Page,
        report_service,
        category_service,
        librarian_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._reports = report_service
        self._categories = category_service
        self._librarians = librarian_service
        self._context = context
        self._toasts = toasts
        self._report: object = None
        self._root: ft.Control | None = None
        self.kpi_issued = KpiCard("Issued", ft.Icons.LOGOUT)
        self.kpi_returned = KpiCard("Returned", ft.Icons.LOGIN)
        self.kpi_overdue = KpiCard("Overdue", ft.Icons.ERROR_OUTLINE)
        self.kpi_fines = KpiCard("Fines Collected", ft.Icons.PAYMENTS)
        self.table = DataTable(
            [
                ColumnSpec("date", "Date", 220, sortable=True),
                ColumnSpec("issued", "Issued", 90),
                ColumnSpec("returned", "Returned", 90),
                ColumnSpec("overdue", "Overdue", 90),
                ColumnSpec("fines", "Fines", 100),
            ],
        )
        self.export_pdf = Button(
            "Export PDF", on_click=lambda e: self._page.run_task(self._export, "pdf"),
            icon=ft.Icons.PICTURE_AS_PDF, variant="secondary",
        )
        self.export_xlsx = Button(
            "Export Excel", on_click=lambda e: self._page.run_task(self._export, "xlsx"),
            icon=ft.Icons.TABLE_VIEW, variant="outline",
        )
        self._picker = None
        try:
            self._picker = ft.FilePicker()
        except Exception:
            pass
        self._category_names: list[str] = []
        self._category_ids: dict[str, int] = {}
        self._librarian_names: list[str] = []
        self._librarian_ids: dict[str, int] = {}

    def build(self) -> ft.Control:
        self.export_pdf.disabled = True
        self.export_xlsx.disabled = True
        if self._picker and self._page.overlay and self._picker not in self._page.overlay:
            self._page.overlay.append(self._picker)
            self._page.update()
        self._load_option_lists()
        self.report_type = DropdownField("Report Type", REPORT_TYPES, value="DAILY", required=True,
                                          on_change=self._on_report_type_change)
        self.from_date = DateField(self._page, "From Date")
        self.to_date = DateField(self._page, "To Date")
        self.academic_year = Field("Academic Year", value="2026 - 2027", hint="e.g. 2026 - 2027")
        self.category_filter = DropdownField("Category (optional)", self._category_names)
        self.librarian_filter = DropdownField("Librarian (optional)", self._librarian_names)
        run_btn = Button("Run Report", on_click=self._run, icon=ft.Icons.PLAY_ARROW, width=150)
        reset_btn = Button("Reset", on_click=self._reset, icon=ft.Icons.REFRESH, variant="outline")
        params = ft.Container(
            ft.Column(
                [
                    self.report_type.container,
                    self.from_date.container,
                    self.to_date.container,
                    self.academic_year.container,
                    self.category_filter.container,
                    self.librarian_filter.container,
                    ft.Row([run_btn, reset_btn], spacing=SPACING["sm"], wrap=True),
                ],
                spacing=SPACING["md"],
            ),
            padding=ft.Padding.all(20),
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
            col={"xs": 12, "lg": 4},
        )
        for card in (self.kpi_issued, self.kpi_returned, self.kpi_overdue, self.kpi_fines):
            card.container.col = {"xs": 12, "sm": 6, "lg": 3}
        preview = ft.Column(
            [
                ft.ResponsiveRow(
                    [
                        self.kpi_issued.container,
                        self.kpi_returned.container,
                        self.kpi_overdue.container,
                        self.kpi_fines.container,
                    ],
                    spacing=SPACING["md"],
                ),
                ft.Row(
                    [self.export_pdf, self.export_xlsx],
                    spacing=SPACING["sm"],
                    alignment=ft.MainAxisAlignment.END,
                    wrap=True,
                ),
                self.table,
            ],
            spacing=SPACING["md"],
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            col={"xs": 12, "lg": 8},
        )
        header = page_header("Reports", "Analyze circulation and fines")
        self._root = ft.Column(
            [
                header,
                ft.ResponsiveRow(
                    [params, preview],
                    spacing=SPACING["lg"],
                    run_spacing=SPACING["md"],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=SPACING["md"],
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
        )
        return self._root

    def activate(self, params: dict | None = None) -> None:
        self._load_option_lists()
        self._on_report_type_change()
        self._load_last()

    def _on_report_type_change(self, e=None) -> None:
        custom = (self.report_type.control.value or "DAILY") == "CUSTOM"
        self.from_date.set_enabled(custom)
        self.to_date.set_enabled(custom)

    def _reset(self, e=None) -> None:
        self.report_type.control.value = "DAILY"
        self.report_type.control.update()
        self.from_date.date = None
        self.from_date.control.value = ""
        self.from_date.set_enabled(False)
        self.to_date.date = None
        self.to_date.control.value = ""
        self.to_date.set_enabled(False)
        self.category_filter.control.value = None
        self.category_filter.control.update()
        self.librarian_filter.control.value = None
        self.librarian_filter.control.update()
        self.table.set_rows([])
        self.kpi_issued.set_value("0")
        self.kpi_returned.set_value("0")
        self.kpi_overdue.set_value("0")
        self.kpi_fines.set_value("₹0.00")
        self.export_pdf.disabled = True
        self.export_xlsx.disabled = True
        self.export_pdf.update()
        self.export_xlsx.update()
        self._report = None

    # -- option lists --------------------------------------------------------------

    def _load_option_lists(self) -> None:
        try:
            cats = self._categories.list_all(self._context)
            self._category_names = [c.name for c in cats]
            self._category_ids = {c.name: c.id for c in cats}
        except LmsError:
            self._category_names = []
        try:
            librarians, _ = self._librarians.list_librarians(self._context, page=1, page_size=100)
            self._librarian_names = [l.full_name for l in librarians]
            self._librarian_ids = {l.full_name: l.id for l in librarians}
        except LmsError:
            self._librarian_names = []

    # -- run -------------------------------------------------------------------------

    def _run(self, e=None) -> None:
        rtype = self.report_type.control.value or "DAILY"
        if rtype == "CUSTOM" and not (self.from_date.date and self.to_date.date):
            self._toasts.show("Select From and To dates for a custom report.", "error")
            return
        self.table.set_loading(True)
        try:
            report = self._reports.generate_report(
                self._context,
                report_type=rtype,
                start_date=self.from_date.date,
                end_date=self.to_date.date,
                category_id=self._category_ids.get(self.category_filter.control.value) if self.category_filter.control.value else None,
                librarian_id=self._librarian_ids.get(self.librarian_filter.control.value) if self.librarian_filter.control.value else None,
                academic_year=self.academic_year.control.value or "",
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        self._report = report
        self.kpi_issued.set_value(str(report.totals.issued))
        self.kpi_returned.set_value(str(report.totals.returned))
        self.kpi_overdue.set_value(str(report.totals.overdue))
        self.kpi_fines.set_value(f"₹{report.totals.fines:.2f}")
        is_weekly = rtype == "WEEKLY"
        is_monthly = rtype == "MONTHLY"
        is_yearly = rtype == "YEARLY"
        rows = [
            TableRow(
                cells={
                    "date": styled_text(
                        f"{r.date.isoformat()} - {(r.date + timedelta(days=5)).isoformat()}"
                        if is_weekly else r.date.strftime("%B")
                        if is_monthly else str(r.date.year)
                        if is_yearly else r.date.isoformat(),
                        style="body",
                    ),
                    "issued": styled_text(str(r.issued), style="body"),
                    "returned": styled_text(str(r.returned), style="body"),
                    "overdue": styled_text(str(r.overdue), style="body"),
                    "fines": styled_text(f"₹{r.fines:.2f}", style="body"),
                },
                sort={"date": str(r.date)},
            )
            for r in report.rows
        ]
        self.table.set_rows(rows)
        self.export_pdf.disabled = not rows
        self.export_xlsx.disabled = not rows
        self.export_pdf.update()
        self.export_xlsx.update()
        self._root.update()

    def _load_last(self) -> None:
        """Re-render after option lists reload on navigation."""
        if self._report and self._root:
            self._root.update()

    # -- export ----------------------------------------------------------------------
    #
    # flet 0.86's file picker is async-only (the native dialog is awaited), so this
    # single handler awaits the save dialog. Everywhere else stays strictly
    # synchronous; no background work happens here, only the OS dialog lifetime.
    # ponytail: the one async leaf in the layer; replaceable by a sync dialog if
    # the flet API ever offers one.

    async def _export(self, fmt: str) -> None:
        if not self._report or not self._picker:
            return
        try:
            result = self._reports.export(self._context, self._report, fmt)
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        path = await self._picker.save_file(
            file_name=result.file_name,
            allowed_extensions=[fmt],
            src_bytes=result.file_bytes,
        )
        if path:
            self._toasts.show(f"Report saved to {path}", "success")