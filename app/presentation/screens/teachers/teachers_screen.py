"""Teachers screen: registry list, add, edit, activate/deactivate."""

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
from app.presentation.shared_components.dialogs import FormDialog, confirm
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import Field
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import (
    COLOR_DANGER,
    COLOR_SUCCESS,
    SPACING,
    styled_text,
)
from app.utils.validators import is_valid_phone


def _active_badge(active: bool) -> ft.Container:
    return badge("Active" if active else "Inactive", COLOR_SUCCESS if active else COLOR_DANGER)


class TeachersScreen:
    def __init__(
        self,
        page: ft.Page,
        teacher_service,
        context,
        toasts: ToastHost,
        on_back=None,
    ) -> None:
        self._page = page
        self._teachers = teacher_service
        self._context = context
        self._toasts = toasts
        self._on_back = on_back
        self._term = ""
        self._page_no = 1
        self._page_size = 25
        self._root: ft.Control | None = None
        self.table = DataTable(
            [
                ColumnSpec("name", "Name", 240, sortable=True),
                ColumnSpec("contact", "Contact", 160),
                ColumnSpec("subject", "Subject", 160),
                ColumnSpec("active", "Status", 110),
            ],
        )
        self.pagination = None

    def build(self) -> ft.Control:
        from app.presentation.shared_components.pagination import PaginationBar
        from app.presentation.shared_components.search_and_filters import SearchFilters

        add_btn = ft.FilledButton(
            content=ft.Text("Add Teacher", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.PERSON_ADD_ALT, icon_color=ft.Colors.WHITE, on_click=self._open_add_dialog,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
        )
        self.filters = SearchFilters("Search by name, contact or subject", self._on_search)
        self.pagination = PaginationBar(
            page_size=self._page_size, on_page=self._go_page, on_page_size=self._change_size
        )
        actions = [add_btn]
        if self._on_back:
            actions.insert(0, ft.FilledButton(
                content=ft.Text("Back to Issues", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), icon=ft.Icons.ARROW_BACK, icon_color=ft.Colors.WHITE, on_click=lambda e: self._on_back(),
                style=ft.ButtonStyle(bgcolor="#2E6F9E", padding=ft.Padding.symmetric(horizontal=18, vertical=11)),
            ))
        header = page_header("Teacher Registry", "Manage the staff borrower registry", actions)
        self._root = ft.Column(
            [
                header,
                self.filters,
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
            teachers, total = self._teachers.list_teachers(
                self._context, search=self._term or None,
                page=self._page_no, page_size=self._page_size,
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            self.table.set_loading(False)
            return
        self.table.set_rows([self._to_row(t) for t in teachers])
        self.pagination.set_state(total, self._page_no)
        self._root.update()

    def _to_row(self, teacher) -> TableRow:
        def edit(e) -> None:
            self._open_edit_dialog(teacher)

        def toggle(e) -> None:
            self._confirm_toggle(teacher)

        return TableRow(
            cells={
                "name": styled_text(teacher.name, style="body_emphasis"),
                "contact": styled_text(teacher.contact_number, style="body"),
                "subject": styled_text(teacher.subject or "—", style="body"),
                "active": _active_badge(teacher.is_active),
            },
            key=str(teacher.id),
            sort={"name": teacher.name.lower()},
            actions=[
                icon_button(ft.Icons.EDIT_OUTLINED, "Edit teacher", edit),
                icon_button(
                    ft.Icons.DO_NOT_DISTURB_ALT if teacher.is_active else ft.Icons.CHECK_CIRCLE_OUTLINE,
                    "Deactivate" if teacher.is_active else "Activate",
                    toggle,
                    color="#C0362C" if teacher.is_active else "#1D9A6C",
                ),
            ],
        )

    def _on_search(self, term: str) -> None:
        self._term = (term or "").strip()
        self._page_no = 1
        self._load()

    def _open_add_dialog(self, e=None) -> None:
        self._teacher_dialog("Add Teacher", None).open()

    def _open_edit_dialog(self, teacher) -> None:
        self._teacher_dialog("Edit Teacher", teacher).open()

    def _teacher_dialog(self, title: str, teacher: object | None) -> FormDialog:
        from app.services.teacher_service import TeacherInput

        name = Field("Full Name", value=teacher.name if teacher else "", required=True)
        contact = Field(
            "Contact Number", value=teacher.contact_number if teacher else "",
            required=True, hint="10-digit mobile number", prefix_icon=ft.Icons.PHONE_OUTLINED,
        )
        subject = Field("Subject", value=teacher.subject or "" if teacher else "", hint="e.g. Physics")

        def save() -> str | None:
            if not (name.control.value or "").strip():
                name.error("Teacher name is required.")
                return "Teacher name is required."
            if not is_valid_phone(contact.control.value or ""):
                contact.error("Enter a valid phone number.")
                return "Enter a valid phone number."
            payload = TeacherInput(
                name=(name.control.value or "").strip(),
                contact_number=(contact.control.value or "").strip(),
                subject=(subject.control.value or "").strip() or None,
            )
            try:
                if teacher:
                    self._teachers.update(self._context, teacher.id, payload)
                else:
                    self._teachers.create(self._context, payload)
            except LmsError as exc:
                return str(exc)
            self._toasts.show(
                f"Teacher '{payload.name}' {'updated' if teacher else 'added'} successfully.",
                "success",
            )
            self._load()
            return None

        return FormDialog(self._page, title, [name.container, contact.container, subject.container], save)

    def _confirm_toggle(self, teacher) -> None:
        def do_toggle() -> None:
            try:
                self._teachers.set_active_status(self._context, teacher.id, not teacher.is_active)
            except LmsError as exc:
                notify_error(self._toasts, exc)
                return
            state = "activated" if not teacher.is_active else "deactivated"
            self._toasts.show(f"{teacher.name} {state}.", "success")
            self._load()

        if teacher.is_active:
            confirm(self._page, "Deactivate Teacher", "Deactivate teacher", do_toggle, object_name=teacher.name)
        else:
            confirm(self._page, "Activate Teacher", "Activate teacher", do_toggle, confirm_text="Activate", danger=False, object_name=teacher.name)

    def _go_page(self, page: int) -> None:
        self._page_no = page
        self._load()

    def _change_size(self, size: int) -> None:
        self._page_size = size
        self._page_no = 1
        self._load()
