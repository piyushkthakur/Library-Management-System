"""UI test: Add Book ISBN autofill drives the async handler with a mocked lookup."""

import unittest
from types import SimpleNamespace
from unittest import mock

from app.presentation.screens.books.books_screen import BooksScreen
from app.presentation.shared_components.toast import ToastHost
from tests.ui.test_ui_flows import ADMIN, FakeBookService, FakeCategoryService, FakeToasts, _fire


class AddBookIsbnAutofillTestsFT(unittest.TestCase):
    def setUp(self):
        self.page = SimpleNamespace(
            overlay=[],
            open=lambda d: None,
            close=lambda d: None,
            update=lambda: None,
            show_dialog=lambda d: None,
            pop_dialog=lambda: None,
        )
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

    def test_valid_isbn_autofills_title_author_and_sets_one_copy(self):
        from app.services.isbn_lookup import IsbnLookupResult

        books = FakeBookService()
        screen = BooksScreen(self.page, books, FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts())
        screen.build()
        screen._category_names = ["Fiction", "Uncategorized"]
        dialog = screen._book_dialog("Add Book", None)
        fields = list(dialog.dialog.content.controls[0].controls)
        isbn_field = fields[0].content.controls[1]
        title_field = fields[1].content.controls[1]
        author_field = fields[2].content.controls[1]
        category_field = fields[3].content.controls[1]
        copies_field = fields[4].content.controls[1]
        result = IsbnLookupResult(
            title="The Great Gatsby", author="F. Scott Fitzgerald", categories=("Fiction",)
        )
        title_field.value = "My Own Title"
        author_field.value = "My Own Author"
        with mock.patch(
            "app.presentation.screens.books.books_screen.lookup_isbn",
            return_value=result,
        ):
            _fire(isbn_field.on_change(SimpleNamespace(control=SimpleNamespace(value="9780743273565"))))
        self.assertEqual(title_field.value, "My Own Title")
        self.assertEqual(author_field.value, "My Own Author")
        self.assertEqual(copies_field.value, "1")
        self.assertEqual(category_field.value, "Fiction")

    def test_unmatched_category_is_left_for_the_user(self):
        # No confident match -> dropdown stays empty (never silently
        # "Uncategorized"); save() already forces an explicit choice.
        from app.services.isbn_lookup import IsbnLookupResult

        books = FakeBookService()
        screen = BooksScreen(self.page, books, FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts())
        screen.build()
        screen._category_names = ["Fiction", "Uncategorized"]
        dialog = screen._book_dialog("Add Book", None)
        fields = list(dialog.dialog.content.controls[0].controls)
        isbn_field = fields[0].content.controls[1]
        category_field = fields[3].content.controls[1]
        result = IsbnLookupResult(title="Some Title", author="Some Author", categories=("Pakistan",))
        with mock.patch(
            "app.presentation.screens.books.books_screen.lookup_isbn",
            return_value=result,
        ):
            _fire(isbn_field.on_change(SimpleNamespace(control=SimpleNamespace(value="9780743273565"))))
        self.assertIsNone(category_field.value)

    def test_unmatched_lookup_offers_create_chip_then_creates(self):
        from app.services.isbn_lookup import IsbnLookupResult

        cats = FakeCategoryService(items=["Fiction", "Uncategorized"])
        books = FakeBookService()
        screen = BooksScreen(self.page, books, cats, mock.Mock(), ADMIN, FakeToasts())
        screen.build()
        dialog = screen._book_dialog("Add Book", None)
        fields = list(dialog.dialog.content.controls[0].controls)
        isbn_field = fields[0].content.controls[1]
        category_field = fields[3].content.controls[1]
        chips = fields[3].content.controls[4]  # label, dropdown, error, helper, chips
        result = IsbnLookupResult(title="Tinderbox", author="M. J. Akbar", categories=("Pakistan",))
        with mock.patch(
            "app.presentation.screens.books.books_screen.lookup_isbn",
            return_value=result,
        ):
            _fire(isbn_field.on_change(SimpleNamespace(control=SimpleNamespace(value="9780743273565"))))
        # nothing written yet: the proposal is a chip, not a selection
        self.assertIsNone(category_field.value)
        proposal = next(c for c in chips.controls if 'Create "Pakistan"' in c.content.value)
        proposal.on_click(None)
        self.assertEqual(cats.created, ["Pakistan"])
        self.assertIn("Pakistan", screen._category_names)
        self.assertEqual(category_field.value, "Pakistan")
        self.assertIn("Pakistan", [o.key for o in category_field.options])  # selectable now
        self.assertNotIn(proposal, chips.controls)  # consumed after creation

    def test_manual_new_category_chip_opens_prompt(self):
        shown = []
        self.page.show_dialog = lambda d: shown.append(d)
        cats = FakeCategoryService()
        screen = BooksScreen(
            self.page, FakeBookService(), cats, mock.Mock(), ADMIN, FakeToasts()
        )
        screen.build()
        dialog = screen._book_dialog("Add Book", None)
        fields = list(dialog.dialog.content.controls[0].controls)
        category_field = fields[3].content.controls[1]
        chips = fields[3].content.controls[4]
        manual = next(c for c in chips.controls if "New category" in c.content.value)
        manual.on_click(None)
        self.assertEqual(len(shown), 1)

        # type a name into the prompt and save it: the category must land in
        # the still-open Add Book dropdown instantly, already selected.
        prompt = shown[0]  # ft.AlertDialog from the nested FormDialog
        name_input = prompt.content.controls[0].controls[0].content.controls[1]
        name_input.value = "Cookbooks"
        prompt.actions[0].on_click(None)  # Save
        self.assertEqual(cats.created, ["Cookbooks"])
        self.assertIn("Cookbooks", [o.key for o in category_field.options])
        self.assertEqual(category_field.value, "Cookbooks")

    def test_clear_resets_controls_and_tracked_values(self):
        from app.services.isbn_lookup import IsbnLookupResult

        screen = BooksScreen(
            self.page, FakeBookService(), FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts()
        )
        screen.build()
        screen._category_names = ["Fiction"]
        dialog = screen._book_dialog("Add Book", None)
        fields = list(dialog.dialog.content.controls[0].controls)
        isbn_field = fields[0].content.controls[1]
        title_field = fields[1].content.controls[1]
        author_field = fields[2].content.controls[1]
        category_field = fields[3].content.controls[1]
        copies_field = fields[4].content.controls[1]
        shelf_field = fields[5].content.controls[1]
        chips = fields[3].content.controls[4]

        # fill everything, including an unmatched-lookup proposal chip
        for control, value in (
            (title_field, "The Great Gatsby"),
            (author_field, "F. Scott Fitzgerald"),
            (shelf_field, "A-12"),
        ):
            control.value = value
            control.on_change(SimpleNamespace(control=SimpleNamespace(value=value)))
        copies_field.value = "5"
        result = IsbnLookupResult(title="Tinderbox", author="M. J. Akbar", categories=("Pakistan",))
        with mock.patch(
            "app.presentation.screens.books.books_screen.lookup_isbn",
            return_value=result,
        ):
            _fire(isbn_field.on_change(SimpleNamespace(control=SimpleNamespace(value="9780743273565"))))
        category_field.value = "Fiction"  # user picks; proposal stays as a chip
        self.assertTrue(len(chips.controls) > 1)  # manual + proposal

        clear = dialog.dialog.actions[0]
        self.assertEqual(clear.content.value, "Clear")
        clear.on_click(None)

        self.assertEqual(isbn_field.value, "")
        self.assertEqual(title_field.value, "")
        self.assertEqual(author_field.value, "")
        self.assertIsNone(category_field.value)
        self.assertEqual(copies_field.value, "1")
        self.assertEqual(shelf_field.value, "")
        self.assertEqual(len(chips.controls), 1)  # proposal consumed, manual stays
        # _tracked was reset too, not just the visible controls
        self.assertEqual(dialog._on_save(), "Title is required.")

    def test_edit_dialog_has_no_clear_button(self):
        book = SimpleNamespace(
            title="T",
            author="A",
            isbn="9780743273565",
            shelf_location=None,
            category_name="Fiction",
            total_copies=1,
        )
        screen = BooksScreen(
            self.page, FakeBookService(), FakeCategoryService(), mock.Mock(), ADMIN, FakeToasts()
        )
        screen.build()
        dialog = screen._book_dialog("Edit Book", book)
        labels = [a.content.value for a in dialog.dialog.actions]
        self.assertNotIn("Clear", labels)
