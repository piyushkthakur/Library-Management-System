"""Cards: KPI cards, setting cards, generic panels (Volume 2, Ch. 29-31)."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from app.presentation.shared_components.buttons import Button
from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_SURFACE,
    RADIUS_MD,
    SPACING,
    styled_text,
)

CARD_PADDING = ft.Padding.all(20)


def _panel(
    content: ft.Control,
    padding: ft.PaddingValue | None = None,
    width: int | None = None,
    expand: bool = False,
) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding or CARD_PADDING,
        width=width,
        bgcolor=COLOR_SURFACE,
        border=ft.Border.all(1, COLOR_BORDER),
        border_radius=RADIUS_MD,
        expand=expand,
    )


class KpiCard:
    """Statistic card: label, icon, headline number (Volume 2, Ch. 29)."""

    def __init__(self, label: str, icon: str) -> None:
        self._label = label
        self._icon = icon
        self.value = styled_text("0", style="display")
        self.container = _panel(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(styled_text(label, style="body_emphasis"), expand=True),
                            ft.Icon(icon, color=COLOR_ACCENT, size=20),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    self.value,
                ],
                spacing=SPACING["xs"],
            ),
            expand=True,
        )

    def set_value(self, value: str) -> None:
        self.value.value = value
        self.value.update()


class CardPanel:
    """White bordered panel with optional title row."""

    def __init__(
        self,
        title: str | None = None,
        trailing: ft.Control | None = None,
        body: ft.Control | None = None,
    ) -> None:
        header = (
            ft.Row(
                [styled_text(title, style="h2"), trailing or ft.Container()],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                wrap=True,
                run_spacing=SPACING["sm"],
            )
            if title
            else None
        )
        children = [header] if header else []
        if body is not None:
            children.append(body)
        self.container = _panel(ft.Column(children, spacing=SPACING["md"]), expand=True)


class SettingCard:
    """Settings row: title, optional description, body control, save button."""

    def __init__(
        self,
        title: str,
        body: ft.Control,
        on_save: Callable[[], str | None] | None = None,
        save_label: str = "Save",
    ) -> None:
        save = Button(save_label, on_click=self._save, variant="secondary", width=110) if on_save else None
        self._on_save = on_save
        self._save_btn = save
        self.container = _panel(
            ft.ResponsiveRow(
                [
                    ft.Container(
                        styled_text(title, style="body_emphasis"),
                        col={"xs": 12, "md": 4, "lg": 3},
                    ),
                    ft.Container(body, col={"xs": 12, "md": 8, "lg": 7 if save else 9}),
                    *([ft.Container(save, col={"xs": 12, "md": 12, "lg": 2})] if save else []),
                ],
                spacing=SPACING["md"],
                run_spacing=SPACING["md"],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )

    def _save(self, e=None) -> None:
        if not self._on_save:
            return
        if self._save_btn:
            self._save_btn.set_busy(True)
        try:
            # on_save reports failures itself (toast/field errors); None means success.
            self._on_save()
        finally:
            if self._save_btn:
                self._save_btn.set_busy(False)
def page_header(title: str, subtitle: str = "", actions: list[ft.Control] | None = None) -> ft.Container:
    """Standard screen header: title + subtitle + trailing action buttons."""
    return ft.Container(
        ft.ResponsiveRow(
            [
                ft.Column(
                    [styled_text(title, style="h1"), styled_text(subtitle, style="caption")],
                    spacing=2,
                    col={"xs": 12, "md": 6 if actions else 12},
                ),
                *([
                    ft.Row(
                        actions,
                        wrap=True,
                        spacing=SPACING["sm"],
                        run_spacing=SPACING["sm"],
                        alignment=ft.MainAxisAlignment.END,
                        col={"xs": 12, "md": 6},
                    )
                ] if actions else []),
            ],
            spacing=SPACING["md"],
            run_spacing=SPACING["sm"],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        margin=ft.Margin.only(bottom=16),
    )
