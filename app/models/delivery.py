from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Delivery target
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    channel_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # State: pending | sent | failed | permanent_failure
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    signal: Mapped["Signal"] = relationship("Signal", back_populates="deliveries")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Delivery {self.id} channel={self.channel} status={self.status}>"
