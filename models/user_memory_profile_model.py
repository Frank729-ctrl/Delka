from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String
from database import Base


class UserMemoryProfile(Base):
    __tablename__ = "user_memory_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    name = Column(String(100), nullable=True)
    language_preference = Column(String(10), default="en")
    tone_preference = Column(String(20), default="adaptive")
    correction_rules = Column(JSON, default=list)
    preferences = Column(JSON, default=dict)
    cv_profile = Column(JSON, default=dict)
    topics_discussed = Column(JSON, default=list)
    total_interactions = Column(Integer, default=0)
    avg_rating_given = Column(Float, default=0.0)
    last_seen = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_user_platform", "user_id", "platform"),)
