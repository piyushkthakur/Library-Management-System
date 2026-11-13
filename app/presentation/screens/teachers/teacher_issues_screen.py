"""Teacher Issues screen: issue/return books to registry teachers, receipt."""

from __future__ import annotations

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.badges import status_badge
from app.presentation.shared_components.buttons import icon_button
from app.presentation.shared_components.cards import page_header
from app.presentation.shared_components.data_table import (
    ColumnSpec,
    DataTable,
    TableRow,
)
from app.presentation.shared_components.dialogs import FormDialog, confirm, info
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import DateField
from app.presentation.shared_components.pagination import PaginationBar
from app.presentation.shared_components.search_and_filters import (
    FilterChips,
    SearchFilters,
)
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import HINT_STYLE, SPACING, styled_text

STATUS_CHIPS = [("all", "All"), ("Issued", "Issued"), ("Overdue", "Overdue"), ("Returned", "Returned")]


class TeacherIssuesScreen:
    def __init__(
        self,
        page: ft.Page,
        teacher_issue_service,
        teacher_service,
        book_service,
        context,
        toasts: ToastHost,
        on_manage_teachers=None,
    ) -> None:
        self._page = page
        self._issues = teacher_issue_service
        self._teachers = teacher_service
        self._books = book_service
        self._context = context
        self._toasts = toasts
        self._on_manage_teachers = on_manage_teachers
        self._status: str | None = None
        self._book_term = ""
        self._teacher_term = ""
        self._page_no = 1
        self._page_size = 25
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("id", "#", 60),
                ColumnSpec("book", "Book", 220, sortable=True),
                ColumnSpec("teacher", "Teacher", 170, sortable=True),
                ColumnSpec("contact", "Contact", 130),
                ColumnSpec("issue", "Issue Date", 110),
                ColumnSpec("due", "Due Date", 110),
                ColumnSpec("status", "Status", 110),
            ],
        )
        self.pagination = PaginationBar(
            page_size=self._page_size, on_page=self._go_page, on_page_size=self._change_size
        )

    def build(self) -> ft.Control:
        self.filters = SearchFilters(
            "Search by book title", self._on_book_search, on_clear=self._on_clear_filters
        )
        self.teacher_search = ft.TextField(
            hint_text="Search by teacher name or contact",
            hint_style=HINT_STYLE,
            prefix_icon=ft.Icons.PERSON_SEARCH,
            height=40,
            width=280,
            text_size=14,
            on_change=self._on_teacher_search,
        )
        self.from_date = DateField(self._page, "From Date")
        self.to_date = DateField(self._page, "To Date")
        self.apply_dates = ft.FilledButton(
            content=ft.Text("Apply Dates", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), on_click=self._on_dates,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=14, vertical=10)),
        )
        self.from_date.container.width = 180
        self.to_date.container.width = 180
        self.chips = FilterChips(STATUS_CHIPS, self._on_chip)
        issue_btn = ft.FilledButton(
            content=ft.Text("Issue Book", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.BOOKMARK_ADD_OUTLINED, icon_color=ft.Colors.WHITE, on_click=self._open_issue_dialog,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
        )
        actions = [issue_btn]
        if self._on_manage_teachers:
            actions.append(ft.FilledButton(
                content=ft.Text("Manage Teachers", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.GROUP, icon_color=ft.Colors.WHITE, on_click=lambda e: self._on_manage_teachers(),
                style=ft.ButtonStyle(bgcolor="#2E6F9E", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
            ))
        header = page_header("Teachers", "Issue and track teacher book loans", actions)
        self._root = ft.Column(
            [
                header,
                self.filters,
                ft.Row(
                    [self.teacher_search, self.from_date.container, self.to_date.container, self.apply_dates],
                    spacing=SPACING["md"],
                    run_spacing=SPACING["sm"],
                    wrap=True,
                ),
                self.chips,
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
        if params:
            if params.get("status"):
                self._status = params["status"]
            self.chips.select(self._status or "all")
        self._load()

    # -- data -------------------------------------------------------------------

    def _load(self) -> None:
        if not self._root:
            return
        self.table.set_loading(True)
        try:
            rows, total = self._issues.list_issues(
                status=self._status,
                start_date=self.from_date.date if self.from_date.date else None,
                end_date=self.to_date.date if self.to_date.date else None,
                book_search=self._book_term or None,
                teacher_search=self._teacher_term or None,
                page=self._page_no,
                page_size=self._page_size,
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        self.table.set_rows([self._to_row(t) for t in rows])
        self.pagination.set_state(total, self._page_no)
        self._root.update()

    def _to_row(self, issue) -> TableRow:
        def do_return(e) -> None:
            self._confirm_return(issue)

        def receipt(e) -> None:
            self._show_receipt(issue)

        return TableRow(
            cells={
                "id": styled_text(f"#{issue.id}", style="body"),
                "book": styled_text(issue.book_title, style="body_emphasis"),
                "teacher": styled_text(issue.teacher_name, style="body"),
                "contact": styled_text(issue.teacher_contact or "—", style="body"),
                "issue": styled_text(issue.issue_date.isoformat() if issue.issue_date else "—", style="body"),
                "due": styled_text(issue.due_date.isoformat() if issue.due_date else "—", style="body"),
                "status": status_badge(issue.status),
            },
            key=str(issue.id),
            sort={
                "book": issue.book_title.lower(),
                "teacher": issue.teacher_name.lower(),
            },
            actions=[
                (
                    icon_button(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, "Return book", do_return)
                    if issue.status in ("Issued", "Overdue")
                    else icon_button(ft.Icons.RECEIPT_LONG, "View receipt", receipt)
                ),
                icon_button(ft.Icons.RECEIPT_LONG, "View receipt", receipt),
            ],
        )

    # -- filters -----------------------------------------------------------------

    def _on_book_search(self, term: str) -> None:
        self._book_term = term.strip()
        self._page_no = 1
        self._load()

    def _on_clear_filters(self) -> None:
        """Reset every filter and reload the table to its startup view."""
        self._status = None
        self._book_term = ""
        self._teacher_term = ""
        self._page_no = 1
        self.teacher_search.value = ""
        self.teacher_search.update()
        for picker in (self.from_date, self.to_date):
            picker.date = None
            picker.control.value = ""
            picker.control.update()
        self.chips.select("all", notify=False)
        self._load()

    def _on_teacher_search(self, e) -> None:
        self._teacher_term = (e.control.value or "").strip()
        self._page_no = 1
        self._load()

    def _on_chip(self, key: str | None) -> None:
        self._status = None if key == "all" else key
        self._page_no = 1
        self._load()

    def _on_dates(self, e) -> None:
        self._page_no = 1
        self._load()

    def _go_page(self, page: int) -> None:
        self._page_no = page
        self._load()

    def _change_size(self, size: int) -> None:
        self._page_size = size
        self._page_no = 1
        self._load()

    # -- issue ---------------------------------------------------------------------

    def _open_issue_dialog(self, e=None) -> None:
        from app.presentation.shared_components.form_controls import DropdownField

        book_dropdown = ft.Dropdown(
            label="Book",
            hint_text="Type to search available books",
            hint_style=HINT_STYLE,
            width=400,
            color="#000000",
            options=[ft.dropdown.Option(str(0), "Select a book...")],
        )
        search_field = ft.TextField(
            hint_text="Search available books by title or ISBN",
            hint_style=HINT_STYLE,
            prefix_icon=ft.Icons.SEARCH,
            height=40,
            text_size=14,
            color="#000000",
        )
        available_count = styled_text("", style="caption")
        try:
            teachers, _ = self._teachers.list_teachers(
                self._context, active_only=True, page=1, page_size=200
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        teacher = DropdownField(
            "Teacher",
            [],
            required=True,
            on_change=None,
        )
        teacher.control.options = [
            ft.dropdown.Option(str(t.id), f"{t.name} — {t.contact_number}")
            for t in teachers
        ]
        if not teachers:
            available_count.value = "No active teachers in the registry — add one first."
        self._issue_selected_book: str | None = None
        self._issue_options: list[ft.dropdown.Option] = []
        self._issue_books: dict[str, str] = {}

        def book_searched(ev, sf, dd) -> None:
            term = sf.value.strip()
            try:
                available, _ = self._books.list_available(term, 1, 25)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            self._issue_options = [
                ft.dropdown.Option(b.isbn, f"{b.title} — {b.author} ({b.available_copies} available)")
                for b in available
            ]
            self._issue_books = {b.isbn: b.isbn for b in available}
            dd.options = self._issue_options
            dd.update()
            if not available:
                available_count.value = "No matching books with available copies."
            else:
                available_count.value = ""
            available_count.update()

        def book_picked(ev) -> None:
            value = ev.control.value
            self._issue_selected_book = self._issue_books.get(value) if value else None

        book_dropdown.on_select = book_picked
        search_field.on_change = lambda ev: book_searched(ev, search_field, book_dropdown)

        def save() -> str | None:
            teacher.clear_error()
            if not self._issue_selected_book:
                return "Select a book to issue."
            if not teacher.control.value:
                teacher.error("Select a teacher.")
                return "Select a teacher."
            from app.services.teacher_issue_service import TeacherIssueInput

            payload = TeacherIssueInput(
                book_isbn=self._issue_selected_book,
                teacher_id=int(teacher.control.value),
            )
            try:
                issued = self._issues.issue_book(payload, self._context)
            except LmsError as exc:
                return str(exc)
            self._toasts.show(
                f"'{issued.book_title}' issued to {issued.teacher_name}.",
                "success",
            )
            self._load()
            return None

        dialog = FormDialog(
            self._page,
            "Issue Book",
            [
                search_field,
                book_dropdown,
                available_count,
                teacher.container,
            ],
            save,
            save_label="Issue",
        )
        dialog.open()

    # -- return --------------------------------------------------------------------

    def _confirm_return(self, issue) -> None:
        def do_return() -> None:
            try:
                self._issues.return_book(issue.id, self._context)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            self._toasts.show(f"'{issue.book_title}' returned.", "success")
            self._load()

        confirm(
            self._page,
            "Return Book",
            f"Return '{issue.book_title}' borrowed by {issue.teacher_name}?",
            do_return,
            confirm_text="Return",
            danger=False,
        )

    # -- receipt ---------------------------------------------------------------------

    def _show_receipt(self, issue) -> None:
        lines = [
            f"Teacher Issue #{issue.id}",
            f"Book: {issue.book_title}",
            f"Teacher: {issue.teacher_name}",
            f"Contact: {issue.teacher_contact or '—'}",
            f"Issued: {issue.issue_date.isoformat() if issue.issue_date else '—'}",
            f"Due: {issue.due_date.isoformat() if issue.due_date else '—'}",
            f"Returned: {issue.return_date.isoformat() if issue.return_date else '—'}",
            f"Status: {issue.status}",
            "Fine: No fine (teachers)",
        ]
        info(self._page, "Teacher Issue Receipt", lines)
