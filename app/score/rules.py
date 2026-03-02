"""
Rule-based impact scorer.
Returns (impact_score: int, reasons: list[str], categories: list[str]).
No external dependencies — pure Python.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.score.categories import (
    KEYWORD_WEIGHTS,
    TITLE_MULTIPLIER,
    recency_bonus,
    source_priority_bonus,
)

# Category inference from matched keywords
_CATEGORY_HINTS: dict[str, str] = {
    "rate hike": "macro", "rate cut": "macro", "fomc": "macro",
    "federal reserve": "macro", "fed ": "macro", "ecb ": "macro",
    "inflation": "macro", "cpi": "macro", "gdp": "macro",
    "nonfarm payroll": "macro", "jobs report": "macro", "recession": "macro",
    "earnings beat": "earnings", "earnings miss": "earnings",
    "earnings surprise": "earnings", "profit warning": "earnings",
    "guidance cut": "earnings", "guidance raise": "earnings",
    "layoffs": "earnings", "merger": "earnings", "acquisition": "earnings",
    "sanctions": "geopolitical", "war": "geopolitical", "tariff": "geopolitical",
    "election": "geopolitical", "coup": "geopolitical",
    "oil spike": "energy", "opec": "energy", "energy crisis": "energy",
    "crude oil": "energy",
    "bank run": "banking", "bank collapse": "banking", "bailout": "banking",
    "default": "banking", "bankruptcy": "banking",
    "crypto ban": "crypto", "exchange collapse": "crypto",
    "bitcoin etf": "crypto", "crypto regulation": "crypto",
    "sec charges": "crypto",
}


def evaluate(
    title: str,
    body: str,
    source_priority: int = 3,
    published_at: datetime | None = None,
) -> tuple[int, list[str], list[str]]:
    """
    Score an article.

    Args:
        title:           cleaned article title
        body:            cleaned article body / summary
        source_priority: 1 (highest) – 5 (lowest)
        published_at:    UTC datetime of article publish time

    Returns:
        (impact_score, reasons, categories)
        impact_score: clamped to 0–100
        reasons:      list of matched keyword phrases (max 5)
        categories:   deduplicated list of inferred categories
    """
    title_lower = title.lower()
    body_lower = body.lower()

    score = 0
    matched_keywords: list[tuple[str, int]] = []  # (keyword, weighted_score)
    inferred_categories: set[str] = set()

    for keyword, base_weight in KEYWORD_WEIGHTS:
        in_title = keyword in title_lower
        in_body = keyword in body_lower

        if in_title:
            w = round(base_weight * TITLE_MULTIPLIER)
            matched_keywords.append((keyword.strip(), w))
            score += w
        elif in_body:
            matched_keywords.append((keyword.strip(), base_weight))
            score += base_weight

        if in_title or in_body:
            cat = _CATEGORY_HINTS.get(keyword)
            if cat:
                inferred_categories.add(cat)

    # Source priority bonus
    score += source_priority_bonus(source_priority)

    # Recency bonus
    if published_at:
        now = datetime.now(timezone.utc)
        age_minutes = (now - published_at).total_seconds() / 60
        score += recency_bonus(max(0, age_minutes))

    # Cap at 100
    score = min(score, 100)

    # Build reasons: top matched keywords by weight (max 5, deduplicated)
    seen: set[str] = set()
    reasons: list[str] = []
    for kw, _ in sorted(matched_keywords, key=lambda x: -x[1]):
        kw_clean = kw.strip()
        if kw_clean not in seen:
            reasons.append(kw_clean)
            seen.add(kw_clean)
        if len(reasons) >= 5:
            break

    categories = sorted(inferred_categories) or ["general"]

    return score, reasons, categories
