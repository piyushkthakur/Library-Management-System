"""Unit tests for AuthService with mocked repositories (Volume 3,
Chapter 34.2) — no database required.

Run: python -m unittest discover -s tests
"""

import os
import unittest
from contextlib import contextmanager
from datetime import datetime as real_datetime
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from app.core.config import SETTING_OTP_EXPIRY_MINUTES
from app.core.exceptions import (
    AccountLockedError,
    OtpVerificationError,
    ValidationError,
)
from app.core.security import OtpCode, hasher
from app.models.user import UserRole
from app.services import auth_service
from app.services.auth_service import AuthService

INACTIVE_ACCOUNT_MESSAGE = (
    "Your account is currently inactive. Please verify the email address "
    "you entered. If the email is correct, please contact the system "
    "administrator."
)

SMTP_ENV = {"SMTP_USERNAME": "lms@example.com", "SMTP_APP_PASSWORD": "app-secret"}

# Fixed epoch shared by every timing test: OTP and lockout computations are
# deterministic and independent of the machine clock (refinement: mocked time).
_FROZEN_EPOCH = 1_700_000_000.0


class FrozenClock:
    """Deterministic test clock; never reads the system time."""

    def __init__(self, start=_FROZEN_EPOCH):
        self.current = start

    @property
    def now(self):
        return real_datetime.fromtimestamp(self.current)

    def advance(self, seconds: float) -> None:
        self.current += seconds


@contextmanager
def frozen_auth_time(clock: FrozenClock):
    """Freeze every time read inside auth_service (time() and datetime.now())
    to the clock's current position for the duration of the block."""
    with (
        mock.patch.object(auth_service, "time", side_effect=lambda: clock.current),
        mock.patch.object(auth_service, "datetime") as dt,
    ):
        dt.now = lambda: clock.now
        dt.timedelta = timedelta
        yield clock


class FakeSession:
    """Simulates the unit-of-work pending state: records added within the
    session are discarded when the session is rolled back."""

    def __init__(self):
        self.pending = []
        self.otp_records = []

    def add(self, record):
        self.pending.append(record)
        self.otp_records.append(record)

    def rollback(self):
        self.pending.clear()
        self.otp_records.clear()


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        try:
            yield self.session
        except Exception:
            self.session.rollback()
            raise


class FakeUserRepository:
    def __init__(self, users):
        self.users = {u["email"]: u for u in users}
        self.next_id = max((u["id"] for u in users), default=0) + 1

    def count_admins(self, session):
        return sum(
            1 for u in self.users.values() if u["role"] == UserRole.ADMINISTRATOR
        )

    def get_by_email(self, session, email):
        user = self.users.get(email)
        if user is None:
            return None
        return SimpleNamespace(
            id=user["id"],
            full_name=user["full_name"],
            email=user["email"],
            role=user["role"],
            is_active=user["is_active"],
            password_hash=user["password_hash"],
        )

    def create(self, session, full_name, email, password_hash, role):
        user = {
            "id": self.next_id,
            "full_name": full_name,
            "email": email,
            "role": UserRole(role),
            "is_active": True,
            "password_hash": password_hash,
        }
        self.users[email] = user
        self.next_id += 1
        return SimpleNamespace(
            id=user["id"],
            full_name=user["full_name"],
            email=user["email"],
            role=user["role"],
            is_active=user["is_active"],
            password_hash=user["password_hash"],
        )

    def update(self, session, user):
        self.users[user.email]["password_hash"] = user.password_hash


class FakeOtpRepository:
    """Persists OTP records into the session so rollback discards them.
    Expiry checks use an injectable clock for deterministic tests."""

    def __init__(self, now_fn=real_datetime.now):
        self.now_fn = now_fn
        self.next_id = 1

    def create(self, session, user_id, otp_code_hash, expires_at):
        record = SimpleNamespace(
            id=self.next_id,
            user_id=user_id,
            otp_code_hash=otp_code_hash,
            expires_at=expires_at,
            is_used=False,
        )
        self.next_id += 1
        session.add(record)
        return record

    def get_latest_unexpired(self, session, user_id):
        now = self.now_fn()
        candidates = [
            r
            for r in session.otp_records
            if r.user_id == user_id and not r.is_used and r.expires_at > now
        ]
        return candidates[-1] if candidates else None

    def mark_used(self, session, otp_id):
        for record in session.otp_records:
            if record.id == otp_id:
                record.is_used = True


