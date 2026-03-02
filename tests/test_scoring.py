"""
Unit tests for the rule-based impact scorer.
No DB, no network — pure function tests.
"""
import pytest
from datetime import datetime, timezone

from app.score.rules import evaluate


# ── High-impact scenarios ──────────────────────────────────────────────────────

def test_fed_rate_cut_in_title_scores_high():
    score, reasons, _ = evaluate(
        title="Fed cuts interest rates by 50 basis points",
        body="The Federal Reserve cut rates amid slowing economic growth.",
    )
    assert score >= 60
    assert any("rate cut" in r or "fed" in r.lower() for r in reasons)


def test_bank_run_in_title_scores_very_high():
    score, reasons, _ = evaluate(
        title="Bank run triggers emergency rate decision at major lender",
        body="Customers withdrew billions in a single day.",
    )
    assert score >= 80


def test_earnings_miss_scores_medium_high():
    score, reasons, _ = evaluate(
        title="Apple reports earnings miss as iPhone sales disappoint",
        body="Revenue came in below analyst expectations for Q2.",
    )
    assert score >= 40
    assert "earnings miss" in reasons


def test_recession_fear_scores_high():
    score, reasons, _ = evaluate(
        title="US economy enters recession, GDP contracts two quarters",
        body="Economic output shrank for the second consecutive quarter.",
    )
    assert score >= 55
    assert "recession" in reasons or "gdp" in reasons


# ── Low-impact / no match ──────────────────────────────────────────────────────

def test_irrelevant_article_scores_low():
    score, reasons, _ = evaluate(
        title="Company unveils new product lineup for summer",
        body="The tech firm announced several consumer devices.",
    )
    assert score < 30
    assert reasons == []


def test_empty_text_scores_near_zero():
    score, _, _ = evaluate(title="", body="", source_priority=3)
    # Only source priority bonus (priority 3 = +9)
    assert score <= 15


# ── Priority and recency bonuses ───────────────────────────────────────────────

def test_priority_1_source_bonus():
    score_p1, _, _ = evaluate(title="inflation data released", body="", source_priority=1)
    score_p5, _, _ = evaluate(title="inflation data released", body="", source_priority=5)
    assert score_p1 > score_p5


def test_recency_bonus_recent_article():
    now = datetime.now(timezone.utc)
    score_recent, _, _ = evaluate(title="fomc meeting", body="", published_at=now)
    score_old, _, _ = evaluate(
        title="fomc meeting",
        body="",
        published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert score_recent > score_old


# ── Category inference ─────────────────────────────────────────────────────────

def test_macro_category_inferred():
    _, _, categories = evaluate(
        title="Fed raises rates sharply amid inflation fears",
        body="",
    )
    assert "macro" in categories


def test_crypto_category_inferred():
    _, _, categories = evaluate(
        title="SEC charges crypto exchange with fraud",
        body="",
    )
    assert "crypto" in categories


def test_multiple_categories():
    _, _, categories = evaluate(
        title="Bank collapse triggers recession fears and crypto selloff",
        body="",
    )
    assert len(categories) >= 2


# ── Score is capped ────────────────────────────────────────────────────────────

def test_score_never_exceeds_100():
    # Pile on every possible keyword
    mega_title = (
        "emergency rate bank run default bankruptcy financial crisis "
        "rate hike fomc fed ecb recession sanctions war"
    )
    score, _, _ = evaluate(title=mega_title, body=mega_title, source_priority=1)
    assert score <= 100


# ── Reasons list ──────────────────────────────────────────────────────────────

def test_reasons_max_5():
    title = "rate hike inflation cpi fomc fed ecb recession default sanctions"
    _, reasons, _ = evaluate(title=title, body="")
    assert len(reasons) <= 5


def test_reasons_no_duplicates():
    title = "fed rate cut fed rate cut again"
    _, reasons, _ = evaluate(title=title, body="")
    assert len(reasons) == len(set(reasons))
