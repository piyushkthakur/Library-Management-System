"""SettingsService — Settings module (Volume 1, Chapter 14.8; Volume 2,
Chapter 22; Volume 3, Chapter 11).

Owns: Administrator-only modification (FR-SET-01) and key-value persistence
(FR-SET-02). SMTP credentials are environment-variable-backed (Volume 2,
Chapter 22); operational parameters live in the settings table.
"""

import logging

from app.core.config import (
    SETTING_FINE_ENABLED,
    SETTING_FINE_RATE_PER_DAY,
    SETTING_LOAN_PERIOD_DAYS,
    SETTING_LOGIN_LOCKOUT_MINUTES,
    SETTING_LOGIN_MAX_ATTEMPTS,
    SETTING_LOGIN_WINDOW_MINUTES,
    SETTING_OTP_EXPIRY_MINUTES,
    SETTING_PASSWORD_MIN_LENGTH,
    SETTING_SMTP_HOST,
    SETTING_SMTP_PORT,
    get_env,
    persist_env,
)
from app.core.database import Database
from app.core.exceptions import ValidationError
from app.core.mailer import send_email
from app.core.security import SessionContext
from app.models.user import UserRole
from app.repositories.interfaces import SettingsRepositoryInterface
from app.services.authorization import require_role
from app.services.interfaces import SettingsServiceInterface
from app.utils.validators import is_valid_email

logger = logging.getLogger(__name__)

_EDITABLE_KEYS = frozenset(
    {
        SETTING_LOAN_PERIOD_DAYS,
        SETTING_FINE_ENABLED,
        SETTING_FINE_RATE_PER_DAY,
        SETTING_OTP_EXPIRY_MINUTES,
        SETTING_SMTP_HOST,
        SETTING_SMTP_PORT,
        SETTING_PASSWORD_MIN_LENGTH,
        SETTING_LOGIN_MAX_ATTEMPTS,
        SETTING_LOGIN_LOCKOUT_MINUTES,
        SETTING_LOGIN_WINDOW_MINUTES,
    }
)


class SettingsService(SettingsServiceInterface):
    """Settings reads and updates, restricted to Administrators
    (FR-SET-01; Volume 3, Chapter 15.1 permission matrix)."""

    def __init__(
        self, database: Database, settings_repository: SettingsRepositoryInterface
    ) -> None:
        self._database = database
        self._settings_repo = settings_repository

    def get_all(self, context: SessionContext) -> dict:
        require_role(context, {UserRole.ADMINISTRATOR})
        with self._database.session_scope() as session:
            return self._settings_repo.get_all(session)

    def update(self, context: SessionContext, changes: dict) -> None:
        require_role(context, {UserRole.ADMINISTRATOR})
        validated = self._validate(changes)
        with self._database.session_scope() as session:
            for key, value in validated.items():
                self._settings_repo.set_value(session, key, value)
            logger.info("Settings updated (user_id=%s)", context.user_id)

    def update_smtp_credentials(
        self, context: SessionContext, gmail_account: str, app_password: str
    ) -> None:
        require_role(context, {UserRole.ADMINISTRATOR})
        account = gmail_account.strip()
        if not is_valid_email(account):
            raise ValidationError("Enter a valid email address.")
        if not app_password:
            raise ValidationError("App Password is required.")
        persist_env("SMTP_USERNAME", account)
        persist_env("SMTP_APP_PASSWORD", app_password)
        logger.info("SMTP credentials updated (user_id=%s)", context.user_id)

    def send_test_email(self, context: SessionContext) -> None:
        require_role(context, {UserRole.ADMINISTRATOR})
        with self._database.session_scope() as session:
            host = self._settings_repo.get_value(session, SETTING_SMTP_HOST)
            port = self._settings_repo.get_value(session, SETTING_SMTP_PORT)
            username = get_env("SMTP_USERNAME")
            app_password = get_env("SMTP_APP_PASSWORD")
            if not username or not app_password:
                raise ValidationError(
                    "Email delivery is not configured. Contact your administrator."
                )
            try:
                send_email(
                    host or "smtp.gmail.com",
                    int(port or 587),
                    username,
                    app_password,
                    username,
                    "LMS test email",
                    "SMTP configuration verified successfully.",
                )
            except Exception as error:
                logger.error("Test email dispatch failed: %s", error)
                raise ValidationError(
                    "Could not confirm SMTP delivery. Please check the "
                    "configuration and try again."
                ) from error
            logger.info("Test email sent (user_id=%s)", context.user_id)

    def _validate(self, changes: dict) -> dict:
        unknown = set(changes) - _EDITABLE_KEYS
        if unknown:
            raise ValidationError("Unknown setting key.")
        validated: dict = {}
        for key, raw in changes.items():
            value = str(raw).strip()
            if key == SETTING_LOAN_PERIOD_DAYS:
                validated[key] = self._positive_int(
                    value, "Loan Period must be a positive integer."
                )
            elif key == SETTING_OTP_EXPIRY_MINUTES:
                validated[key] = self._positive_int(
                    value, "OTP Expiry Window must be a positive integer."
                )
            elif key == SETTING_PASSWORD_MIN_LENGTH:
                validated[key] = self._positive_int(
                    value, "Password minimum length must be a positive integer."
                )
            elif key == SETTING_LOGIN_MAX_ATTEMPTS:
                validated[key] = self._positive_int(
                    value, "Maximum login attempts must be a positive integer."
                )
            elif (
                key == SETTING_LOGIN_LOCKOUT_MINUTES
                or key == SETTING_LOGIN_WINDOW_MINUTES
            ):
                validated[key] = self._positive_int(
                    value, "Lockout window must be a positive integer."
                )
            elif key == SETTING_FINE_ENABLED:
                if value not in ("true", "false"):
                    raise ValidationError("Enable Fines must be on or off.")
                validated[key] = value
            elif key == SETTING_FINE_RATE_PER_DAY:
                try:
                    rate = float(value)
                except ValueError:
                    raise ValidationError("Fine Rate must be a positive number.")
                if rate < 0:
                    raise ValidationError("Fine Rate must be a positive number.")
                if changes.get(SETTING_FINE_ENABLED) == "true" and rate == 0:
                    raise ValidationError(
                        "Fine Rate must be positive when fines are enabled."
                    )
                validated[key] = value
            elif key == SETTING_SMTP_HOST:
                if not value:
                    raise ValidationError("SMTP host is required.")
                validated[key] = value
            elif key == SETTING_SMTP_PORT:
                try:
                    port = int(value)
                except ValueError:
                    raise ValidationError("SMTP port must be a valid number.")
                if not 1 <= port <= 65535:
                    raise ValidationError("SMTP port must be between 1 and 65535.")
                validated[key] = value
        return validated

    @staticmethod
    def _positive_int(value: str, message: str) -> str:
        try:
            number = int(value)
        except ValueError:
            raise ValidationError(message)
        if number < 1:
            raise ValidationError(message)
        return value
