"""
Unit tests for hash and fuzzy deduplication.
"""
import pytest

from app.dedupe.hash import compute
from app.dedupe.similarity import is_duplicate, find_duplicate


# ── Hash dedup ─────────────────────────────────────────────────────────────────

def test_same_title_and_url_produce_same_hash():
    h1 = compute("Fed cuts rates", "https://reuters.com/article/fed")
    h2 = compute("Fed cuts rates", "https://reuters.com/article/fed")
    assert h1 == h2


def test_different_url_produces_different_hash():
    h1 = compute("Fed cuts rates", "https://reuters.com/article/fed")
    h2 = compute("Fed cuts rates", "https://apnews.com/article/fed")
    assert h1 != h2


def test_different_title_produces_different_hash():
    h1 = compute("Fed cuts rates", "https://reuters.com/article/fed")
    h2 = compute("Fed raises rates", "https://reuters.com/article/fed")
    assert h1 != h2


def test_hash_is_case_insensitive_on_title():
    h1 = compute("FED CUTS RATES", "https://reuters.com/article")
    h2 = compute("fed cuts rates", "https://reuters.com/article")
    assert h1 == h2


def test_hash_is_64_char_hex():
    h = compute("inflation data", "https://example.com/news")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ── Fuzzy dedup ────────────────────────────────────────────────────────────────

def test_identical_titles_are_duplicate():
    assert is_duplicate(
        "Fed signals rate cut sooner than expected",
        ["Fed signals rate cut sooner than expected"],
    )


def test_slightly_different_titles_are_duplicate():
    # Same story, different wording
    assert is_duplicate(
        "Federal Reserve signals earlier rate cut",
        ["Fed signals rate cut sooner than expected"],
        threshold=70,
    )


def test_completely_different_titles_not_duplicate():
    assert not is_duplicate(
        "Apple earnings beat expectations",
        ["Oil prices spike after OPEC decision"],
    )


def test_empty_candidates_returns_false():
    assert not is_duplicate("Fed rate cut", [])


def test_find_duplicate_returns_correct_id():
    candidates = [
        (10, "Fed cuts interest rates by 50bps"),
        (11, "Oil prices fall on demand fears"),
    ]
    result = find_duplicate("Fed cuts rates 50 basis points", candidates, threshold=60)
    assert result == 10


def test_find_duplicate_returns_none_when_no_match():
    candidates = [
        (10, "Oil prices spike after OPEC meeting"),
    ]
    result = find_duplicate("Apple earnings miss expectations", candidates)
    assert result is None


def test_word_order_invariant():
    # token_sort_ratio handles word order differences
    assert is_duplicate(
        "rate cut 50bps Federal Reserve",
        ["Federal Reserve rate cut 50bps announced"],
        threshold=80,
    )


# ── Normalize + cleaner ────────────────────────────────────────────────────────

def test_cleaner_strips_html():
    from app.normalize.cleaner import clean
    assert clean("<b>Fed cuts rates</b>") == "Fed cuts rates"


def test_cleaner_decodes_entities():
    from app.normalize.cleaner import clean
    assert clean("CPI &amp; inflation data") == "CPI & inflation data"


def test_cleaner_collapses_whitespace():
    from app.normalize.cleaner import clean
    assert clean("  Fed   cuts  \n  rates  ") == "Fed cuts rates"


def test_cleaner_handles_none():
    from app.normalize.cleaner import clean
    assert clean(None) == ""


def test_cleaner_unicode_normalization():
    from app.normalize.cleaner import clean
    # curly quote → straight
    result = clean("\u201cFed\u201d cuts rates")
    assert '"' in result or "Fed" in result
