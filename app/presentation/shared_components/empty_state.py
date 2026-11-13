"""Empty state placeholder for tables and panels (Volume 2, Ch. 28)."""

from __future__ import annotations

import flet as ft

from app.presentation.theme import COLOR_TEXT_SECONDARY, SPACING, styled_text


class EmptyState(ft.Container):
    def __init__(
        self,
        headline: str,
        body: str = "",
        icon: str = ft.Icons.INBOX_OUTLINED,
        action: ft.Control | None = None,
    ) -> None:
        column = ft.Column(
            [
                ft.Icon(icon, size=40, color=COLOR_TEXT_SECONDARY),
                styled_text(headline, style="body_emphasis", color=COLOR_TEXT_SECONDARY),
            ] + ([styled_text(body, style="caption")] if body else [])
            + ([action] if action else []),
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=SPACING["sm"],
        )
        super().__init__(
            content=column,
            alignment=ft.Alignment.CENTER,
            padding=ft.Padding.symmetric(vertical=48),
        )