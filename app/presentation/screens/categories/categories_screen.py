"""Categories screen: list, add, edit, delete with usage guard."""

from __future__ import annotations

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.buttons import icon_button
from app.presentation.shared_components.cards import page_header
from app.presentation.shared_components.data_table import (
    ColumnSpec,
    DataTable,
    TableRow,
)
from app.presentation.shared_components.dialogs import FormDialog, confirm
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import Field
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import SPACING, styled_text


class CategoriesScreen:
    def __init__(
        self,
        page: ft.Page,
        category_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._categories = category_service
        self._context = context
        self._toasts = toasts
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("name", "Name", 260, sortable=True),
                ColumnSpec("description", "Description", 320),
                ColumnSpec("books", "Books", 90),
            ],
        )

    def build(self) -> ft.Control:
        add_btn = ft.FilledButton(
            content=ft.Text("Add Category", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.ADD, icon_color=ft.Colors.WHITE, on_click=self._open_add_dialog,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
        )
        header = page_header("Categories", "Organise your book collection", [add_btn])
        self._root = ft.Column(
            [
                header,
                self.table,
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
            categories = self._categories.list_all(self._context)
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        self.table.set_rows([self._to_row(c) for c in categories])
        self._root.update()

    def _to_row(self, category) -> TableRow:
        def edit(e) -> None:
            self._open_edit_dialog(category)

        def delete(e) -> None:
            self._confirm_delete(category)

        return TableRow(
            cells={
                "name": styled_text(category.name, style="body_emphasis"),
                "description": styled_text(category.description or "—", style="body"),
                "books": styled_text(str(category.book_count), style="body"),
            },
            key=str(category.id),
            sort={"name": category.name.lower()},
            actions=[
                icon_button(ft.Icons.EDIT_OUTLINED, "Edit category", edit),
                icon_button(ft.Icons.DELETE_OUTLINE, "Delete category", delete, color="#C0362C"),
            ],
        )

    def _open_add_dialog(self, e=None) -> None:
        self._category_dialog("Add Category", None).open()

    def _open_edit_dialog(self, category) -> None:
        self._category_dialog("Edit Category", category).open()

    def _category_dialog(self, title: str, category: object | None) -> FormDialog:
        name = Field("Category Name", value=category.name if category else "", required=True, hint="e.g. Fiction")
        description = Field("Description", value=category.description or "" if category else "")

        def save() -> str | None:
            from app.services.category_service import CategoryInput

            if not (name.control.value or "").strip():
                name.error("Category name is required.")
                return "Category name is required."

            payload = CategoryInput(
                name=(name.control.value or "").strip(),
                description=(description.control.value or "").strip() or None,
            )
            try:
                if category:
                    self._categories.update(category.id, payload, self._context)
                else:
                    self._categories.create(payload, self._context)
            except LmsError as exc:
                return str(exc)
            self._toasts.show(
                f"Category '{payload.name}' {'updated' if category else 'added'} successfully.",
                "success",
            )
            self._load()
            return None

        return FormDialog(self._page, title, [name.container, description.container], save)

    def _confirm_delete(self, category) -> None:
        def do_delete() -> None:
            try:
                self._categories.delete(category.id, self._context)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            self._toasts.show(f"Category '{category.name}' deleted.", "success")
            self._load()

        confirm(self._page, "Delete Category", "Delete category", do_delete, object_name=category.name)