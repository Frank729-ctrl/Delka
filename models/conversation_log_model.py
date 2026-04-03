from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text
from database import Base


class ConversationLog(Base):
    __tablename__ = "conversation_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    session_id = Column(String(36), nullable=False)
    role = Column(String(20), nullable=False)   # "user" | "assistant" | "summary" | "compact_summary"
    content = Column(Text, nullable=False)
    tokens_estimate = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Per-message metadata (Feature 3 — mirrors Claude Code's per-message cost tracking)
    provider = Column(String(50), nullable=True)        # groq | gemini | cerebras | …
    model_name = Column(String(100), nullable=True)     # llama-3.1-8b-instant | …
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    effort_tier = Column(String(20), nullable=True)     # quick | medium | complex | code | …
    latency_ms = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_conv_user_platform_created", "user_id", "platform", "created_at"),
    )
