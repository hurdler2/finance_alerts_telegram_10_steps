from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )

    impact_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)

    # JSON arrays stored as JSONB for efficient querying
    reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tickers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    categories: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # sent | suppressed | failed | pending
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    article: Mapped["Article"] = relationship("Article", back_populates="signal")  # noqa: F821
    deliveries: Mapped[list["Delivery"]] = relationship(  # noqa: F821
        "Delivery", back_populates="signal"
    )

    def __repr__(self) -> str:
        return f"<Signal {self.id} score={self.impact_score} status={self.status}>"
