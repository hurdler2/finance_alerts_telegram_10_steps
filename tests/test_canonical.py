import pytest
from app.ingest.canonical import normalize


def test_strips_utm_params():
    url = "https://reuters.com/article/fed?utm_source=newsletter&utm_medium=email"
    assert normalize(url) == "https://reuters.com/article/fed"


def test_strips_fbclid():
    url = "https://cnbc.com/news?fbclid=IwAR123abc"
    assert normalize(url) == "https://cnbc.com/news"


def test_preserves_real_params():
    url = "https://example.com/search?q=inflation&page=2"
    result = normalize(url)
    assert "q=inflation" in result
    assert "page=2" in result


def test_drops_fragment():
    url = "https://ft.com/article/rates#comments"
    assert "#" not in normalize(url)


def test_lowercases_scheme_and_host():
    url = "HTTPS://Reuters.COM/article"
    result = normalize(url)
    assert result.startswith("https://reuters.com/")


def test_strips_mixed_params():
    url = "https://wsj.com/article?ref=home&utm_campaign=daily&id=123"
    result = normalize(url)
    assert "utm_campaign" not in result
    assert "ref=" not in result
    assert "id=123" in result


def test_empty_url_returns_as_is():
    assert normalize("") == ""
