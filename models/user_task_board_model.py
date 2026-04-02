from sqlalchemy import Column, String, Text, DateTime, Integer, func
from database import Base


class UserTaskBoard(Base):
    __tablename__ = "user_task_boards"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(128), unique=True, nullable=False, index=True)
    user_id = Column(String(200), nullable=False, index=True)
    platform = Column(String(100), nullable=False)
    tasks_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
