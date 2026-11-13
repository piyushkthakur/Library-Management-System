import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft

from app.core.security import SessionContext
from app.main import _MainWindow
from app.services.dashboard_service import (
    CategoryDistributionDto,
    DashboardDto,
    TrendPointDto,
)
from app.models.user import UserRole
from app.presentation.screens.auth.auth_screen import (
    AdminRegistrationScreen,
    ForgotPasswordScreen,
    LoginScreen,
    ResetPasswordScreen,
)
from app.presentation.screens.books.books_screen import BooksScreen
from app.presentation.screens.books.import_books_dialog import ImportBooksDialog
from app.presentation.screens.categories.categories_screen import CategoriesScreen
from app.presentation.screens.dashboard.dashboard_screen import DashboardScreen
from app.presentation.screens.librarians.librarians_screen import LibrariansScreen
from app.presentation.screens.my_activity.my_activity_screen import MyActivityScreen
from app.presentation.screens.reports.reports_screen import ReportsScreen
from app.presentation.screens.settings.settings_screen import SettingsScreen
from app.presentation.screens.transactions.transactions_screen import TransactionsScreen
from app.presentation.shared_components.chart_container import ChartContainer
from app.presentation.shared_components.shell import Header
from app.presentation.shared_components.toast import ToastHost


