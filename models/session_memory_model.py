from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer
from database import Base


class SessionMemory(Base):
    __tablename__ = "session_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, index=True)
    platform = Column(String(64), nullable=False, index=True)
    mem_type = Column(String(32), nullable=False)  # user, feedback, project, reference
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
