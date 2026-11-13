"""Transactions screen: issue, return, filter, receipt (Volume 2, S8)."""

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
from app.presentation.shared_components.form_controls import (
    DateField,
    DropdownField,
    Field,
)
from app.presentation.shared_components.pagination import PaginationBar
from app.presentation.shared_components.search_and_filters import (
    FilterChips,
    SearchFilters,
)
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import HINT_STYLE, SPACING, styled_text
from app.utils.validators import is_valid_phone, normalize_phone

STATUS_CHIPS = [("all", "All"), ("Issued", "Issued"), ("Overdue", "Overdue"), ("Returned", "Returned")]


class TransactionsScreen:
    def __init__(
        self,
        page: ft.Page,
        transaction_service,
        book_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._txns = transaction_service
        self._books = book_service
        self._context = context
        self._toasts = toasts
        self._status: str | None = None
        self._book_term = ""
        self._borrower_term = ""
        self._from_date = None
        self._to_date = None
        self._page_no = 1
        self._page_size = 25
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("id", "#", 60),
                ColumnSpec("book", "Book", 220, sortable=True),
                ColumnSpec("student", "Student", 160, sortable=True),
                ColumnSpec("contact", "Contact", 130),
                ColumnSpec("klass", "Class", 90),
                ColumnSpec("issue", "Issue Date", 110),
                ColumnSpec("due", "Due Date", 110),
                ColumnSpec("status", "Status", 110),
                ColumnSpec("fine", "Fine", 80),
            ],
        )
        self.pagination = PaginationBar(
            page_size=self._page_size, on_page=self._go_page, on_page_size=self._change_size
        )

    def build(self) -> ft.Control:
        self.filters = SearchFilters(
            "Search by book title", self._on_book_search, on_clear=self._on_clear_filters
        )
        self.borrower_search = ft.TextField(
            hint_text="Search by student name or contact",
            hint_style=HINT_STYLE,
            prefix_icon=ft.Icons.PERSON_SEARCH,
            height=40,
            width=280,
            text_size=14,
            color="#000000",
            on_change=self._on_borrower_search,
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
        header = page_header("Issued/Returned Books", "Issue and track book loans", [issue_btn])
        self._root = ft.Column(
            [
                header,
                self.filters,
                ft.Row(
                    [self.borrower_search, self.from_date.container, self.to_date.container, self.apply_dates],
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
            if params.get("borrower") is not None:
                self._borrower_term = (params["borrower"] or "").strip()
                self._page_no = 1
                try:
                    self.borrower_search.value = self._borrower_term
                    self.borrower_search.update()
                except Exception:
                    pass
            self.chips.select(self._status or "all")
        self._load()

    def clear_search(self) -> None:
        """Drop any applied (global or local) borrower term without reloading;
        the caller reloads the visible screen."""
        self._borrower_term = ""
        self._page_no = 1
        try:
            self.borrower_search.value = ""
            self.borrower_search.update()
        except Exception:
            pass

    # -- data -------------------------------------------------------------------

    def _load(self) -> None:
        if not self._root:
            return
        self.table.set_loading(True)
        try:
            rows, total = self._txns.list_transactions(
                status=self._status,
                start_date=self.from_date.date if self.from_date.date else None,
                end_date=self.to_date.date if self.to_date.date else None,
                book_search=self._book_term or None,
                borrower_search=self._borrower_term or None,
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

    def _to_row(self, txn) -> TableRow:
        def do_return(e) -> None:
            self._confirm_return(txn)

        def receipt(e) -> None:
            self._show_receipt(txn)

        return TableRow(
            cells={
                "id": styled_text(f"#{txn.id}", style="body"),
                "book": styled_text(txn.book_title, style="body_emphasis"),
                "student": styled_text(txn.student_name, style="body"),
                "contact": styled_text(txn.contact_number or "—", style="body"),
                "klass": styled_text(f"{txn.class_name} {txn.stream or ''} {txn.section or ''}".strip(), style="body"),
                "issue": styled_text(txn.issue_date.isoformat() if txn.issue_date else "—", style="body"),
                "due": styled_text(txn.due_date.isoformat() if txn.due_date else "—", style="body"),
                "status": status_badge(txn.status),
                "fine": styled_text(
                    f"₹{txn.fine_amount:.2f}" if txn.fine_amount else "—", style="body"
                ),
            },
            key=str(txn.id),
            sort={
                "book": txn.book_title.lower(),
                "student": txn.student_name.lower(),
            },
            actions=[
                (
                    icon_button(ft.Icons.ASSIGNMENT_TURNED_IN_OUTLINED, "Return book", do_return)
                    if txn.status in ("Issued", "Overdue")
                    else icon_button(ft.Icons.RECEIPT_LONG, "View receipt", receipt)
                ),
                icon_button(ft.Icons.RECEIPT_LONG, "View receipt", receipt),
            ],
        )

    # -- filters -----------------------------------------------------------------

    def _on_book_search(self, term: str | None) -> None:
        self._book_term = (term or "").strip()
        self._page_no = 1
        self._load()

    def _on_clear_filters(self) -> None:
        """Reset every filter and reload the table to its startup view."""
        self._status = None
        self._book_term = ""
        self._borrower_term = ""
        self._page_no = 1
        self.borrower_search.value = ""
        self.borrower_search.update()
        for picker in (self.from_date, self.to_date):
            picker.date = None
            picker.control.value = ""
            picker.control.update()
        self.chips.select("all", notify=False)
        self._load()

    def _on_borrower_search(self, e) -> None:
        self._borrower_term = (e.control.value or "").strip()
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
        student = Field("Student Name", required=True, hint="Full name of the borrower")
        contact = Field("Contact Number", required=True, hint="10-digit mobile number", prefix_icon=ft.Icons.PHONE)
        stream = DropdownField("Stream", [], required=False)
        section = Field("Section", hint="e.g. A")
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

        def on_class_change(ev):
            grade = ev.control.value
            is_senior = grade in ("11", "12")
            stream.set_required(is_senior)
            if is_senior:
                stream.control.options = [
                    ft.dropdown.Option(s) for s in ["Science", "Commerce", "Humanities"]
                ]
            else:
                stream.control.options = []
                stream.control.value = None
            stream.control.update()

        klass = DropdownField("Class", [str(i) for i in range(1, 13)], required=True, on_change=on_class_change)

        def save() -> str | None:
            student.clear_error()
            contact.clear_error()
            stream.clear_error()
            if not self._issue_selected_book:
                return "Select a book to issue."
            name = (student.control.value or "").strip()
            if not name:
                student.error("Student name is required.")
                return "Student name is required."
            phone = (contact.control.value or "").strip()
            if not phone or not is_valid_phone(phone):
                contact.error("Enter a valid phone number.")
                return "Enter a valid phone number."
            if not klass.control.value:
                klass.error("Class is required.")
                return "Class is required."
            grade = klass.control.value
            if grade in ("11", "12") and not stream.control.value:
                stream.error("Select a stream.")
                return "Select a stream."
            from app.services.transaction_service import IssueInput

            payload = IssueInput(
                book_isbn=self._issue_selected_book,
                student_name=name,
                contact_number=normalize_phone(phone),
                class_name=grade,
                stream=stream.control.value or "",
                section=(section.control.value or "").strip() or None,
            )
            try:
                issued = self._txns.issue_book(payload, self._context)
            except LmsError as exc:
                return str(exc)
            self._toasts.show(
                f"'{issued.book_title}' issued to {issued.student_name}.",
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
                student.container,
                contact.container,
                klass.container,
                stream.container,
                section.container,
            ],
            save,
            save_label="Issue",
        )
        dialog.open()

    # -- return --------------------------------------------------------------------

    def _confirm_return(self, txn) -> None:
        def do_return() -> None:
            try:
                result = self._txns.return_book(txn.id, self._context)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            if result.fine_amount:
                self._toasts.show(
                    f"'{txn.book_title}' returned with a fine of ₹{result.fine_amount:.2f}.",
                    "warning",
                )
            else:
                self._toasts.show(f"'{txn.book_title}' returned.", "success")
            self._load()

        confirm(
            self._page,
            "Return Book",
            f"Return '{txn.book_title}' borrowed by {txn.student_name}?",
            do_return,
            confirm_text="Return",
            danger=False,
        )

    # -- receipt ---------------------------------------------------------------------

    def _show_receipt(self, txn) -> None:
        lines = [
            f"Transaction #{txn.id}",
            f"Book: {txn.book_title}",
            f"Student: {txn.student_name}",
            f"Contact: {txn.contact_number or '—'}",
            f"Class: {txn.class_name} {txn.stream or ''} {txn.section or ''}".strip(),
            f"Issued: {txn.issue_date.isoformat() if txn.issue_date else '—'}",
            f"Due: {txn.due_date.isoformat() if txn.due_date else '—'}",
            f"Returned: {txn.return_date.isoformat() if txn.return_date else '—'}",
            f"Status: {txn.status}",
            f"Fine: ₹{txn.fine_amount:.2f}" if txn.fine_amount else "Fine: —",
        ]
        info(self._page, "Transaction Receipt", lines)