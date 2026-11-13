"""Form controls: labelled inputs with inline error state (Volume 2, Ch. 35)."""

from __future__ import annotations

import calendar
from collections.abc import Callable
from datetime import UTC
from datetime import date as _date
from datetime import datetime as _dt

import flet as ft

from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_DANGER,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    HINT_STYLE,
    SPACING,
    styled_text,
)

DIALOG_BG = ft.Colors.with_opacity(0.9, COLOR_SURFACE)

_INPUT_PROPS = {
    "height": 40,
    "text_size": 14,
    "color": "#000000",
    "hint_style": HINT_STYLE,
    "border": ft.InputBorder.OUTLINE,
    "border_color": COLOR_BORDER,
    "focused_border_color": COLOR_ACCENT,
    "border_width": 1,
    "content_padding": ft.Padding.symmetric(horizontal=12, vertical=9),
}


class _LabeledInput:
    """Base wrapper rendering label + input + error caption."""

    def __init__(
        self,
        label: str,
        required: bool = False,
        helper: str | None = None,
    ) -> None:
        self._label = label
        self._required = required
        self._helper = helper
        self._required_text = ft.Text("*", size=13, color=COLOR_DANGER) if required else ft.Text()
        self._error_text = styled_text("", style="caption", color=COLOR_DANGER)
        self._error_text.visible = False
        label_row = ft.Row(
            [
                styled_text(label, style="label"),
                self._required_text,
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        helper_row = (
            styled_text(helper, style="caption") if helper else ft.Container(width=0, height=0)
        )
        self.container = ft.Container(
            content=ft.Column(
                [
                    label_row,
                    self._build_input(),
                    self._error_text,
                    helper_row,
                ],
                spacing=SPACING["xs"],
            ),
        )

    def _build_input(self) -> ft.Control:
        raise NotImplementedError

    def error(self, message: str) -> None:
        self._error_text.value = message
        self._error_text.visible = bool(message)
        self._error_text.update()

    def clear_error(self) -> None:
        self.error("")

    def set_required(self, required: bool) -> None:
        self._required_text.visible = required
        self._required_text.update()


class Field(_LabeledInput):
    def __init__(
        self,
        label: str,
        value: str = "",
        required: bool = False,
        helper: str | None = None,
        hint: str | None = None,
        prefix_icon: str | None = None,
        on_change: Callable[[ft.ControlEvent], None] | None = None,
        on_submit: Callable[[ft.ControlEvent], None] | None = None,
        keyboard_type: ft.KeyboardType | None = None,
    ) -> None:
        self.value = value
        self.on_change = on_change
        self.on_submit = on_submit
        self.keyboard_type = keyboard_type
        self.hint = hint
        self.prefix_icon = prefix_icon
        super().__init__(label, required, helper)

    def _build_input(self) -> ft.Control:
        return ft.TextField(
            value=self.value,
            hint_text=self.hint,
            prefix_icon=self.prefix_icon,
            on_change=self.on_change,
            on_submit=self.on_submit,
            keyboard_type=self.keyboard_type,
            **_INPUT_PROPS,
        )

    @property
    def control(self) -> ft.TextField:
        return self.container.content.controls[1]


class PasswordField(_LabeledInput):
    def __init__(
        self,
        label: str,
        required: bool = False,
        helper: str | None = None,
        hint: str | None = None,
    ) -> None:
        self._hint = hint
        super().__init__(label, required, helper)

    def _build_input(self) -> ft.Control:
        field = ft.TextField(
            password=True,
            can_reveal_password=True,
            hint_text=self._hint,
            **_INPUT_PROPS,
        )
        return field

    @property
    def control(self) -> ft.TextField:
        return self.container.content.controls[1]


class DropdownField(_LabeledInput):
    def __init__(
        self,
        label: str,
        options: list[str],
        value: str | None = None,
        required: bool = False,
        on_change: Callable[[ft.ControlEvent], None] | None = None,
    ) -> None:
        self._options = options
        self._value = value
        self._on_change = on_change
        super().__init__(label, required)

    def _build_input(self) -> ft.Control:
        return ft.Dropdown(
            value=self._value,
            options=[ft.dropdown.Option(o) for o in self._options],
            on_select=self._on_change,
            **_INPUT_PROPS,
        )

    @property
    def control(self) -> ft.Dropdown:
        return self.container.content.controls[1]


class NumberField(Field):
    """Whole-number field that rejects non-digits as typed."""

    def __init__(self, label: str, value: str = "", required: bool = False) -> None:
        super().__init__(label, value=value, required=required)

    def _build_input(self) -> ft.Control:
        field = ft.TextField(
            value=self.value,
            prefix_icon=ft.Icons.PIN,
            keyboard_type=ft.KeyboardType.NUMBER,
            on_change=self._sanitize,
            **_INPUT_PROPS,
        )
        return field

    def _sanitize(self, e: ft.ControlEvent) -> None:
        cleaned = "".join(ch for ch in (e.control.value or "") if ch.isdigit())
        if cleaned != e.control.value:
            e.control.value = cleaned
            e.control.update()


class DateField(_LabeledInput):
    """Date input with a custom calendar dialog (Flet 0.86 DatePicker is broken on desktop)."""

    def __init__(
        self,
        page: ft.Page,
        label: str,
        required: bool = False,
        default=None,
    ) -> None:
        self._page = page
        self.date = default
        self._months = [calendar.month_name[i] for i in range(1, 13)]
        self._years = [str(y) for y in range(2020, 2031)]
        self._dialog: ft.AlertDialog | None = None
        self._closing = False
        super().__init__(label, required)

    def _build_input(self) -> ft.Control:
        self._text = ft.TextField(
            value=self.date.isoformat() if self.date else "",
            hint_text="YYYY-MM-DD",
            read_only=True,
            suffix_icon=ft.Icons.CALENDAR_MONTH,
            on_focus=self._on_focus,
            **_INPUT_PROPS,
        )
        return self._text

    def _on_focus(self, e=None) -> None:
        if self._closing:
            self._closing = False
            return
        if self._text.disabled:
            return
        self._open_picker()

    def set_enabled(self, enabled: bool) -> None:
        self._text.disabled = not enabled
        if self._text.page is not None:
            self._text.update()

    def _open_picker(self, e=None) -> None:
        today = self.date or _date.today()
        if self._dialog is None:
            input_props = {k: v for k, v in _INPUT_PROPS.items() if k not in ("height", "text_size")}
            self._day_dd = ft.Dropdown(width=100, text_size=14, **input_props)
            self._month_dd = ft.Dropdown(width=160, text_size=14, **input_props)
            self._year_dd = ft.Dropdown(width=100, text_size=14, **input_props)
            self._dialog = ft.AlertDialog(
                bgcolor=DIALOG_BG,
                title=styled_text("Select Date", style="h1", color=COLOR_PRIMARY),
                title_padding=ft.Padding.only(left=24, top=20, right=24),
                content=ft.Row([self._day_dd, self._month_dd, self._year_dd], spacing=8),
                content_padding=ft.Padding.only(left=24, top=8, right=24, bottom=12),
                actions=[
                    ft.TextButton("Cancel", on_click=self._close_dialog,
                                  style=ft.ButtonStyle(
                                      color=COLOR_DANGER,
                                      bgcolor={"hovered": "#FEE2E2"},
                                  )),
                    ft.ElevatedButton("OK", on_click=self._confirm, bgcolor=COLOR_PRIMARY, color="#FFFFFF"),
                ],
                actions_padding=ft.Padding.only(left=24, right=24, bottom=18),
                actions_alignment=ft.MainAxisAlignment.END,
            )
        self._day_dd.options = [ft.dropdown.Option(str(d)) for d in range(1, 32)]
        self._day_dd.value = str(today.day)
        self._month_dd.options = [ft.dropdown.Option(m) for m in self._months]
        self._month_dd.value = self._months[today.month - 1]
        self._year_dd.options = [ft.dropdown.Option(y) for y in self._years]
        self._year_dd.value = str(today.year)
        try:
            self._page.show_dialog(self._dialog)
        except Exception:
            pass

    def _close_dialog(self, e=None) -> None:
        self._closing = True
        self._page.pop_dialog()

    def _confirm(self, e=None) -> None:
        try:
            m = self._months.index(self._month_dd.value) + 1
            d = min(int(self._day_dd.value), calendar.monthrange(int(self._year_dd.value), m)[1])
            self.date = _date(int(self._year_dd.value), m, d)
            self._text.value = self.date.isoformat()
            self._text.update()
        except (ValueError, TypeError):
            pass
        self._close_dialog()

    @property
    def control(self) -> ft.TextField:
        return self._text


def toggle_field(label: str, value: bool = False, helper: str | None = None) -> ft.Row:
    """Switch control rendered as label + toggle (Volume 2, Ch. 22)."""
    switch = ft.Switch(value=value, active_color=COLOR_ACCENT)
    row = ft.Row(
        [
            ft.Container(styled_text(label, style="body"), expand=True),
            styled_text(helper or "", style="caption"),
            switch,
        ],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    row.data = switch
    return row