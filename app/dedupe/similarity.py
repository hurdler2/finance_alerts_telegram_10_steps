"""
Fuzzy title-based deduplication using rapidfuzz.
Catches same story from different outlets with slightly different titles.
"""
from __future__ import annotations

from rapidfuzz import fuzz

# Articles with similarity above this threshold are considered duplicates
DEFAULT_THRESHOLD = 85


def is_duplicate(
    title: str,
    candidates: list[str],
    threshold: int = DEFAULT_THRESHOLD,
) -> bool:
    """
    Returns True if `title` is sufficiently similar to any candidate title.

    Uses token_sort_ratio: handles word-order differences well
    (e.g. "Fed cuts rates 50bps" vs "50bps rate cut by Federal Reserve").
    """
    title_lower = title.lower()
    for candidate in candidates:
        score = fuzz.token_sort_ratio(title_lower, candidate.lower())
        if score >= threshold:
            return True
    return False


def find_duplicate(
    title: str,
    candidates: list[tuple[int, str]],  # (article_id, title)
    threshold: int = DEFAULT_THRESHOLD,
) -> int | None:
    """
    Returns the article_id of the first duplicate found, or None.
    `candidates` is a list of (article_id, title) pairs.
    """
    title_lower = title.lower()
    for article_id, candidate_title in candidates:
        score = fuzz.token_sort_ratio(title_lower, candidate_title.lower())
        if score >= threshold:
            return article_id
    return None