class ResponsiveShellScreenTests(unittest.TestCase):
    def setUp(self):
        update = patch("flet.controls.base_control.BaseControl.update")
        update.start()
        self.addCleanup(update.stop)
        self.page = SimpleNamespace(
            width=1360, height=600, overlay=[], update=Mock(),
            show_dialog=Mock(), pop_dialog=Mock(), run_task=Mock(),
        )
        self.context = SessionContext(
            user_id=1, role=UserRole.ADMINISTRATOR, full_name="Ada", email="ada@lib.local"
        )
        self.service = Mock()
        self.service.list_all.return_value = []
        self.service.list_librarians.return_value = ([], 0)
        self.service.unread_count.return_value = 0
        self.toasts = ToastHost()

    def window(self, width=1360):
        self.page.width = width
        window = _MainWindow(self.page, {"notifications": self.service}, self.toasts)
        window._session = self.context
        window._build_shell()
        return window

    def resize(self, width):
        self.page.width = width
        self.page.on_resize(SimpleNamespace(width=width, height=600))

    def test_sidebar_auto_collapse_restore_and_manual_override(self):
        window = self.window()
        sidebar = window.sidebar
        self.assertEqual(sidebar.width, 240)
        self.resize(1099)
        self.assertEqual(sidebar.width, 64)
        self.assertFalse(sidebar._brand_row.controls[1].visible)
        for item in sidebar._items.values():
            self.assertTrue(item.content.controls[0].visible)
            self.assertTrue(all(not c.visible for c in item.content.controls[1:]))
        sidebar._toggle_btn.on_click(None)
        self.assertEqual(sidebar.width, 240)
        self.resize(800)
        self.assertEqual(sidebar.width, 240)
        self.resize(1100)
        self.assertEqual(sidebar.width, 240)
        sidebar._toggle_btn.on_click(None)
        self.assertEqual(sidebar.width, 64)
        self.resize(800)
        self.resize(1360)
        self.assertEqual(sidebar.width, 64)
        sidebar._toggle_btn.on_click(None)
        self.assertEqual(sidebar.width, 240)
        self.assertTrue(sidebar._brand_row.controls[1].visible)

    def test_initial_narrow_shell_and_resizing_do_not_rebuild_screen(self):
        window = self.window(800)
        self.assertEqual(window.sidebar.width, 64)
        self.assertFalse(window.header._search.visible)
        self.assertEqual(window._content.padding.left, 16)
        screen = SimpleNamespace(build=Mock(return_value=ft.TextField(value="draft")), activate=Mock())
        window._make_screen = Mock(return_value=screen)
        window.navigate("dashboard")
        content = window._content.content
        self.resize(1360)
        self.assertEqual(window.sidebar.width, 240)
        self.assertEqual(window._content.padding.left, 32)
        self.assertIs(window._content.content, content)
        self.assertEqual(content.value, "draft")
        screen.build.assert_called_once()
        self.assertEqual(self.service.refresh.call_count, 1)
        window._session = None
        self.resize(800)
        self.assertEqual(window.sidebar.width, 240)

    def test_header_search_sizes_and_only_avatar_opens_account(self):
        search, notifications = Mock(), Mock()
        header = Header(self.page, on_global_search=search, on_notifications=notifications)
        row = header.content.content
        avatar = row.controls[-1]
        self.assertIsNone(header.on_click)
        self.assertIsNone(header.content.on_click)
        for width, visible, search_width in [(1120, True, 360), (900, True, 220), (560, False, 200)]:
            header.resize(width)
            self.assertEqual(header._search.visible, visible)
            self.assertEqual(header._search.width, search_width)
            self.assertTrue(header.bell.visible)
            self.assertTrue(avatar.visible)
            self.assertTrue(row.controls[0].expand)
        header.bell.on_click(None)
        notifications.assert_called_once_with()
        self.assertFalse(header.dropdown.visible)
        header._search.value = "Ada"
        header._search.on_submit(SimpleNamespace(control=header._search))
        search.assert_called_once_with("Ada")
        self.assertFalse(header.dropdown.visible)
        avatar.on_click(None)
        self.assertTrue(header.dropdown.visible)
        avatar.on_click(None)
        self.assertFalse(header.dropdown.visible)

    def test_toast_width_wrap_dismiss_and_navigation(self):
        window = self.window(800)
        for width in (1120, 736, 280):
            self.toasts.resize(width)
            self.assertLessEqual(self.toasts.stack.width + 32, width)
            self.assertLessEqual(self.toasts.stack.width, 360)
        self.assertGreaterEqual(self.toasts.stack.top, 64)
        for _ in range(4):
            self.toasts.show("A long notification message " * 20)
        self.assertEqual(len(self.toasts.stack.controls), 3)
        card = self.toasts.stack.controls[0]
        self.assertTrue(card.content.controls[1].expand)
        card.content.controls[-1].on_click(None)
        self.assertEqual(len(self.toasts.stack.controls), 2)
        window._make_screen = Mock(return_value=SimpleNamespace(build=lambda: ft.Text("x"), activate=Mock()))
        window.navigate("dashboard")
        self.assertFalse(self.toasts.stack.visible)

    def test_dashboard_native_grid_and_full_width_overdue(self):
        screen = DashboardScreen(self.page, self.service, self.context, self.toasts, Mock())
        root = screen.build()
        # ponytail: the shell provides the solid background; the screen
        # itself is a plain Column of cards.
        self.assertIsInstance(root, ft.Column)
        content = root
        kpis, charts, overdue = content.controls[1:]
        self.assertIsInstance(kpis, ft.ResponsiveRow)
        self.assertTrue(all(c.col == {"xs": 12, "sm": 6, "lg": 3} for c in kpis.controls))
        self.assertIsInstance(charts, ft.ResponsiveRow)
        self.assertTrue(all(c.col == {"xs": 12, "lg": 6} for c in charts.controls))
        self.assertFalse(charts.expand)
        self.assertFalse(overdue.expand)
        self.assertIsNone(overdue.width)
        self.assertEqual(content.horizontal_alignment, ft.CrossAxisAlignment.STRETCH)
        self.assertIsNone(screen._overdue_list.scroll)
        self.assertIsNotNone(content.scroll)
        for width, expected in [(528, 1), (704, 2), (1056, 4)]:
            active = [key.value for key, minimum in kpis.breakpoints.items() if width >= minimum]
            col = next(kpis.controls[0].col[key] for key in reversed(active) if key in kpis.controls[0].col)
            self.assertEqual(12 // col, expected)

    def test_screen_toolbars_and_tables_remain_reachable(self):
        screens = [
            BooksScreen(self.page, self.service, self.service, self.service, self.context, self.toasts),
            CategoriesScreen(self.page, self.service, self.context, self.toasts),
            LibrariansScreen(self.page, self.service, self.context, self.toasts),
            TransactionsScreen(self.page, self.service, self.service, self.context, self.toasts),
            MyActivityScreen(self.page, self.service, self.context, self.toasts),
        ]
        for screen in screens:
            with self.subTest(screen=type(screen).__name__):
                root = screen.build()
                self.assertIsNotNone(root.scroll)
                self.assertEqual(root.horizontal_alignment, ft.CrossAxisAlignment.STRETCH)
                self.assertTrue(screen.table.expand)
                # ponytail: no fixed height — table expands to near the
                # bottom of the screen instead of stopping at 320px.
                self.assertIsNone(screen.table.height)
                if isinstance(screen, (TransactionsScreen, MyActivityScreen)):
                    toolbar = root.controls[2]
                    self.assertTrue(toolbar.wrap)
                    self.assertEqual(screen.from_date.container.width, 180)
                    self.assertEqual(screen.to_date.container.width, 180)
                    screen.from_date.date = "preserved"
                    screen._load = Mock()
                    toolbar.controls[-1].on_click(None)
                    screen._load.assert_called_once_with()
                    self.assertEqual(screen.from_date.date, "preserved")

    def test_reports_stack_parameters_preview_and_wrap_exports(self):
        screen = ReportsScreen(self.page, self.service, self.service, self.service, self.context, self.toasts)
        root = screen.build()
        layout = root.controls[1]
        self.assertIsInstance(layout, ft.ResponsiveRow)
        params, preview = layout.controls
        self.assertEqual(params.col, {"xs": 12, "lg": 4})
        self.assertEqual(preview.col, {"xs": 12, "lg": 8})
        self.assertIsNone(params.width)
        self.assertTrue(params.content.controls[-1].wrap)
        self.assertIsInstance(preview.controls[0], ft.ResponsiveRow)
        self.assertTrue(preview.controls[1].wrap)
        # ponytail: DataTable always expands to fill the frame; the old
        # per-screen `table.expand = False` override was removed.
        self.assertTrue(screen.table.expand)
        self.assertIsNotNone(root.scroll)

    def test_settings_and_auth_scroll_and_reflow(self):
        settings = SettingsScreen(self.page, self.service, self.context, self.toasts)
        self.assertIsNotNone(settings.build().scroll)
        # ponytail: toggle renders as a plain Row + Switch; the old
        # wrap=True hack was removed.
        self.assertIsInstance(settings.fine_enabled, ft.Row)
        self.assertIsInstance(settings.fine_enabled.data, ft.Switch)
        screens = [
            LoginScreen(self.page, self.service, Mock(), Mock(), Mock()),
            AdminRegistrationScreen(self.page, self.service, Mock()),
            ForgotPasswordScreen(self.page, self.service, Mock(), Mock()),
            ResetPasswordScreen(self.page, self.service, "ada@lib.local", Mock(), Mock()),
        ]
        for screen in screens:
            root = screen.build().content
            # ponytail: panels share the full window height (stretched row,
            # no scroll), so both always match.
            self.assertIsNone(root.scroll)
            self.assertTrue(root.expand)
            layout = root.controls[0]
            self.assertIsInstance(layout, ft.ResponsiveRow)
            self.assertTrue(layout.expand)
            self.assertEqual(
                layout.vertical_alignment, ft.CrossAxisAlignment.STRETCH
            )
            self.assertTrue(all(c.col == {"xs": 12, "sm": 6} for c in layout.controls))
            form = layout.controls[1].content
            self.assertEqual(form.horizontal_alignment, ft.CrossAxisAlignment.CENTER)
            self.assertLessEqual(form.controls[-1].width, 400)
        # tiny browser window: scroll mode on, expand off (never combined)
        self.page.width = 500
        self.page.on_resize(None)
        self.assertIsNotNone(root.scroll)
        self.assertFalse(layout.expand)
        self.page.width = 1360
        self.page.on_resize(None)
        self.assertIsNone(root.scroll)
        self.assertTrue(layout.expand)

    def test_large_dialogs_fit_minimum_window_and_scroll(self):
        preview = ImportBooksDialog(self.page, self.service, self.context, Mock(), self.toasts)
        preview._build_dialog()
        dialog = preview._dialog
        self.assertEqual(dialog.alignment, ft.Alignment.CENTER)
        self.assertTrue(dialog.scrollable)
        self.assertLessEqual(dialog.content.width + 48 + 80, 800)
        self.assertLessEqual(dialog.content.height, 360)
        screen = DashboardScreen(self.page, self.service, self.context, self.toasts, Mock())
        screen._category_data = [("Fiction", 5), ("Reference", 1)]
        screen._open_category_chart()
        dialog = self.page.show_dialog.call_args.args[0]
        self.assertTrue(dialog.scrollable)
        self.assertLessEqual(dialog.content.width + 48 + 80, 800)
        self.assertLessEqual(dialog.content.height, 360)

    def test_dashboard_activate_renders_charts_synchronously(self):
        dto = DashboardDto(
            total_books=10, total_available_copies=9, active_transactions=1,
            overdue_transactions=0,
            trend=(TrendPointDto(date=date(2026, 9, 1), issued=2, returned=1),),
            category_distribution=(CategoryDistributionDto("Fiction", 5),),
            overdue_items=(),
        )
        service = Mock()
        service.get_dashboard.return_value = dto
        screen = DashboardScreen(self.page, service, self.context, self.toasts, Mock())
        screen.build()
        screen.activate()
        # ponytail: in-process Agg renders land in the same pass — no task.
        self.page.run_task.assert_not_called()
        for chart in (screen.trend_chart, screen.category_chart):
            self.assertTrue(chart._image.visible)
            self.assertTrue(chart._image.src.startswith(b"\x89PNG"))

    def test_chart_has_bounded_body_without_vertical_flex(self):
        chart = ChartContainer("Trend", height=280, width=480)
        self.assertEqual(chart.width, 480)
        self.assertEqual(chart._body.height, 280)
        self.assertFalse(chart._body.expand)
        self.assertTrue(chart.content.tight)
        self.assertEqual(chart._image.fit, ft.BoxFit.CONTAIN)
        figure = Mock()
        figure.to_image.return_value = b"png"
        chart.render(figure)
        figure.to_image.assert_called_once_with(format="png", scale=2, width=480, height=280)


if __name__ == "__main__":
    unittest.main()
