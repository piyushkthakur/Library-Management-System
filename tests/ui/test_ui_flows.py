"""Simulated Flet interaction tests for the presentation layer.

Volumes 4, Ch 38 style: drive the event-handler flows of the screens with fake
services and a stub page. No GUI is launched; flet's ``Control.update`` is
softened so changes that require an attached live page no-op instead of raising.

Run: python -m unittest discover -s tests -p 'test_ui_*.py'
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

import flet as ft

from app.core.exceptions import OtpVerificationError, ValidationError
from app.core.security import SessionContext
from app.main import _classify_search, _MainWindow, _nav_items
from app.models.user import UserRole
from app.presentation.screens.auth.auth_screen import (
    AdminRegistrationScreen,
    LoginScreen,
    ResetPasswordScreen,
)
from app.presentation.screens.books.books_screen import BooksScreen
from app.presentation.screens.settings.settings_screen import SettingsScreen
from app.presentation.screens.transactions.transactions_screen import TransactionsScreen
from app.presentation.shared_components.buttons import Button
from app.presentation.shared_components.toast import ToastHost

ADMIN = SessionContext(user_id=1, role=UserRole.ADMINISTRATOR, full_name="A", email="a@lib.local")


def _fire(coro):
    """Drive an async screen handler to completion (login/register handlers
    are async so the throbber paints before the blocking service call)."""
    asyncio.run(coro)


class UIFlowTestCase(unittest.TestCase):
    def setUp(self):
        self.page = SimpleNamespace(overlay=[], open=lambda d: None, close=lambda d: None, update=lambda: None)
        self.toasts = ToastHost()
        import flet.controls.base_control as base

        orig = base.BaseControl.update

        def _soft_update(self, *args, **kwargs):
            try:
                orig(self, *args, **kwargs)
            except RuntimeError:
                pass

        base.BaseControl.update = _soft_update
        self.addCleanup(lambda: setattr(base.BaseControl, "update", orig))


class FakeToasts:
    def __init__(self):
        self.shown = []
        self.stack = SimpleNamespace(margin=None)

    def show(self, message, kind="success"):
        self.shown.append((message, kind))

    def clear(self):
        pass

    def bind(self, *args, **kwargs):
        pass

    def resize(self, content_width):
        self.stack.width = min(360, content_width - 32)


class FakeAuthService:
    def __init__(self):
        self.logins = []
        self.registered = []

    def admin_exists(self):
        return True

    def login(self, email, password):
        self.logins.append((email, password))
        return ADMIN

    def register_administrator(self, full_name, email, password):
        self.registered.append((full_name, email, password))
        raise ValidationError("An account with this email already exists.")


class LoginFlowTests(UIFlowTestCase):
    def test_empty_submit_shows_required_error_without_calling_service(self):
        auth = FakeAuthService()
        screen = LoginScreen(self.page, auth, lambda c: None, lambda: None, lambda: None)
        screen.build()
        screen.on_activate()
        screen.password.control.value = "secret"
        _fire(screen._login(None))
        self.assertTrue(screen.email._error_text.visible)
        self.assertFalse(auth.logins)

    def test_invalid_email_blocks_login(self):
        auth = FakeAuthService()
        screen = LoginScreen(self.page, auth, lambda c: None, lambda: None, lambda: None)
        screen.build()
        screen.email.control.value = "not-an-email"
        screen.password.control.value = "secret"
        _fire(screen._login(None))
        self.assertTrue(screen.email._error_text.visible)
        self.assertFalse(auth.logins)

    def test_valid_login_signs_in(self):
        auth = FakeAuthService()
        results = []
        screen = LoginScreen(self.page, auth, lambda c: results.append(c), lambda: None, lambda: None)
        screen.build()
        screen.email.control.value = "admin@lib.local"
        screen.password.control.value = "correct-password"
        _fire(screen._login(None))
        self.assertEqual(auth.logins, [("admin@lib.local", "correct-password")])
        self.assertEqual(results, [ADMIN])
        self.assertFalse(screen.email._error_text.visible)

    def test_register_link_hidden_once_admin_exists(self):
        auth = FakeAuthService()
        screen = LoginScreen(self.page, auth, lambda c: None, lambda: None, lambda: None)
        screen.build()
        screen.on_activate()
        self.assertFalse(screen._register_row.visible)

    def test_register_link_visible_before_any_admin_registered(self):
        auth = FakeAuthService()

        def no_admins():
            return False

        auth.admin_exists = no_admins
        screen = LoginScreen(self.page, auth, lambda c: None, lambda: None, lambda: None)
        screen.build()
        screen.on_activate()
        self.assertTrue(screen._register_row.visible)


class RegistrationFlowTests(UIFlowTestCase):
    def test_password_mismatch_blocks_registration(self):
        auth = FakeAuthService()
        screen = AdminRegistrationScreen(self.page, auth, lambda: None)
        screen.build()
        screen.full_name.control.value = "Ada"
        screen.email.control.value = "ada@lib.local"
        screen.password.control.value = "StrongPass1!"
        screen.confirm.control.value = "Different1!"
        _fire(screen._register_admin(None))
        self.assertTrue(screen.confirm._error_text.visible)
        self.assertFalse(auth.registered)

    def test_duplicate_email_surfaces_service_error(self):
        auth = FakeAuthService()
        screen = AdminRegistrationScreen(self.page, auth, lambda: None)
        screen.build()
        screen.full_name.control.value = "Ada"
        screen.email.control.value = "ada@lib.local"
        screen.password.control.value = "StrongPass1!"
        screen.confirm.control.value = "StrongPass1!"
        _fire(screen._register_admin(None))
        self.assertTrue(screen._error.visible)
        self.assertIn("already exists", screen._error.value)


class ResetFlowTests(UIFlowTestCase):
    def test_otp_mismatch_surfaces_otp_error(self):
        auth = FakeAuthService()

        def reset_password(email, otp, password):
            raise OtpVerificationError("Invalid or expired OTP code.")

        auth.reset_password = reset_password
        screen = ResetPasswordScreen(self.page, auth, "ada@lib.local", lambda: None, lambda: None)
        screen.build()
        screen.otp.control.value = "123456"
        screen.password.control.value = "NewPass1!"
        screen.confirm.control.value = "NewPass1!"
        screen._reset_password(None)
        self.assertEqual(screen.otp._error_text.value, "Invalid or expired OTP code.")


class FakeBookService:
    def __init__(self):
        self.searches = []
        self.calls = []

    def search(self, term, category_id, page, page_size):
        self.calls.append((term, category_id, page, page_size))
        return [], 0

    def list_available(self, term, page, page_size):
        return [], 0


class FakeCategoryService:
    def __init__(self, items=None):
        self.calls = []
        self.created = []
        self._items = list(items or [])

    def list_all(self, context):
        self.calls.append(True)
        return [
            SimpleNamespace(id=index + 1, name=name, description=None)
            for index, name in enumerate(self._items)
        ]

    def create(self, category_input, context):
        self.created.append(category_input.name)
        self._items.append(category_input.name)
        return SimpleNamespace(id=len(self._items), name=category_input.name, description=None)


class BookCatalogTests(UIFlowTestCase):
    def test_quick_filter_triggers_query_and_renders(self):
        books = FakeBookService()
        screen = BooksScreen(self.page, books, FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts())
        screen.build()
        screen._on_chip("available")
        self.assertEqual(len(books.calls), 1)
        self.assertIsNone(screen._category_id)
        screen._on_search("Clean")
        self.assertEqual(screen._term, "Clean")


class TransactionCatalogTests(UIFlowTestCase):
    def test_activate_applies_deep_link_status(self):
        class FakeTxn:
            def __init__(self):
                self.filters = []
                self.active = []

            def list_transactions(self, status=None, start_date=None, end_date=None,
                                  book_search=None, borrower_search=None, page=1, page_size=10):
                self.filters.append((status, start_date, end_date, book_search, borrower_search, page, page_size))
                return [], 0

        txn = FakeTxn()
        screen = TransactionsScreen(self.page, txn, FakeBookService(), ADMIN, FakeToasts())
        screen.build()
        screen.activate({"status": "Overdue"})
        self.assertEqual(txn.filters[-1][0], "Overdue")


class SettingsFlows(UIFlowTestCase):
    def test_circulation_save_posts_expected_keys(self):
        class FakeSettings:
            def __init__(self):
                self.updates = []

            def get_all(self, context):
                return {"loan_period_days": "14", "fine_enabled": "true",
                        "fine_rate_per_day": "5.00", "otp_expiry_minutes": "10",
                        "password_min_length": "8"}

            def update(self, context, changes):
                self.updates.append(changes)

            def update_smtp_credentials(self, context, account, app_password):
                pass

            def send_test_email(self, context):
                pass

        settings = FakeSettings()
        screen = SettingsScreen(self.page, settings, ADMIN, FakeToasts())
        screen.build()
        screen.activate()
        screen.loan_days.control.value = "21"
        screen.fine_rate.control.value = "2.50"
        screen.fine_enabled.data.value = True
        screen._save_circulation()
        changes = settings.updates[-1]
        self.assertEqual(changes["loan_period_days"], "21")
        self.assertEqual(changes["fine_rate_per_day"], "2.50")
        self.assertEqual(changes["fine_enabled"], "true")


class RoleNavigationTests(unittest.TestCase):
    def test_roles_hide_admin_only_modules(self):
        admin = {item[2] for item in _nav_items(UserRole.ADMINISTRATOR)}
        lib = {item[2] for item in _nav_items(UserRole.LIBRARIAN)}
        self.assertIn("reports", admin)
        self.assertIn("reports", lib)
        self.assertNotIn("librarians", lib)
        self.assertNotIn("settings", lib)
        self.assertNotIn("my_activity", admin)


class MainWindowLoginTests(UIFlowTestCase):
    @mock.patch("app.main.save_session")
    def test_login_attaches_shell_before_navigation(self, save_session):
        toasts = FakeToasts()
        window = _MainWindow(self.page, {}, toasts)
        order = []
        window._build_shell = mock.Mock(side_effect=lambda: order.append("shell"))
        window.navigate = mock.Mock(side_effect=lambda *a, **k: order.append("navigate"))
        toasts.show = mock.Mock(side_effect=lambda *a, **k: order.append("toast"))
        window._on_login(ADMIN)
        self.assertEqual(order, ["shell", "navigate"])
        save_session.assert_called_once_with(ADMIN)

    def test_navigate_attaches_screen_before_activate(self):
        record = {"updates": 0}
        page = SimpleNamespace(
            overlay=[], open=lambda d: None, close=lambda d: None,
            update=lambda: record.__setitem__("updates", record["updates"] + 1),
        )
        notifications = mock.Mock()
        notifications.unread_count.return_value = 0
        window = _MainWindow(page, {"notifications": notifications}, self.toasts)
        window._session = ADMIN
        window._build_shell()
        probe = {}
        window._make_screen = mock.Mock(
            side_effect=lambda key: SimpleNamespace(
                build=lambda: probe.__setitem__("at_build", record["updates"]) or ft.Text("x"),
                activate=lambda params=None: probe.__setitem__("at_activate", record["updates"]),
            )
        )
        window.navigate("dashboard")
        self.assertGreater(probe["at_activate"], probe["at_build"])


class GlobalSearchTests(UIFlowTestCase):
    def test_classify_isbn_digits_text(self):
        self.assertEqual(_classify_search("9780306406157"), "books")
        self.assertEqual(_classify_search("978-0-306-40615-7"), "books")
        self.assertEqual(_classify_search("9876543"), "transactions")
        self.assertEqual(_classify_search("Gatsby"), "text")
        self.assertEqual(_classify_search("Aarav Sharma"), "text")
        self.assertEqual(_classify_search("Class 10"), "text")

    def _window(self, book_hits=0, txn_hits=0):
        class FakeBooks:
            def search(self, term, category_id, page, page_size):
                return [], book_hits

        class FakeTxns:
            def list_transactions(self, **kw):
                return [], txn_hits

        toasts = FakeToasts()
        window = _MainWindow(
            self.page,
            {"books": FakeBooks(), "transactions": FakeTxns()},
            toasts,
        )
        window.navigate = mock.Mock()
        return window, toasts

    def test_isbn_routes_to_books(self):
        window, _ = self._window()
        window._global_search("9780306406157")
        window.navigate.assert_called_once_with("books", {"search": "9780306406157"})

    def test_digits_route_to_transactions(self):
        window, _ = self._window()
        window._global_search("9876543")
        window.navigate.assert_called_once_with("transactions", {"borrower": "9876543"})

    def test_text_with_book_hits_routes_to_books(self):
        window, _ = self._window(book_hits=2)
        window._global_search("Gatsby")
        window.navigate.assert_called_once_with("books", {"search": "Gatsby"})

    def test_text_without_book_hits_falls_back_to_transactions(self):
        window, toasts = self._window(book_hits=0, txn_hits=3)
        window._global_search("Aarav")
        window.navigate.assert_called_once_with("transactions", {"borrower": "Aarav"})
        self.assertTrue(any("No books matched" in m for m, _ in toasts.shown))

    def test_text_without_any_hits_stays_and_toasts(self):
        window, toasts = self._window(book_hits=0, txn_hits=0)
        window._global_search("Zzzzzz")
        window.navigate.assert_not_called()
        self.assertTrue(any("No books or transactions" in m for m, _ in toasts.shown))

    def test_books_activate_applies_search_param(self):
        books = FakeBookService()
        screen = BooksScreen(self.page, books, FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts())
        screen.build()
        screen.activate({"search": "Gatsby"})
        self.assertEqual(screen._term, "Gatsby")
        self.assertEqual(screen.filters.search.value, "Gatsby")
        self.assertEqual(books.calls[-1][0], "Gatsby")

    def test_transactions_activate_applies_borrower_param(self):
        class FakeTxn:
            def list_transactions(self, **kw):
                return [], 0

        screen = TransactionsScreen(self.page, FakeTxn(), FakeBookService(), ADMIN, FakeToasts())
        screen.build()
        screen.activate({"borrower": "9876543"})
        self.assertEqual(screen._borrower_term, "9876543")
        self.assertEqual(screen.borrower_search.value, "9876543")

    def test_books_clear_search_resets_state(self):
        books = FakeBookService()
        screen = BooksScreen(self.page, books, FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts())
        screen.build()
        screen.activate({"search": "Gatsby"})
        screen.clear_search()
        self.assertEqual(screen._term, "")
        self.assertEqual(screen.filters.search.value, "")
        self.assertEqual(screen._page_no, 1)

    def test_transactions_clear_search_resets_state(self):
        class FakeTxn:
            def list_transactions(self, **kw):
                return [], 0

        screen = TransactionsScreen(self.page, FakeTxn(), FakeBookService(), ADMIN, FakeToasts())
        screen.build()
        screen.activate({"borrower": "9876543"})
        screen.clear_search()
        self.assertEqual(screen._borrower_term, "")
        self.assertEqual(screen.borrower_search.value, "")

    def test_window_clear_resets_both_and_reloads_visible(self):
        window = _MainWindow(self.page, {}, FakeToasts())
        books, txns = mock.Mock(), mock.Mock()
        window._screens = {"books": books, "transactions": txns}
        window._current_key = "transactions"
        window._clear_global_search()
        books.clear_search.assert_called_once_with()
        txns.clear_search.assert_called_once_with()
        books.activate.assert_not_called()
        txns.activate.assert_called_once_with()

    def test_window_clear_reloads_nothing_off_tab(self):
        window = _MainWindow(self.page, {}, FakeToasts())
        books, txns = mock.Mock(), mock.Mock()
        window._screens = {"books": books, "transactions": txns}
        window._current_key = "dashboard"
        window._clear_global_search()
        books.clear_search.assert_called_once_with()
        txns.clear_search.assert_called_once_with()
        books.activate.assert_not_called()
        txns.activate.assert_not_called()


class ButtonBusyTests(unittest.TestCase):
    """No soft-update patch here: update() must be able to raise."""

    def test_set_busy_safe_on_detached_button(self):
        btn = Button("Go")
        btn.set_busy(True)
        btn.set_busy(False)


if __name__ == "__main__":
    unittest.main()