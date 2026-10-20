from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class GoogleConnection(Base):
    __tablename__ = "google_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    encrypted_credentials: Mapped[str] = mapped_column(Text, nullable=False)
    search_console_site: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ga4_property_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    site_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cta_event: Mapped[str | None] = mapped_column(String(100), nullable=True)
    invite_submit_event: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reconnect_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
