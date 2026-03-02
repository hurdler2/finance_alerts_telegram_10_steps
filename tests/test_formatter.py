"""
Unit tests for the Telegram message formatter.
"""
import pytest
from datetime import datetime, timezone

from app.notify.formatter import render, _score_emoji


# ── Emoji selection ────────────────────────────────────────────────────────────

def test_high_score_uses_alarm_emoji():
    assert _score_emoji(80) == "🚨"
    assert _score_emoji(95) == "🚨"


def test_medium_score_uses_megaphone_emoji():
    assert _score_emoji(65) == "📢"
    assert _score_emoji(79) == "📢"


def test_low_score_uses_pin_emoji():
    assert _score_emoji(60) == "📌"
    assert _score_emoji(0) == "📌"


# ── render() output structure ──────────────────────────────────────────────────

def test_render_contains_score():
    text = render(
        impact_score=82,
        title="Fed signals rate cut",
        reasons=["rate cut", "Fed"],
        source_name="Reuters",
        published_at=datetime(2026, 3, 2, 14, 5, tzinfo=timezone.utc),
        url="https://reuters.com/article",
    )
    assert "[IMPACT 82]" in text


def test_render_contains_title():
    text = render(82, "Fed signals rate cut", [], "Reuters", None, "https://x.com")
    assert "Fed signals rate cut" in text


def test_render_contains_url():
    url = "https://reuters.com/article/fed-rates"
    text = render(82, "Fed cuts", [], "Reuters", None, url)
    assert url in text


def test_render_contains_source_name():
    text = render(70, "Inflation data", [], "CNBC", None, "https://cnbc.com/x")
    assert "CNBC" in text


def test_render_contains_reasons():
    text = render(
        75, "CPI rises", ["inflation", "CPI", "Fed"], "AP", None, "https://ap.com/x"
    )
    assert "inflation" in text
    assert "CPI" in text


def test_render_max_3_reasons():
    text = render(
        75, "Big news", ["r1", "r2", "r3", "r4", "r5"], "AP", None, "https://x.com"
    )
    # Only first 3 reasons should appear
    assert "r4" not in text
    assert "r5" not in text


def test_render_timestamp_format():
    dt = datetime(2026, 3, 2, 14, 5, 0, tzinfo=timezone.utc)
    text = render(70, "Title", [], "Source", dt, "https://x.com")
    assert "2026-03-02" in text
    assert "14:05 UTC" in text


def test_render_handles_none_published_at():
    # Should not raise; uses current time instead
    text = render(70, "Title", [], "Source", None, "https://x.com")
    assert "UTC" in text


def test_render_truncates_long_title():
    long_title = "A" * 200
    text = render(70, long_title, [], "Source", None, "https://x.com")
    assert "A" * 121 not in text   # truncated at 120 + ellipsis
    assert "…" in text


def test_render_escapes_html_in_title():
    text = render(70, "S&P 500 <record>", [], "Source", None, "https://x.com")
    assert "<record>" not in text
    assert "&lt;record&gt;" in text


def test_render_stays_within_4096_chars():
    very_long = "x" * 5000
    text = render(70, very_long, [], "Source", None, "https://x.com/" + "y" * 3000)
    assert len(text) <= 4096


# ── Telegram adapter (mocked) ─────────────────────────────────────────────────

def test_telegram_send_success():
    from unittest.mock import patch, MagicMock
    from app.notify.telegram import TelegramNotifier

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.json.return_value = {
        "ok": True,
        "result": {"message_id": 42},
    }

    with patch("app.notify.telegram.httpx.post", return_value=mock_response):
        notifier = TelegramNotifier(token="fake_token")
        result = notifier.send("Hello", "@testchannel")

    assert result.success is True
    assert result.message_id == "42"
    assert result.error is None


def test_telegram_send_rate_limited():
    from unittest.mock import patch, MagicMock
    from app.notify.telegram import TelegramNotifier

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.json.return_value = {"parameters": {"retry_after": 15}}

    with patch("app.notify.telegram.httpx.post", return_value=mock_response):
        notifier = TelegramNotifier(token="fake_token")
        result = notifier.send("Hello", "@testchannel")

    assert result.success is False
    assert "retry_after=15" in result.error


def test_telegram_send_api_error():
    from unittest.mock import patch, MagicMock
    from app.notify.telegram import TelegramNotifier

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.is_success = False
    mock_response.text = "Bad Request: chat not found"

    with patch("app.notify.telegram.httpx.post", return_value=mock_response):
        notifier = TelegramNotifier(token="fake_token")
        result = notifier.send("Hello", "@badchannel")

    assert result.success is False
    assert "400" in result.error


def test_telegram_no_token_returns_error():
    from app.notify.telegram import TelegramNotifier
    notifier = TelegramNotifier(token="")
    result = notifier.send("Hello", "@channel")
    assert result.success is False
    assert "not configured" in result.error


def test_telegram_request_error():
    import httpx
    from unittest.mock import patch
    from app.notify.telegram import TelegramNotifier

    with patch("app.notify.telegram.httpx.post", side_effect=httpx.RequestError("timeout")):
        notifier = TelegramNotifier(token="fake_token")
        result = notifier.send("Hello", "@channel")

    assert result.success is False
    assert "RequestError" in result.error
