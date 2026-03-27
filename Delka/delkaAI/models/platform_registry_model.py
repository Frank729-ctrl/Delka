from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from database import Base


class PlatformRegistry(Base):
    __tablename__ = "platform_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    owner_email: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_hmac: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_platform_registry_name", "platform_name", unique=True),
    )
