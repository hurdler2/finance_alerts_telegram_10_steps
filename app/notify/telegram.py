"""
Telegram Bot API adapter.
Uses httpx for direct REST calls — no third-party bot SDK needed.

Rate limit: Telegram allows ~30 messages/second globally,
and 1 message/second per chat. We rely on Celery task spacing + retries.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import log
from app.notify.base import BaseNotifier, DeliveryResult

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 10  # seconds


class TelegramNotifier(BaseNotifier):
    def __init__(self, token: str | None = None):
        self._token = token or settings.telegram_bot_token

    def _url(self, method: str) -> str:
        return _BASE_URL.format(token=self._token, method=method)

    def send(self, text: str, channel_id: str) -> DeliveryResult:
        """
        POST sendMessage to Telegram Bot API.
        Returns DeliveryResult with success flag and message_id or error.
        """
        if not self._token:
            return DeliveryResult(success=False, error="TELEGRAM_BOT_TOKEN not configured")

        payload = {
            "chat_id": channel_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            response = httpx.post(
                self._url("sendMessage"),
                json=payload,
                timeout=_TIMEOUT,
            )
        except httpx.RequestError as exc:
            log.warning("telegram: request error", error=str(exc))
            return DeliveryResult(success=False, error=f"RequestError: {exc}")

        if response.status_code == 429:
            # Rate limited — return error so Celery retries with backoff
            retry_after = response.json().get("parameters", {}).get("retry_after", 30)
            log.warning("telegram: rate limited", retry_after=retry_after)
            return DeliveryResult(
                success=False,
                error=f"RateLimited:retry_after={retry_after}",
            )

        if not response.is_success:
            err = response.text[:200]
            log.warning("telegram: API error", status=response.status_code, body=err)
            return DeliveryResult(
                success=False,
                error=f"HTTP {response.status_code}: {err}",
            )

        data = response.json()
        if not data.get("ok"):
            err = data.get("description", "unknown error")
            log.warning("telegram: API not ok", description=err)
            return DeliveryResult(success=False, error=err)

        message_id = str(data["result"]["message_id"])
        log.info("telegram: sent", channel=channel_id, message_id=message_id)
        return DeliveryResult(success=True, message_id=message_id)
