"""
Celery processing tasks.

process_article   — normalize → dedupe → score → route to notify
cleanup_old_articles — housekeeping: delete articles older than 30 days
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, delete

from app.celery_app import celery_app
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.logging import log
from app.dedupe import hash as dedup_hash
from app.dedupe import similarity as dedup_sim
from app.models.article import Article
from app.models.signal import Signal
from app.models.source import Source
from app.normalize import cleaner
from app.normalize import langdetect as lang_mod
from app.score import rules as scorer


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@celery_app.task(
    name="app.tasks.process.process_article",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def process_article(self, article_id: int):
    """
    Full pipeline for a single article:
      1. Normalize text
      2. Deduplicate (hash + fuzzy)
      3. Score (keyword rules)
      4. Route to notify queue if score >= threshold
    """
    async def _inner():
        logger = log.bind(article_id=article_id)

        async with AsyncSessionLocal() as session:
            # ── Load article + source ──────────────────────────────────────
            article = await session.get(Article, article_id)
            if not article:
                logger.error("process_article: article not found")
                return

            source = await session.get(Source, article.source_id)
            source_priority = source.priority if source else 3

            # ── 1. Normalize ───────────────────────────────────────────────
            title_clean = cleaner.clean(article.title)
            body_clean = cleaner.clean(article.raw_text or "")
            lang = lang_mod.detect_lang(f"{title_clean} {body_clean}")

            article.cleaned_text = body_clean
            article.lang = lang
            article.status = "normalized"

            # ── 2. Deduplicate (hash) ──────────────────────────────────────
            h = dedup_hash.compute(title_clean, article.canonical_url)
            article.hash = h

            # Check for same hash in DB (exact URL + title match)
            dup_result = await session.execute(
                select(Article.id)
                .where(Article.hash == h)
                .where(Article.id != article_id)
                .limit(1)
            )
            dup_row = dup_result.fetchone()
            if dup_row:
                article.is_duplicate = True
                article.duplicate_of = dup_row[0]
                article.status = "duplicate"
                await session.commit()
                logger.info("process_article: exact duplicate", duplicate_of=dup_row[0])
                return

            # Check for same canonical URL (different hash — e.g. title updated)
            url_dup = await session.execute(
                select(Article.id)
                .where(Article.canonical_url == article.canonical_url)
                .where(Article.id != article_id)
                .limit(1)
            )
            url_dup_row = url_dup.fetchone()
            if url_dup_row:
                article.is_duplicate = True
                article.duplicate_of = url_dup_row[0]
                article.status = "duplicate"
                await session.commit()
                logger.info("process_article: URL duplicate", duplicate_of=url_dup_row[0])
                return

            # ── 2b. Fuzzy dedup (1-hour window) ───────────────────────────
            window_start = datetime.now(timezone.utc) - timedelta(hours=1)
            recent_result = await session.execute(
                select(Article.id, Article.cleaned_text)
                .where(Article.published_at >= window_start)
                .where(Article.id != article_id)
                .where(Article.is_duplicate.is_(False))
                .where(Article.cleaned_text.isnot(None))
                .limit(200)
            )
            recent_rows = recent_result.fetchall()

            # Build candidates from title (first sentence of cleaned_text ≈ title)
            candidates = [(row[0], row[1][:120]) for row in recent_rows if row[1]]
            fuzzy_dup_id = dedup_sim.find_duplicate(title_clean, candidates)
            if fuzzy_dup_id:
                article.is_duplicate = True
                article.duplicate_of = fuzzy_dup_id
                article.status = "duplicate"
                await session.commit()
                logger.info("process_article: fuzzy duplicate", duplicate_of=fuzzy_dup_id)
                return

            # ── 3. Score ───────────────────────────────────────────────────
            impact_score, reasons, categories = scorer.evaluate(
                title=title_clean,
                body=body_clean,
                source_priority=source_priority,
                published_at=article.published_at,
            )

            signal = Signal(
                article_id=article_id,
                impact_score=impact_score,
                reasons=reasons,
                tickers=[],        # ticker extraction → v2 (NER)
                categories=categories,
                status="pending",
            )
            session.add(signal)
            article.status = "scored"
            await session.flush()   # get signal.id before commit
            signal_id = signal.id
            await session.commit()

            logger.info(
                "process_article: scored",
                score=impact_score,
                reasons=reasons,
                categories=categories,
            )

        # ── 4. Route ───────────────────────────────────────────────────────
        if impact_score >= settings.impact_threshold:
            from app.tasks.notify import send_signal
            send_signal.apply_async(args=[signal_id], queue="notify")
            logger.info("process_article: queued for notify", signal_id=signal_id)
        else:
            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(Signal)
                    .where(Signal.id == signal_id)
                    .values(status="suppressed")
                )
                await session.commit()
            logger.info(
                "process_article: suppressed (below threshold)",
                score=impact_score,
                threshold=settings.impact_threshold,
            )

    try:
        _run(_inner())
    except Exception as exc:
        log.error("process_article: unhandled error", article_id=article_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(name="app.tasks.process.cleanup_old_articles")
def cleanup_old_articles():
    """Delete articles (and cascaded signals/deliveries) older than 30 days."""
    async def _inner():
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(Article).where(Article.created_at < cutoff)
            )
            await session.commit()
            log.info("cleanup_old_articles: done", deleted=result.rowcount)

    _run(_inner())
