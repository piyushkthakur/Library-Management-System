"""ISBN lookup tests — every source's parsing plus the offline-safe
'always None on failure' contract the Add Book autofill relies on."""

import json
import unittest
from unittest.mock import patch

from app.services.isbn_lookup import (
    IsbnLookupResult,
    _isbn10_to_isbn13,
    lookup_isbn,
    match_category,
)

ISBN = "9780306406157"

OL_PAYLOAD = {
    "ISBN:" + ISBN: {
        "title": "Numerical Recipes",
        "authors": [{"name": "William H. Press"}, {"name": "Brian P. Flannery"}],
        "subjects": [{"name": "Science"}, {"name": "Physics"}],
    }
}

OL_SEARCH_PAYLOAD = {
    "docs": [
        {
            "title": "Search Result",
            "author_name": ["Search Author"],
            "subject": ["Search Category"],
        }
    ]
}

GOOGLE_PAYLOAD = {
    "items": [
        {
            "volumeInfo": {
                "title": "Google Title",
                "authors": ["Some Author"],
                "categories": ["Fiction"],
            }
        }
    ]
}

GOV_ISBN = "9789378041198"
GOV_ROW = {
    "Index1": 1,
    "title": "Wings of Fire",
    "isbn_number": "978-93-7804-119-8",
    "Author": "A. P. J. Abdul Kalam",
    "publisher": "Scholastic India",
}
GOV_PAYLOAD = {"recordsTotal": 1, "recordsFiltered": 1, "data": json.dumps([GOV_ROW])}
GOV_EMPTY_PAYLOAD = {"recordsTotal": 0, "recordsFiltered": 0, "data": "[]"}


def _mock(payload):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return _Resp()


# Open Library miss, Open Library search miss, Google Books miss — the three
# responses every source chain burns before the gov portal fallback fires.
_MISSES = [_mock({}), _mock({}), _mock({"totalItems": 0, "items": []})]


class IsbnLookupTest(unittest.TestCase):
    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_openlibrary_hit_stops_the_chain(self, mock_urlopen):
        mock_urlopen.return_value = _mock(OL_PAYLOAD)
        result = lookup_isbn(ISBN)
        self.assertEqual(
            result,
            IsbnLookupResult(
                title="Numerical Recipes",
                author="William H. Press, Brian P. Flannery",
                categories=("Science", "Physics"),
            ),
        )
        self.assertEqual(mock_urlopen.call_count, 1)
        self.assertIn("openlibrary.org/api/books", mock_urlopen.call_args[0][0])

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_openlibrary_search_falls_back(self, mock_urlopen):
        mock_urlopen.return_value = _mock(OL_SEARCH_PAYLOAD)
        result = lookup_isbn(ISBN)
        self.assertEqual(
            result,
            IsbnLookupResult(title="Search Result", author="Search Author", categories=("Search Category",)),
        )
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertIn("openlibrary.org/search.json", mock_urlopen.call_args_list[1][0][0])

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_openlibrary_miss_falls_back_to_google(self, mock_urlopen):
        mock_urlopen.side_effect = [_mock({}), _mock({}), _mock(GOOGLE_PAYLOAD)]
        result = lookup_isbn(ISBN)
        self.assertEqual(
            result,
            IsbnLookupResult(title="Google Title", author="Some Author", categories=("Fiction",)),
        )
        self.assertEqual(mock_urlopen.call_count, 3)
        self.assertIn("googleapis.com", mock_urlopen.call_args_list[2][0][0])

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_google_bisac_categories_split_on_slash(self, mock_urlopen):
        payload = {
            "items": [
                {
                    "volumeInfo": {
                        "title": "Google Title",
                        "authors": ["Some Author"],
                        "categories": ["Fiction / Literary", "Literature"],
                    }
                }
            ]
        }
        mock_urlopen.side_effect = [_mock({}), _mock({}), _mock(payload)]
        self.assertEqual(lookup_isbn(ISBN).categories, ("Fiction", "Literary", "Literature"))

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_openlibrary_error_falls_back_to_google(self, mock_urlopen):
        mock_urlopen.side_effect = [OSError("offline"), OSError("offline"), _mock(GOOGLE_PAYLOAD)]
        self.assertEqual(lookup_isbn(ISBN).title, "Google Title")

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_openlibrary_hit_without_authors_falls_back(self, mock_urlopen):
        payload = {"ISBN:" + ISBN: {"title": "No Author Book"}}
        mock_urlopen.side_effect = [_mock(payload), _mock({}), _mock(GOOGLE_PAYLOAD)]
        self.assertEqual(lookup_isbn(ISBN).title, "Google Title")

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_unknown_isbn_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = [
            _mock({}),
            _mock({}),
            _mock({"totalItems": 0, "items": []}),
        ]
        self.assertIsNone(lookup_isbn(ISBN))

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_everything_failing_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("no internet")
        self.assertIsNone(lookup_isbn(ISBN))


