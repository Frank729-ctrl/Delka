from sqlalchemy import Column, String, Text, DateTime, Integer, Float, func
from database import Base


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(100), nullable=False, index=True)
    platform = Column(String(100), nullable=True, index=True)
    user_id = Column(String(200), nullable=True, index=True)
    provider = Column(String(100), nullable=True)
    model = Column(String(200), nullable=True)
    latency_ms = Column(Float, nullable=True)
    cost_usd = Column(Float, nullable=True)
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    extra = Column(Text, nullable=True)   # JSON blob for ad-hoc fields
    created_at = Column(DateTime, server_default=func.now(), index=True)
