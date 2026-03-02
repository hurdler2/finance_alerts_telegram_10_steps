"""
Scraping fallback using trafilatura.
Only called when source.scrape_allowed = True AND RSS summary is too short.
"""
import trafilatura
from trafilatura.settings import use_config

from app.core.config import settings

_trafilatura_config = use_config()
_trafilatura_config.set("DEFAULT", "DOWNLOAD_TIMEOUT", "12")


def fetch_body(url: str, min_length: int = 200) -> str | None:
    """
    Fetch and extract article body from URL.
    Returns cleaned text or None if extraction fails / content too short.
    """
    try:
        downloaded = trafilatura.fetch_url(
            url,
            config=_trafilatura_config,
            headers={"User-Agent": settings.user_agent if hasattr(settings, "user_agent") else
                     "FinanceAlertsBot/1.0"},
        )
        if not downloaded:
            return None

        text = trafilatura.extract(
            downloaded,
            favor_recall=True,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if text and len(text) >= min_length:
            return text
        return None
    except Exception:
        return None
