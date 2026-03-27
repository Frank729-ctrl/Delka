from datetime import datetime
from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from database import Base


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    session_id = Column(String(36), nullable=False)
    role = Column(String(10), nullable=False)   # "user" | "assistant" | "summary"
    content = Column(Text, nullable=False)
    tokens_estimate = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_conv_user_platform_created", "user_id", "platform", "created_at"),
    )
