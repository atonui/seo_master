from datetime import date, datetime, timezone
import uuid

from sqlalchemy import Date, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SavedReport(Base):
    __tablename__ = "saved_reports"
    __table_args__ = (Index("ix_saved_reports_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_timestamps: Mapped[dict] = mapped_column(JSON, nullable=False)
    warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
