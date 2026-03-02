from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Identity
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    # Content
    title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Timing
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Pipeline state
    # raw | normalized | scored | sent | suppressed | duplicate | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="raw", index=True)

    # Deduplication
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_of: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    source: Mapped["Source"] = relationship("Source", lazy="select")  # noqa: F821
    signal: Mapped["Signal | None"] = relationship(  # noqa: F821
        "Signal", back_populates="article", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Article {self.id} status={self.status} title={self.title[:40]!r}>"
