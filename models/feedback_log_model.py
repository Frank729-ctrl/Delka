from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String
from database import Base


class FeedbackLog(Base):
    __tablename__ = "feedback_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False)
    session_id = Column(String(36), nullable=False)
    service = Column(String(20), nullable=False)
    request_data = Column(JSON, default=dict)
    response_data = Column(JSON, default=dict)
    provider_used = Column(String(20), default="")
    model_used = Column(String(100), default="")
    rating = Column(Integer, nullable=True)
    rating_comment = Column(String(500), nullable=True)
    correction = Column(String(1000), nullable=True)
    response_ms = Column(Integer, default=0)
    auto_score = Column(Float, nullable=True)          # 0.0-1.0, rule-based quality score
    auto_score_issues = Column(JSON, default=list)     # list of issue strings from quality scorer
    created_at = Column(DateTime, default=datetime.utcnow)
