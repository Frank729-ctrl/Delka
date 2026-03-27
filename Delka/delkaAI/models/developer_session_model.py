from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from database import Base


class DeveloperSession(Base):
    __tablename__ = "developer_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    developer_id: Mapped[int] = mapped_column(Integer, ForeignKey("developer_accounts.id"), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_active: Mapped[bool] = mapped_column(Integer, default=True, nullable=False)

    __table_args__ = (
        Index("ix_developer_sessions_token", "session_token", unique=True),
        Index("ix_developer_sessions_dev_id", "developer_id"),
    )
