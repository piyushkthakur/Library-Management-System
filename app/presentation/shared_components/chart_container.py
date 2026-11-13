"""Chart host: renders a Plotly figure to a PNG image via Kaleido (P-9).

Kaleido runs synchronously in-process (no threads, no task scheduler), which
keeps the presentation layer's strictly-synchronous model intact.
"""

from __future__ import annotations

import flet as ft

from app.presentation.shared_components.empty_state import EmptyState
from app.presentation.theme import COLOR_BORDER, COLOR_SURFACE, RADIUS_MD, styled_text


class ChartContainer(ft.Container):
    def __init__(self, title: str, height: int = 300, width: int | None = None) -> None:
        self._title = title
        self._height = height
        self._fig = None
        self._image = ft.Image(src=b"", fit=ft.BoxFit.CONTAIN, height=height)
        body = ft.Container(
            content=self._image,
            alignment=ft.Alignment.CENTER,
            bgcolor=COLOR_SURFACE,
            height=height,
        )
        self._body = body
        header = ft.Container(
            styled_text(title, style="body_emphasis"),
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
        )
        super().__init__(
            content=ft.Column([header, body], spacing=0, tight=True),
            width=width,
            bgcolor=COLOR_SURFACE,
            border=ft.Border.all(1, COLOR_BORDER),
            border_radius=RADIUS_MD,
            expand=True,
        )

    @property
    def fig(self):
        return self._fig

    def render(self, fig, width: int | None = None, height: int | None = None) -> None:
        """Render a Plotly figure. Falls back to an error/empty state."""
        try:
            self._fig = fig
            w = width or self.width or 520
            h = height or self._height
            png = fig.to_image(format="png", scale=2, width=max(w, 200), height=max(h, 200))
            self.render_png(png)
        except Exception:
            self.show_empty("Chart rendering is unavailable.")

    def render_png(self, png: bytes) -> None:
        """Show pre-rendered PNG bytes (e.g. fallback renderer output)."""
        self._image.src = png
        self._image.visible = True
        self._body.content = self._image

    def render_png(self, png: bytes) -> None:
        """Show pre-rendered PNG bytes (e.g. from a background task)."""
        self._image.src = png
        self._image.visible = True
        self._body.content = self._image

    def show_loading(self) -> None:
        """Shimmer placeholder painted instantly while charts render."""
        self._image.visible = False
        self._body.content = ft.Container(
            ft.Column(
                [
                    ft.Container(height=18, bgcolor="#D9DEE6", border_radius=4)
                    for _ in range(4)
                ],
                spacing=10,
            ),
            padding=16,
        )

    def show_empty(self, text: str) -> None:
        self._image.visible = False
        self._body.content = EmptyState(icon=ft.Icons.INSERT_CHART_OUTLINED, headline=text)