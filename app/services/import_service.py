"""BookImportService — bulk book import via CSV, Excel, or JSON.

Parses uploaded files with smart column detection, validates each row
against business rules, presents a preview with per-row status, and
commits valid rows to the database. Duplicates (by ISBN) are skipped;
missing categories are created automatically.
"""

import csv
import difflib
import io
import json
import logging
import re
from dataclasses import dataclass, replace

from openpyxl import load_workbook

from app.core.database import Database
from app.core.exceptions import RecordNotFoundError
from app.core.security import SessionContext
from app.repositories.interfaces import (
    BookRepositoryInterface,
    CategoryRepositoryInterface,
)
from app.services.interfaces import ImportServiceInterface
from app.utils.validators import is_valid_isbn, normalize_isbn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column detection — expanded aliases + fuzzy substring matching
# ---------------------------------------------------------------------------

_KEY_ALIASES = {
    # title
    "title": "title",
    "book title": "title",
    "booktitle": "title",
    "book_name": "title",
    "book name": "title",
    "name": "title",
    "book_title": "title",
    # author
    "author": "author",
    "book author": "author",
    "bookauthor": "author",
    "book_author": "author",
    "writer": "author",
    "written by": "author",
    "writtenby": "author",
    # isbn
    "isbn": "isbn",
    "isbn-10": "isbn",
    "isbn-13": "isbn",
    "isbn10": "isbn",
    "isbn13": "isbn",
    "isbn_no": "isbn",
    "isbn no": "isbn",
    "isbn number": "isbn",
    "isbnumber": "isbn",
    "book_isbn": "isbn",
    "book isbn": "isbn",
    # category
    "category": "category",
    "category name": "category",
    "categoryname": "category",
    "category_name": "category",
    "genre": "category",
    "subject": "category",
    "type": "category",
    "book type": "category",
    "booktype": "category",
    "classification": "category",
    # total_copies
    "total copies": "total_copies",
    "totalcopies": "total_copies",
    "total_copies": "total_copies",
    "copies": "total_copies",
    "quantity": "total_copies",
    "qty": "total_copies",
    "count": "total_copies",
    "no.": "total_copies",
    "num": "total_copies",
    "number": "total_copies",
    "stock": "total_copies",
    "inventory": "total_copies",
    "book copies": "total_copies",
    "bookcopies": "total_copies",
    # shelf_location
    "shelf location": "shelf_location",
    "shelflocation": "shelf_location",
    "shelf_location": "shelf_location",
    "shelf": "shelf_location",
    "location": "shelf_location",
    "rack": "shelf_location",
    "position": "shelf_location",
    "place": "shelf_location",
    "almirah": "shelf_location",
    "row": "shelf_location",
    "section": "shelf_location",
}


def _normalize_key(raw: str) -> str | None:
    """Map a raw header/key to a canonical field name, or None if unknown.
    Uses exact alias match first, then substring fuzzy matching."""
    normalized = raw.strip().lower()
    if normalized in _KEY_ALIASES:
        return _KEY_ALIASES[normalized]
    # substring fuzzy matching — order matters (most specific first)
    if "isbn" in normalized:
        return "isbn"
    if "title" in normalized or "book name" in normalized or "bookname" in normalized:
        return "title"
    if "author" in normalized or "writer" in normalized or "written" in normalized:
        return "author"
    if "categ" in normalized or "genre" in normalized or "subject" in normalized or "classification" in normalized:
        return "category"
    if "cop" in normalized or "quantity" in normalized or "count" in normalized or "no." in normalized or "stock" in normalized or "qty" in normalized:
        return "total_copies"
    if "shelf" in normalized or "location" in normalized or "rack" in normalized or "position" in normalized or "almirah" in normalized or "section" in normalized:
        return "shelf_location"
    return None


def _parse_copies(value) -> int | None:
    """Try to coerce a value to a positive integer. Returns None on failure."""
    if value is None:
        return None
    s = str(value).strip()
    s = re.sub(r"[^\d]", "", s)
    if not s:
        return None
    try:
        n = int(s)
        return n if n >= 1 else None
    except (TypeError, ValueError):
        return None


