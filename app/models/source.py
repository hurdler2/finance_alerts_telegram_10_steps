from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rss_url: Mapped[str] = mapped_column(Text, nullable=False)
    home_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    has_rss: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scrape_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, default="en")
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Source {self.slug} enabled={self.enabled}>"
