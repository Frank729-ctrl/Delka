from datetime import datetime
from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String, Text
from database import Base


class ToolAuditLog(Base):
    """
    Audit log for every tool invocation — MCP tools, sandbox executions,
    web fetches, and search calls. Queryable via GET /v1/audit/tools.
    """
    __tablename__ = "tool_audit_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    platform = Column(String(50), nullable=False, index=True)
    session_id = Column(String(100), nullable=False)

    tool_name = Column(String(100), nullable=False)   # web_search | bash | python | mcp:name | fetch
    tool_type = Column(String(30), nullable=False)    # search | sandbox | fetch | mcp | skill
    inputs = Column(JSON, nullable=True)              # sanitised input parameters
    outputs = Column(JSON, nullable=True)             # result summary (not full content)
    success = Column(Integer, default=1)              # 1=success, 0=failure
    error_msg = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tool_audit_user_platform", "user_id", "platform", "created_at"),
    )
