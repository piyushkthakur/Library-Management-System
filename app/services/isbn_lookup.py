"""Best-effort online book lookup for ISBN autofill in the Add Book dialog.

Offline-safe by design: every failure returns ``None`` and the caller
continues with manual entry. Keyless and stdlib-only (urllib) —
Open Library edition lookup first, Open Library full-text search as
fallback, then Google Books, then the Indian national ISBN agency
portal (isbn.gov.in) as the last resort. 100-200 lookups/day is far
under any of these services' quota.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
_AMP = chr(38)
_OL_ENDPOINT = (
    "https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}"
    + _AMP
    + "format=json"
    + _AMP
    + "jscmd=data"
)
_OL_SEARCH_ENDPOINT = (
    "https://openlibrary.org/search.json?q=isbn:{isbn}"
    + _AMP
    + "fields=title,author_name,subject"
)
_GOOGLE_ENDPOINT = "https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"

# Indian national ISBN agency portal (isbn.gov.in) — last-resort source.
# The search page is a client-side DataTables grid; this is the JSON POST
# endpoint behind its "Search" button. The portal 401s the default urllib
# agent, so a browser-ish identity is required.
_GOV_AJAX_URL = "https://isbn.gov.in/Home/FillSearchText"
_GOV_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_GOV_TIMEOUT_SECONDS = 8.0  # slow shared government host; give it a little longer
# Columns the site's grid declares; the endpoint echoes rows keyed by them.
_GOV_COLUMNS = (
    "Index1",
    "title",
    "isbn_number",
    "productform",
    "language",
    "applicant_type",
    "publisher",
    "Inprint",
    "Author",
    "publicationdate",
)


@dataclass(frozen=True)
class IsbnLookupResult:
    title: str
    author: str
    categories: tuple[str, ...] = ()


def lookup_isbn(isbn: str) -> IsbnLookupResult | None:
    """Fetch title/author/categories for a normalized ISBN, or None."""
    return (
        _lookup_openlibrary(isbn)
        or _lookup_google(isbn)
        or _lookup_isbn_gov_in(isbn)
    )


# Filler tokens from BISAC-style subjects ("Fiction / General") — they
# would otherwise let a source topic match an unrelated user category.
_STOPWORDS = frozenset(
    {"the", "of", "and", "a", "an", "for", "to", "in", "on", "at", "by", "is", "general", "other"}
)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        t for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) >= 2 and t not in _STOPWORDS
    )


def match_category(candidates: Iterable[str], names: Iterable[str]) -> str | None:
    """Best user category for lookup candidates, or None.

    Tier 1: case-insensitive exact match. Tier 2: token-subset in either
    direction ("Modern fiction" <-> "Fiction"). Strict on purpose — a
    wrong autofill is worse than no autofill, so an unmatched candidate
    returns None and the dialog leaves the dropdown empty for the user.
    Ties resolve to the most specific (longest) name.
    """
    cands = [c.strip() for c in candidates if c and c.strip()]
    known = [n.strip() for n in names if n and n.strip()]
    if not cands or not known:
        return None
    exact = [n for n in known if any(n.casefold() == c.casefold() for c in cands)]
    if exact:
        return max(exact, key=len)
    cand_tokens = [_tokens(c) for c in cands]
    hits = [
        n
        for n in known
        if _tokens(n) and any(t and (_tokens(n) <= t or t <= _tokens(n)) for t in cand_tokens)
    ]
    if hits:
        return max(hits, key=len)
    return None


def _lookup_openlibrary(isbn: str) -> IsbnLookupResult | None:
    """Open Library: edition lookup first, full-text search fallback."""
    result = _openlibrary_bibkeys(isbn)
    if result is not None:
        return result
    return _openlibrary_search(isbn)


def _openlibrary_bibkeys(isbn: str) -> IsbnLookupResult | None:
    url = _OL_ENDPOINT.format(isbn=urllib.parse.quote(isbn, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.debug("Open Library bibkeys lookup failed for %s", isbn, exc_info=True)
        return None
    if not payload:
        return None
    info = next(iter(payload.values())) or {}
    if not isinstance(info, dict):
        return None
    title = str(info.get("title") or "").strip()
    authors = ", ".join(
        str(a.get("name") or "").strip() for a in (info.get("authors") or [])
    ).strip(", ")
    if not title or not authors:
        return None
    subjects = [str(s.get("name") or "").strip() for s in (info.get("subjects") or [])]
    return IsbnLookupResult(
        title=title,
        author=authors,
        categories=tuple(s for s in subjects if s)[:6],
    )


def _openlibrary_search(isbn: str) -> IsbnLookupResult | None:
    url = _OL_SEARCH_ENDPOINT.format(isbn=urllib.parse.quote(isbn, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.debug("Open Library search lookup failed for %s", isbn, exc_info=True)
        return None
    docs = payload.get("docs") or []
    if not docs:
        return None
    doc = docs[0]
    title = str(doc.get("title") or "").strip()
    authors = ", ".join(str(a).strip() for a in (doc.get("author_name") or []) if str(a).strip())
    if not title or not authors:
        return None
    subjects = [str(s).strip() for s in (doc.get("subject") or []) if str(s).strip()]
    return IsbnLookupResult(
        title=title,
        author=authors,
        categories=tuple(subjects)[:6],
    )


def _lookup_google(isbn: str) -> IsbnLookupResult | None:
    url = _GOOGLE_ENDPOINT.format(isbn=urllib.parse.quote(isbn, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.debug("Google Books lookup failed for %s", isbn, exc_info=True)
        return None
    items = payload.get("items") or []
    if not items:
        return None
    info = items[0].get("volumeInfo") or {}
    title = str(info.get("title") or "").strip()
    authors = [str(a).strip() for a in (info.get("authors") or []) if str(a).strip()]
    if not title or not authors:
        return None
    # Google hands back BISAC codes ("Fiction / Literary"); split them so
    # each segment can match a user category on its own.
    segments = [
        part.strip()
        for c in (info.get("categories") or [])
        for part in str(c).split("/")
        if part.strip()
    ]
    return IsbnLookupResult(
        title=title,
        author=", ".join(authors),
        categories=tuple(segments),
    )


def _isbn10_to_isbn13(isbn10: str) -> str:
    """978-prefixed ISBN-13 equivalent — the gov portal indexes 13s only."""
    core = "978" + isbn10[:9]
    total = sum(
        int(digit) * (1 if position % 2 == 0 else 3)
        for position, digit in enumerate(core)
    )
    return core + str((10 - total % 10) % 10)


def _gov_datatables_payload() -> dict:
    """Request shape the portal's own search grid sends (server-side DataTables)."""
    return {
        "draw": 1,
        "start": 0,
        "length": 10,
        "search": {"value": "", "regex": False},
        "order": [{"column": 1, "dir": "asc"}],
        "columns": [
            {
                "data": name,
                "name": name,
                "searchable": True,
                "orderable": True,
                "search": {"value": "", "regex": False},
            }
            for name in _GOV_COLUMNS
        ],
    }


