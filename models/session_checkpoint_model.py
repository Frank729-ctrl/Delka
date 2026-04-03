from datetime import datetime
from sqlalchemy import Column, DateTime, Index, Integer, JSON, String, Text
from database import Base


class SessionCheckpoint(Base):
    """
    Named snapshot of a conversation session at a specific point in time.
    Stores full message history + relevant metadata so the session can be
    restored to this exact state.

    Equivalent of Claude Code's git-worktree session isolation, but DB-backed
    and accessible cross-device.
    """
    __tablename__ = "session_checkpoints"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    session_id = Column(String(100), nullable=False)
    name = Column(String(200), nullable=False)       # user-visible label
    description = Column(Text, nullable=True)        # optional note about why checkpoint was created
    history_snapshot = Column(JSON, nullable=False)  # list[{role, content, meta}]
    meta = Column(JSON, nullable=True)               # {message_count, effort_tier, output_style, …}
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_checkpoint_user_session", "user_id", "session_id"),
    )
