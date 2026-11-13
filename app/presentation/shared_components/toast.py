"""Non-blocking toast notifications anchored to the content area's top-right.

Volume 2 (Ch. 30) specifies success/warning/error toasts that auto-dismiss.
Because the presentation layer is strictly synchronous (Volume 4, Ch. 23.3)
no timer infrastructure exists, so toasts here:
- rotate: a new toast retires the oldest (capped at three on screen);
- are cleared automatically on shell navigation.
# ponytail: manual + rotate dismissal instead of clock timers; if auto-dismiss
# 4s/6s is ever required, add a single timer in the host, nothing more.
"""

from __future__ import annotations

import flet as ft

from app.presentation.theme import (
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_SURFACE,
    COLOR_WARNING,
    RADIUS_MD,
    SPACING,
    styled_text,
)

KIND_COLORS = {
    "success": COLOR_SUCCESS,
    "warning": COLOR_WARNING,
    "error": COLOR_DANGER,
    "info": COLOR_INFO,
}
KIND_ICONS = {
    "success": ft.Icons.CHECK_CIRCLE,
    "warning": ft.Icons.WARNING_AMBER,
    "error": ft.Icons.ERROR_OUTLINE,
    "info": ft.Icons.INFO_OUTLINE,
}


class ToastHost:
    """Overlay that owns the live toast cards."""

    def __init__(self) -> None:
        self._page: ft.Page | None = None
        self.stack = ft.Column(
            spacing=SPACING["sm"],
            horizontal_alignment=ft.CrossAxisAlignment.END,
            tight=True,
            width=360,
            top=80,
            right=SPACING["md"],
            visible=False,
        )

    def bind(self, page: ft.Page) -> None:
        self._page = page
        page.update()

    def resize(self, content_width: float) -> None:
        self.stack.width = min(360, max(0, content_width - 2 * SPACING["md"]))

    def show(self, message: str, kind: str = "success") -> None:
        color = KIND_COLORS.get(kind, COLOR_INFO)
        text = styled_text(message)
        text.expand = True
        card = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(KIND_ICONS.get(kind, ft.Icons.INFO_OUTLINE), color=color),
                    text,
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        tooltip="Close notification",
                        icon_color=color,
                        on_click=lambda e: self._close(card),
                    ),
                ],
                spacing=SPACING["sm"],
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, color),
            border_radius=RADIUS_MD,
            padding=SPACING["sm"],
        )
        self.stack.controls.append(card)
        self.stack.controls[:] = self.stack.controls[-3:]
        self._update()

    def clear(self) -> None:
        self.stack.controls.clear()
        self._update()

    def _close(self, card: ft.Container) -> None:
        self.stack.controls[:] = [item for item in self.stack.controls if item is not card]
        self._update()

    def _update(self) -> None:
        self.stack.visible = bool(self.stack.controls)
        if self._page is not None:
            self._page.update()