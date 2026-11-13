"""Status and availability pills (Volume 2, Ch. 43)."""

from __future__ import annotations

import flet as ft

from app.presentation.theme import (
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_INFO,
    COLOR_SUCCESS,
    COLOR_TEXT_SECONDARY,
    RADIUS_SM,
    STATUS_COLORS,
    styled_text,
)

PILL_FG = "#FFFFFF"


def _pill(text: str, bg: str) -> ft.Container:
    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
        bgcolor=bg,
        border_radius=RADIUS_SM,
        content=styled_text(text, style="caption", color=PILL_FG, weight=ft.FontWeight.W_600),
    )


def status_badge(status: str) -> ft.Container:
    """Coloured pill for transaction status (Issued/Returned/Overdue)."""
    return _pill(status, STATUS_COLORS.get(status, COLOR_TEXT_SECONDARY))


def badge(text: str, bg: str) -> ft.Container:
    """Custom-coloured pill."""
    return _pill(text, bg)


def availability_badge(available: int, total: int) -> ft.Container:
    """Green/amber availability pill for a book's copy counts."""
    bg = COLOR_SUCCESS if available > 0 else COLOR_DANGER
    return _pill(f"{available} of {total} available", bg)


def nav_badge(count: int) -> ft.Container:
    """Small counter pill for navigation labels."""
    return ft.Container(
        width=22,
        height=22,
        alignment=ft.Alignment.CENTER,
        bgcolor=COLOR_INFO,
        border_radius=RADIUS_SM,
        content=styled_text(str(count), style="caption", color=PILL_FG, weight=ft.FontWeight.W_600),
    )


def dot(color: str) -> ft.Container:
    return ft.Container(width=8, height=8, bgcolor=color, border_radius=4, border=ft.Border.all(1, COLOR_BORDER))