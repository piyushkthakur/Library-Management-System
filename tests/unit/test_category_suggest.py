"""Category suggestion stages — candidates, title rules, keyed AI fallback.

Every test is hermetic: the AI stage only fires with OPENROUTER_API_KEY
set, and the no-key cases assert urlopen is never touched.
"""

import json
import os
import unittest
from unittest.mock import patch

from app.services.category_suggest import _clean_category, suggest_category
from app.services.isbn_lookup import IsbnLookupResult

_OFFLINE = {"OPENROUTER_API_KEY": ""}


def _result(title="Some Book", author="A. Author", categories=()):
    return IsbnLookupResult(title=title, author=author, categories=categories)


def _resp(payload):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return _Resp()


class CandidateStageTest(unittest.TestCase):
    def test_candidates_win_over_title_rules(self):
        result = _result(title="The Joy of Cooking", categories=("Modern fiction",))
        with patch.dict(os.environ, _OFFLINE):
            self.assertEqual(suggest_category(result), "Modern Fiction")

    def test_long_or_numeric_candidate_falls_through_to_rules(self):
        result = _result(
            title="The History of Modern India",
            categories=("A very long academic subject descriptor here", "978 subjects"),
        )
        with patch.dict(os.environ, _OFFLINE):
            self.assertEqual(suggest_category(result), "History")

    def test_comma_candidate_uses_first_sane_segment(self):
        with patch.dict(os.environ, _OFFLINE):
            self.assertEqual(
                suggest_category(_result(categories=("Pakistan, history",))), "Pakistan"
            )

    def test_stopword_only_candidate_is_skipped(self):
        with patch.dict(os.environ, _OFFLINE):
            self.assertIsNone(
                suggest_category(_result(title="Wings of Fire", categories=("The",)))
            )


class TitleRulesTest(unittest.TestCase):
    def test_clear_titles_map_to_their_category(self):
        with patch.dict(os.environ, _OFFLINE):
            self.assertEqual(
                suggest_category(_result(title="Clean Code: A Handbook of Agile Software Development")),
                "Technology",
            )
            self.assertEqual(suggest_category(_result(title="The Joy of Cooking")), "Cooking")
            self.assertEqual(
                suggest_category(_result(title="A Short History of Nearly Everything")),
                "History",
            )

    def test_ambiguous_titles_make_no_guess_without_ai(self):
        with patch.dict(os.environ, _OFFLINE):
            for title in (
                "Wings of Fire",
                "Tinderbox: India and the Problem Within",
                "The Double Helix",
            ):
                self.assertIsNone(suggest_category(_result(title=title)))

    def test_rules_run_before_ai_even_with_key(self):
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}), patch(
            "app.services.category_suggest.urllib.request.urlopen"
        ) as mock_open:
            self.assertEqual(suggest_category(_result(title="Cookbook Recipes")), "Cooking")
            mock_open.assert_not_called()


class AiStageTest(unittest.TestCase):
    @patch("app.services.category_suggest.urllib.request.urlopen")
    def test_keyed_ai_parses_fenced_json(self, mock_open):
        mock_open.return_value = _resp(
            {
                "choices": [
                    {"message": {"content": '```json\n{"category": "political science"}\n```'}}
                ]
            }
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            proposal = suggest_category(_result(title="Tinderbox", author="M. J. Akbar"))
        self.assertEqual(proposal, "Political science")
        request = mock_open.call_args[0][0]
        self.assertIn("Bearer sk-test", request.get_header("Authorization"))

    @patch("app.services.category_suggest.urllib.request.urlopen")
    def test_no_key_never_touches_the_network(self, mock_open):
        with patch.dict(os.environ, _OFFLINE):
            self.assertIsNone(suggest_category(_result(title="Tinderbox")))
        mock_open.assert_not_called()

    @patch("app.services.category_suggest.urllib.request.urlopen")
    def test_garbage_ai_output_is_rejected(self, mock_open):
        mock_open.return_value = _resp(
            {"choices": [{"message": {"content": "Hard to say, maybe post-colonial lit?"}}]}
        )
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            self.assertIsNone(suggest_category(_result(title="Tinderbox")))


class CleanCategoryTest(unittest.TestCase):
    def test_plain_text_is_titlecased(self):
        self.assertEqual(_clean_category("  history "), "History")

    def test_too_many_words_or_too_short_rejected(self):
        self.assertIsNone(_clean_category("one two three four"))
        self.assertIsNone(_clean_category("ok"))

    def test_bad_characters_rejected(self):
        self.assertIsNone(_clean_category("Sci/Fi"))
        self.assertIsNone(_clean_category('{"category": ""}'))


if __name__ == "__main__":
    unittest.main()