def _empty_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    v = str(value).strip()
    return v if v else None


def _clean_isbn(value: str | None) -> str | None:
    """Strip dashes, spaces, and other non-alphanumeric chars from ISBN.
    Handles scientific notation like 9.78043902348e+12 → 9780439023480."""
    if value is None:
        return None
    v = value.strip()
    # Handle scientific notation: try float→int conversion first
    try:
        f = float(v)
        if f > 1e9:
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    cleaned = re.sub(r"[^\dXx]", "", v)
    return cleaned if cleaned else None


def _resolve_isbn(candidates: list[str]) -> str | None:
    """From multiple ISBN column values, return the one that validates.
    If exactly one validates, use it. If multiple validate, prefer
    ISBN-13 (13 digits) over ISBN-10 (10 digits). If none validate,
    return the first non-empty candidate as-is (validation will catch it later)."""
    cleaned = [_clean_isbn(c) for c in candidates if _empty_to_none(c)]
    if not cleaned:
        return None
    valid = [c for c in cleaned if is_valid_isbn(c)]
    if len(valid) == 1:
        return valid[0]
    if len(valid) > 1:
        # prefer ISBN-13 (13 digits) over ISBN-10 (10 digits)
        return max(valid, key=len)
    # none valid — return first cleaned candidate, let validation flag it
    return cleaned[0]


def _clean_string(value) -> str:
    """Normalize whitespace and strip a string value."""
    if value is None:
        return ""
    s = str(value).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _build_row(pairs: list[tuple]) -> dict:
    """Build a normalized row from (raw_key, raw_value) pairs.
    Tracks ISBN candidates separately so we can pick the valid one."""
    row = {}
    isbn_candidates = []
    positional_buf = {}
    for pos, (raw_key, val) in enumerate(pairs):
        if raw_key is None:
            continue
        canon = _normalize_key(str(raw_key))
        val_str = str(val).strip() if val is not None else ""
        if canon == "isbn":
            isbn_candidates.append(val_str)
        elif canon:
            row[canon] = val_str
        else:
            positional_buf[pos] = val_str
    if isbn_candidates:
        row["isbn"] = _resolve_isbn(isbn_candidates) or ""
    elif positional_buf:
        row.update(positional_buf)
    return row


# ---------------------------------------------------------------------------
# Format parsers — pure functions, no DB access
# ---------------------------------------------------------------------------

_POSITIONAL_MAP = ["title", "author", "isbn", "category", "total_copies", "shelf_location"]


def _apply_positional_fallback(rows: list[dict]) -> list[dict]:
    """If no rows have any recognized keys, map by column position.
    Handles both string keys (from header-based parsing) and integer keys
    (from headerless positional parsing)."""
    if not rows:
        return rows
    first = rows[0]
    # Check if any row has known canonical field names as keys
    has_known_keys = any(
        k in _POSITIONAL_MAP for k in first if isinstance(k, str)
    )
    if has_known_keys:
        return rows
    # Positional fallback: first try data-driven, then pure positional
    return _data_driven_column_detect(rows) or _pure_positional(rows)


