"""My Activity screen: the signed-in user's own transactions (Volume 2, S10)."""

from __future__ import annotations

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.badges import status_badge
from app.presentation.shared_components.cards import page_header
from app.presentation.shared_components.data_table import (
    ColumnSpec,
    DataTable,
    TableRow,
)
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import DateField
from app.presentation.shared_components.pagination import PaginationBar
from app.presentation.shared_components.search_and_filters import FilterChips
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import SPACING, styled_text

STATUS_CHIPS = [("all", "All"), ("Issued", "Issued"), ("Overdue", "Overdue"), ("Returned", "Returned")]


class MyActivityScreen:
    def __init__(
        self,
        page: ft.Page,
        transaction_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._txns = transaction_service
        self._context = context
        self._toasts = toasts
        self._status: str | None = None
        self._page_no = 1
        self._page_size = 25
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("book", "Book", 220, sortable=True),
                ColumnSpec("student", "Student", 150),
                ColumnSpec("klass", "Class", 100),
                ColumnSpec("issued", "Issued", 110),
                ColumnSpec("due", "Due", 110),
                ColumnSpec("returned", "Returned", 110),
                ColumnSpec("status", "Status", 110),
                ColumnSpec("fine", "Fine", 90),
            ],
        )
        self.pagination = PaginationBar(
            page_size=self._page_size, on_page=self._go_page, on_page_size=self._change_size
        )

    def build(self) -> ft.Control:
        self.from_date = DateField(self._page, "From Date")
        self.to_date = DateField(self._page, "To Date")
        self.apply_dates = ft.FilledButton(
            content=ft.Text("Apply Dates", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), on_click=self._on_dates,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=14, vertical=10)),
        )
        self.from_date.container.width = 180
        self.to_date.container.width = 180
        self.chips = FilterChips(STATUS_CHIPS, self._on_chip)
        header = page_header("My Activity", "Everything you have issued and returned")
        self._root = ft.Column(
            [
                header,
                self.chips,
                ft.Row(
                    [self.from_date.container, self.to_date.container, self.apply_dates],
                    spacing=SPACING["md"],
                    run_spacing=SPACING["sm"],
                    wrap=True,
                ),
                self.table,
                self.pagination,
            ],
            spacing=SPACING["md"],
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
        )
        return self._root

    def activate(self, params: dict | None = None) -> None:
        self._load()

    def _load(self) -> None:
        if not self._root:
            return
        self.table.set_loading(True)
        try:
            rows, total = self._txns.list_own_activity(
                self._context,
                start_date=self.from_date.date if self.from_date.date else None,
                end_date=self.to_date.date if self.to_date.date else None,
                status=self._status,
                page=self._page_no,
                page_size=self._page_size,
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        self.table.set_rows(
            [
                TableRow(
                    cells={
                        "book": styled_text(t.book_title, style="body_emphasis"),
                        "student": styled_text(t.student_name, style="body"),
                        "klass": styled_text(f"{t.class_name} {t.stream or ''}".strip(), style="body"),
                        "issued": styled_text(t.issue_date.isoformat() if t.issue_date else "—", style="body"),
                        "due": styled_text(t.due_date.isoformat() if t.due_date else "—", style="body"),
                        "returned": styled_text(t.return_date.isoformat() if t.return_date else "—", style="body"),
                        "status": status_badge(t.status),
                        "fine": styled_text(f"₹{t.fine_amount:.2f}" if t.fine_amount else "—", style="body"),
                    },
                    sort={"book": t.book_title.lower()},
                )
                for t in rows
            ]
        )
        self.pagination.set_state(total, self._page_no)
        self._root.update()

    def _on_chip(self, key: str | None) -> None:
        self._status = None if key == "all" else key
        self._page_no = 1
        self._load()

    def _on_dates(self, e=None) -> None:
        self._page_no = 1
        self._load()

    def _go_page(self, page: int) -> None:
        self._page_no = page
        self._load()

    def _change_size(self, size: int) -> None:
        self._page_size = size
        self._page_no = 1
        self._load()