def _lookup_isbn_gov_in(isbn: str) -> IsbnLookupResult | None:
    """Indian national ISBN agency portal (isbn.gov.in) — last resort.

    Reproduces the search the portal's own page performs: search type
    "ISBN Number/Series" (``isbn_number_Nodash``) with the dash-free
    ISBN. The database only covers ISBNs allotted in India, so it mostly
    matters for domestic titles the international sources miss. It
    publishes no subject/category, so ``category`` stays None and the
    dialog falls back to "Uncategorized".
    """
    digits = "".join(ch for ch in isbn if ch.isdigit())
    if len(digits) == 10:
        digits = _isbn10_to_isbn13(digits)
    if len(digits) != 13:
        return None
    body = json.dumps(
        {
            "data": _gov_datatables_payload(),
            "_obj": {
                "Type": "isbn_number_Nodash",
                "SearchValue": digits,
                # 11 = exact match, same rows as the LIKE path (1) for a full
                # ISBN but ~0.4s vs ~12s: the LIKE scan overruns our 8s
                # timeout and the lookup silently returns None.
                "ViewReport": 11,
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _GOV_AJAX_URL,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": _GOV_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_GOV_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = json.loads(payload.get("data") or "[]")
    except Exception:
        logger.debug("isbn.gov.in lookup failed for %s", isbn, exc_info=True)
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        found = "".join(ch for ch in str(row.get("isbn_number") or "") if ch.isdigit())
        if found != digits:
            continue  # the portal LIKE-matches; only accept an exact hit
        title = str(row.get("title") or "").strip()
        author = str(row.get("Author") or "").strip()
        if title and author:
            return IsbnLookupResult(title=title, author=author)
    return None
