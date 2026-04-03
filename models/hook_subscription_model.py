"""
Hook subscription — stores external HTTP webhook registrations per platform/event.
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer
from sqlalchemy.sql import func
from database import Base


class HookSubscription(Base):
    __tablename__ = "hook_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)              # human label
    platform = Column(String(128), nullable=False, index=True)
    event = Column(String(64), nullable=False, index=True)  # pre_chat|post_chat|post_memory|...
    url = Column(String(512), nullable=False)               # POST target
    secret = Column(String(256), nullable=True)             # HMAC secret for signature
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
