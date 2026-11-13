"""Librarians screen (Administrator only): list, add, edit, activate, reset."""

from __future__ import annotations

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.badges import badge
from app.presentation.shared_components.buttons import icon_button
from app.presentation.shared_components.cards import page_header
from app.presentation.shared_components.data_table import (
    ColumnSpec,
    DataTable,
    TableRow,
)
from app.presentation.shared_components.dialogs import FormDialog
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import Field, PasswordField
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import (
    COLOR_DANGER,
    COLOR_SUCCESS,
    SPACING,
    styled_text,
)
from app.utils.validators import is_valid_email, password_error


def _active_badge(active: bool) -> ft.Container:
    return badge("Active" if active else "Inactive", COLOR_SUCCESS if active else COLOR_DANGER)


class LibrariansScreen:
    def __init__(
        self,
        page: ft.Page,
        librarian_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._librarians = librarian_service
        self._context = context
        self._toasts = toasts
        self._page_no = 1
        self._page_size = 25
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("name", "Name", 240, sortable=True),
                ColumnSpec("email", "Email", 260),
                ColumnSpec("created", "Added On", 120),
                ColumnSpec("active", "Status", 110),
            ],
        )
        self.pagination = None

    def build(self) -> ft.Control:
        add_btn = ft.FilledButton(
            content=ft.Text("Add Librarian", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.PERSON_ADD_ALT, icon_color=ft.Colors.WHITE, on_click=self._open_add_dialog,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
        )
        from app.presentation.shared_components.pagination import PaginationBar

        self.pagination = PaginationBar(
            page_size=self._page_size, on_page=self._go_page, on_page_size=self._change_size
        )
        header = page_header("Librarians", "Manage support staff access", [add_btn])
        self._root = ft.Column(
            [
                header,
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
            librarians, total = self._librarians.list_librarians(
                self._context, page=self._page_no, page_size=self._page_size
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        self.table.set_rows([self._to_row(lib) for lib in librarians])
        self.pagination.set_state(total, self._page_no)
        self._root.update()

    def _to_row(self, lib) -> TableRow:
        def edit(e) -> None:
            self._open_edit_dialog(lib)

        def reset(e) -> None:
            self._open_reset_dialog(lib)

        def toggle(e) -> None:
            self._confirm_toggle(lib)

        actions = [
            icon_button(ft.Icons.KEY_OUTLINED, "Reset temporary password", reset),
            icon_button(ft.Icons.EDIT_OUTLINED, "Edit librarian", edit),
            icon_button(
                ft.Icons.DO_NOT_DISTURB_ALT if lib.is_active else ft.Icons.CHECK_CIRCLE_OUTLINE,
                "Deactivate" if lib.is_active else "Activate",
                toggle,
                color="#C0362C" if lib.is_active else "#1D9A6C",
            ),
        ]
        return TableRow(
            cells={
                "name": styled_text(lib.full_name, style="body_emphasis"),
                "email": styled_text(lib.email, style="body"),
                "created": styled_text(
                    lib.created_at.strftime("%d %b %Y") if lib.created_at else "—", style="body"
                ),
                "active": _active_badge(lib.is_active),
            },
            key=str(lib.id),
            sort={"name": lib.full_name.lower()},
            actions=actions,
        )

    def _open_add_dialog(self, e=None) -> None:
        self._librarian_dialog("Add Librarian", None).open()

    def _open_edit_dialog(self, lib) -> None:
        self._librarian_dialog("Edit Librarian", lib).open()

    def _librarian_dialog(self, title: str, lib: object | None) -> FormDialog:
        name = Field("Full Name", value=lib.full_name if lib else "", required=True)
        email = Field("Email Address", value=lib.email if lib else "", required=True, prefix_icon=ft.Icons.MAIL_OUTLINE)
        password = PasswordField("Temporary Password", required=True, helper="Sent to the librarian; minimum 8 characters.")
        if lib:
            password.container.visible = False

        def save() -> str | None:
            from app.services.librarian_service import LibrarianInput

            if not (name.control.value or "").strip():
                name.error("Full name is required.")
                return "Full name is required."
            email_value = (email.control.value or "").strip()
            if not email_value or not is_valid_email(email_value):
                email.error("Enter a valid email address.")
                return "Enter a valid email address."
            if not lib:
                pw_error = password_error(password.control.value or "")
                if pw_error:
                    password.error(pw_error)
                    return pw_error
                payload = LibrarianInput(
                    full_name=(name.control.value or "").strip(),
                    email=email_value,
                    temporary_password=password.control.value,
                )
                try:
                    self._librarians.create(self._context, payload)
                except LmsError as exc:
                    return str(exc)
                created = payload.full_name
                self._toasts.show(f"Librarian '{created}' added.", "success")
            else:
                payload = LibrarianInput(
                    full_name=(name.control.value or "").strip(),
                    email=email_value,
                    temporary_password="",
                )
                try:
                    self._librarians.update(self._context, lib.id, payload)
                except LmsError as exc:
                    return str(exc)
                self._toasts.show("Librarian updated.", "success")
            self._load()
            return None

        return FormDialog(self._page, title, [name.container, email.container, password.container], save)

    def _open_reset_dialog(self, lib) -> None:
        password = PasswordField("New Temporary Password", required=True, helper="Minimum 8 characters.")
        def save() -> str | None:
            from app.services.librarian_service import LibrarianInput

            pw_error = password_error(password.control.value or "")
            if pw_error:
                password.error(pw_error)
                return pw_error
            try:
                self._librarians.update(
                    self._context, lib.id,
                    LibrarianInput(full_name=lib.full_name, email=lib.email, temporary_password=password.control.value),
                )
            except LmsError as exc:
                return str(exc)
            self._toasts.show(f"Temporary password set for {lib.full_name}.", "success")
            return None

        FormDialog(self._page, f"Reset Password — {lib.full_name}", [password.container], save, save_label="Save").open()

    def _confirm_toggle(self, lib) -> None:
        from app.presentation.shared_components.dialogs import confirm

        def do_toggle() -> None:
            try:
                self._librarians.set_active_status(self._context, lib.id, not lib.is_active)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            state = "activated" if not lib.is_active else "deactivated"
            self._toasts.show(f"{lib.full_name} {state}.", "success")
            self._load()

        if lib.is_active:
            confirm(self._page, "Deactivate Librarian", "Deactivate librarian", do_toggle, object_name=lib.full_name)
        else:
            confirm(self._page, "Activate Librarian", "Activate librarian", do_toggle, confirm_text="Activate", danger=False, object_name=lib.full_name)

    def _go_page(self, page: int) -> None:
        self._page_no = page
        self._load()

    def _change_size(self, size: int) -> None:
        self._page_size = size
        self._page_no = 1
        self._load()