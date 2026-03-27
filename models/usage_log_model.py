from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from database import Base


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    key_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    detected_lang: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_usage_logs_request_id", "request_id"),
        Index("ix_usage_logs_created_at", "created_at"),
    )
