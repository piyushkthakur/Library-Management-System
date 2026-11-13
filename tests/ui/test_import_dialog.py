"""Paged + filtered import preview dialog tests (no GUI; control updates
are softened like the other UI flow tests)."""

import unittest
from types import SimpleNamespace

from app.presentation.screens.books.import_books_dialog import ImportBooksDialog
from app.services.import_service import ImportPreviewDto, ImportRowDto


def make_row(i, status="valid"):
    return ImportRowDto(
        row_number=i,
        title=f"Title {i}",
        author="Author",
        isbn=f"978000000{i:04d}",
        category_name="Fiction",
        total_copies=1,
        shelf_location=None,
        status=status,
        error_message="" if status == "valid" else "Bad row",
    )


def make_preview(n=250):
    rows = tuple(
        make_row(
            i + 1,
            "error" if i % 10 == 9 else ("merged" if i % 10 == 8 else "valid"),
        )
        for i in range(n)
    )
    return ImportPreviewDto(
        rows=rows,
        valid_count=sum(1 for r in rows if r.status == "valid"),
        merged_count=sum(1 for r in rows if r.status == "merged"),
        error_count=sum(1 for r in rows if r.status == "error"),
    )


class ImportPreviewTests(unittest.TestCase):
    def setUp(self):
        import flet.controls.base_control as base

        orig = base.BaseControl.update

        def _soft_update(self, *args, **kwargs):
            try:
                orig(self, *args, **kwargs)
            except RuntimeError:
                pass

        base.BaseControl.update = _soft_update
        self.addCleanup(lambda: setattr(base.BaseControl, "update", orig))
        self.page = SimpleNamespace(
            pop_dialog=lambda: None,
            show_dialog=lambda d: None,
            update=lambda: None,
        )

    def _dialog(self, n=250):
        dialog = ImportBooksDialog(
            self.page, None, None, lambda: None, SimpleNamespace(show=lambda *a: None)
        )
        dialog._preview = make_preview(n)
        dialog._filter = "all"
        dialog._page_no = 1
        dialog._show_preview()
        return dialog

    def test_first_page_renders_page_size_rows(self):
        dialog = self._dialog()
        self.assertEqual(len(dialog._table._body.controls), 100)
        self.assertEqual(dialog.pagination._total, 250)

    def test_second_page_shows_next_slice(self):
        dialog = self._dialog()
        dialog._on_page(2)
        cells = dialog._table._body.controls[0].content.controls[0].content.value
        self.assertEqual(cells, "101")

    def test_error_filter_shows_only_errors(self):
        dialog = self._dialog()
        dialog._on_filter("error")
        self.assertEqual(dialog.pagination._total, 25)
        self.assertEqual(len(dialog._table._body.controls), 25)

    def test_page_size_change_reflows(self):
        dialog = self._dialog()
        dialog._on_size(25)
        self.assertEqual(len(dialog._table._body.controls), 25)
        self.assertEqual(dialog.pagination._total, 250)

    def test_filter_resets_to_first_page(self):
        dialog = self._dialog()
        dialog._on_page(3)
        dialog._on_filter("merged")
        self.assertEqual(dialog._page_no, 1)
        self.assertEqual(dialog.pagination._total, 25)

    def test_merged_filter_shows_only_merged(self):
        dialog = self._dialog()
        dialog._on_filter("merged")
        self.assertEqual(dialog.pagination._total, 25)


if __name__ == "__main__":
    unittest.main()
