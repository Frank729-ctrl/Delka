from sqlalchemy import Column, String, Text, DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase

from database import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(200), nullable=False, index=True)
    platform = Column(String(100), nullable=False)
    doc_type = Column(String(20), nullable=False)   # "cv" | "letter"
    content_b64 = Column(Text, nullable=False)       # base64 PDF
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, server_default=func.now())
