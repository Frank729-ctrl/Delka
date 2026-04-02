from sqlalchemy import Column, String, Text, DateTime, Integer, func
from database import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(String(200), nullable=False, index=True)
    platform = Column(String(100), nullable=False)
    prompt = Column(Text, nullable=False)
    schedule = Column(String(100), nullable=False)   # "every_hour", "every_morning", etc.
    webhook_url = Column(String(500), nullable=True)
    is_active = Column(Integer, default=1)           # 1=active, 0=paused
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