class IsbnGovInFallbackTest(unittest.TestCase):
    """The last-resort source: the Indian national ISBN agency portal."""

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_google_miss_falls_back_to_isbn_gov_in(self, mock_urlopen):
        mock_urlopen.side_effect = [*_MISSES, _mock(GOV_PAYLOAD)]
        result = lookup_isbn(GOV_ISBN)
        self.assertEqual(
            result,
            IsbnLookupResult(title="Wings of Fire", author="A. P. J. Abdul Kalam"),
        )
        self.assertEqual(mock_urlopen.call_count, 4)
        self.assertIn("isbn.gov.in", mock_urlopen.call_args_list[3][0][0].full_url)

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_gov_in_searches_the_isbn13_without_dashes(self, mock_urlopen):
        mock_urlopen.side_effect = [*_MISSES, _mock(GOV_EMPTY_PAYLOAD)]
        self.assertIsNone(lookup_isbn(GOV_ISBN))
        request = mock_urlopen.call_args_list[3][0][0]
        self.assertEqual(request.get_header("Content-type"), "application/json; charset=utf-8")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["_obj"]["Type"], "isbn_number_Nodash")
        self.assertEqual(body["_obj"]["SearchValue"], GOV_ISBN)

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_gov_in_ignores_partial_like_matches(self, mock_urlopen):
        # The portal LIKE-matches; a row for another ISBN must never autofill.
        other = {**GOV_ROW, "isbn_number": "978-93-7804-119-9"}
        payload = {"recordsTotal": 1, "recordsFiltered": 1, "data": json.dumps([other])}
        mock_urlopen.side_effect = [*_MISSES, _mock(payload)]
        self.assertIsNone(lookup_isbn(GOV_ISBN))

    @patch("app.services.isbn_lookup.urllib.request.urlopen")
    def test_gov_in_malformed_response_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = [*_MISSES, _mock({"data": "not json"})]
        self.assertIsNone(lookup_isbn(GOV_ISBN))

    def test_isbn10_is_converted_to_isbn13_for_the_portal(self):
        # Well-known pair: 0-306-40615-2 <-> 978-0-306-40615-7.
        self.assertEqual(_isbn10_to_isbn13("0306406152"), "9780306406157")


class MatchCategoryTest(unittest.TestCase):
    """Tiered candidate -> user category matching for the dialog autofill."""

    def test_tier1_exact_match_is_case_insensitive(self):
        self.assertEqual(match_category(("fiction",), ["Fiction", "Science"]), "Fiction")

    def test_tier2_token_subset_matches_source_topic(self):
        # Open Library subjects are supersets of genre names ("Modern fiction").
        self.assertEqual(match_category(("Modern fiction",), ["Fiction", "Science"]), "Fiction")

    def test_tier2_matches_when_user_name_is_more_specific(self):
        self.assertEqual(match_category(("Science",), ["Popular Science"]), "Popular Science")

    def test_stopword_only_candidate_cannot_match(self):
        # BISAC filler ("Fiction / General") must not grab "General Knowledge".
        self.assertIsNone(match_category(("General",), ["General Knowledge"]))

    def test_ties_resolve_to_most_specific_name(self):
        self.assertEqual(
            match_category(("Science fiction classics",), ["Fiction", "Science fiction"]),
            "Science fiction",
        )

    def test_unrelated_topic_returns_none(self):
        # Real Open Library subject noise: a book about Pakistan gets "Pakistan".
        self.assertIsNone(match_category(("Pakistan",), ["Fiction", "Science"]))

    def test_empty_inputs_return_none(self):
        self.assertIsNone(match_category((), ["Fiction"]))
        self.assertIsNone(match_category(("Fiction",), []))


if __name__ == "__main__":
    unittest.main()
