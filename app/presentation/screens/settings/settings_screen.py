"""Settings screen: circulation rules, email/OTP, security policy (Volume 2, S12)."""

from __future__ import annotations

import flet as ft

from app.core.exceptions import LmsError
from app.presentation.shared_components.cards import SettingCard, page_header
from app.presentation.shared_components.errors import notify_error
from app.presentation.shared_components.form_controls import (
    Field,
    NumberField,
    PasswordField,
    toggle_field,
)
from app.presentation.shared_components.toast import ToastHost
from app.presentation.theme import SPACING

KEY_LOAN = "loan_period_days"
KEY_FINE_ENABLED = "fine_enabled"
KEY_FINE_RATE = "fine_rate_per_day"
KEY_OTP_MINUTES = "otp_expiry_minutes"
KEY_PW_MIN_LENGTH = "password_min_length"


class SettingsScreen:
    def __init__(
        self,
        page: ft.Page,
        settings_service,
        context,
        toasts: ToastHost,
    ) -> None:
        self._page = page
        self._settings = settings_service
        self._context = context
        self._toasts = toasts
        self._root: ft.Control | None = None
        self._values: dict[str, str] = {}

    def build(self) -> ft.Control:
        self.loan_days = NumberField("Loan Period (days)", required=True)
        self.fine_enabled = toggle_field("Charge Late Fines", helper="Enable per-day fine calculation")
        self.fine_rate = NumberField("Fine Rate (₹/day)", required=True)
        circulation = SettingCard(
            "Circulation Rules",
            ft.Column(
                [
                    self.loan_days.container,
                    self.fine_rate.container,
                    self.fine_enabled,
                ],
                spacing=SPACING["sm"],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            on_save=self._save_circulation,
        )
        self.account = Field("Gmail Account", prefix_icon=ft.Icons.MAIL_OUTLINE, hint="you@gmail.com")
        self.app_password = PasswordField(
            "App Password",
            helper="Stored in the local .env file. It is never shown again and is not stored in the database.",
        )
        self.otp_minutes = NumberField("OTP Expiry Window (minutes)", required=True)
        test_email = ft.FilledButton(
            content=ft.Text("Send Test Email", size=14, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE), on_click=self._send_test_email,
            style=ft.ButtonStyle(bgcolor="#1F2A44", padding=ft.Padding.symmetric(horizontal=14, vertical=10)),
        )
        email = SettingCard(
            "Email & OTP",
            ft.Column(
                [
                    self.account.container,
                    self.app_password.container,
                    self.otp_minutes.container,
                ],
                spacing=SPACING["sm"],
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            on_save=self._save_email,
        )
        self.pw_min_length = NumberField("Minimum Password Length", required=True)
        security = SettingCard(
            "Security Policy",
            self.pw_min_length.container,
            on_save=self._save_security,
        )
        header = page_header("Settings", "Configure how the library operates")
        self._root = ft.Column(
            [
                header,
                circulation.container,
                email.container,
                test_email,
                security.container,
            ],
            spacing=SPACING["md"],
            scroll=ft.ScrollMode.AUTO,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            expand=True,
        )
        return self._root

    def activate(self, params: dict | None = None) -> None:
        self._load()

    def _load(self) -> None:
        try:
            self._values = self._settings.get_all(self._context)
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        self.loan_days.control.value = self._values.get(KEY_LOAN, "14")
        self.fine_rate.control.value = self._values.get(KEY_FINE_RATE, "5")
        self.fine_enabled.data.value = self._values.get(KEY_FINE_ENABLED, "false").lower() in ("true", "1", "yes")
        self.otp_minutes.control.value = self._values.get(KEY_OTP_MINUTES, "10")
        self.pw_min_length.control.value = self._values.get(KEY_PW_MIN_LENGTH, "8")
        self._root.update()

    def _save_circulation(self) -> None:
        days = self.loan_days.control.value
        rate = self.fine_rate.control.value
        if not days.isdigit() or int(days) < 1:
            self.loan_days.error("Enter a positive number of days.")
            return
        try:
            rate_f = float(rate)
            if rate_f < 0:
                raise ValueError
        except ValueError:
            self.fine_rate.error("Enter a positive fine rate.")
            return
        try:
            self._settings.update(
                self._context,
                {
                    KEY_LOAN: str(int(days)),
                    KEY_FINE_ENABLED: "true" if self.fine_enabled.data.value else "false",
                    KEY_FINE_RATE: f"{rate_f:.2f}",
                },
            )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        self._toasts.show("Circulation rules saved.", "success")

    def _save_email(self) -> None:
        try:
            if (self.account.control.value or "").strip():
                self._settings.update_smtp_credentials(
                    self._context,
                    (self.account.control.value or "").strip(),
                    self.app_password.control.value or "",
                )
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        otp = self.otp_minutes.control.value
        if not otp.isdigit() or int(otp) < 1:
            self.otp_minutes.error("Enter a positive number of minutes.")
            return
        try:
            self._settings.update(self._context, {KEY_OTP_MINUTES: str(int(otp))})
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        self.app_password.control.value = ""
        self.app_password.control.update()
        self._toasts.show("Email settings saved.", "success")

    def _send_test_email(self, e=None) -> None:
        try:
            self._settings.send_test_email(self._context)
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        self._toasts.show("Test email sent. Check the inbox of the configured account.", "success")

    def _save_security(self) -> None:
        value = self.pw_min_length.control.value
        if not value.isdigit() or int(value) < 8:
            self.pw_min_length.error("Minimum password length must be at least 8.")
            return
        try:
            self._settings.update(self._context, {KEY_PW_MIN_LENGTH: str(int(value))})
        except LmsError as exc:
            notify_error(self._toasts, exc)
            return
        self._toasts.show("Security policy saved.", "success")