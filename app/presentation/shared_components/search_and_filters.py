"""Search bar, quick-filter chips and clear-all (Volume 2, Ch. 27, 47-48)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_TEXT_SECONDARY,
    HINT_STYLE,
    RADIUS_SM,
    SPACING,
    styled_text,
)


class FilterChips(ft.Row):
    """Selectable quick-filter chips (e.g. All / Available / Unavailable)."""

    def __init__(
        self,
        chips: list[tuple[str, str]],
        on_change: Callable[[str | None], None] | None = None,
    ) -> None:
        self._on_change = on_change
        self._chips: dict[str, ft.Container] = {}
        super().__init__(
            spacing=SPACING["sm"], run_spacing=SPACING["sm"], wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        for key, label in chips:
            self._chips[key] = self._chip(key, label, selected=False)
            self.controls.append(self._chips[key])

    def _chip(self, key: str, label: str, selected: bool) -> ft.Container:
        bg = COLOR_PRIMARY if selected else COLOR_SURFACE
        fg = ft.Colors.WHITE if selected else COLOR_TEXT_SECONDARY
        border = ft.Border.all(1, COLOR_PRIMARY if selected else COLOR_BORDER)
        text = styled_text(label, style="body", color=fg)

        def click(e: ft.ControlEvent) -> None:
            self.select(key)

        return ft.Container(
            content=text,
            bgcolor=bg,
            border=border,
            border_radius=RADIUS_SM,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            on_click=click,
        )

    def select(self, key: str | None, notify: bool = True) -> None:
        for k, chip in self._chips.items():
            selected = k == key
            chip.bgcolor = COLOR_PRIMARY if selected else COLOR_SURFACE
            chip.border = ft.Border.all(1, COLOR_PRIMARY if selected else COLOR_BORDER)
            chip.content = styled_text(
                chip.content.value, style="body",
                color=ft.Colors.WHITE if selected else COLOR_TEXT_SECONDARY,
            )
            chip.update()
        if notify and self._on_change:
            self._on_change(key)


class SearchFilters(ft.Container):
    """Search field + optional dropdown filters + clear-all link."""

    def __init__(
        self,
        hint: str,
        on_search: Callable[[str], None],
        dropdowns: list[tuple[str, list[str], Callable[[str | None], None] | None]] | None = None,
        on_clear: Callable[[], None] | None = None,
    ) -> None:
        self._on_search = on_search
        self._on_clear = on_clear or (lambda: on_search(""))
        self._dropdowns: list[ft.Dropdown] = []
        self.search = ft.TextField(
            hint_text=hint,
            hint_style=HINT_STYLE,
            prefix_icon=ft.Icons.SEARCH,
            border_radius=RADIUS_SM,
            height=40,
            text_size=14,
            color="#000000",
            border_color=COLOR_BORDER,
            focused_border_color=COLOR_ACCENT,
            on_change=self._search_changed,
            width=320,
            content_padding=ft.Padding.symmetric(horizontal=12),
        )
        controls: list[ft.Control] = [self.search]
        for label, options, on_change in dropdowns or []:
            dropdown = ft.Dropdown(
                label=label,
                options=[ft.dropdown.Option(o) for o in options],
                width=170,
                height=40,
                text_size=13,
                color="#000000",
                label_style=ft.TextStyle(size=13),
                hint_style=HINT_STYLE,
                border_color=COLOR_BORDER,
                focused_border_color=COLOR_ACCENT,
            )
            dropdown.on_select = self._dropdown_changed(on_change)
            self._dropdowns.append(dropdown)
            controls.append(dropdown)
        self.clear_all = ft.TextButton(
            "Clear all", on_click=self._clear, style=ft.ButtonStyle(color=COLOR_PRIMARY)
        )
        controls.append(self.clear_all)
        super().__init__(
            ft.Row(
                controls, spacing=SPACING["sm"], run_spacing=SPACING["sm"], wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    def _search_changed(self, e: ft.ControlEvent) -> None:
        self._on_search(e.control.value)

    def _dropdown_changed(self, callback) -> Callable:
        def handler(e: ft.ControlEvent) -> None:
            if callback:
                callback(e.control.value or None)

        return handler

    def _clear(self, e: ft.ControlEvent) -> None:
        self.search.value = ""
        self.search.update()
        for dropdown in self._dropdowns:
            dropdown.value = None
            dropdown.update()
        self._on_clear()