class FakeSettingsRepository:
    def __init__(self, values=None):
        self.values = values or {}

    def get_value(self, session, key):
        return self.values.get(key)

    def set_value(self, session, key, value):
        self.values[key] = value

    def get_all(self, session):
        return dict(self.values)


def make_service(users=None, settings=None, clock=None):
    users = (
        users
        if users is not None
        else [
            {
                "id": 1,
                "full_name": "Ada Lovelace",
                "email": "ada@library.local",
                "role": UserRole.ADMINISTRATOR,
                "is_active": True,
                "password_hash": hasher.hash("Passw0rd!"),
            }
        ]
    )
    return (
        AuthService(
            FakeDatabase(),
            FakeUserRepository(users),
            FakeOtpRepository(
                now_fn=(lambda: clock.now) if clock else real_datetime.now
            ),
            FakeSettingsRepository(settings),
        ),
        users,
    )


def issue_otp(service, user_id, code, expiry_delta=None, clock=None):
    """Seed an OTP record directly, returning the plaintext code."""
    now = clock.now if clock else real_datetime.now()
    expires_at = now + (
        expiry_delta if expiry_delta is not None else timedelta(minutes=10)
    )
    service._otp_repo.create(
        service._database.session, user_id, OtpCode.digest(code), expires_at
    )
    return code


