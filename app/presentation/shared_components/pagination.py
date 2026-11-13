"""Pagination bar (Volume 2, Ch. 24): prev/next + page size selector."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.theme import (
    COLOR_ACCENT,
    SPACING,
    styled_text,
)

SIZES = (25, 50, 100)


class PaginationBar(ft.Row):
    def __init__(
        self,
        total: int = 0,
        page: int = 1,
        page_size: int = 25,
        on_page: Callable[[int], None] | None = None,
        on_page_size: Callable[[int], None] | None = None,
    ) -> None:
        self._page_no = page
        self._page_size = page_size
        self._total = total
        self._on_page = on_page
        self._on_page_size = on_page_size
        self.total_pages = self._page_count()
        self.label = styled_text("", style="caption")
        self.prev = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT, tooltip="Previous page",
            on_click=self._nav(-1), icon_color=COLOR_ACCENT,
        )
        self.next = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT, tooltip="Next page",
            on_click=self._nav(+1), icon_color=COLOR_ACCENT,
        )
        self.page_size_dropdown = ft.Dropdown(
            value=str(page_size),
            options=[ft.dropdown.Option(str(s)) for s in SIZES],
            width=90,
            color="#000000",
        )
        self.page_size_dropdown.on_select = self._size_changed
        super().__init__(
            [
                self.prev,
                self.next,
                self.label,
                ft.Container(width=16),
                styled_text("Rows per page:", style="caption"),
                self.page_size_dropdown,
            ],
            alignment=ft.MainAxisAlignment.END,
            spacing=SPACING["sm"],
            run_spacing=SPACING["sm"],
            wrap=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self._sync_controls()

    def set_state(self, total: int, page: int) -> None:
        self._total = total
        self._page_no = page
        self.total_pages = self._page_count()
        self._sync_controls()

    def _page_count(self) -> int:
        if not self._total:
            return 1
        return (self._total + self._page_size - 1) // self._page_size

    def _sync_controls(self) -> None:
        self.label.value = f"Page {self._page_no} of {self.total_pages}"
        self.prev.disabled = self._page_no <= 1
        self.next.disabled = self._page_no >= self.total_pages
        if self._is_mounted():
            self.label.update()
            self.prev.update()
            self.next.update()

    def _is_mounted(self) -> bool:
        node = self.parent
        while node is not None:
            if isinstance(node, ft.Page):
                return True
            node = getattr(node, "parent", None)
        return False

    def _nav(self, delta: int) -> Callable:
        def handler(e: ft.ControlEvent) -> None:
            if self._on_page:
                self._on_page(self._page_no + delta)

        return handler

    def _size_changed(self, e: ft.ControlEvent) -> None:
        if self._on_page_size:
            self._on_page_size(int(e.control.value))