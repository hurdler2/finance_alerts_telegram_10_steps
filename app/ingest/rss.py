"""
RSS/Atom feed parser.
Returns a list of RawArticle dataclasses ready for DB upsert.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

import feedparser
import httpx

from app.core.config import settings
from app.core.logging import log
from app.ingest import canonical as canon

_USER_AGENT = "FinanceAlertsBot/1.0 (+https://github.com/finance-alerts)"
_REQUEST_TIMEOUT = 15  # seconds
_MAX_ARTICLES = 50


@dataclass
class RawArticle:
    source_id: int
    source_slug: str
    url: str
    canonical_url: str
    title: str
    summary: str
    published_at: Optional[datetime]
    raw_html: Optional[str] = None   # set only when scrape_allowed


def _parse_date(entry) -> datetime | None:
    """Try multiple feedparser date fields and return UTC datetime or None."""
    for attr in ("published", "updated", "created"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                pass
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None


def _clean_html(text: str | None) -> str:
    """Strip HTML tags from summary text."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _best_summary(entry) -> str:
    """Pick the longest available summary / content field."""
    candidates = []

    # content[] preferred over summary
    for content in getattr(entry, "content", []):
        candidates.append(_clean_html(content.get("value", "")))

    if hasattr(entry, "summary"):
        candidates.append(_clean_html(entry.summary))

    if candidates:
        return max(candidates, key=len)
    return ""


def fetch(source_id: int, source_slug: str, rss_url: str) -> list[RawArticle]:
    """
    Fetch and parse an RSS/Atom feed.
    Returns up to _MAX_ARTICLES RawArticle objects.
    Raises httpx.HTTPError on network failure (let caller handle retry).
    """
    logger = log.bind(source=source_slug)

    # Download raw feed bytes
    try:
        response = httpx.get(
            rss_url,
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("RSS HTTP error", status=exc.response.status_code, url=rss_url)
        raise
    except httpx.RequestError as exc:
        logger.warning("RSS request error", error=str(exc), url=rss_url)
        raise

    # Parse with feedparser (works on both RSS and Atom)
    feed = feedparser.parse(response.content)

    if feed.bozo and feed.bozo_exception:
        logger.warning("Feed parse warning", exc=str(feed.bozo_exception))

    articles: list[RawArticle] = []
    entries = feed.entries[:_MAX_ARTICLES]

    for entry in entries:
        link = getattr(entry, "link", None) or getattr(entry, "id", None)
        title = getattr(entry, "title", "").strip()

        if not link or not title:
            continue

        canonical_url = canon.normalize(link)
        summary = _best_summary(entry)
        published_at = _parse_date(entry)

        articles.append(
            RawArticle(
                source_id=source_id,
                source_slug=source_slug,
                url=link,
                canonical_url=canonical_url,
                title=title,
                summary=summary,
                published_at=published_at,
            )
        )

    logger.info("RSS fetched", count=len(articles))
    return articles
