"""
Celery ingest tasks.

fetch_all_sources  — Beat-triggered every 5 min; fans out to fetch_source per source.
fetch_source       — Fetches one RSS feed, upserts articles, queues process_article.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.core.logging import log
from app.ingest import rss as rss_parser
from app.ingest import scraper
from app.models.article import Article
from app.models.source import Source


# ── helpers ───────────────────────────────────────────────────────────────────

def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _quick_hash(title: str, url: str) -> str:
    """sha256(lowercase_title|canonical_url) — fast pre-DB dedup key."""
    payload = f"{title.lower().strip()}|{url}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ── tasks ─────────────────────────────────────────────────────────────────────

@celery_app.task(name="app.tasks.ingest.fetch_all_sources", bind=True, max_retries=0)
def fetch_all_sources(self):
    """Fan-out: queue one fetch_source per enabled source with staggered start."""
    async def _inner():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Source).where(Source.enabled.is_(True))
            )
            sources = result.scalars().all()

        if not sources:
            log.warning("fetch_all_sources: no enabled sources found")
            return

        log.info("fetch_all_sources: dispatching", count=len(sources))
        for i, source in enumerate(sources):
            fetch_source.apply_async(
                args=[source.id],
                queue="ingest",
                countdown=i * 2,  # stagger 2 s apart to avoid burst
            )

    _run(_inner())


@celery_app.task(
    name="app.tasks.ingest.fetch_source",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def fetch_source(self, source_id: int):
    """
    1. Load source from DB
    2. Fetch RSS feed
    3. For each new article: upsert → queue process_article
    4. Update source.last_checked_at (or error fields on failure)
    """
    async def _inner():
        logger = log.bind(source_id=source_id)

        async with AsyncSessionLocal() as session:
            source = await session.get(Source, source_id)
            if not source:
                logger.error("fetch_source: source not found")
                return

            logger = logger.bind(source=source.slug)

            # ── Fetch RSS ──────────────────────────────────────────────────
            try:
                articles_raw = rss_parser.fetch(
                    source_id=source.id,
                    source_slug=source.slug,
                    rss_url=source.rss_url,
                )
            except (httpx.HTTPError, Exception) as exc:
                await session.execute(
                    update(Source)
                    .where(Source.id == source_id)
                    .values(
                        last_error_at=datetime.now(timezone.utc),
                        last_error_msg=str(exc)[:500],
                        consecutive_errors=Source.consecutive_errors + 1,
                    )
                )
                await session.commit()
                logger.warning("fetch_source: RSS fetch failed", error=str(exc))
                raise self.retry(exc=exc)

            # ── Optional body scraping ─────────────────────────────────────
            for art in articles_raw:
                if source.scrape_allowed and len(art.summary) < 200:
                    body = scraper.fetch_body(art.canonical_url)
                    if body:
                        art.raw_html = body

            # ── Upsert articles ───────────────────────────────────────────
            new_ids: list[int] = []
            for art in articles_raw:
                h = _quick_hash(art.title, art.canonical_url)
                stmt = (
                    pg_insert(Article)
                    .values(
                        source_id=art.source_id,
                        url=art.url,
                        canonical_url=art.canonical_url,
                        hash=h,
                        title=art.title,
                        raw_text=art.raw_html or art.summary,
                        published_at=art.published_at,
                        status="raw",
                    )
                    .on_conflict_do_nothing(index_elements=["hash"])
                    .returning(Article.id)
                )
                result = await session.execute(stmt)
                row = result.fetchone()
                if row:
                    new_ids.append(row[0])

            # ── Update source heartbeat ───────────────────────────────────
            await session.execute(
                update(Source)
                .where(Source.id == source_id)
                .values(
                    last_checked_at=datetime.now(timezone.utc),
                    last_error_msg=None,
                    consecutive_errors=0,
                )
            )
            await session.commit()

        logger.info("fetch_source: complete", new_articles=len(new_ids))

        # ── Queue processing for each new article ──────────────────────────
        from app.tasks.process import process_article
        for article_id in new_ids:
            process_article.apply_async(args=[article_id], queue="default")

    _run(_inner())
