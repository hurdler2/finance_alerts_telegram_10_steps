"""
Celery notification tasks.

send_signal              — formats and sends one Telegram alert, logs delivery.
retry_failed_deliveries  — re-queues failed deliveries (beat every 10 min).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.celery_app import celery_app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import log
from app.models.article import Article
from app.models.delivery import Delivery
from app.models.signal import Signal
from app.models.source import Source
from app.notify import formatter
from app.notify.telegram import TelegramNotifier

_notifier = TelegramNotifier()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(
    name="app.tasks.notify.send_signal",
    bind=True,
    max_retries=3,
)
def send_signal(self, signal_id: int):
    """
    1. Load signal + article + source
    2. Format Telegram message
    3. POST to Telegram Bot API
    4. Insert delivery log row (sent / failed)
    5. On failure: retry with exponential backoff (10s → 20s → 40s)
    """
    async def _inner():
        logger = log.bind(signal_id=signal_id)

        async with AsyncSessionLocal() as session:
            # Load signal
            signal = await session.get(Signal, signal_id)
            if not signal:
                logger.error("send_signal: signal not found")
                return

            # Load article
            article = await session.get(Article, signal.article_id)
            if not article:
                logger.error("send_signal: article not found")
                return

            # Load source
            source = await session.get(Source, article.source_id)
            source_name = source.name if source else "Unknown Source"

            # Determine target channel
            channel_id = settings.telegram_channel_id
            if not channel_id:
                logger.error("send_signal: TELEGRAM_CHANNEL_ID not configured")
                await session.execute(
                    update(Signal).where(Signal.id == signal_id).values(status="failed")
                )
                await session.commit()
                return

            # Format message
            text = formatter.render(
                impact_score=signal.impact_score,
                title=article.title,
                reasons=signal.reasons,
                source_name=source_name,
                published_at=article.published_at,
                url=article.canonical_url,
            )

            # Attempt number for this task
            attempt = self.request.retries + 1

            # Send
            result = _notifier.send(text=text, channel_id=channel_id)

            if result.success:
                # Log successful delivery
                delivery = Delivery(
                    signal_id=signal_id,
                    channel="telegram",
                    channel_id=channel_id,
                    status="sent",
                    attempt=attempt,
                    sent_at=datetime.now(timezone.utc),
                )
                session.add(delivery)
                await session.execute(
                    update(Signal).where(Signal.id == signal_id).values(status="sent")
                )
                await session.commit()
                logger.info(
                    "send_signal: delivered",
                    channel=channel_id,
                    message_id=result.message_id,
                    score=signal.impact_score,
                )

            else:
                # Log failed attempt
                delivery = Delivery(
                    signal_id=signal_id,
                    channel="telegram",
                    channel_id=channel_id,
                    status="failed",
                    attempt=attempt,
                    error=result.error,
                )
                session.add(delivery)
                await session.commit()
                logger.warning("send_signal: delivery failed", error=result.error)

                # Determine retry countdown: 10s, 20s, 40s
                countdown = 10 * (2 ** self.request.retries)

                # Check for rate-limit hint from Telegram
                if result.error and "retry_after=" in result.error:
                    try:
                        countdown = int(result.error.split("retry_after=")[1]) + 2
                    except (ValueError, IndexError):
                        pass

                raise self.retry(exc=Exception(result.error), countdown=countdown)

    try:
        _run(_inner())
    except self.MaxRetriesExceededError:
        # Mark delivery as permanent failure
        async def _mark_permanent():
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Signal).where(Signal.id == signal_id).values(status="failed")
                )
                # Update last delivery attempt to permanent_failure
                await session.execute(
                    update(Delivery)
                    .where(Delivery.signal_id == signal_id)
                    .where(Delivery.status == "failed")
                    .values(status="permanent_failure")
                )
                await session.commit()
        _run(_mark_permanent())
        log.error("send_signal: permanent failure", signal_id=signal_id)


@celery_app.task(name="app.tasks.notify.retry_failed_deliveries")
def retry_failed_deliveries():
    """
    Beat task (every 10 min).
    Find signals in 'pending' or 'failed' state older than 5 minutes
    that have no 'sent' delivery — re-queue them.
    """
    async def _inner():
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)

        async with AsyncSessionLocal() as session:
            # Signals that never reached 'sent' and are not 'suppressed'/'duplicate'
            result = await session.execute(
                select(Signal.id)
                .where(Signal.status.in_(["pending", "failed"]))
                .where(Signal.created_at < cutoff)
                .limit(50)
            )
            signal_ids = [row[0] for row in result.fetchall()]

        if not signal_ids:
            return

        log.info("retry_failed_deliveries: re-queuing", count=len(signal_ids))
        for sid in signal_ids:
            send_signal.apply_async(args=[sid], queue="notify")

    _run(_inner())
