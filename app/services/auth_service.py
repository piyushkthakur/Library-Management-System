"""AuthService — Authentication module (Volume 1, Chapter 27; Volume 2,
Chapter 15; Volume 3, Chapters 11, 14).

Owns: Administrator self-registration singleton (FR-AUTH-01/02), bcrypt
authentication (FR-AUTH-04), OTP issuance/expiry/single-use (FR-AUTH-05/06/07),
and the login lockout window (FR-AUTH-09). Session context per Volume 3,
Chapter 14.2; configuration per Volume 3, Chapter 20.
"""

import logging
import math
from datetime import datetime, timedelta
from time import time

from sqlalchemy.orm import Session

from app.core.config import (
    SETTING_LOGIN_LOCKOUT_MINUTES,
    SETTING_LOGIN_MAX_ATTEMPTS,
    SETTING_LOGIN_WINDOW_MINUTES,
    SETTING_OTP_EXPIRY_MINUTES,
    SETTING_PASSWORD_MIN_LENGTH,
    SETTING_SMTP_HOST,
    SETTING_SMTP_PORT,
    get_env,
)
from app.core.database import Database
from app.core.exceptions import (
    AccountLockedError,
    OtpVerificationError,
    ValidationError,
)
from app.core.mailer import send_email
from app.core.security import OtpCode, SessionContext, hasher
from app.models.user import UserRole
from app.repositories.interfaces import (
    OtpRepositoryInterface,
    SettingsRepositoryInterface,
    UserRepositoryInterface,
)
from app.services.interfaces import AuthServiceInterface
from app.utils.validators import is_valid_email, password_error

logger = logging.getLogger(__name__)

_DEFAULT_OTP_EXPIRY_MINUTES = 10
_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_LOCKOUT_MINUTES = 15
_DEFAULT_WINDOW_MINUTES = 15


