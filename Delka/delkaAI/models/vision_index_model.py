from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, UniqueConstraint
from database import Base


class VisionIndexItem(Base):
    __tablename__ = "vision_index_items"

    id = Column(Integer, primary_key=True)
    item_id = Column(String(100), nullable=False)
    platform = Column(String(50), nullable=False, index=True)
    image_url = Column(String(500), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=False, default=dict)
    is_indexed = Column(Boolean, default=False)
    indexed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("item_id", "platform"),)
