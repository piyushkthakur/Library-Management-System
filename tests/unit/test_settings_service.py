"""Unit tests for SettingsService and the role guard (Volume 3,
Chapters 15.2, 34.2) — no database required.

Run: python -m unittest discover -s tests
"""

import os
import unittest
from contextlib import contextmanager
from unittest import mock

from app.core.exceptions import UnauthorizedOperationError, ValidationError
from app.core.security import SessionContext
from app.models.user import UserRole
from app.services import settings_service
from app.services.authorization import require_role
from app.services.settings_service import SettingsService

ADMIN = SessionContext(
    user_id=1, role=UserRole.ADMINISTRATOR.value, full_name="Ada", email="ada@lms.local"
)
LIBRARIAN = SessionContext(
    user_id=2, role=UserRole.LIBRARIAN.value, full_name="Grace", email="grace@lms.local"
)


class FakeSession:
    pass


class FakeDatabase:
    def __init__(self):
        self.session = FakeSession()

    @contextmanager
    def session_scope(self):
        yield self.session


class FakeSettingsRepository:
    def __init__(self, values=None):
        self.values = values or {}

    def get_value(self, session, key):
        return self.values.get(key)

    def set_value(self, session, key, value):
        self.values[key] = value

    def get_all(self, session):
        return dict(self.values)


def make_service(values=None):
    return SettingsService(FakeDatabase(), FakeSettingsRepository(values))


class SettingsServiceTest(unittest.TestCase):
    # ----- Reads -----

    def test_admin_can_read_all_settings(self):
        service = make_service({"loan_period_days": "14"})
        self.assertEqual(service.get_all(ADMIN), {"loan_period_days": "14"})

    def test_non_admin_read_denied(self):
        service = make_service()
        with self.assertRaises(UnauthorizedOperationError):
            service.get_all(LIBRARIAN)

    # ----- Updates -----

    def test_admin_updates_settings(self):
        service = make_service({"loan_period_days": "14"})
        service.update(ADMIN, {"loan_period_days": "21", "fine_enabled": "true"})
        self.assertEqual(service._settings_repo.values["loan_period_days"], "21")
        self.assertEqual(service._settings_repo.values["fine_enabled"], "true")

    def test_non_admin_update_denied(self):
        service = make_service()
        with self.assertRaises(UnauthorizedOperationError):
            service.update(LIBRARIAN, {"loan_period_days": "21"})

    def test_invalid_setting_rejected(self):
        service = make_service()
        for bad in (
            {"loan_period_days": "abc"},
            {"loan_period_days": "0"},
            {"otp_expiry_minutes": "-5"},
            {"fine_enabled": "yes"},
            {"fine_rate_per_day": "abc"},
            {"fine_enabled": "true", "fine_rate_per_day": "0"},
            {"smtp_port": "99999"},
        ):
            with self.assertRaises(ValidationError, msg=str(bad)):
                service.update(ADMIN, bad)

    def test_unknown_setting_key_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.update(ADMIN, {"bogus_key": "1"})

    # ----- SMTP credentials -----

    def test_smtp_credentials_persisted_to_env(self):
        service = make_service()
        with mock.patch.object(settings_service, "persist_env") as persist:
            service.update_smtp_credentials(ADMIN, "lms@example.com", "app-secret")
        persist.assert_any_call("SMTP_USERNAME", "lms@example.com")
        persist.assert_any_call("SMTP_APP_PASSWORD", "app-secret")

    def test_smtp_credentials_invalid_email_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.update_smtp_credentials(ADMIN, "not-an-email", "app-secret")

    def test_smtp_credentials_non_admin_denied(self):
        service = make_service()
        with self.assertRaises(UnauthorizedOperationError):
            service.update_smtp_credentials(LIBRARIAN, "lms@example.com", "secret")

    # ----- Test email -----

    @mock.patch.dict(
        os.environ, {"SMTP_USERNAME": "lms@example.com", "SMTP_APP_PASSWORD": "x"}
    )
    def test_test_email_success(self):
        service = make_service()
        with mock.patch.object(settings_service, "send_email") as send:
            service.send_test_email(ADMIN)
        send.assert_called_once()

    @mock.patch.dict(os.environ, {"SMTP_USERNAME": "", "SMTP_APP_PASSWORD": ""})
    def test_test_email_unconfigured_rejected(self):
        service = make_service()
        with self.assertRaises(ValidationError):
            service.send_test_email(ADMIN)

    @mock.patch.dict(
        os.environ, {"SMTP_USERNAME": "lms@example.com", "SMTP_APP_PASSWORD": "x"}
    )
    def test_test_email_failure(self):
        service = make_service()
        with (
            mock.patch.object(
                settings_service, "send_email", side_effect=ConnectionError("boom")
            ),
            self.assertRaises(ValidationError),
        ):
            service.send_test_email(ADMIN)

    def test_test_email_non_admin_denied(self):
        service = make_service()
        with self.assertRaises(UnauthorizedOperationError):
            service.send_test_email(LIBRARIAN)


class AuthorizationTest(unittest.TestCase):
    def test_permission_granted(self):
        require_role(ADMIN, {UserRole.ADMINISTRATOR})

    def test_permission_denied(self):
        with self.assertRaises(UnauthorizedOperationError):
            require_role(LIBRARIAN, {UserRole.ADMINISTRATOR})


if __name__ == "__main__":
    unittest.main()
