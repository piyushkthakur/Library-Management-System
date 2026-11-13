import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import flet as ft

from app.presentation.screens.books.books_screen import BooksScreen
from app.presentation.shared_components.cards import CardPanel, KpiCard, SettingCard, page_header
from app.presentation.shared_components.data_table import ColumnSpec, DataTable, TableRow
from app.presentation.shared_components.empty_state import EmptyState
from app.presentation.shared_components.pagination import PaginationBar
from app.presentation.shared_components.search_and_filters import FilterChips, SearchFilters
from app.presentation.theme import COLOR_PRIMARY


class ResponsiveSharedComponentsTests(unittest.TestCase):
    def setUp(self):
        update = patch("flet.controls.base_control.BaseControl.update")
        self.update = update.start()
        self.addCleanup(update.stop)

    def test_header_reflows_at_narrow_content_width_and_wraps_actions(self):
        actions = [ft.FilledButton("Import Books"), ft.FilledButton("Add Book")]
        header = page_header("Book Catalog", "Manage your library's collection", actions)
        layout = header.content
        self.assertIsInstance(layout, ft.ResponsiveRow)
        title, buttons = layout.controls
        self.assertEqual(title.col, {"xs": 12, "md": 6})
        self.assertEqual(buttons.col, {"xs": 12, "md": 6})
        self.assertGreater(layout.breakpoints[ft.ResponsiveRowBreakpoint.MD], 700)
        self.assertTrue(buttons.wrap)
        self.assertEqual(buttons.controls, actions)
        self.assertEqual(title.controls[0].size, 22)
        self.assertEqual(len(page_header("Dashboard").content.controls), 1)

    def test_kpi_label_flexes_without_scaling_text_or_icon(self):
        card = KpiCard("Active Transactions", ft.Icons.BOOKMARK_ADDED)
        label, icon = card.container.content.controls[0].controls
        self.assertTrue(label.expand)
        self.assertEqual(label.content.size, 14)
        self.assertEqual(icon.size, 20)
        card.set_value("12345")
        self.assertEqual(card.value.value, "12345")
        self.assertEqual(card.value.size, 28)

    def test_panel_header_wraps(self):
        panel = CardPanel("A long panel title", ft.TextButton("View all"), ft.Text("Body"))
        self.assertTrue(panel.container.content.controls[0].wrap)

    def test_settings_stack_and_preserve_body_and_save_callback(self):
        body = ft.Column([ft.TextField(value="14"), ft.TextField(value="5")])
        save = Mock(return_value=None)
        card = SettingCard("Circulation Rules", body, save)
        layout = card.container.content
        self.assertIsInstance(layout, ft.ResponsiveRow)
        self.assertEqual([c.col["xs"] for c in layout.controls], [12, 12, 12])
        self.assertEqual([c.col["lg"] for c in layout.controls], [3, 7, 2])
        self.assertIs(layout.controls[1].content, body)
        card._save()
        save.assert_called_once_with()
        self.assertFalse(card._save_btn.disabled)
        without_save = SettingCard("Read only", ft.Text("Value"))
        self.assertEqual(len(without_save.container.content.controls), 2)
        self.assertEqual(without_save.container.content.controls[1].col["lg"], 9)

    def test_setting_save_restores_button_after_error(self):
        card = SettingCard("Settings", ft.TextField(), Mock(side_effect=ValueError("invalid")))
        with self.assertRaises(ValueError):
            card._save()
        self.assertFalse(card._save_btn.disabled)

    def test_filters_wrap_and_keep_search_dropdown_clear_handlers(self):
        search, selected, clear = Mock(), Mock(), Mock()
        filters = SearchFilters("Search", search, [("Category", ["Fiction"], selected)], clear)
        self.assertTrue(filters.content.wrap)
        self.assertEqual(filters.search.width, 320)
        self.assertEqual(filters.search.text_size, 14)
        filters.search.value = "Book"
        filters.search.on_change(SimpleNamespace(control=filters.search))
        search.assert_called_once_with("Book")
        dropdown = filters._dropdowns[0]
        dropdown.value = "Fiction"
        dropdown.on_select(SimpleNamespace(control=dropdown))
        selected.assert_called_once_with("Fiction")
        filters.clear_all.on_click(None)
        self.assertEqual(filters.search.value, "")
        self.assertIsNone(dropdown.value)
        clear.assert_called_once_with()

    def test_filter_fields_default_dark_text(self):
        filters = SearchFilters("hint", Mock(), dropdowns=[("Category", [], None)])
        self.assertEqual(filters.search.color, "#000000")
        self.assertEqual(filters._dropdowns[0].color, "#000000")

    def test_chip_select_silent_mode_skips_callback(self):
        changed = Mock()
        chips = FilterChips([("all", "All"), ("available", "Available")], changed)
        chips.select("available", notify=False)
        changed.assert_not_called()
        self.assertEqual(chips.controls[1].bgcolor, COLOR_PRIMARY)
        chips.select("available")
        changed.assert_called_once_with("available")

    def test_form_dialog_stays_open_on_error_and_closes_on_success(self):
        from app.presentation.shared_components.dialogs import FormDialog

        page = Mock()
        dialog = FormDialog(page, "Test", [], lambda: "Fix this field.")
        dialog._submit()
        page.pop_dialog.assert_not_called()
        self.assertTrue(dialog._error.visible)
        self.assertEqual(dialog._error.value, "Fix this field.")
        dialog2 = FormDialog(page, "Test", [], lambda: None)
        dialog2._submit()
        page.pop_dialog.assert_called_once_with()

    def test_chips_wrap_and_keep_selection(self):
        changed = Mock()
        chips = FilterChips([("all", "All"), ("available", "Available")], changed)
        self.assertTrue(chips.wrap)
        chips.controls[1].on_click(None)
        self.assertEqual(chips.controls[1].bgcolor, COLOR_PRIMARY)
        changed.assert_called_once_with("available")
        chips.select(None)
        self.assertNotEqual(chips.controls[1].bgcolor, COLOR_PRIMARY)

    def test_pagination_wraps_without_changing_navigation(self):
        navigate, resize = Mock(), Mock()
        bar = PaginationBar(total=75, on_page=navigate, on_page_size=resize)
        self.assertTrue(bar.wrap)
        self.assertTrue(bar.prev.disabled)
        self.assertFalse(bar.next.disabled)
        bar.next.on_click(None)
        navigate.assert_called_once_with(2)
        bar.set_state(75, 3)
        self.assertEqual(bar.label.value, "Page 3 of 3")
        self.assertTrue(bar.next.disabled)
        bar.page_size_dropdown.value = "50"
        bar.page_size_dropdown.on_select(SimpleNamespace(control=bar.page_size_dropdown))
        resize.assert_called_once_with(50)
        bar.set_state(0, 1)
        self.assertTrue(bar.prev.disabled)
        self.assertTrue(bar.next.disabled)

    def test_table_has_shared_horizontal_viewport_and_bounded_vertical_body(self):
        table = DataTable([ColumnSpec("title", "Title", 600), ColumnSpec("author", "Author")])
        table.width = 700
        table.set_rows([TableRow({"title": ft.Text("A", size=14)}) for _ in range(100)])
        # ponytail: no outer scroll Row (unbounded width collapsed flex cells);
        # _table Column fills the Container directly so flex widths stay bounded.
        self.assertIs(table.content, table._table)
        self.assertEqual(
            table._table.horizontal_alignment, ft.CrossAxisAlignment.STRETCH
        )
        self.assertTrue(table._table.expand)
        self.assertTrue(table.expand)
        self.assertIsNone(table.height)
        self.assertTrue(table._body.expand)
        self.assertTrue(table._body.scroll.thumb_visibility)
        self.assertIs(table._table.controls[2], table._body)
        self.assertEqual(len(table._body.controls), 100)
        header_widths = [c.expand for c in table._header.content.controls]
        self.assertEqual(header_widths, [600, 160])
        for row in table._body.controls:
            self.assertEqual([c.expand for c in row.content.controls], header_widths)
            self.assertTrue(all(c.expand for c in row.content.controls))
            self.assertEqual(row.content.controls[0].content.size, 14)
            self.assertEqual(row.content.controls[1].content.value, "—")

    def test_table_actions_align_for_mixed_rows_and_disappear_when_unused(self):
        table = DataTable([ColumnSpec("name", "Name", 220)])
        actions = [ft.IconButton(ft.Icons.EDIT) for _ in range(3)]
        table.set_rows([TableRow({"name": ft.Text("A")}, actions=actions), TableRow({})])
        exps = [c.expand for c in table._header.content.controls]
        self.assertEqual(exps, [220, 168])
        self.assertTrue(table._table.expand)
        for row in table._body.controls:
            self.assertEqual([c.expand for c in row.content.controls], exps)
        self.assertEqual(table._body.controls[0].content.controls[-1].content.controls, actions)
        self.assertEqual(table._body.controls[1].content.controls[-1].content.controls, [])
        table.set_rows([TableRow({})])
        self.assertEqual(len(table._header.content.controls), 1)
        self.assertEqual(table._header.content.controls[0].expand, 220)

    def test_sort_updates_inner_header_without_replacing_scroll_viewport(self):
        sorted_callback = Mock()
        col = ColumnSpec("name", "Name", sortable=True)
        table = DataTable([col], sorted_callback)
        viewport = table.content
        table.set_rows([
            TableRow({"name": ft.Text("B")}, sort={"name": "b"}),
            TableRow({"name": ft.Text("A")}, sort={"name": "a"}),
        ])
        for expected, arrow in [(["A", "B"], "▲"), (["B", "A"], "▼")]:
            table._header.content.controls[0].on_click(None)
            self.assertIs(table.content, viewport)
            self.assertIs(table._table.controls[0], table._header)
            self.assertIn(arrow, table._header.content.controls[0].content.value)
            self.assertEqual([r.content.controls[0].content.value for r in table._body.controls], expected)
        self.assertEqual(sorted_callback.call_count, 2)
        sorted_callback.assert_called_with("name", "descend")

    def test_table_loading_and_empty_states_keep_scroll_structure(self):
        table = DataTable([ColumnSpec("name", "Name", 800)])
        viewport = table.content
        table.set_loading(True)
        self.assertNotIsInstance(table._body.controls[0], EmptyState)
        table.set_empty_message("Nothing matches")
        table.set_rows([])
        self.assertIsInstance(table._body.controls[0], EmptyState)
        self.assertIs(table.content, viewport)
        self.assertIs(table._table.controls[0], table._header)
        self.assertTrue(table._table.expand)

    def test_book_caller_with_import_service_keeps_filter_and_table_flow(self):
        books = Mock()
        books.search.return_value = ([], 0)
        categories = Mock()
        categories.list_all.return_value = []
        screen = BooksScreen(SimpleNamespace(), books, categories, Mock(), Mock(), Mock())
        screen.build()
        screen._on_chip("available")
        books.search.assert_called_once_with("", None, 1, 25)
        screen._on_search("Clean")
        self.assertEqual(screen._term, "Clean")
        self.assertIs(screen.table._table.controls[2], screen.table._body)


if __name__ == "__main__":
    unittest.main()
