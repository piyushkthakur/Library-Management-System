"""Stateless validation helpers (Volume 3, Chapter 22.3), consumed by both
the Presentation Layer (convenience checks) and the Service Layer
(authoritative checks) so the two tiers never diverge.
"""

import re
from datetime import date

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s\-]{10,18}$")
_DIGITS_ONLY_RE = re.compile(r"^\d{10,15}$")
_STREAMS = ("Science", "Commerce", "Humanities")

PASSWORD_MIN_LENGTH = 8


def is_valid_email(value: str) -> bool:
    """Syntactically valid email address (Volume 1, Chapter 27)."""
    return bool(_EMAIL_RE.match(value.strip()))


def is_valid_phone(value: str) -> bool:
    """Valid phone number format: 10-15 digits, optionally prefixed with +,
    allowing spaces/hyphens between digit groups (Volume 2, Chapter 18)."""
    return bool(_PHONE_RE.match(value.strip()))


def normalize_phone(value: str) -> str:
    """Strip separators from a validated phone number, keeping any leading +."""
    stripped = re.sub(r"[\s\-]", "", value.strip())
    return stripped


def is_valid_stream(value: str) -> bool:
    """Stream must be Science, Commerce, or Humanities."""
    return value.strip() in _STREAMS


def normalize_isbn(value: str) -> str:
    """Canonical ISBN form for storage and comparison: ISBNs are the book
    primary key, so '978-0-13' and '978013' must map to one value."""
    return re.sub(r"[\s\-]", "", value.strip()).upper()


def is_valid_isbn(value: str) -> bool:
    """ISBN-10 or ISBN-13 checksum validation (FR-BOOK-02)."""
    isbn = value.strip().replace("-", "").replace(" ", "").upper()
    if len(isbn) == 10:
        total = 0
        for index, char in enumerate(isbn):
            if char == "X" and index == 9:
                total += 10
            elif char.isdigit():
                total += int(char) * (10 - index)
            else:
                return False
        return total % 11 == 0
    if len(isbn) == 13:
        if not isbn.isdigit():
            return False
        total = sum(
            int(digit) * (1 if position % 2 == 0 else 3)
            for position, digit in enumerate(isbn)
        )
        return total % 10 == 0
    return False


def is_valid_date_range(start: date, end: date) -> bool:
    """Start Date must not be later than End Date (Volume 1, Chapter 25)."""
    return start <= end


def normalize_category_name(value: str) -> str:
    """Canonical category-name normalization (FR-CAT-02 implementation
    detail): trim leading/trailing whitespace and collapse consecutive
    internal spaces into one. Comparison remains case-insensitive; no
    additional normalization rules are introduced."""
    return re.sub(r"\s+", " ", value.strip())


def password_policy(min_length: int = PASSWORD_MIN_LENGTH) -> dict:
    """Password complexity policy (Volume 3, Chapter 22.3): minimum length
    plus at least one uppercase, one lowercase, and one digit."""
    return {
        "min_length": min_length,
        "require_upper": True,
        "require_lower": True,
        "require_digit": True,
    }


def password_error(value: str, min_length: int = PASSWORD_MIN_LENGTH) -> str | None:
    """Return a user-safe validation message, or None when valid."""
    policy = password_policy(min_length)
    if len(value) < policy["min_length"]:
        return f"Password must be at least {policy['min_length']} characters long."
    if policy["require_upper"] and not any(c.isupper() for c in value):
        return "Password must contain at least one uppercase letter."
    if policy["require_lower"] and not any(c.islower() for c in value):
        return "Password must contain at least one lowercase letter."
    if policy["require_digit"] and not any(c.isdigit() for c in value):
        return "Password must contain at least one digit."
    return None
