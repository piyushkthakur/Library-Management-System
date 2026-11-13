import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft

from app.core.security import SessionContext
from app.main import NAV
from app.models.user import UserRole
from app.presentation.screens.teachers.teacher_issues_screen import TeacherIssuesScreen
from app.presentation.screens.teachers.teachers_screen import TeachersScreen
from app.presentation.shared_components.toast import ToastHost


class TeacherScreensTests(unittest.TestCase):
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
        self.toasts = ToastHost()

    def test_nav_places_teacher_issues_below_transactions(self):
        keys = list(NAV.keys())
        self.assertEqual(keys.index("teacher_issues"), keys.index("transactions") + 1)

    def test_teacher_issues_builds_full_toolbar_and_table(self):
        screen = TeacherIssuesScreen(
            self.page, Mock(), Mock(), Mock(), self.context, self.toasts,
            on_manage_teachers=Mock(),
        )
        root = screen.build()
        self.assertIsNotNone(root.scroll)
        self.assertEqual(root.horizontal_alignment, ft.CrossAxisAlignment.STRETCH)
        self.assertEqual(
            [c.key for c in screen.table._columns],
            ["id", "book", "teacher", "contact", "issue", "due", "status"],
        )
        self.assertTrue(screen.table.expand)
        # header carries Issue + Manage Teachers actions
        header_row = root.controls[0].content
        self.assertEqual(len(header_row.controls[1].controls), 2)

    def test_teacher_dialog_survives_empty_values(self):
        # ponytail: cleared fields may report None — save must return a
        # message, never raise.
        import flet as ft

        screen = TeachersScreen(self.page, Mock(), self.context, self.toasts)
        dialog = screen._teacher_dialog("Add Teacher", None)

        def null_texts(control):
            if isinstance(control, ft.TextField):
                control.value = None
            for child in getattr(control, "controls", []) or []:
                null_texts(child)
            content = getattr(control, "content", None)
            if isinstance(content, ft.Control):
                null_texts(content)

        null_texts(dialog.dialog)
        dialog.dialog.actions[0].on_click(None)
        self.page.pop_dialog.assert_not_called()
        self.assertTrue(dialog._error.visible)

    def test_teachers_registry_builds_search_table_and_back(self):
        back = Mock()
        screen = TeachersScreen(self.page, Mock(), self.context, self.toasts, on_back=back)
        root = screen.build()
        self.assertIsNotNone(root.scroll)
        self.assertEqual(
            [c.key for c in screen.table._columns],
            ["name", "contact", "subject", "active"],
        )
        header_row = root.controls[0].content
        self.assertEqual(len(header_row.controls[1].controls), 2)
        header_row.controls[1].controls[0].on_click(None)
        back.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
