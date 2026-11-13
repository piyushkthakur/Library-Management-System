"""Authentication screens: login, admin self-registration, forgot/reset password.

Each screen is its own controller (Volume 3, 18.1): user action -> convenience
validation -> single service call -> result -> UI update.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import flet as ft

from app.core.exceptions import (
    AccountLockedError,
    DatabaseConnectivityError,
    LmsError,
    OtpVerificationError,
    ValidationError,
)
from app.presentation.shared_components.buttons import Button, text_button
from app.presentation.shared_components.form_controls import Field, PasswordField
from app.presentation.theme import (
    COLOR_ACCENT,
    COLOR_PRIMARY,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT_SECONDARY,
    NAV_INACTIVE,
    SPACING,
    styled_text,
)
from app.utils.validators import is_valid_email, password_error

PASSWORD_HELPER = "Minimum 8 characters with at least one uppercase letter, one number and one symbol."


def _auth_card(
    title: str,
    subtitle: str,
    body: ft.Control,
    page=None,
) -> ft.Control:
    """Dark/Light Split layout: dark branding left, clean form right.

    Full-height equal panels normally; scroll mode on tiny windows where
    the stacked panels would otherwise clip.
    """
    brand_panel = ft.Container(
        content=ft.Column(
            [
                ft.Icon(ft.Icons.LOCAL_LIBRARY, color=COLOR_ACCENT, size=88),
                ft.Container(height=8),
                styled_text("Library", style="display", color=COLOR_SURFACE),
                styled_text("Management System", style="h2", color=NAV_INACTIVE),
                ft.Container(height=6),
                styled_text(
                    "Streamline your library operations with modern digital management.",
                    style="body",
                    color=NAV_INACTIVE,
                    size=15,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
        ),
        col={"xs": 12, "sm": 6},
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_LEFT,
            end=ft.Alignment.BOTTOM_RIGHT,
            colors=[COLOR_PRIMARY, "#1A2744"],
        ),
        padding=ft.Padding.all(48),
    )
    form_panel = ft.Container(
        content=ft.Column(
            [
                styled_text(title, style="h1", size=22),
                styled_text(subtitle, style="caption"),
                ft.Divider(height=1, color=COLOR_SURFACE_ALT),
                ft.Container(
                    content=body,
                    width=300,
                    padding=ft.Padding.only(left=24),
                ),
            ],
            spacing=SPACING["md"],
            scroll=ft.ScrollMode.AUTO,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
        col={"xs": 12, "sm": 6},
        bgcolor=COLOR_SURFACE,
        padding=ft.Padding.all(32),
    )
    # ponytail: no scroll + stretched row, so both panels share the full
    # window height instead of sizing to their own content.
    row = ft.ResponsiveRow(
        [brand_panel, form_panel],
        spacing=0,
        run_spacing=0,
        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        expand=True,
    )
    outer = ft.Column(spacing=0, expand=True, controls=[row])
    container = ft.Container(content=outer, expand=True)

    def _fit(e=None) -> None:
        # ponytail: expand inside a scrollable is unbounded (collapses), so
        # scroll and expand are toggled together, never combined.
        narrow = (getattr(page, "width", 1360) or 1360) < 576
        outer.scroll = ft.ScrollMode.AUTO if narrow else None
        row.expand = not narrow
        try:
            outer.update()
        except Exception:
            pass

    if page is not None:
        _fit()
        page.on_resize = _fit
    return container


class LoginScreen:
    def __init__(
        self,
        page: ft.Page,
        auth_service,
        on_success: Callable[[object], None],
        on_forgot: Callable[[], None],
        on_register: Callable[[], None],
    ) -> None:
        self._page = page
        self._auth = auth_service
        self._on_success = on_success
        self._on_forgot = on_forgot
        self._on_register = on_register
        self.email = Field("Email Address", hint="you@example.com", required=True, prefix_icon=ft.Icons.MAIL_OUTLINE)
        self.password = PasswordField("Password", required=True, hint="Enter your password")
        self._error = styled_text("", style="caption", color=ft.Colors.RED_700)
        self._error.visible = False
        self._register_link = text_button("Register administrator", self._register_clicked, color=COLOR_ACCENT)
        self._register_row = ft.Row(
            [self._register_link], alignment=ft.MainAxisAlignment.CENTER
        )
        self._register_row.visible = False
        self._sign_in = Button("Sign In", icon=ft.Icons.LOGIN, width=160)
        # ponytail: assigned directly so Button's sync wrapper doesn't reset
        # the busy state of this async handler prematurely.
        self._sign_in.on_click = self._login
        self._spinner = ft.ProgressRing(width=18, height=18, stroke_width=2, color=COLOR_PRIMARY, visible=False)

    def build(self) -> ft.Control:
        body = ft.Column(
            [
                ft.Container(self.email.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.password.container, padding=ft.Padding.only(left=11)),
                self._error,
                ft.Container(ft.Row([self._sign_in, self._spinner], alignment=ft.MainAxisAlignment.CENTER, spacing=8), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=12)),
                ft.Container(ft.Row([text_button("Forgot password?", self._forgot_clicked, color=COLOR_ACCENT)], alignment=ft.MainAxisAlignment.CENTER), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=4)),
                self._register_row,
            ],
            spacing=SPACING["sm"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return _auth_card("Welcome back", "Sign in to continue to your library", body, self._page)

    def on_activate(self) -> None:
        self.email.clear_error()
        self.password.clear_error()
        self._error.visible = False
        try:
            self._register_row.visible = not self._auth.admin_exists()
        except LmsError:
            self._register_row.visible = False
        self._register_row.update()

    async def _login(self, e: ft.ControlEvent) -> None:
        self._busy(True)
        await asyncio.sleep(0)  # let the throbber paint before blocking work
        try:
            self.email.clear_error()
            self.password.clear_error()
            email_val = (self.email.control.value or "").strip()
            if not email_val:
                self.email.error("Email is required.")
                return
            if not is_valid_email(email_val):
                self.email.error("Enter a valid email address.")
                return
            if not self.password.control.value:
                self.password.error("Password is required.")
                return
            context = await asyncio.to_thread(
                self._auth.login, email_val, self.password.control.value
            )
            self._on_success(context)
        except AccountLockedError as exc:
            self._error.value = str(exc)
            self._error.visible = True
            self._error.update()
        except DatabaseConnectivityError:
            self._error.value = "Unable to reach the database. Please try again."
            self._error.visible = True
            self._error.update()
        except LmsError as exc:
            self._error.value = str(exc)
            self._error.visible = True
            self._error.update()
        finally:
            self._busy(False)

    def _busy(self, on: bool) -> None:
        self._sign_in.disabled = on
        self._spinner.visible = on
        for control in (self._sign_in, self._spinner):
            try:
                control.update()
            except Exception:
                pass

    def _forgot_clicked(self, e: ft.ControlEvent) -> None:
        self._on_forgot()

    def _register_clicked(self, e: ft.ControlEvent) -> None:
        self._on_register()


class AdminRegistrationScreen:
    def __init__(
        self,
        page: ft.Page,
        auth_service,
        on_back: Callable[[], None],
    ) -> None:
        self._page = page
        self._auth = auth_service
        self._on_back = on_back
        self.full_name = Field("Full Name", required=True, prefix_icon=ft.Icons.PERSON_OUTLINE)
        self.email = Field("Email Address", required=True, prefix_icon=ft.Icons.MAIL_OUTLINE)
        self.password = PasswordField("Password", required=True, helper=PASSWORD_HELPER)
        self.confirm = PasswordField("Confirm Password", required=True)
        self._error = styled_text("", style="caption", color=ft.Colors.RED_700)
        self._error.visible = False
        self._register = Button("Register Administrator", icon=ft.Icons.PERSON_ADD, width=220)
        # ponytail: assigned directly so Button's sync wrapper doesn't reset
        # the busy state of this async handler prematurely.
        self._register.on_click = self._register_admin
        self._spinner = ft.ProgressRing(width=18, height=18, stroke_width=2, color=COLOR_PRIMARY, visible=False)

    def build(self) -> ft.Control:
        body = ft.Column(
            [
                ft.Container(self.full_name.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.email.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.password.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.confirm.container, padding=ft.Padding.only(left=11)),
                self._error,
                ft.Container(ft.Row([self._register, self._spinner], alignment=ft.MainAxisAlignment.CENTER, spacing=8), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=12)),
                ft.Container(ft.Row([text_button("Back to sign in", self._on_back, color=COLOR_ACCENT)], alignment=ft.MainAxisAlignment.CENTER), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=4)),
            ],
            spacing=SPACING["sm"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return _auth_card(
            "Set up your library",
            "Register the first administrator account",
            body,
            self._page,
        )

    async def _register_admin(self, e: ft.ControlEvent) -> None:
        self._busy(True)
        await asyncio.sleep(0)  # let the throbber paint before blocking work
        try:
            self.full_name.clear_error()
            self.email.clear_error()
            self.password.clear_error()
            self.confirm.clear_error()
            name = (self.full_name.control.value or "").strip()
            email = (self.email.control.value or "").strip()
            password = self.password.control.value
            confirm = self.confirm.control.value
            if not name:
                self.full_name.error("Full name is required.")
                return
            if not email or not is_valid_email(email):
                self.email.error("Enter a valid email address.")
                return
            pw_error = password_error(password)
            if pw_error:
                self.password.error(pw_error)
                return
            if password != confirm:
                self.confirm.error("Passwords do not match.")
                return
            await asyncio.to_thread(self._auth.register_administrator, name, email, password)
            self._error.value = ""
            self._error.visible = False
            self._error.update()
            self._on_back()
        except ValidationError as exc:
            self._error.value = str(exc)
            self._error.visible = True
            self._error.update()
        except DatabaseConnectivityError:
            self._error.value = "Unable to reach the database. Please try again."
            self._error.visible = True
            self._error.update()
        except LmsError as exc:
            self._error.value = str(exc)
            self._error.visible = True
            self._error.update()
        finally:
            self._busy(False)

    def _busy(self, on: bool) -> None:
        self._register.disabled = on
        self._spinner.visible = on
        for control in (self._register, self._spinner):
            try:
                control.update()
            except Exception:
                pass


class ForgotPasswordScreen:
    def __init__(
        self,
        page: ft.Page,
        auth_service,
        on_back: Callable[[], None],
        on_otp_sent: Callable[[str], None],
    ) -> None:
        self._page = page
        self._auth = auth_service
        self._on_back = on_back
        self._on_otp_sent = on_otp_sent
        self.email = Field("Email Address", required=True, prefix_icon=ft.Icons.MAIL_OUTLINE)
        self._error = styled_text("", style="caption", color=ft.Colors.RED_700)
        self._error.visible = False
        self._send = Button("Send OTP", on_click=self._request_otp, icon=ft.Icons.SEND, width=160)

    def build(self) -> ft.Control:
        body = ft.Column(
            [
                styled_text(
                    "We will email you a one-time code to reset your password.",
                    style="body",
                    color=COLOR_TEXT_SECONDARY,
                ),
                ft.Container(self.email.container, padding=ft.Padding.only(left=11)),
                self._error,
                ft.Container(ft.Row([self._send], alignment=ft.MainAxisAlignment.CENTER), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=12)),
                ft.Container(ft.Row([text_button("Back to sign in", self._on_back, color=COLOR_ACCENT)], alignment=ft.MainAxisAlignment.CENTER), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=4)),
            ],
            spacing=SPACING["sm"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return _auth_card("Reset your password", "Forgot your password?", body, self._page)

    def _request_otp(self, e: ft.ControlEvent) -> None:
        self.email.clear_error()
        self._error.visible = False
        email = (self.email.control.value or "").strip()
        if not email or not is_valid_email(email):
            self.email.error("Enter a valid email address.")
            return
        self._send.set_busy(True)
        try:
            self._auth.request_otp(email)
            self._on_otp_sent(email)
        except LmsError as exc:
            self._error.value = str(exc)
            self._error.visible = True
            self._error.update()
        finally:
            self._send.set_busy(False)


class ResetPasswordScreen:
    def __init__(
        self,
        page: ft.Page,
        auth_service,
        email: str,
        on_back: Callable[[], None],
        on_reset: Callable[[], None],
    ) -> None:
        self._page = page
        self._auth = auth_service
        self._on_back = on_back
        self._on_reset = on_reset
        self.email = Field("Email Address", required=True, prefix_icon=ft.Icons.MAIL_OUTLINE)
        self.email.control.value = email
        self.email.control.disabled = True
        self.otp = Field("OTP Code", required=True, hint="6-digit code", prefix_icon=ft.Icons.PIN)
        self.password = PasswordField("New Password", required=True, helper=PASSWORD_HELPER)
        self.confirm = PasswordField("Confirm New Password", required=True)
        self._error = styled_text("", style="caption", color=ft.Colors.RED_700)
        self._error.visible = False
        self._reset = Button("Reset Password", on_click=self._reset_password, icon=ft.Icons.LOCK_RESET, width=180)

    def build(self) -> ft.Control:
        body = ft.Column(
            [
                styled_text(
                    "Enter the code you received and choose a new password.",
                    style="body",
                    color=COLOR_TEXT_SECONDARY,
                ),
                ft.Container(self.email.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.otp.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.password.container, padding=ft.Padding.only(left=11)),
                ft.Container(self.confirm.container, padding=ft.Padding.only(left=11)),
                self._error,
                ft.Container(ft.Row([self._reset], alignment=ft.MainAxisAlignment.CENTER), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=12)),
                ft.Container(ft.Row([text_button("Back to sign in", self._on_back, color=COLOR_ACCENT)], alignment=ft.MainAxisAlignment.CENTER), alignment=ft.Alignment(-0.95, 0), padding=ft.Padding.only(top=4)),
            ],
            spacing=SPACING["sm"],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return _auth_card("Set a new password", "OTP verification", body, self._page)

    def _reset_password(self, e: ft.ControlEvent) -> None:
        self.otp.clear_error()
        self.password.clear_error()
        self.confirm.clear_error()
        otp = (self.otp.control.value or "").strip()
        password = self.password.control.value
        if not otp:
            self.otp.error("OTP code is required.")
            return
        pw_error = password_error(password)
        if pw_error:
            self.password.error(pw_error)
            return
        if password != self.confirm.control.value:
            self.confirm.error("Passwords do not match.")
            return
        self._reset.set_busy(True)
        try:
            self._auth.reset_password(self.email.control.value, otp, password)
            self._on_reset()
        except OtpVerificationError as exc:
            self.otp.error(str(exc))
        except LmsError as exc:
            self._error.value = str(exc)
            self._error.visible = True
            self._error.update()
        finally:
            self._reset.set_busy(False)