"""
Tests for admin API endpoints.
Uses in-memory SQLite for isolation (no Docker needed).
"""
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

from app.main import app
from app.core.config import settings

VALID_TOKEN = settings.admin_token
AUTH_HEADERS = {"Authorization": f"Bearer {VALID_TOKEN}"}
BAD_HEADERS = {"Authorization": "Bearer wrong_token"}


# ── Auth guard ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/admin/sources")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_rejects_wrong_token():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/admin/sources", headers=BAD_HEADERS)
    assert response.status_code == 401


# ── /admin/stats ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_returns_expected_keys():
    mock_scalar = AsyncMock(return_value=0)

    with patch("app.api.admin.AsyncSessionLocal") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session.execute = AsyncMock(return_value=AsyncMock(scalar=mock_scalar))
        mock_session_cls.return_value = mock_session

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/admin/stats", headers=AUTH_HEADERS)

    assert response.status_code == 200
    data = response.json()
    for key in ("enabled_sources", "total_articles", "total_signals",
                "deliveries_sent", "deliveries_failed"):
        assert key in data


# ── /admin/config/threshold ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_threshold_valid():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.patch(
            "/admin/config/threshold",
            json={"impact_threshold": 75},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 200
    assert response.json()["impact_threshold"] == 75
    # Reset
    settings.impact_threshold = 60


@pytest.mark.asyncio
async def test_set_threshold_out_of_range():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.patch(
            "/admin/config/threshold",
            json={"impact_threshold": 150},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 400


# ── /stripe/webhook ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stripe_webhook_invalid_signature():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            "/stripe/webhook",
            content=b'{"type":"test"}',
            headers={
                "stripe-signature": "invalid",
                "content-type": "application/json",
            },
        )
    # Without STRIPE_WEBHOOK_SECRET configured, expect 500;
    # with bad signature, expect 400
    assert response.status_code in (400, 500)
