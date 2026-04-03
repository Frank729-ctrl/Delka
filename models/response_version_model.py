from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String, Text
from database import Base


class ResponseVersion(Base):
    """
    Stores multiple AI responses for the same user message.
    Version 1 = original response. Version 2+ = regenerations.
    Allows users to pick the best response or see alternatives.
    """
    __tablename__ = "response_versions"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    session_id = Column(String(100), nullable=False)
    message_hash = Column(String(32), nullable=False)   # MD5 of user message — groups versions
    user_message = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    response = Column(Text, nullable=False)
    provider = Column(String(50), nullable=True)
    model_name = Column(String(100), nullable=True)
    effort_tier = Column(String(20), nullable=True)
    output_style = Column(String(30), nullable=True)
    tokens = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    selected = Column(Integer, default=0)   # 1 = user selected this version
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_response_versions_hash", "user_id", "session_id", "message_hash"),
    )
