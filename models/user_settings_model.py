from sqlalchemy import Column, String, DateTime, Integer, func
from database import Base


class UserSetting(Base):
    __tablename__ = "user_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(200), nullable=False, index=True)
    platform = Column(String(100), nullable=False, index=True)
    setting_key = Column(String(100), nullable=False)
    setting_value = Column(String(500), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
