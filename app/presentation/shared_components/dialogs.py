"""Modal dialogs: form, confirmation, read-only info (Volume 2, Ch. 33-36)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.shared_components.buttons import Button
from app.presentation.theme import (
    COLOR_DANGER,
    COLOR_SURFACE,
    COLOR_TEXT_SECONDARY,
    SPACING,
    styled_text,
)

DIALOG_BG = ft.Colors.with_opacity(0.9, COLOR_SURFACE)


def _make(page: ft.Page, title: str, body: ft.Control, actions: list[ft.Control], width: int = 600) -> ft.AlertDialog:
    dialog = ft.AlertDialog(
        modal=True,
        bgcolor=DIALOG_BG,
        title=styled_text(title, style="h1"),
        title_padding=ft.Padding.only(left=24, top=20, right=24),
        content=ft.Column(
            [body],
            scroll=ft.Scrollbar(thumb_visibility=True),
            height=280,
        ),
        content_padding=ft.Padding.only(left=24, top=8, right=24, bottom=12),
        actions=actions,
        actions_padding=ft.Padding.only(left=24, right=24, bottom=18),
        actions_alignment=ft.MainAxisAlignment.END,
    )
    dialog.width = width
    return dialog


class FormDialog:
    """Form dialog with a busy save button and inline error line.

    ``on_save`` returns ``None`` to close, or an error string shown inline;
    per-field errors are set by the caller via :meth:`set_error`.
    ``extra_actions`` prepends caller-supplied buttons before Save/Cancel.
    """

    def __init__(
        self,
        page: ft.Page,
        title: str,
        fields: list[ft.Control],
        on_save: Callable[[], str | None],
        save_label: str = "Save",
        width: int = 500,
        extra_actions: list[ft.Control] | None = None,
    ) -> None:
        self._page = page
        self._on_save = on_save
        self._error = styled_text("", style="caption", color=COLOR_DANGER)
        self._error.visible = False
        self.save = Button(save_label, on_click=self._submit, icon=ft.Icons.CHECK, width=110)
        body = ft.Column(
            [*fields, self._error],
            spacing=SPACING["md"],
            scroll=ft.Scrollbar(thumb_visibility=True),
        )
        self.dialog = _make(
            page,
            title,
            body,
            [*(extra_actions or []), self.save, Button("Cancel", on_click=self._cancel, variant="outline")],
        )
        self.dialog.width = width

    def open(self) -> None:
        self._error.visible = False
        self._page.show_dialog(self.dialog)

    def set_error(self, message: str) -> None:
        self._error.value = message
        self._error.visible = bool(message)
        self._error.update()

    def _cancel(self, e=None) -> None:
        self._page.pop_dialog()

    def _submit(self, e=None) -> None:
        # ponytail: one guard here beats guards in every caller — a raising
        # save shows the error in-dialog instead of red-screening the app.
        try:
            error = self._on_save()
        except Exception as exc:
            self.set_error(str(exc) or "Something went wrong. Please try again.")
            return
        if error:
            self.set_error(error)
        else:
            self.save.set_busy(True)
            try:
                self._cancel()
            finally:
                self.save.set_busy(False)


def confirm(
    page: ft.Page,
    title: str,
    message: str,
    on_confirm: Callable[[], None],
    confirm_text: str = "Delete/Deactivate",
    danger: bool = True,
    object_name: str | None = None,
) -> None:
    """Confirmation dialog; ``on_confirm`` runs after the user agrees."""
    body = message if not object_name else f'{message} "{object_name}"'
    confirm_btn = Button(
        confirm_text,
        on_click=lambda e: (on_confirm(), close()),
        variant="danger" if danger else "primary",
        width=110,
    )
    dialog = _make(
        page,
        title,
        styled_text(body, style="body", color=COLOR_TEXT_SECONDARY),
        [confirm_btn, Button("Cancel", on_click=lambda e: close(), variant="outline")],
    )

    def close() -> None:
        page.pop_dialog()

    page.show_dialog(dialog)


def info(page: ft.Page, title: str, lines: list[str]) -> ft.AlertDialog:
    """Read-only dialog (e.g. Profile). Caller closes via ``page.pop_dialog``."""
    dialog = _make(
        page,
        title,
        ft.Column(
            [styled_text(line, style="body", color=COLOR_TEXT_SECONDARY) for line in lines],
            spacing=SPACING["sm"],
        ),
        [Button("Close", on_click=lambda e: close(), variant="outline")],
    )

    def close() -> None:
        page.pop_dialog()

    page.show_dialog(dialog)
    return dialog
