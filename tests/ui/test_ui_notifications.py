import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import flet as ft

from app.core.security import SessionContext
from app.main import _MainWindow
from app.models.user import UserRole
from app.presentation.shared_components.toast import ToastHost


class NotificationUITests(unittest.TestCase):
    def setUp(self):
        self.page = SimpleNamespace(update=Mock(), show_dialog=Mock(), pop_dialog=Mock(), overlay=[])
        self.context = SessionContext(
            user_id=1, role=UserRole.ADMINISTRATOR, full_name="Ada", email="ada@lib.local"
        )
        self.service = Mock()
        self.service.list_notifications.return_value = []
        self.service.unread_count.return_value = 0
        self.toasts = ToastHost()
        self.window = _MainWindow(self.page, {"notifications": self.service}, self.toasts)
        self.window._session = self.context
        self.window._build_shell()
        self.screen = SimpleNamespace(build=lambda: ft.Text("Dashboard"), activate=Mock())
        self.window._make_screen = Mock(return_value=self.screen)

    def test_navigation_and_bell_refresh_notifications(self):
        self.window.navigate("dashboard")
        self.service.refresh.assert_called_once_with(self.context)
        self.window._show_notifications()
        self.assertEqual(self.service.refresh.call_count, 2)
        self.service.list_notifications.assert_called_with(self.context)
        self.page.show_dialog.assert_called_once()


if __name__ == "__main__":
    unittest.main()
