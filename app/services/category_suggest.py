"""Category proposals when the lookup's genre doesn't exist in the catalog.

Offline-safe by design, same contract as :mod:`app.services.isbn_lookup`:
every failure returns ``None`` and the Add Book dialog simply keeps the
category manual — nothing here ever writes to the database. The dialog
shows the proposal as a "+ Create" chip and only writes after the user
clicks it.

Three stages, cheapest first:

1. A short sane segment of the lookup's own candidates (Open Library /
   Google subjects) — "Pakistan, history" -> "Pakistan".
2. A conservative word-bounded keyword table over the fetched title.
   Deliberately sparse: no suggestion beats a wrong one.
3. One OpenRouter chat call with title+author — only when
   ``OPENROUTER_API_KEY`` is set (model overridable via ``LMS_AI_MODEL``;
   the free roster churns monthly). Output is strictly validated, any
   junk is treated as no suggestion.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

from app.services.isbn_lookup import IsbnLookupResult

logger = logging.getLogger(__name__)

_AI_URL = "https://openrouter.ai/api/v1/chat/completions"
_AI_MODEL_DEFAULT = "nvidia/nemotron-3.5-lightning:free"
_AI_TIMEOUT_SECONDS = 8.0

# (category, title regex) — order is priority, patterns are word-bounded
# so "novelty" never matches "novel".
_TITLE_RULES: tuple[tuple[str, str], ...] = (
    ("Cooking", r"\bcookbooks?\b|\brecipes?\b|\bcuisine\b|\bbaking\b|\bcooking\b"),
    ("Technology", r"\bprogramming\b|\bsoftware\b|\balgorithms?\b|\bcomputers?\b|\bmachine learning\b|\bdatabases?\b"),
    ("History", r"\bhistory of\b|\bchronicles?\b"),
    ("Biography", r"\bautobiograph\w*\b|\bmemoirs?\b|\bbiograph\w*\b|\blife of\b"),
    ("Science", r"\bphysics\b|\bchemistry\b|\bbiology\b|\bgenetics\b|\bquantum\b|\bastrophysics\b"),
    ("Mathematics", r"\bmathematics\b|\bcalculus\b|\balgebra\b|\bgeometry\b"),
    ("Fiction", r"\bnovels?\b|\bstories\b|\bfiction\b"),
    ("Business", r"\bstartups?\b|\bentrepreneur\w*\b|\bmarketing\b|\binvesting\b"),
    ("Politics", r"\bpolitics\b|\bpolitical\b"),
)

_FILLER = frozenset({"the", "of", "a", "an", "and", "for", "to", "in", "on"})


def _candidate_name(candidate: str) -> str | None:
    """Short sane segment of one source candidate, title-cased, or None.

    Shape-gated only (1-3 words, 3-24 chars, letters/punct-free): we
    cannot tell a genre from a place name offline, so the dialog's
    confirm-chip stays the judge.
    """
    for segment in re.split(r"[,/]| - ", candidate):
        seg = " ".join(segment.split())
        words = seg.split()
        if not (1 <= len(words) <= 3) or not (3 <= len(seg) <= 24):
            continue
        if not re.fullmatch(r"[A-Za-z][A-Za-z '&-]*", seg):
            continue
        if all(w.casefold() in _FILLER for w in words):
            continue
        return " ".join(w.capitalize() for w in words)
    return None


def _from_candidates(candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        name = _candidate_name(candidate)
        if name:
            return name
    return None


def _from_title(title: str) -> str | None:
    for name, pattern in _TITLE_RULES:
        if re.search(pattern, title or "", flags=re.IGNORECASE):
            return name
    return None


def _clean_category(raw: object) -> str | None:
    """Accept at most a short plain name; reject anything else."""
    text = str(raw or "")
    match = re.search(r"\{[^{}]*\}", text)  # tolerate fences/prose around JSON
    if match:
        try:
            text = str(json.loads(match.group()).get("category", ""))
        except ValueError:
            pass
    text = " ".join(text.strip().split()).strip("\"'.,;:")
    if not (3 <= len(text) <= 30) or len(text.split()) > 3:
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9&' -]*", text):
        return None
    return text[0].upper() + text[1:]


def _from_ai(title: str, author: str) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key or not title:
        return None
    body = json.dumps(
        {
            "model": os.environ.get("LMS_AI_MODEL") or _AI_MODEL_DEFAULT,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You name library shelf categories. Reply with JSON only: "
                        '{"category": "One-Short-Name"} — at most 3 words, a common '
                        "genre or subject label, no explanation."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Title: {title}\nAuthor: {author or 'unknown'}",
                },
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        _AI_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    try:
        with urllib.request.urlopen(request, timeout=_AI_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
    except Exception:
        logger.debug("AI category suggestion failed for %r", title, exc_info=True)
        return None
    return _clean_category(content)


def suggest_category(result: IsbnLookupResult) -> str | None:
    """Best new-category proposal for an unmatched lookup, or None.

    Stages run in order and the first hit wins: candidates, title rules,
    then the keyed AI call. Offline-safe — any failure ends in None.
    """
    return (
        _from_candidates(result.categories)
        or _from_title(result.title)
        or _from_ai(result.title, result.author)
    )
