from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text
from database import Base


class FeedbackLog(Base):
    __tablename__ = "feedback_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=True, index=True)
    platform = Column(String(50), index=True)
    session_id = Column(String(36), index=True)
    service = Column(String(20))                        # cv/letter/chat/support/vision
    request_data = Column(JSON, default=dict)           # full input
    system_prompt_hash = Column(String(64), nullable=True)  # sha256 of system prompt used
    response_data = Column(JSON, default=dict)          # full output
    thinking_tokens = Column(Text, nullable=True)       # chain-of-thought blocks stripped from output
    provider_used = Column(String(20), default="")
    model_used = Column(String(100), default="")
    rating = Column(Integer, nullable=True)             # 1-5, null until rated
    rating_comment = Column(String(500), nullable=True)
    correction = Column(String(1000), nullable=True)
    response_ms = Column(Integer, default=0)
    auto_score = Column(Float, nullable=True)           # 0.0-1.0, rule-based quality score
    auto_score_issues = Column(JSON, default=list)      # list of issue strings from quality scorer
    created_at = Column(DateTime, default=datetime.utcnow)

    # DB migration (run once on production):
    # ALTER TABLE feedback_logs ADD COLUMN system_prompt_hash VARCHAR(64);
    # ALTER TABLE feedback_logs ADD COLUMN thinking_tokens TEXT;
