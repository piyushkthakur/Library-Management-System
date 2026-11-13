"""Book Catalog screen: search, quick filters, add/edit/delete, QR codes."""

from __future__ import annotations

import asyncio
import io
import logging

import flet as ft
import qrcode

from app.core.exceptions import DuplicateResourceError, LmsError
from app.presentation.shared_components.badges import availability_badge
from app.presentation.shared_components.buttons import Button, icon_button, text_button
from app.presentation.shared_components.cards import page_header
from app.presentation.shared_components.data_table import (
    ColumnSpec,
    DataTable,
    TableRow,
)
from app.presentation.shared_components.dialogs import FormDialog, confirm, info
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import (
    DropdownField,
    Field,
    NumberField,
)
from app.presentation.shared_components.pagination import PaginationBar
from app.presentation.shared_components.search_and_filters import (
    FilterChips,
    SearchFilters,
)
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import SPACING, styled_text
from app.services.category_suggest import suggest_category
from app.services.isbn_lookup import lookup_isbn, match_category
from app.utils.validators import is_valid_isbn, normalize_isbn

logger = logging.getLogger(__name__)


class BooksScreen:
    def __init__(
        self,
        page: ft.Page,
        book_service,
        category_service,
        import_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._books = book_service
        self._categories = category_service
        self._importer = import_service
        self._context = context
        self._toasts = toasts
        self._term = ""
        self._category_id: int | None = None
        self._availability: str | None = None
        self._page_no = 1
        self._page_size = 25
        self._category_names: list[str] = []
        self._category_ids: dict[str, int] = {}
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("title", "Title", 220, sortable=True),
                ColumnSpec("author", "Author", 180),
                ColumnSpec("isbn", "ISBN", 140),
                ColumnSpec("category", "Category", 140),
                ColumnSpec("copies", "Copies", 160),
                ColumnSpec("shelf", "Shelf", 100),
            ],
        )
        self.pagination = PaginationBar(
            page_size=self._page_size, on_page=self._go_page, on_page_size=self._change_size
        )

    def build(self) -> ft.Control:
        self._load_categories()
        self.filters = SearchFilters(
            "Search by title, author or ISBN",
            self._on_search,
            dropdowns=[("Category", self._category_names, self._on_category)],
            on_clear=self._on_clear_filters,
        )
        self.chips = FilterChips(
            [("all", "All"), ("available", "Available"), ("unavailable", "Unavailable")],
            self._on_chip,
        )
        add_btn = ft.FilledButton(
            content=ft.Text("Add Book", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.ADD, icon_color=ft.Colors.WHITE, on_click=self._open_add_dialog,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
        )
        import_btn = ft.FilledButton(
            content=ft.Text("Import Books", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.UPLOAD_FILE, icon_color=ft.Colors.WHITE, on_click=self._open_import,
            style=ft.ButtonStyle(bgcolor="#2E6F9E", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
        )
        header = page_header("Book Catalog", "Manage your library's collection", [import_btn, add_btn])
        self._root = ft.Column(
            [
                header,
                self.filters,
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
        if params and params.get("search") is not None:
            self._term = (params["search"] or "").strip()
            self._page_no = 1
            try:
                self.filters.search.value = self._term
                self.filters.search.update()
            except Exception:
                pass
        self._load()

    def clear_search(self) -> None:
        """Drop any applied (global or local) search term without reloading;
        the caller reloads the visible screen."""
        self._term = ""
        self._page_no = 1
        try:
            self.filters.search.value = ""
            self.filters.search.update()
        except Exception:
            pass

    # -- data -----------------------------------------------------------------

    def _load_categories(self) -> None:
        try:
            cats = self._categories.list_all(self._context)
            self._category_names = [c.name for c in cats]
            self._category_ids = {c.name: c.id for c in cats}
        except LmsError:
            self._category_names = []

    def _load(self) -> None:
        if not self._root:
            return
        self.table.set_loading(True)
        try:
            books, total = self._books.search(
                self._term, self._category_id, self._page_no, self._page_size
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        rows = [self._to_row(b) for b in books]
        if self._availability == "available":
            rows = [r for r in rows if r.sort.get("copies", 0) > 0]
        elif self._availability == "unavailable":
            rows = [r for r in rows if r.sort.get("copies", 0) == 0]
        self.table.set_rows(rows)
        self.pagination.set_state(total, self._page_no)
        self._root.update()

    def _to_row(self, book) -> TableRow:
        def view(e) -> None:
            self._show_details(book)

        def edit(e) -> None:
            self._open_edit_dialog(book)

        def delete(e) -> None:
            self._confirm_delete(book)

        def qr(e) -> None:
            self._show_qr(book)

        return TableRow(
            cells={
                "title": styled_text(book.title, style="body_emphasis"),
                "author": styled_text(book.author, style="body"),
                "isbn": styled_text(book.isbn, style="body"),
                "category": styled_text(book.category_name or "—", style="body"),
                "copies": availability_badge(book.available_copies, book.total_copies),
                "shelf": styled_text(book.shelf_location or "—", style="body"),
            },
            key=book.isbn,
            sort={
                "title": book.title.lower(),
                "author": book.author.lower(),
                "isbn": book.isbn,
                "copies": book.available_copies,
            },
            actions=[
                icon_button(ft.Icons.VISIBILITY_OUTLINED, "View book details", view),
                icon_button(ft.Icons.QR_CODE_2, "View QR code", qr),
                icon_button(ft.Icons.EDIT_OUTLINED, "Edit book", edit),
                icon_button(ft.Icons.DELETE_OUTLINE, "Delete book", delete, color="#C0362C"),
            ],
        )

    # -- filter handlers --------------------------------------------------------

    def _on_search(self, term: str | None) -> None:
        self._term = (term or "").strip()
        self._page_no = 1
        self._load()

    def _on_category(self, name: str | None) -> None:
        self._category_id = self._category_ids.get(name) if name else None
        self._page_no = 1
        self._load()

    def _on_chip(self, key: str | None) -> None:
        self._availability = key
        self._load()

    def _on_clear_filters(self) -> None:
        """Reset filters and reload the table to its startup view."""
        self._term = ""
        self._category_id = None
        self._availability = None
        self._page_no = 1
        self.chips.select("all", notify=False)
        self._load()

    def _go_page(self, page: int) -> None:
        self._page_no = page
        self._load()

    def _change_size(self, size: int) -> None:
        self._page_size = size
        self._page_no = 1
        self._load()

    # -- add / edit ---------------------------------------------------------------

    def _open_add_dialog(self, e=None) -> None:
        dialog = self._book_dialog("Add Book", None)
        dialog.open()

    def _open_import(self, e=None) -> None:
        from app.presentation.screens.books.import_books_dialog import ImportBooksDialog
        self._import_dialog = ImportBooksDialog(
            self._page,
            self._importer,
            self._context,
            self._load,
            self._toasts,
        )
        self._import_dialog.open()

    def _open_edit_dialog(self, book) -> None:
        dialog = self._book_dialog("Edit Book", book)
        dialog.open()

    def _book_dialog(self, title: str, book: object | None) -> FormDialog:
        _tracked: dict[str, str] = {
            "name": book.title if book else "",
            "author": book.author if book else "",
            "isbn": book.isbn if book else "",
            "shelf": book.shelf_location or "" if book else "",
        }

        def _on_name(e):
            _tracked["name"] = e.control.value or ""

        def _on_author(e):
            _tracked["author"] = e.control.value or ""

        # -- ISBN autofill: one online lookup per valid ISBN per dialog --

        # ponytail: the source chain (Open Library -> Google Books ->
        # isbn.gov.in) can take a few seconds on a miss; hint while it runs.
        # Several lookups may overlap (ISBN-10 fires at 10 digits, ISBN-13
        # at 13), so the hint hides only when the last one finishes.
        _lookups_running = 0
        searching = ft.Row(
            [
                ft.ProgressRing(width=14, height=14, stroke_width=2),
                styled_text("Searching ISBN online…", style="caption"),
            ],
            spacing=SPACING["xs"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        searching.visible = False

        def _set_searching(active: bool) -> None:
            nonlocal _lookups_running
            _lookups_running += 1 if active else -1
            searching.visible = _lookups_running > 0
            try:
                searching.update()
            except Exception:
                pass  # dialog closed mid-lookup


        def _apply_lookup(result) -> None:
            # Non-destructive: fill only fields the user left empty.
            if not name.control.value:
                name.control.value = result.title
                _tracked["name"] = result.title
                name.clear_error()
            if not author.control.value:
                author.control.value = result.author
                _tracked["author"] = result.author
                author.clear_error()
            if not category.control.value:
                matched = match_category(result.categories, self._category_names)
                if matched:
                    category.control.value = matched
            # per product decision: a fetched entry always carries 1 copy
            copies.control.value = "1"

        async def _on_isbn(e):
            value = (e.control.value or "").strip()
            _tracked["isbn"] = value
            _clear_proposal()  # a proposal belongs to one exact ISBN
            if book is not None:
                return
            norm = normalize_isbn(value)
            if not is_valid_isbn(value):
                return

            proposal: str | None = None
            _set_searching(True)
            try:
                result = await asyncio.to_thread(lookup_isbn, norm)
                # dialog closed or the ISBN was edited while the lookup ran
                if result is None or (_tracked["isbn"] or "").strip() != value:
                    return
                try:
                    _apply_lookup(result)
                    if not category.control.value:
                        # candidates -> title rules -> keyed AI, off the UI thread
                        proposal = await asyncio.to_thread(suggest_category, result)
                except Exception:
                    logger.debug("ISBN autofill skipped; dialog changed mid-flight", exc_info=True)
                    return
            finally:
                _set_searching(False)
            if (_tracked["isbn"] or "").strip() != value:
                return  # kept typing during the suggestion
            if proposal and not category.control.value:
                existing = match_category((proposal,), self._category_names)
                if existing:
                    category.control.value = existing
                else:
                    _show_proposal(proposal)
            try:
                for c in (name.control, author.control, category.control, copies.control):
                    c.update()
            except Exception:
                logger.debug("ISBN autofill skipped; dialog changed mid-flight", exc_info=True)

        def _on_shelf(e):
            _tracked["shelf"] = e.control.value or ""

        name = Field("Title", value=_tracked["name"], required=True, hint="e.g. The Great Gatsby", on_change=_on_name)
        author = Field("Author", value=_tracked["author"], required=True, hint="e.g. F. Scott Fitzgerald", on_change=_on_author)
        isbn = Field("ISBN", value=_tracked["isbn"], required=True, hint="10 or 13 digit ISBN", on_change=_on_isbn)
        isbn.container.content.controls.append(searching)  # lookup hint below the input
        if book is not None:
            # ponytail: ISBN is the primary key — immutable after creation.
            isbn.control.disabled = True
        category = DropdownField("Category", self._category_names, value=book.category_name if book else None, required=True)
        copies = NumberField("Copies", value=str(book.total_copies) if book else "1", required=True)
        shelf = Field("Shelf Location", value=_tracked["shelf"], hint="e.g. A-12", on_change=_on_shelf)

        # -- new-category affordance: proposal slot + always-on manual chip.
        # Nothing writes until a chip is clicked; edit mode gets neither.
        proposal_slot: list = []
        chips = ft.Row([], spacing=SPACING["xs"], visible=book is None)

        def _clear_proposal() -> None:
            if not proposal_slot:
                return
            try:
                chips.controls.remove(proposal_slot.pop())
                chips.update()
            except Exception:
                pass  # dialog closed mid-flow

        def _show_proposal(name: str) -> None:
            if category.control.value or proposal_slot:
                return
            chip = text_button(f'+ Create "{name}"', lambda e: _create_category(name))
            proposal_slot.append(chip)
            chips.controls.insert(0, chip)
            try:
                chips.update()
            except Exception:
                pass  # dialog closed mid-flow

        def _create_category(name: str) -> None:
            from app.services.category_service import CategoryInput

            try:
                self._categories.create(CategoryInput(name=name), self._context)
            except DuplicateResourceError:
                self._load_categories()  # raced an existing name: select it below
            except LmsError as exc:
                self._toasts.show(str(exc), "error")
                return
            else:
                self._toasts.show(f"Category '{name}' added successfully.", "success")
                self._load_categories()
            # the open dialog's dropdown is a build-time snapshot of the
            # options — refresh them so the new category is selectable now.
            category.control.options = [ft.dropdown.Option(n) for n in self._category_names]
            actual = next(
                (n for n in self._category_names if n.casefold() == name.casefold()),
                None,
            )
            if actual:
                category.control.value = actual
            _clear_proposal()
            try:
                category.control.update()
            except Exception:
                pass  # dialog closed mid-flow

        def _new_category(e=None) -> None:
            name_field = Field("Category Name", required=True, hint="e.g. Fiction")

            def save_new() -> str | None:
                name = (name_field.control.value or "").strip()
                if not name:
                    return "Category name is required."
                _create_category(name)
                return None

            FormDialog(self._page, "New Category", [name_field.container], save_new).open()

        if book is None:
            chips.controls.append(text_button("+ New category…", _new_category))
            category.container.content.controls.append(chips)

        def save() -> str | None:
            name_val = _tracked["name"].strip()
            author_val = _tracked["author"].strip()
            isbn_val = _tracked["isbn"].strip()
            shelf_val = _tracked["shelf"].strip()

            if not name_val:
                return "Title is required."
            if not author_val:
                return "Author is required."
            if not isbn_val:
                return "ISBN is required."
            if not is_valid_isbn(isbn_val):
                return "Enter a valid ISBN-10 or ISBN-13."
            if not category.control.value:
                return "Select a category."
            copies_value = int((copies.control.value or "0").strip())
            if copies_value < 1:
                return "Copies must be at least 1."

            from app.services.book_service import BookInput
            payload = BookInput(
                title=name_val,
                author=author_val,
                isbn=isbn_val,
                category_id=self._category_ids.get(category.control.value),
                total_copies=copies_value,
                shelf_location=shelf_val or None,
            )
            try:
                if book:
                    self._books.update(book.isbn, payload, self._context)
                else:
                    self._books.create(payload, self._context)
            except LmsError as exc:
                return str(exc)
            except Exception as exc:
                notify_error(self._toasts, exc)
                return str(exc)
            self._toasts.show(
                f"Book '{payload.title}' {'updated' if book else 'added'} successfully.",
                "success",
            )
            self._load()
            return None

        def _clear_form(e=None) -> None:
            """Reset every field to its default state (Add mode only)."""
            _tracked.update(name="", author="", isbn="", shelf="")
            for field, value in (
                (isbn, ""),
                (name, ""),
                (author, ""),
                (copies, "1"),
                (shelf, ""),
            ):
                field.control.value = value
            category.control.value = None
            _clear_proposal()
            try:
                for f in (isbn, name, author, category, copies, shelf):
                    f.clear_error()
                dialog.set_error("")
                for c in (
                    isbn.control,
                    name.control,
                    author.control,
                    category.control,
                    copies.control,
                    shelf.control,
                ):
                    c.update()
            except Exception:
                logger.debug("Clear skipped; dialog changed mid-flight", exc_info=True)

        # ponytail: ISBN leads the form — the user types it first and the
        # rest of the catalog data autofills below it.
        dialog = FormDialog(
            self._page,
            title,
            [isbn.container, name.container, author.container, category.container, copies.container, shelf.container],
            save,
            extra_actions=[Button("Clear", on_click=_clear_form, variant="subtle")] if book is None else None,
        )
        return dialog

    # -- delete --------------------------------------------------------------

    def _confirm_delete(self, book) -> None:
        def do_delete() -> None:
            try:
                self._books.delete(book.isbn, self._context)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            self._toasts.show(f"Book '{book.title}' deleted.", "success")
            self._load()

        confirm(self._page, "Delete Book", "Delete book", do_delete, object_name=book.title)

    # -- QR ------------------------------------------------------------------

    def _show_details(self, book) -> None:
        """Read-only book details (no editing)."""
        info(
            self._page,
            book.title,
            [
                f"Author: {book.author}",
                f"ISBN: {book.isbn}",
                f"Category: {book.category_name or '—'}",
                f"Copies: {book.available_copies} of {book.total_copies} available",
                f"Shelf: {book.shelf_location or '—'}",
            ],
        )

    def _show_qr(self, book) -> None:
        payload = "\n".join(
            [
                f"Title: {book.title}",
                f"Author: {book.author}",
                f"ISBN: {book.isbn}",
                f"Category: {book.category_name or '—'}",
                f"Copies: {book.available_copies} of {book.total_copies} available",
                f"Shelf: {book.shelf_location or '—'}",
            ]
        )
        img = qrcode.make(payload, box_size=6, border=2)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        qr_view = ft.Container(
            ft.Image(
                src=buf.getvalue(),
                width=220,
                height=220,
            ),
            alignment=ft.Alignment.CENTER,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=styled_text(f"QR Code — {book.title}", style="h1"),
            content=ft.Column(
                [
                    qr_view,
                    styled_text(f"ISBN: {book.isbn}", style="caption"),
                    styled_text("Scan to look up this book's details.", style="caption"),
                ],
                spacing=SPACING["sm"],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            actions=[ft.FilledButton(content=ft.Text("Close", color=ft.Colors.WHITE), on_click=lambda e: self._page.pop_dialog())],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        dialog.width = 420
        self._page.show_dialog(dialog)