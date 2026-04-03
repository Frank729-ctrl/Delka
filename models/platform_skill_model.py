from sqlalchemy import Column, String, Text, DateTime, Integer, func
from database import Base


class PlatformSkill(Base):
    __tablename__ = "platform_skills"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    platform = Column(String(100), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False, default="")
    prompt_template = Column(Text, nullable=False)
    aliases_json = Column(Text, default="[]")         # JSON array of strings
    argument_hint = Column(String(300), default="")
    when_to_use = Column(String(500), default="")
    model = Column(String(100), default="")
    user_invocable = Column(Integer, default=1)       # 1=yes, 0=hidden
    is_active = Column(Integer, default=1)
    created_by = Column(String(200), default="admin")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