def _data_driven_column_detect(rows: list[dict]) -> list[dict] | None:
    """Scan column values to guess what each column represents.
    Returns mapped rows if detection succeeds, None if ambiguous."""
    if not rows:
        return None
    # Collect all values per column index
    col_values: dict[int, list[str]] = {}
    for raw in rows:
        for k, v in raw.items():
            col_values.setdefault(k, []).append(str(v).strip() if v else "")

    col_scores: dict[int, dict[str, int]] = {}
    for col_idx, vals in col_values.items():
        scores = {"isbn": 0, "title": 0, "author": 0, "category": 0, "copies": 0, "skip": 0}
        # Penalize columns with all-identical values (likely type indicators, not titles)
        unique_ratio = len(set(vals)) / max(len(vals), 1)
        for v in vals:
            if not v:
                continue
            # ISBN: 10 or 13 digits (possibly with dashes/X)
            stripped = re.sub(r"[^\dXx]", "", v)
            if stripped and len(stripped) in (10, 13) and stripped.replace("X", "").replace("x", "").isdigit():
                scores["isbn"] += 2
            # Category path: contains ">"
            elif ">" in v:
                scores["category"] += 3
            # Pure small integer: likely copies
            elif re.match(r"^\d{1,4}$", v) and int(v) <= 9999:
                scores["copies"] += 1
            # Long text (>80 chars): likely description, skip
            elif len(v) > 80:
                scores["skip"] += 3
            # Short text: could be title, author, or other
            elif len(v) < 60:
                # Looks like a person name (2-3 words, title case)
                words = v.split()
                if 1 < len(words) <= 4 and all(w[0].isupper() for w in words if w):
                    scores["author"] += 1
                else:
                    # Penalize if all values are identical (likely type indicator)
                    title_score = 2 if unique_ratio > 0.5 else 0
                    scores["title"] += title_score
            else:
                scores["skip"] += 1
        col_scores[col_idx] = scores

    # Assign each column to its best-matching field (one field per column)
    mapping = {}
    used_fields = set()
    for col_idx, scores in col_scores.items():
        best = max(scores, key=scores.get)
        if best == "skip" or best in used_fields:
            continue
        if scores[best] >= 2:
            mapping[col_idx] = best
            used_fields.add(best)

    if not mapping or "isbn" not in mapping.values():
        return None

    result = []
    for raw in rows:
        row = {}
        for k, v in raw.items():
            field = mapping.get(k)
            if field:
                row[field] = str(v).strip() if v else ""
        result.append(row)
    return result


def _pure_positional(rows: list[dict]) -> list[dict]:
    """Map columns by position using the default order."""
    header_count = max(len(r) for r in rows)
    mapping = {i: field for i, field in enumerate(_POSITIONAL_MAP) if i < header_count}
    result = []
    for raw in rows:
        row = {}
        keys = list(raw.keys())
        for pos, key in enumerate(keys):
            if pos in mapping:
                val = raw[key]
                row[mapping[pos]] = str(val).strip() if val is not None else ""
        result.append(row)
    return result


