"""Button primitives with busy/loading state."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    RADIUS_SM,
    button_style,
)


class Button(ft.FilledButton):
    """Fill/outlined/text button that can show a spinner while busy.

    ``on_click`` receives the ``ft.ControlEvent``; the button toggles itself
    busy for the duration of the callback so duplicate taps are impossible.
    """

    def __init__(
        self,
        text: str,
        on_click: Callable[[ft.ControlEvent], None] | None = None,
        variant: str = "primary",
        icon: str | None = None,
        width: int | None = None,  # accepted for call-site symmetry, ignored
        tooltip: str | None = None,
    ) -> None:
        styles = {
            "primary": button_style(COLOR_PRIMARY),
            "secondary": button_style(COLOR_ACCENT),
            "outline": ft.ButtonStyle(
                color=COLOR_PRIMARY,
                bgcolor=COLOR_SURFACE,
                side=ft.BorderSide(1, COLOR_PRIMARY),
                padding=ft.Padding.symmetric(horizontal=18, vertical=11),
                shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
            ),
            "danger": button_style(COLOR_DANGER),
            "subtle": ft.ButtonStyle(
                color=COLOR_ACCENT,
                bgcolor=COLOR_SURFACE_ALT,
                padding=ft.Padding.symmetric(horizontal=16, vertical=9),
                shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
            ),
        }
        fg = {
            "primary": ft.Colors.WHITE,
            "secondary": ft.Colors.WHITE,
            "outline": COLOR_PRIMARY,
            "subtle": COLOR_PRIMARY,
        }
        self._fg = fg.get(variant, ft.Colors.WHITE)
        self._icon = icon
        self._label = text
        super().__init__(
            content=ft.Text(text, size=14, weight=ft.FontWeight.W_600, color=self._fg),
            icon=icon,
            on_click=self._wrap(on_click) if on_click else None,
            style=styles.get(variant, styles["primary"]),
        )

    def _wrap(self, handler) -> Callable:
        def wrapped(e: ft.ControlEvent) -> None:
            try:
                handler(e)
            finally:
                self.set_busy(False)

        return wrapped

    def set_busy(self, busy: bool) -> None:
        if busy:
            self.icon = ft.ProgressRing(width=18, height=18, stroke_width=2, color=COLOR_SURFACE)
        else:
            self.icon = self._icon
        self.content = ft.Text(self._label, size=14, weight=ft.FontWeight.W_600, color=self._fg)
        self.disabled = busy
        # ponytail: a callback may detach this button mid-flow (login -> shell
        # swap, dialog close) before the busy-reset finally runs; update()
        # would then raise "Control must be added to the page first".
        if self._on_page():
            self.update()

    def _on_page(self) -> bool:
        node = self.parent
        while node is not None:
            if isinstance(node, ft.Page):
                return True
            node = node.parent
        return False


def text_button(
    text: str,
    on_click: Callable[[ft.ControlEvent], None] | None,
    color: str = COLOR_ACCENT,
) -> ft.TextButton:
    return ft.TextButton(
        content=ft.Text(text, size=14, color=color, weight=ft.FontWeight.W_500),
        style=ft.ButtonStyle(color=color),
        on_click=on_click,
    )


def icon_button(
    icon: str,
    tooltip: str,
    on_click: Callable[[ft.ControlEvent], None] | None,
    # destructive/active row actions pass their explicit red/green.
    color: str = COLOR_PRIMARY,
    fgcolor: str = COLOR_PRIMARY,
    data=None,
) -> ft.IconButton:
    return ft.IconButton(
        icon=icon,
        tooltip=tooltip,
        on_click=on_click,
        icon_color=color,
        data=data,
    )