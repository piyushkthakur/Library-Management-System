"""Centralized design tokens for the library UI (Volume 2, Chapters 40-42).

Every screen and shared component styles itself exclusively from the values
declared here. No screen scatters literal colours, spacing or typography.
"""

from __future__ import annotations

import flet as ft

# --- Colour tokens ------------------------------------------------------------------
COLOR_PRIMARY = "#1F2A44"          # Sidebar, nav, primary buttons
COLOR_ACCENT = "#2E6F9E"           # active nav, links, focus rings
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_ALT = "#F2F4F7"
COLOR_BORDER = "#D0D5DD"
COLOR_TEXT = "#1D2939"
COLOR_TEXT_SECONDARY = "#667085"
COLOR_SUCCESS = "#1D9A6C"
COLOR_WARNING = "#B7791F"
COLOR_DANGER = "#C0362C"
COLOR_INFO = "#2E6F9E"
NAV_INACTIVE = "#C7CEDB"
DISABLED_FILL = "#EDEFF3"

# Status colour mapping used by badges and fine labels.
STATUS_COLORS = {
    "Issued": COLOR_INFO,
    "Returned": COLOR_SUCCESS,
    "Overdue": COLOR_DANGER,
}

# Spacing scale (px)
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
    "2xl": 48,
    "3xl": 64,
}
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
SHADOW_SM = 1
SHADOW_MD = 3
SHADOW_LG = 6

# Typography.
FONT_FAMILY = "Segoe UI"
FONT_FALLBACK = "Segoe UI, Arial, sans-serif"


def styled_text(
    text: str,
    style: str = "body",
    color: str | None = None,
    weight: ft.FontWeight | None = None,
    size: int | None = None,
) -> ft.Text:
    """Build a :class:`ft.Text` using the design token type scale."""
    spec = {
        "display": {"size": 28, "weight": ft.FontWeight.W_600, "color": COLOR_TEXT},
        "h1": {"size": 22, "weight": ft.FontWeight.W_600, "color": COLOR_TEXT},
        "h2": {"size": 18, "weight": ft.FontWeight.W_600, "color": COLOR_TEXT},
        "body": {"size": 14, "weight": ft.FontWeight.W_400, "color": COLOR_TEXT},
        "body_emphasis": {"size": 14, "weight": ft.FontWeight.W_600, "color": COLOR_TEXT},
        "caption": {"size": 12, "weight": ft.FontWeight.W_400, "color": COLOR_TEXT_SECONDARY},
        "label": {"size": 13, "weight": ft.FontWeight.W_600, "color": COLOR_TEXT},
    }.get(style, {})
    return ft.Text(
        text,
        size=size or spec.get("size", 14),
        weight=weight or spec.get("weight", ft.FontWeight.W_400),
        color=color or spec.get("color", COLOR_TEXT),
        font_family=FONT_FALLBACK,
    )


# Placeholder text: soft gray on white fields.
HINT_STYLE = ft.TextStyle(color="#98A2B3")


def button_style(bgcolor: str, fgcolor: str = COLOR_SURFACE) -> ft.ButtonStyle:
    """Uniform button geometry + hover states from the tokens."""
    return ft.ButtonStyle(
        color=fgcolor,
        bgcolor=bgcolor,
        padding=ft.Padding.symmetric(horizontal=18, vertical=11),
        shape=ft.RoundedRectangleBorder(radius=RADIUS_SM),
        side=ft.BorderSide(0, COLOR_BORDER),
    )