from sqlalchemy import Column, String, Text, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase

from database import Base


class TeamMemory(Base):
    __tablename__ = "team_memories"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(100), nullable=False, index=True)
    memory_key = Column(String(200), nullable=False)
    memory_value = Column(Text, nullable=False)
    set_by = Column(String(200), default="admin")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
