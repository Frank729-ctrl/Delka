from sqlalchemy import (
    Boolean, DateTime, Index, Integer, JSON, String
)
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from database import Base


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    key_type: Mapped[str] = mapped_column(String(2), nullable=False)  # "pk" or "sk"
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    owner: Mapped[str] = mapped_column(String(100), nullable=False)
    requires_hmac: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hmac_secret_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    violation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ip_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_api_keys_raw_prefix", "raw_prefix"),
        Index("ix_api_keys_key_hash", "key_hash", unique=True),
    )
