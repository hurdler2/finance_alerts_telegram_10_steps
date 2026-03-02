"""
Tests for the RSS parser.
Uses a minimal in-memory fake feed — no network calls.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.ingest.rss import fetch, RawArticle


FAKE_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Finance Feed</title>
    <link>https://example.com</link>
    <item>
      <title>Fed raises rates by 50bps</title>
      <link>https://example.com/fed-rates?utm_source=rss</link>
      <description>The Federal Reserve raised interest rates by 50 basis points.</description>
      <pubDate>Mon, 02 Mar 2026 14:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Oil prices spike on OPEC news</title>
      <link>https://example.com/oil-opec</link>
      <description>Crude oil jumped 3% after OPEC announced production cuts.</description>
      <pubDate>Mon, 02 Mar 2026 13:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def mock_http_response():
    resp = MagicMock()
    resp.content = FAKE_RSS
    resp.raise_for_status = MagicMock()
    return resp


def test_fetch_returns_raw_articles(mock_http_response):
    with patch("app.ingest.rss.httpx.get", return_value=mock_http_response):
        articles = fetch(source_id=1, source_slug="test_feed", rss_url="https://example.com/rss")

    assert len(articles) == 2
    assert all(isinstance(a, RawArticle) for a in articles)


def test_fetch_strips_utm_from_url(mock_http_response):
    with patch("app.ingest.rss.httpx.get", return_value=mock_http_response):
        articles = fetch(source_id=1, source_slug="test_feed", rss_url="https://example.com/rss")

    fed_article = articles[0]
    assert "utm_source" not in fed_article.canonical_url
    assert fed_article.canonical_url == "https://example.com/fed-rates"


def test_fetch_parses_title(mock_http_response):
    with patch("app.ingest.rss.httpx.get", return_value=mock_http_response):
        articles = fetch(source_id=1, source_slug="test_feed", rss_url="https://example.com/rss")

    assert articles[0].title == "Fed raises rates by 50bps"
    assert articles[1].title == "Oil prices spike on OPEC news"


def test_fetch_parses_published_at(mock_http_response):
    with patch("app.ingest.rss.httpx.get", return_value=mock_http_response):
        articles = fetch(source_id=1, source_slug="test_feed", rss_url="https://example.com/rss")

    assert articles[0].published_at is not None
    assert articles[0].published_at.tzinfo == timezone.utc


def test_fetch_raises_on_http_error():
    import httpx
    with patch("app.ingest.rss.httpx.get", side_effect=httpx.RequestError("timeout")):
        with pytest.raises(httpx.RequestError):
            fetch(source_id=1, source_slug="bad_feed", rss_url="https://bad.example.com/rss")


def test_fetch_skips_entries_without_title():
    no_title_rss = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><link>https://example.com/a</link></item>
      <item><title>Valid</title><link>https://example.com/b</link></item>
    </channel></rss>"""
    resp = MagicMock()
    resp.content = no_title_rss
    resp.raise_for_status = MagicMock()

    with patch("app.ingest.rss.httpx.get", return_value=resp):
        articles = fetch(source_id=1, source_slug="test", rss_url="https://x.com/rss")

    assert len(articles) == 1
    assert articles[0].title == "Valid"