class AuthService(AuthServiceInterface):
    """Authentication flows. Lockout state is derived from in-memory
    timestamped failure records per account rather than a persisted counter,
    avoiding an additional schema table (Volume 3, Chapter 14.4).

    DOCUMENTED LIMITATION — lockout state is process-local. It is not shared
    across multiple application instances, and restarting the application
    clears the in-memory lockout state. This is intentional: Volumes 1-4 do
    not define persistent lockout storage, so no Redis, cache server,
    additional table, or external storage is introduced (FR-AUTH-09 is
    implemented exactly as documented in Volume 3, Chapter 14.4).
    """

    def __init__(
        self,
        database: Database,
        user_repository: UserRepositoryInterface,
        otp_repository: OtpRepositoryInterface,
        settings_repository: SettingsRepositoryInterface,
    ) -> None:
        self._database = database
        self._user_repo = user_repository
        self._otp_repo = otp_repository
        self._settings_repo = settings_repository
        self._failures: dict[int, list[float]] = {}
        self._locked_until: dict[int, float] = {}

    def hash_password(self, password: str) -> str:
        """bcrypt hash at account creation; exclusive password wrapper
        (Volume 3, Chapter 25)."""
        return hasher.hash(password)

    def verify_password(self, password: str, stored_hash: str) -> bool:
        """Re-verify, never re-hash, on login (Volume 3, Chapter 14.1)."""
        return hasher.verify(password, stored_hash)

    def admin_exists(self) -> bool:
        try:
            with self._database.session_scope() as session:
                return self._user_repo.count_admins(session) > 0
        except Exception as e:
            # Table might not exist on first run — treat as no admin
            logger.warning("Could not check admin existence: %s", e)
            return False

    def register_administrator(
        self, full_name: str, email: str, password: str
    ) -> SessionContext:
        with self._database.session_scope() as session:
            if self._user_repo.count_admins(session) > 0:
                raise ValidationError("An Administrator account already exists.")
            if not is_valid_email(email):
                raise ValidationError("Enter a valid email address.")
            policy_error = password_error(
                password, self._setting_int(session, SETTING_PASSWORD_MIN_LENGTH, 8)
            )
            if policy_error is not None:
                raise ValidationError(policy_error)
            user = self._user_repo.create(
                session,
                full_name,
                email,
                self.hash_password(password),
                UserRole.ADMINISTRATOR.value,
            )
            logger.info("Administrator account created (user_id=%s)", user.id)
            return SessionContext(
                user_id=user.id,
                role=user.role.value,
                full_name=user.full_name,
                email=user.email,
            )

    def login(self, email: str, password: str) -> SessionContext:
        with self._database.session_scope() as session:
            user = self._user_repo.get_by_email(session, email)
            if user is None or not user.is_active:
                logger.warning("Login rejected for unknown or inactive account")
                raise ValidationError("Invalid email or password.")
            user_id = user.id
            now = time()
            locked_until = self._locked_until.get(user_id, 0.0)
            if locked_until > now:
                logger.warning("Login rejected during lockout (user_id=%s)", user_id)
                raise AccountLockedError(self._lockout_message(locked_until, now))
            self._prune_failures(user_id, session, now)
            if not self.verify_password(password, user.password_hash):
                self._failures.setdefault(user_id, []).append(now)
                logger.warning(
                    "Login rejected (invalid credentials, user_id=%s)", user_id
                )
                if len(self._failures[user_id]) >= self._setting_int(
                    session, SETTING_LOGIN_MAX_ATTEMPTS, _DEFAULT_MAX_ATTEMPTS
                ):
                    lockout_minutes = self._setting_int(
                        session, SETTING_LOGIN_LOCKOUT_MINUTES, _DEFAULT_LOCKOUT_MINUTES
                    )
                    locked_until = now + lockout_minutes * 60
                    self._locked_until[user_id] = locked_until
                    self._failures.pop(user_id, None)
                    logger.warning("Login lockout triggered (user_id=%s)", user_id)
                    raise AccountLockedError(self._lockout_message(locked_until, now))
                raise ValidationError("Invalid email or password.")
            self._failures.pop(user_id, None)
            self._locked_until.pop(user_id, None)
            logger.info("Login successful (user_id=%s)", user_id)
            return SessionContext(
                user_id=user.id,
                role=user.role.value,
                full_name=user.full_name,
                email=user.email,
            )

    def request_otp(self, email: str) -> None:
        """Issue a password-reset OTP without revealing account existence.

        - Active account: generate, hash, persist, and email the OTP.
        - Unknown email: no OTP, no email, identical success response
          (anti-enumeration; Volume 2, Chapter 15 error-handling discipline).
        - Inactive account: dedicated error, no OTP, no email (logged
          internally).
        """
        with self._database.session_scope() as session:
            user = self._user_repo.get_by_email(session, email)
            if user is None:
                logger.warning("OTP requested for unknown account")
                return
            if not user.is_active:
                logger.warning(
                    "OTP requested for inactive account (user_id=%s)", user.id
                )
                raise ValidationError(
                    "Your account is currently inactive. Please verify the "
                    "email address you entered. If the email is correct, "
                    "please contact the system administrator."
                )
            expiry_minutes = self._setting_int(
                session, SETTING_OTP_EXPIRY_MINUTES, _DEFAULT_OTP_EXPIRY_MINUTES
            )
            code = OtpCode.generate()
            self._otp_repo.create(
                session,
                user.id,
                OtpCode.digest(code),
                datetime.now() + timedelta(minutes=expiry_minutes),
            )
            self._dispatch_email(
                session,
                user.email,
                "Your LMS password reset code",
                f"Your password reset code is {code}. "
                f"It expires in {expiry_minutes} minutes.",
            )
            logger.warning("OTP requested (user_id=%s)", user.id)

    def reset_password(self, email: str, otp_code: str, new_password: str) -> None:
        with self._database.session_scope() as session:
            user = self._user_repo.get_by_email(session, email)
            if user is None:
                raise OtpVerificationError("Invalid or expired OTP.")
            record = self._otp_repo.get_latest_unexpired(session, user.id)
            if record is None or not OtpCode.matches(otp_code, record.otp_code_hash):
                logger.warning("OTP verification failed (user_id=%s)", user.id)
                raise OtpVerificationError("Invalid or expired OTP.")
            policy_error = password_error(
                new_password, self._setting_int(session, SETTING_PASSWORD_MIN_LENGTH, 8)
            )
            if policy_error is not None:
                raise ValidationError(policy_error)
            self._otp_repo.mark_used(session, record.id)
            user.password_hash = self.hash_password(new_password)
            self._user_repo.update(session, user)
            self._locked_until.pop(user.id, None)
            logger.info("Password reset completed (user_id=%s)", user.id)

    def _prune_failures(self, user_id: int, session: Session, now: float) -> None:
        window = self._setting_int(
            session, SETTING_LOGIN_WINDOW_MINUTES, _DEFAULT_WINDOW_MINUTES
        )
        cutoff = now - window * 60
        self._failures[user_id] = [
            stamp for stamp in self._failures.get(user_id, []) if stamp > cutoff
        ]

    def _setting_int(self, session: Session, key: str, default: int) -> int:
        raw = self._settings_repo.get_value(session, key)
        try:
            return int(raw) if raw is not None else default
        except ValueError:
            return default

    def _dispatch_email(
        self, session: Session, to_address: str, subject: str, body: str
    ) -> None:
        host = (
            self._settings_repo.get_value(session, SETTING_SMTP_HOST)
            or "smtp.gmail.com"
        )
        try:
            port = int(self._settings_repo.get_value(session, SETTING_SMTP_PORT) or 587)
        except ValueError:
            port = 587
        username = get_env("SMTP_USERNAME")
        app_password = get_env("SMTP_APP_PASSWORD")
        if not username or not app_password:
            logger.error("SMTP credentials are not configured")
            raise ValidationError(
                "Email delivery is not configured. Contact your administrator."
            )
        try:
            send_email(host, port, username, app_password, to_address, subject, body)
        except Exception as error:
            logger.error("OTP dispatch failed: %s", error)
            raise ValidationError(
                "Could not send the email. Please try again."
            ) from error

    @staticmethod
    def _lockout_message(locked_until: float, now: float) -> str:
        remaining = math.ceil((locked_until - now) / 60)
        return f"Too many failed login attempts. Try again in {remaining} minute(s)."