def _detect_encoding(file_bytes: bytes) -> str:
    """Try common encodings. Returns the first that decodes without error."""
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252", "iso-8859-1", "utf-16"):
        try:
            file_bytes.decode(enc)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def _detect_delimiter(text: str) -> str:
    """Sniff the CSV delimiter from the first few lines."""
    sample = "\n".join(text.split("\n")[:5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _looks_like_header(row_vals: list[str]) -> bool:
    """Heuristic: does the first row look like column headers?
    Returns True if any cell matches a known field alias (most reliable signal)."""
    if not row_vals:
        return False
    for v in row_vals:
        v = v.strip()
        if not v:
            continue
        if _normalize_key(v) is not None:
            return True
    return False


def parse_csv(file_bytes: bytes) -> list[dict]:
    """Parse CSV bytes into a list of raw row dicts with normalized keys.
    Auto-detects encoding, delimiter, and whether the first row is headers."""
    enc = _detect_encoding(file_bytes)
    text = file_bytes.decode(enc, errors="replace")
    delimiter = _detect_delimiter(text)

    # Read all non-empty lines
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []

    # Detect if first row is headers
    first_vals = next(csv.reader([lines[0]], delimiter=delimiter))
    has_headers = _looks_like_header(first_vals)

    if has_headers:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        rows = []
        for raw in reader:
            rows.append(_build_row(list(raw.items())))
    else:
        # No headers — read all rows as positional data
        all_rows = list(csv.reader(lines, delimiter=delimiter))
        rows = []
        for values in all_rows:
            pairs = [(f"col{i}", v) for i, v in enumerate(values)]
            rows.append(_build_row(pairs))

    return _apply_positional_fallback(rows)


def parse_excel(file_bytes: bytes) -> list[dict]:
    """Parse the first sheet of an .xlsx workbook into raw row dicts."""
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = None
    for candidate in rows_iter:
        if any(v is not None for v in candidate):
            headers = candidate
            break
    if headers is None:
        wb.close()
        return []
    rows = []
    for values in rows_iter:
        if not any(v is not None for v in values):
            continue
        rows.append(_build_row(list(zip(headers, values))))
    wb.close()
    return _apply_positional_fallback(rows)


def parse_xls(file_bytes: bytes) -> list[dict]:
    """Parse the first sheet of an .xls workbook using xlrd."""
    try:
        import xlrd
    except ImportError:
        raise ValueError(
            "Reading .xls files requires the 'xlrd' package. "
            "Install it with: pip install 'xlrd>=1.2,<2.0'"
        )
    wb = xlrd.open_workbook(file_contents=file_bytes)
    ws = wb.sheet_by_index(0)
    if ws.nrows == 0:
        return []
    headers = [ws.cell_value(0, c) for c in range(ws.ncols)]
    rows = []
    for r in range(1, ws.nrows):
        values = [ws.cell_value(r, c) for c in range(ws.ncols)]
        if not any(v for v in values):
            continue
        rows.append(_build_row(list(zip(headers, values))))
    return _apply_positional_fallback(rows)


def parse_json(file_bytes: bytes) -> list[dict]:
    """Parse JSON into raw row dicts. Handles multiple shapes:
    - Array of objects: [{"title": "...", ...}, ...]
    - Object with a nested array: {"books": [...]} or {"data": [...]}
    - Array of arrays: [["title", "author", ...], ["val1", "val2", ...]]
    - Single object: {"title": "...", ...}
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    data = json.loads(text)

    # Unwrap: if it's a dict, look for the first array value
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
        else:
            # Single object — treat as one row
            if isinstance(data, dict) and any(data.values()):
                data = [data]
            else:
                return []

    if isinstance(data, list) and data and isinstance(data[0], list):
        # Array of arrays — first row is headers
        headers = data[0]
        rows = []
        for values in data[1:]:
            if not any(v for v in values):
                continue
            rows.append(_build_row(list(zip(headers, values))))
        return _apply_positional_fallback(rows)

    if not isinstance(data, list):
        return []

    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append(_build_row(list(item.items())))
    return _apply_positional_fallback(rows)


_PARSERS = {
    ".csv": parse_csv,
    ".xlsx": parse_excel,
    ".xls": parse_xls,
    ".json": parse_json,
}


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportRowDto:
    """One parsed row with its validation status."""

    row_number: int
    title: str
    author: str
    isbn: str
    category_name: str
    total_copies: int
    shelf_location: str | None
    status: str  # "valid" | "merged" | "error"
    error_message: str = ""


@dataclass(frozen=True)
class ImportPreviewDto:
    """The full parsed-and-validated preview."""

    rows: tuple[ImportRowDto, ...]
    valid_count: int
    merged_count: int
    error_count: int


@dataclass(frozen=True)
class ImportResultDto:
    """Result after committing the import."""

    imported: int
    merged: int
    errors: int
    categories_created: int = 0


# ---------------------------------------------------------------------------
# Fuzzy category matching
# ---------------------------------------------------------------------------


def _identity_mismatch(first: ImportRowDto, row: ImportRowDto) -> list[str]:
    """Identity fields (besides copies) on which two same-ISBN rows differ.
    Copies never conflict — they are summed. An empty category/shelf defers
    to the stated one."""
    bad = []
    if row.title.strip().casefold() != first.title.strip().casefold():
        bad.append("title")
    if row.author.strip().casefold() != first.author.strip().casefold():
        bad.append("author")
    if (
        row.category_name
        and first.category_name
        and row.category_name.strip().casefold() != first.category_name.strip().casefold()
    ):
        bad.append("category")
    row_shelf = (row.shelf_location or "").strip()
    first_shelf = (first.shelf_location or "").strip()
    if row_shelf and first_shelf and row_shelf != first_shelf:
        bad.append("shelf location")
    return bad


def _fuzzy_match_category(name: str, known: dict[str, str], threshold: float = 0.6) -> str | None:
    """Try exact match first, then fuzzy match against known category names."""
    if not name:
        return None
    lower = name.lower().strip()
    if lower in known:
        return known[lower]
    # fuzzy match
    matches = difflib.get_close_matches(lower, list(known.keys()), n=1, cutoff=threshold)
    if matches:
        return known[matches[0]]
    return None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class BookImportService(ImportServiceInterface):
    def __init__(
        self,
        database: Database,
        book_repository: BookRepositoryInterface,
        category_repository: CategoryRepositoryInterface,
    ) -> None:
        self._database = database
        self._book_repo = book_repository
        self._category_repo = category_repository

    def preview(self, file_bytes: bytes, file_ext: str) -> ImportPreviewDto:
        ext = file_ext.lower()
        parser = _PARSERS.get(ext)
        if parser is None:
            raise ValueError(f"Unsupported file format: {ext}")

        raw_rows = parser(file_bytes)
        if not raw_rows:
            return ImportPreviewDto(rows=(), valid_count=0, merged_count=0, error_count=0)

        logger.debug("Parsed %d raw rows, first row keys: %s", len(raw_rows), list(raw_rows[0].keys()) if raw_rows else [])

        # Batch-load existing books and categories, auto-create missing categories
        with self._database.session_scope() as session:
            existing_isbn_rows = self._book_repo.search(
                session, "", None, 1, 100_000, include_inactive=True
            )
            # ponytail: plain tuples, not ORM objects — phase 2 runs after
            # this session closes, and detached attribute access would raise.
            catalog_by_isbn = {
                normalize_isbn(b.isbn): (
                    b.title or "",
                    b.author or "",
                    b.category_id,
                    b.shelf_location,
                )
                for b in existing_isbn_rows[0]
            }

            categories = self._category_repo.list_all(session)
            cat_by_name = {c.name.strip().lower(): c for c in categories}

            # Auto-create categories found in import file but missing from DB
            # Use the last segment of ">" paths (e.g. "Books > Fiction > Thriller" → "Thriller")
            seen_cats: set[str] = set()
            for raw in raw_rows:
                cat_raw = _empty_to_none(raw.get("category"))
                if not cat_raw:
                    continue
                # Extract the last non-empty segment from ">" separated paths
                if ">" in cat_raw:
                    segments = [s.strip() for s in cat_raw.split(">") if s.strip()]
                    cat_name = segments[-1] if segments else cat_raw.strip()
                else:
                    cat_name = cat_raw.strip()
                cat_key = cat_name.lower()
                if cat_key in seen_cats:
                    continue
                seen_cats.add(cat_key)
                if cat_key not in cat_by_name:
                    new_cat = self._category_repo.create(session, cat_name, None)
                    cat_by_name[cat_key] = new_cat

            # Reload to pick up any newly created categories
            categories = self._category_repo.list_all(session)
            cat_by_name = {c.name.strip().lower(): c for c in categories}
            cat_name_by_id = {c.id: c.name for c in categories}
            uncategorized = cat_by_name.get("uncategorized")

        # Phase 1: per-row field validation (no duplicate handling yet).
        result_rows: list[ImportRowDto] = []
        for idx, raw in enumerate(raw_rows, start=1):
            result_rows.append(
                self._validate_row(idx, raw, cat_by_name, uncategorized)
            )

        # Phase 2: group by ISBN — repeats merge their copies into the first
        # surviving row; catalog hits merge into the cataloged book.
        groups: dict[str, list[int]] = {}
        for i, row in enumerate(result_rows):
            if row.status != "error":
                groups.setdefault(row.isbn, []).append(i)

        for isbn, idxs in groups.items():
            catalog = catalog_by_isbn.get(isbn)
            if catalog is not None:
                survivors = self._check_against_catalog(
                    result_rows, idxs, catalog, cat_name_by_id
                )
                if not survivors:
                    continue
                first = survivors[0]
                total = sum(result_rows[i].total_copies for i in survivors)
                result_rows[first] = replace(
                    result_rows[first],
                    total_copies=total,
                    status="merged",
                    error_message=(
                        f"Exists in catalog — {total} copies across "
                        f"{len(survivors)} rows will be added."
                    ),
                )
                for i in survivors[1:]:
                    first_no = result_rows[first].row_number
                    result_rows[i] = replace(
                        result_rows[i],
                        status="merged",
                        error_message=(
                            f"Merged into row {first_no} "
                            f"(+{result_rows[i].total_copies} copies)."
                        ),
                    )
            else:
                first = idxs[0]
                survivors = [first]
                for i in idxs[1:]:
                    fields = _identity_mismatch(result_rows[first], result_rows[i])
                    if fields:
                        first_no = result_rows[first].row_number
                        result_rows[i] = replace(
                            result_rows[i],
                            status="error",
                            error_message=(
                                f"Conflicts with row {first_no}: "
                                f"{', '.join(fields)} differ."
                            ),
                        )
                    else:
                        survivors.append(i)
                total = sum(result_rows[i].total_copies for i in survivors)
                result_rows[first] = replace(result_rows[first], total_copies=total)
                for i in survivors[1:]:
                    first_no = result_rows[first].row_number
                    result_rows[i] = replace(
                        result_rows[i],
                        status="merged",
                        error_message=(
                            f"Merged into row {first_no} "
                            f"(+{result_rows[i].total_copies} copies)."
                        ),
                    )

        valid = sum(1 for r in result_rows if r.status == "valid")
        merged = sum(1 for r in result_rows if r.status == "merged")
        err = sum(1 for r in result_rows if r.status == "error")
        return ImportPreviewDto(
            rows=tuple(result_rows),
            valid_count=valid,
            merged_count=merged,
            error_count=err,
        )

    @staticmethod
    def _check_against_catalog(result_rows, idxs, catalog, cat_name_by_id) -> list[int]:
        """Mark rows whose identity fields differ from the cataloged book as
        errors; return the surviving indices. ``catalog`` is a plain
        (title, author, category_id, shelf_location) tuple."""
        catalog_title, catalog_author, catalog_category_id, catalog_shelf_raw = catalog
        catalog_title = catalog_title.strip().casefold()
        catalog_author = catalog_author.strip().casefold()
        catalog_category = (cat_name_by_id.get(catalog_category_id) or "").strip().casefold()
        catalog_shelf = (catalog_shelf_raw or "").strip()
        survivors = []
        for i in idxs:
            row = result_rows[i]
            bad = []
            if row.title.strip().casefold() != catalog_title:
                bad.append("title")
            if row.author.strip().casefold() != catalog_author:
                bad.append("author")
            if (
                row.category_name
                and row.category_name.strip().casefold() != catalog_category
            ):
                bad.append("category")
            # ponytail: an empty shelf defers to the cataloged one; only
            # two stated locations conflict.
            if (
                row.shelf_location
                and catalog_shelf
                and row.shelf_location.strip() != catalog_shelf
            ):
                bad.append("shelf location")
            if bad:
                result_rows[i] = replace(
                    row,
                    status="error",
                    error_message=(
                        f"Differs from cataloged book: {', '.join(bad)}."
                    ),
                )
            else:
                survivors.append(i)
        return survivors

    def commit(self, preview: ImportPreviewDto, context: SessionContext) -> ImportResultDto:
        imported = merged_books = errors = created = 0

        with self._database.session_scope() as session:
            categories = self._category_repo.list_all(session)
            cat_by_name = {c.name.strip().lower(): c for c in categories}
            uncategorized = cat_by_name.get("uncategorized")
            existing_rows = self._book_repo.search(
                session, "", None, 1, 100_000, include_inactive=True
            )
            existing_isbns = {normalize_isbn(b.isbn) for b in existing_rows[0]}
            handled_merges: set[str] = set()

            for row in preview.rows:
                if row.status == "error":
                    errors += 1
                    continue
                if row.status == "merged":
                    # New-ISBN repeats were folded into their group's valid
                    # row; only the first row of a catalog group acts.
                    if row.isbn in existing_isbns and row.isbn not in handled_merges:
                        handled_merges.add(row.isbn)
                        try:
                            with session.begin_nested():
                                book = self._book_repo.get_by_isbn(session, row.isbn)
                                if book is None:
                                    raise RecordNotFoundError(
                                        "The requested book was not found."
                                    )
                                book.total_copies += row.total_copies
                                book.available_copies += row.total_copies
                                self._book_repo.update(session, book)
                            merged_books += 1
                        except Exception:
                            logger.exception(
                                "Failed to merge row %s (ISBN=%s)",
                                row.row_number, row.isbn,
                            )
                            errors += 1
                    continue

                cat = cat_by_name.get(row.category_name.lower())
                if cat is None and row.category_name:
                    cat = self._category_repo.create(session, row.category_name, None)
                    cat_by_name[row.category_name.lower()] = cat
                    created += 1
                cat_id = cat.id if cat else (uncategorized.id if uncategorized else None)
                if cat_id is None:
                    errors += 1
                    continue

                # ponytail: one bad row (e.g. a race inserting the same ISBN)
                # must not poison the other 5000 — savepoint per row, so a
                # failure rolls back just that row and the loop continues.
                try:
                    with session.begin_nested():
                        self._book_repo.create(
                            session,
                            {
                                "title": row.title,
                                "author": row.author,
                                "isbn": row.isbn,
                                "category_id": cat_id,
                                "total_copies": row.total_copies,
                                "available_copies": row.total_copies,
                                "shelf_location": row.shelf_location,
                            },
                        )
                    imported += 1
                except Exception:
                    logger.exception("Failed to import row %s (ISBN=%s)", row.row_number, row.isbn)
                    errors += 1

        logger.info(
            "Book import committed by user %s: %d imported, %d merged, %d errors, %d categories created",
            context.user_id,
            imported,
            merged_books,
            errors,
            created,
        )
        return ImportResultDto(imported=imported, merged=merged_books, errors=errors, categories_created=created)

    def _validate_row(
        self,
        idx: int,
        raw: dict,
        cat_by_name: dict,
        uncategorized,
    ) -> ImportRowDto:
        title = _empty_to_none(raw.get("title"))
        author = _empty_to_none(raw.get("author"))
        isbn_raw = normalize_isbn(_clean_isbn(_empty_to_none(raw.get("isbn"))) or "")
        category_raw = _empty_to_none(raw.get("category"))
        copies_raw = raw.get("total_copies", "")
        shelf = _empty_to_none(raw.get("shelf_location"))

        def _error(msg: str) -> ImportRowDto:
            return ImportRowDto(
                row_number=idx,
                title=_clean_string(title) if title else "",
                author=_clean_string(author) if author else "",
                isbn=isbn_raw or "",
                category_name=category_raw or "",
                total_copies=0,
                shelf_location=shelf,
                status="error",
                error_message=msg,
            )

        if not title:
            return _error("Title is required.")
        if not author:
            author = "Anonymous"
        if not isbn_raw:
            return _error("ISBN is required.")
        if not is_valid_isbn(isbn_raw):
            return _error("Invalid ISBN format.")
        copies = _parse_copies(copies_raw) or 1

        cat_name = category_raw or ""
        cat = cat_by_name.get(cat_name.lower())
        # Try extracting last segment from path like "Books > Non-Fiction > Fiction"
        if cat is None and ">" in cat_name:
            for segment in reversed(cat_name.split(">")):
                segment = segment.strip()
                if not segment:
                    continue
                cat = cat_by_name.get(segment.lower())
                if cat:
                    cat_name = segment
                    break
                # fuzzy match each segment
                matched = _fuzzy_match_category(segment, cat_by_name)
                if matched:
                    cat = cat_by_name.get(matched)
                    cat_name = segment
                    break
        # fuzzy fallback on full name
        if cat is None and cat_name:
            matched = _fuzzy_match_category(cat_name, cat_by_name)
            if matched:
                cat = cat_by_name.get(matched)
        if cat is None and uncategorized is None:
            return _error(f"Category '{cat_name}' not found and no Uncategorized fallback.")

        return ImportRowDto(
            row_number=idx,
            title=_clean_string(title),
            author=_clean_string(author),
            isbn=isbn_raw,
            category_name=cat_name,
            total_copies=copies,
            shelf_location=shelf,
            status="valid",
        )
