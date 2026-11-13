"""Import Books dialog — tkinter file picker -> loading -> preview table -> confirm import."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.badges import badge
from app.presentation.shared_components.buttons import Button
from app.presentation.shared_components.data_table import ColumnSpec, DataTable, TableRow
from app.presentation.shared_components.dialogs import DIALOG_BG
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.pagination import PaginationBar
from app.presentation.shared_components.search_and_filters import FilterChips
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import (
    COLOR_DANGER,
    COLOR_SUCCESS,
    COLOR_WARNING,
    SPACING,
    styled_text,
)

_FILETYPES = [
    ("Importable files", "*.csv *.xlsx *.xls *.json"),
    ("CSV files", "*.csv"),
    ("Excel files", "*.xlsx *.xls"),
    ("JSON files", "*.json"),
    ("All files", "*.*"),
]


class ImportBooksDialog:
    def __init__(
        self,
        page: ft.Page,
        import_service,
        context,
        on_done: callable,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._importer = import_service
        self._context = context
        self._on_done = on_done
        self._toasts = toasts
        self._preview = None
        self._filter = "all"
        self._page_no = 1
        self._page_size = 100
        self._table = DataTable(
            [
                ColumnSpec("row", "#", 40),
                ColumnSpec("title", "Title", 220),
                ColumnSpec("author", "Author", 160),
                ColumnSpec("isbn", "ISBN", 140),
                ColumnSpec("category", "Category", 130),
                ColumnSpec("copies", "Copies", 70),
                ColumnSpec("status", "Status", 160),
            ]
        )
        self.chips = FilterChips(
            [("all", "All"), ("valid", "Ready"), ("merged", "Merged"), ("error", "Errors")],
            self._on_filter,
        )
        self.pagination = PaginationBar(
            page_size=self._page_size,
            on_page=self._on_page,
            on_page_size=self._on_size,
        )
        self._summary = styled_text("", style="body")
        self._import_btn = Button(
            "Import",
            on_click=self._commit,
            icon=ft.Icons.CLOUD_UPLOAD,
            width=120,
        )
        self._import_btn.disabled = True
        self._dialog: ft.AlertDialog | None = None

    def open(self) -> None:
        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", True)
        path = filedialog.askopenfilename(
            title="Import Books",
            filetypes=_FILETYPES,
        )
        root.destroy()
        if not path:
            return

        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext not in {".csv", ".xlsx", ".xls", ".json"}:
            self._toasts.show("Unsupported file format: " + ext, "error")
            return

        self._show_loading()

        try:
            with open(path, "rb") as f:
                file_bytes = f.read()
        except OSError as exc:
            self._page.pop_dialog()
            self._toasts.show("Could not read file: " + str(exc), "error")
            return

        try:
            preview = self._importer.preview(file_bytes, ext)
        except LmsError as exc:
            self._page.pop_dialog()
            notify_error(self._toasts, exc)
            return
        except Exception as exc:
            self._page.pop_dialog()
            notify_error(self._toasts, exc)
            return

        self._preview = preview
        self._filter = "all"
        self._page_no = 1
        self._show_preview()

    def _render_page(self) -> None:
        """Render the current filter/page slice (TableRows are built only
        for the visible page, so thousand-row files stay fast)."""
        rows = self._preview.rows
        if self._filter != "all":
            rows = [r for r in rows if r.status == self._filter]
        total = len(rows)
        pages = max(1, -(-total // self._page_size))
        self._page_no = min(max(1, self._page_no), pages)
        chunk = rows[(self._page_no - 1) * self._page_size:self._page_no * self._page_size]
        self._table.set_rows([self._to_table_row(r) for r in chunk])
        self.pagination.set_state(total, self._page_no)

    def _on_filter(self, key: str | None) -> None:
        self._filter = key or "all"
        self._page_no = 1
        self._render_page()

    def _on_page(self, page: int) -> None:
        self._page_no = page
        self._render_page()

    def _on_size(self, size: int) -> None:
        self._page_size = size
        self._page_no = 1
        self._render_page()

    def _to_table_row(self, r) -> TableRow:
        return TableRow(
            cells={
                "row": styled_text(str(r.row_number), style="caption"),
                "title": styled_text(r.title[:30], style="body"),
                "author": styled_text(r.author[:20], style="body"),
                "isbn": styled_text(r.isbn, style="caption"),
                "category": styled_text(r.category_name or "\u2014", style="caption"),
                "copies": styled_text(
                    str(r.total_copies) if r.total_copies else "\u2014", style="caption"
                ),
                "status": self._status_cell(r),
            },
            sort={"row": r.row_number},
        )

    def _show_loading(self) -> None:
        loading_dialog = ft.AlertDialog(
            modal=True,
            title=styled_text("Import Books", style="h1"),
            content=ft.Column(
                [
                    ft.ProgressRing(width=36, height=36, stroke_width=3, color="#2E6F9E"),
                    ft.Container(height=SPACING["md"]),
                    styled_text(
                        "Please wait while the preview loads...",
                        style="body",
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=SPACING["sm"],
            ),
            content_padding=ft.Padding.only(left=24, top=20, right=24, bottom=24),
            actions=[],
        )
        loading_dialog.width = 420
        self._page.show_dialog(loading_dialog)

    def _show_preview(self) -> None:
        self._page.pop_dialog()
        preview = self._preview

        if self._dialog is None:
            self._build_dialog()
        self._page.show_dialog(self._dialog)

        self._summary.value = (
            str(preview.valid_count) + " ready, "
            + str(preview.merged_count) + " merged, "
            + str(preview.error_count) + " errors"
        )
        self._import_btn.disabled = preview.valid_count == 0 and preview.merged_count == 0
        self.chips.select("all", notify=False)
        self._render_page()

    def _build_dialog(self) -> None:
        close_btn = Button(
            "Close", on_click=lambda e: self._page.pop_dialog(), variant="outline", width=100
        )
        self._dialog = ft.AlertDialog(
            modal=True,
            bgcolor=DIALOG_BG,
            title=styled_text("Import Preview", style="h1"),
            title_padding=ft.Padding.only(left=24, top=20, right=24),
            content=ft.Column(
                [
                    self._summary,
                    self.chips,
                    self._table,
                    self.pagination,
                ],
                spacing=SPACING["md"],
                scroll=ft.Scrollbar(thumb_visibility=True),
                height=340,
                width=640,
            ),
            content_padding=ft.Padding.only(left=24, top=8, right=24, bottom=12),
            actions=[self._import_btn, close_btn],
            actions_padding=ft.Padding.only(left=24, right=24, bottom=18),
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._dialog.scrollable = True
        self._dialog.alignment = ft.Alignment.CENTER

    def _status_cell(self, row) -> ft.Control:
        if row.status == "valid":
            return badge("Ready", COLOR_SUCCESS)
        if row.status == "merged":
            return badge("Merged", COLOR_WARNING)
        return badge(row.error_message[:30] or "Error", COLOR_DANGER)

    def _commit(self, e=None) -> None:
        if not self._preview:
            return
        self._import_btn.disabled = True
        self._import_btn.update()
        try:
            result = self._importer.commit(self._preview, self._context)
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self._import_btn.disabled = False
            self._import_btn.update()
            return
        except Exception as exc:
            notify_error(self._toasts, exc)
            self._import_btn.disabled = False
            self._import_btn.update()
            return
        self._page.pop_dialog()
        msg = (
            "Import complete: " + str(result.imported) + " new books added, "
            + str(result.merged) + " catalog books gained copies, "
            + str(result.errors) + " errors."
        )
        if result.categories_created:
            msg += " " + str(result.categories_created) + " new categories created."
        self._toasts.show(msg, "success")
        self._on_done()
