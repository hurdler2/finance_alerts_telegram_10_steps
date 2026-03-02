"""
Seed the sources table from configs/sources.yaml.
Run inside Docker:
    docker compose exec api python scripts/seed_sources.py
Or locally (with DATABASE_URL set):
    python scripts/seed_sources.py
"""
import asyncio
import sys
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import AsyncSessionLocal
from app.models.source import Source


SOURCES_YAML = Path(__file__).parent.parent / "configs" / "sources.yaml"


async def seed(session: AsyncSession) -> None:
    data = yaml.safe_load(SOURCES_YAML.read_text())
    sources = data.get("sources", [])
    defaults = data.get("defaults", {})

    created = updated = 0

    for s in sources:
        result = await session.execute(select(Source).where(Source.slug == s["id"]))
        existing = result.scalar_one_or_none()

        if existing:
            # Update mutable fields (don't overwrite enabled toggle set by admin)
            existing.name = s["name"]
            existing.rss_url = s["rss_url"]
            existing.home_url = s.get("home_url")
            existing.category = s.get("category", "general")
            existing.priority = s.get("priority", 3)
            existing.has_rss = s.get("has_rss", True)
            existing.scrape_allowed = s.get("scrape_allowed", False)
            existing.lang = s.get("lang", "en")
            existing.poll_interval_minutes = s.get(
                "poll_interval_minutes", defaults.get("poll_interval_minutes", 5)
            )
            existing.notes = s.get("notes")
            updated += 1
        else:
            session.add(
                Source(
                    slug=s["id"],
                    name=s["name"],
                    rss_url=s["rss_url"],
                    home_url=s.get("home_url"),
                    category=s.get("category", "general"),
                    priority=s.get("priority", 3),
                    enabled=s.get("enabled", True),
                    has_rss=s.get("has_rss", True),
                    scrape_allowed=s.get("scrape_allowed", False),
                    lang=s.get("lang", "en"),
                    poll_interval_minutes=s.get(
                        "poll_interval_minutes", defaults.get("poll_interval_minutes", 5)
                    ),
                    notes=s.get("notes"),
                )
            )
            created += 1

    await session.commit()
    print(f"Seed complete: {created} created, {updated} updated.")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)


if __name__ == "__main__":
    asyncio.run(main())
