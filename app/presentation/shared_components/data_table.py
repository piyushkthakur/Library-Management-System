"""Data table: zebra rows, hover, sortable headers, optional action column.

Sorting applies to the currently loaded page only (the backend API returns a
page at a time and does not expose server-side sort, so this is client-side
within the fetched page).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import flet as ft

from app.presentation.shared_components.empty_state import EmptyState
from app.presentation.theme import (
    COLOR_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    styled_text,
)


@dataclass
class ColumnSpec:
    key: str
    label: str
    width: int | None = None
    sortable: bool = False


@dataclass
class TableRow:
    cells: dict[str, ft.Control]
    key: str = ""
    sort: dict[str, object] = field(default_factory=dict)
    actions: list[ft.Control] = field(default_factory=list)


def _or_placeholder(control: ft.Control | None) -> ft.Control:
    if control is not None:
        return control
    return styled_text("—", style="caption")


class DataTable(ft.Container):
    """Zebra-striped, hover-highlighted table of ``TableRow`` controls."""

    def __init__(
        self,
        columns: list[ColumnSpec],
        on_sort: Callable[[str, str], None] | None = None,
    ) -> None:
        self._columns = columns
        self._rows: list[TableRow] = []
        self._sort_key: str | None = None
        self._sort_dir = "ascend"
        self._loading = False
        self._empty_message = "No records found."
        self._on_sort = on_sort
        self._actions_width = 0
        self._header = self._build_header()
        self._body = ft.Column(spacing=0, scroll=ft.Scrollbar(thumb_visibility=True), expand=True,
                               horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        self._table = ft.Column(
            [self._header, ft.Divider(height=1, color=COLOR_BORDER), self._body],
            spacing=0,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        # ponytail: no scrollable Row wrapper — it gives children unbounded
        # width, collapsing every flex cell (header vanishes, rows go narrow).
        # _table Column fills this Container directly, so widths stay bounded.
        # ponytail: no fixed height — expand fills the screen Column down
        # to the pagination bar instead of stopping at 320px.
        super().__init__(
            content=self._table,
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=8,
            expand=True,
        )
        self._render_body()

    # -- public -------------------------------------------------------------

    def set_rows(self, rows: list[TableRow]) -> None:
        self._rows = rows
        self._loading = False
        self._render_body()
        self.update()

    def set_loading(self, loading: bool) -> None:
        self._loading = loading
        self._render_body()
        self.update()

    def set_empty_message(self, message: str) -> None:
        self._empty_message = message

    # -- rendering ----------------------------------------------------------

    def _has_actions(self) -> bool:
        return any(row.actions for row in self._rows)

    def _build_header(self) -> ft.Container:
        cells = []
        for col in self._columns:
            if col.sortable:
                arrow = (
                    "▲" if self._sort_key == col.key and self._sort_dir == "ascend" else
                    "▼" if self._sort_key == col.key else "↕"
                )
                cells.append(
                    ft.Container(
                        ft.Text(f"{col.label} {arrow}", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        on_click=lambda e, c=col: self._toggle_sort(c),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=9),
                        expand=col.width if col.width is not None else 160,
                    )
                )
            else:
                cells.append(
                    ft.Container(
                        ft.Text(col.label, size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                        padding=ft.Padding.symmetric(horizontal=8, vertical=9),
                        expand=col.width if col.width is not None else 160,
                    )
                )
        if self._actions_width:
            cells.append(
                ft.Container(
                    ft.Text("Actions", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=9),
                    expand=self._actions_width,
                )
            )
        return ft.Container(
            content=ft.Row(cells, spacing=0, expand=True),
            bgcolor="#FCC103",
            border_radius=ft.BorderRadius(top_left=8, top_right=8, bottom_left=0, bottom_right=0),
        )

    def _toggle_sort(self, col: ColumnSpec) -> None:
        if self._sort_key != col.key or self._sort_dir != "ascend":
            self._sort_key, self._sort_dir = col.key, "ascend"
        else:
            self._sort_dir = "descend"
        key = self._sort_key
        self._rows.sort(
            key=lambda r: (r.sort.get(key) if key in r.sort else ""),
            reverse=self._sort_dir == "descend",
        )
        self._render_body()
        self.update()
        if self._on_sort:
            self._on_sort(key, self._sort_dir)

    def _row_container(self, row: TableRow) -> ft.Container:
        cells = []
        for col in self._columns:
            cells.append(
                ft.Container(
                    _or_placeholder(row.cells.get(col.key)),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=10),
                    expand=col.width if col.width is not None else 160,
                )
            )
        if self._actions_width:
            cells.append(
                ft.Container(
                    ft.Row(row.actions, spacing=4, wrap=True),
                    padding=ft.Padding.symmetric(horizontal=8, vertical=10),
                    expand=self._actions_width,
                )
            )

        base_bg = COLOR_SURFACE
        hover_bg = COLOR_SURFACE_ALT

        def on_hover(e: ft.ControlEvent) -> None:
            e.control.bgcolor = hover_bg if e.data == "true" else base_bg
            e.control.update()

        return ft.Container(
            content=ft.Row(cells, spacing=0, expand=True),
            bgcolor=base_bg,
            border=ft.Border(bottom=ft.BorderSide(1, "#EEF1F6")),
            on_hover=on_hover,
        )

    def _render_body(self) -> None:
        self._actions_width = max(
            (
                max(120, 16 + sum(action.width or 48 for action in row.actions)
                    + 4 * (len(row.actions) - 1))
                for row in self._rows if row.actions
            ),
            default=0,
        )
        self._header = self._build_header()
        self._table.controls[0] = self._header
        if self._loading:
            self._body.controls = [self._skeleton()]
            return
        if not self._rows:
            self._body.controls = [EmptyState(self._empty_message)]
            return
        self._body.controls = [self._row_container(r) for r in self._rows]
        self._body.spacing = 0
        # ponytail: _render_body runs from __init__ (not on page yet); guard the update
        if self._on_page():
            self._body.update()
            self.update()

    def _on_page(self) -> bool:
        node = self.parent
        while node is not None:
            if isinstance(node, ft.Page):
                return True
            node = getattr(node, "parent", None)
        return False

    def _skeleton(self) -> ft.Container:
        return ft.Container(
            ft.Column(
                [
                    ft.Container(height=18, bgcolor=COLOR_SURFACE_ALT, border_radius=4)
                    for _ in range(6)
                ],
                spacing=10,
            ),
            padding=16,
        )