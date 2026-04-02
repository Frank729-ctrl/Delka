from sqlalchemy import Column, String, Text, DateTime, Integer, func
from database import Base


class WorkspaceFile(Base):
    __tablename__ = "workspace_files"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(200), nullable=False, index=True)
    platform = Column(String(100), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content = Column(Text(length=2**21), nullable=False)   # up to ~2MB TEXT
    file_type = Column(String(50), default="text")
    size_bytes = Column(Integer, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