class AuthServiceTest(unittest.TestCase):
    # ----- Authentication -----

    def test_login_success_returns_context(self):
        service, _ = make_service()
        context = service.login("ada@library.local", "Passw0rd!")
        self.assertEqual(context.role, UserRole.ADMINISTRATOR.value)
        self.assertEqual(context.full_name, "Ada Lovelace")

    def test_login_invalid_password_rejected(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.login("ada@library.local", "wrong")

    def test_login_inactive_account_rejected(self):
        users = [
            {
                "id": 2,
                "full_name": "Grace Hopper",
                "email": "grace@library.local",
                "role": UserRole.LIBRARIAN,
                "is_active": False,
                "password_hash": hasher.hash("Passw0rd!"),
            }
        ]
        service, _ = make_service(users)
        with self.assertRaises(ValidationError):
            service.login("grace@library.local", "Passw0rd!")

    def test_login_failure_then_lockout_then_blocked(self):
        clock = FrozenClock()
        service, _ = make_service(clock=clock)
        with frozen_auth_time(clock):
            for _ in range(4):
                with self.assertRaises(ValidationError):
                    service.login("ada@library.local", "wrong")
            with self.assertRaises(AccountLockedError):
                service.login("ada@library.local", "wrong")
            with self.assertRaises(AccountLockedError):
                service.login("ada@library.local", "Passw0rd!")

    def test_lockout_expires_and_login_allowed(self):
        clock = FrozenClock()
        service, _ = make_service(clock=clock)
        with frozen_auth_time(clock):
            for _ in range(5):
                with self.assertRaises((ValidationError, AccountLockedError)):
                    service.login("ada@library.local", "wrong")
            clock.advance(16 * 60)
            context = service.login("ada@library.local", "Passw0rd!")
        self.assertEqual(context.user_id, 1)

    def test_register_administrator_first_run(self):
        service, _ = make_service(users=[])
        context = service.register_administrator(
            "Ada Lovelace", "ada@library.local", "Passw0rd!"
        )
        self.assertEqual(context.role, UserRole.ADMINISTRATOR.value)
        self.assertTrue(service._user_repo.users["ada@library.local"]["is_active"])

    def test_register_administrator_blocked_after_setup(self):
        service, _ = make_service()
        with self.assertRaises(ValidationError):
            service.register_administrator(
                "Second Admin", "second@library.local", "Passw0rd!"
            )

    # ----- Password Reset -----

    @mock.patch.dict(os.environ, SMTP_ENV)
    def test_otp_generated_and_email_sent(self):
        clock = FrozenClock()
        service, _ = make_service(
            settings={SETTING_OTP_EXPIRY_MINUTES: "10"}, clock=clock
        )
        with (
            frozen_auth_time(clock),
            mock.patch.object(auth_service, "send_email") as send,
        ):
            service.request_otp("ada@library.local")
        record = service._database.session.otp_records[0]
        self.assertEqual(record.expires_at, clock.now + timedelta(minutes=10))
        send.assert_called_once()
        body = send.call_args.args[6]
        self.assertIn("expires in 10 minutes", body)

    @mock.patch.dict(os.environ, SMTP_ENV)
    def test_otp_stored_only_as_hash(self):
        service, _ = make_service()
        with mock.patch.object(auth_service, "send_email"):
            service.request_otp("ada@library.local")
        stored = service._database.session.otp_records[0].otp_code_hash
        self.assertNotIn("123456", stored)
        self.assertTrue(stored.startswith("$2"))

    def test_request_otp_unknown_email_generic_success(self):
        service, _ = make_service()
        with mock.patch.object(auth_service, "send_email") as send:
            result = service.request_otp("ghost@library.local")
        self.assertIsNone(result)
        self.assertEqual(len(service._database.session.otp_records), 0)
        send.assert_not_called()

    def test_request_otp_inactive_account_error(self):
        users = [
            {
                "id": 2,
                "full_name": "Grace Hopper",
                "email": "grace@library.local",
                "role": UserRole.LIBRARIAN,
                "is_active": False,
                "password_hash": hasher.hash("Passw0rd!"),
            }
        ]
        service, _ = make_service(users)
        with (
            mock.patch.object(auth_service, "send_email") as send,
            self.assertRaises(ValidationError) as caught,
        ):
            service.request_otp("grace@library.local")
        self.assertEqual(caught.exception.message, INACTIVE_ACCOUNT_MESSAGE)
        self.assertEqual(len(service._database.session.otp_records), 0)
        send.assert_not_called()

    def test_smtp_failure_rolls_back_otp_persistence(self):
        service, _ = make_service()
        with (
            mock.patch.dict(os.environ, SMTP_ENV),
            mock.patch.object(
                auth_service, "send_email", side_effect=ConnectionError("boom")
            ),
            self.assertRaises(ValidationError),
        ):
            service.request_otp("ada@library.local")
        self.assertEqual(len(service._database.session.otp_records), 0)

    def test_reset_password_success_rotates_hash(self):
        service, _ = make_service()
        code = issue_otp(service, 1, OtpCode.generate())
        service.reset_password("ada@library.local", code, "NewPass1!")
        context = service.login("ada@library.local", "NewPass1!")
        self.assertEqual(context.user_id, 1)

    def test_otp_expired_rejected(self):
        clock = FrozenClock()
        service, _ = make_service(clock=clock)
        with frozen_auth_time(clock):
            code = issue_otp(
                service, 1, OtpCode.generate(), timedelta(minutes=-5), clock=clock
            )
            with self.assertRaises(OtpVerificationError):
                service.reset_password("ada@library.local", code, "NewPass1!")

    def test_otp_reused_rejected(self):
        service, _ = make_service()
        code = issue_otp(service, 1, OtpCode.generate())
        service.reset_password("ada@library.local", code, "NewPass1!")
        with self.assertRaises(OtpVerificationError):
            service.reset_password("ada@library.local", code, "NewPass2!")

    def test_reset_password_clears_lockout(self):
        clock = FrozenClock()
        service, _ = make_service(clock=clock)
        with frozen_auth_time(clock):
            for _ in range(5):
                with self.assertRaises((ValidationError, AccountLockedError)):
                    service.login("ada@library.local", "wrong")
            code = issue_otp(service, 1, OtpCode.generate(), clock=clock)
            service.reset_password("ada@library.local", code, "NewPass1!")
            context = service.login("ada@library.local", "NewPass1!")
        self.assertEqual(context.user_id, 1)


if __name__ == "__main__":
    unittest.main()
