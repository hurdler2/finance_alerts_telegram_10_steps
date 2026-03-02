"""
Admin API endpoints.
All routes require Bearer token auth (ADMIN_TOKEN env var).
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.api.deps import require_admin
from app.core.database import AsyncSessionLocal
from app.models.article import Article
from app.models.delivery import Delivery
from app.models.signal import Signal
from app.models.source import Source

router = APIRouter(tags=["admin"])
AdminDep = Annotated[str, Depends(require_admin)]


# ── Sources ────────────────────────────────────────────────────────────────────

@router.get("/sources")
async def list_sources(_: AdminDep):
    """List all configured sources with their current status."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Source).order_by(Source.priority, Source.slug)
        )
        sources = result.scalars().all()

    return [
        {
            "id": s.id,
            "slug": s.slug,
            "name": s.name,
            "category": s.category,
            "priority": s.priority,
            "enabled": s.enabled,
            "last_checked_at": s.last_checked_at,
            "last_error_at": s.last_error_at,
            "last_error_msg": s.last_error_msg,
            "consecutive_errors": s.consecutive_errors,
        }
        for s in sources
    ]


class SourcePatch(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    poll_interval_minutes: int | None = None


@router.patch("/sources/{source_id}")
async def patch_source(source_id: int, body: SourcePatch, _: AdminDep):
    """Enable/disable a source or change its priority."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    async with AsyncSessionLocal() as session:
        source = await session.get(Source, source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        await session.execute(
            update(Source).where(Source.id == source_id).values(**updates)
        )
        await session.commit()

    return {"ok": True, "updated": updates}


# ── Signals ────────────────────────────────────────────────────────────────────

@router.get("/signals")
async def list_signals(
    _: AdminDep,
    limit: int = Query(50, ge=1, le=200),
    min_score: int = Query(0, ge=0, le=100),
    status_filter: str | None = Query(None, alias="status"),
):
    """List recent signals, optionally filtered by score or status."""
    async with AsyncSessionLocal() as session:
        q = (
            select(Signal, Article.title, Article.canonical_url, Article.published_at)
            .join(Article, Signal.article_id == Article.id)
            .where(Signal.impact_score >= min_score)
        )
        if status_filter:
            q = q.where(Signal.status == status_filter)
        q = q.order_by(Signal.created_at.desc()).limit(limit)

        result = await session.execute(q)
        rows = result.fetchall()

    return [
        {
            "signal_id": sig.id,
            "article_id": sig.article_id,
            "impact_score": sig.impact_score,
            "reasons": sig.reasons,
            "categories": sig.categories,
            "status": sig.status,
            "title": title,
            "url": url,
            "published_at": published_at,
            "created_at": sig.created_at,
        }
        for sig, title, url, published_at in rows
    ]


# ── Deliveries ─────────────────────────────────────────────────────────────────

@router.get("/deliveries")
async def list_deliveries(
    _: AdminDep,
    limit: int = Query(50, ge=1, le=200),
    status_filter: str | None = Query(None, alias="status"),
):
    """List recent delivery attempts."""
    async with AsyncSessionLocal() as session:
        q = select(Delivery).order_by(Delivery.created_at.desc()).limit(limit)
        if status_filter:
            q = q.where(Delivery.status == status_filter)
        result = await session.execute(q)
        deliveries = result.scalars().all()

    return [
        {
            "id": d.id,
            "signal_id": d.signal_id,
            "channel": d.channel,
            "channel_id": d.channel_id,
            "status": d.status,
            "attempt": d.attempt,
            "sent_at": d.sent_at,
            "error": d.error,
            "created_at": d.created_at,
        }
        for d in deliveries
    ]


# ── Config ─────────────────────────────────────────────────────────────────────

class ThresholdPatch(BaseModel):
    impact_threshold: int


@router.patch("/config/threshold")
async def set_threshold(body: ThresholdPatch, _: AdminDep):
    """
    Update the global impact threshold at runtime.
    Note: updates in-process settings only.
    For persistence across restarts, update IMPACT_THRESHOLD in .env.
    """
    from app.core.config import settings as s
    if not (0 <= body.impact_threshold <= 100):
        raise HTTPException(status_code=400, detail="threshold must be 0–100")
    s.impact_threshold = body.impact_threshold
    return {"ok": True, "impact_threshold": s.impact_threshold}


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.get("/stats")
async def stats(_: AdminDep):
    """Quick pipeline health summary."""
    async with AsyncSessionLocal() as session:
        total_articles = (await session.execute(select(func.count(Article.id)))).scalar()
        total_signals = (await session.execute(select(func.count(Signal.id)))).scalar()
        sent = (
            await session.execute(
                select(func.count(Delivery.id)).where(Delivery.status == "sent")
            )
        ).scalar()
        failed = (
            await session.execute(
                select(func.count(Delivery.id)).where(
                    Delivery.status.in_(["failed", "permanent_failure"])
                )
            )
        ).scalar()
        enabled_sources = (
            await session.execute(
                select(func.count(Source.id)).where(Source.enabled.is_(True))
            )
        ).scalar()

    return {
        "enabled_sources": enabled_sources,
        "total_articles": total_articles,
        "total_signals": total_signals,
        "deliveries_sent": sent,
        "deliveries_failed": failed,
    }
