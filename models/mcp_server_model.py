"""
MCP Server registry — persisted external MCP server configurations.
Transport types: stdio | sse | http | ws
"""
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer
from sqlalchemy.sql import func
from database import Base


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, index=True)          # unique per platform
    platform = Column(String(128), nullable=False, index=True)
    transport = Column(String(16), nullable=False, default="http")  # stdio|sse|http|ws
    # HTTP / SSE / WS
    url = Column(String(512), nullable=True)
    auth_token = Column(String(512), nullable=True)                 # Bearer token
    headers_json = Column(Text, nullable=True)                      # JSON {k:v}
    # Stdio
    command = Column(String(512), nullable=True)                    # e.g. "npx"
    args_json = Column(Text, nullable=True)                         # JSON ["@modelcontextprotocol/server-github"]
    env_json = Column(Text, nullable=True)                          # JSON {k:v}
    # Metadata
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String(128), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
