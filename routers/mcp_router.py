"""
MCP Server Management API.

POST   /v1/mcp/servers              — register an MCP server
GET    /v1/mcp/servers              — list registered servers for a platform
DELETE /v1/mcp/servers/{name}       — deactivate a server
GET    /v1/mcp/tools                — list all available tools (built-in + external)
POST   /v1/mcp/tools/call           — call a specific tool directly
POST   /v1/mcp/servers/{name}/ping  — test-connect to a server and list its tools
"""
from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from services.mcp_service import get_all_tools, execute_tool, BUILTIN_TOOLS
from services.mcp_client_service import list_tools as client_list_tools

router = APIRouter(prefix="/v1/mcp")


# ── Schemas ───────────────────────────────────────────────────────────────────

class RegisterServerRequest(BaseModel):
    name: str = Field(..., description="Unique name for this server within the platform")
    platform: str
    transport: str = Field("http", description="http | sse | stdio | ws")
    # HTTP/SSE/WS
    url: Optional[str] = Field(None, description="Base URL for http/sse/ws transports")
    auth_token: Optional[str] = Field(None, description="Bearer token")
    headers: Optional[dict] = Field(None, description="Extra request headers")
    # Stdio
    command: Optional[str] = Field(None, description="Executable for stdio transport, e.g. 'npx'")
    args: Optional[list[str]] = Field(None, description="CLI args, e.g. ['@modelcontextprotocol/server-github']")
    env: Optional[dict] = Field(None, description="Environment variables for stdio process")
    # Meta
    description: Optional[str] = None
    created_by: Optional[str] = None


class CallToolRequest(BaseModel):
    tool_name: str
    arguments: dict = Field(default_factory=dict)
    platform: str = ""
    session_id: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/servers", summary="Register an external MCP server")
async def api_register_server(req: RegisterServerRequest, db: AsyncSession = Depends(get_db)):
    # Validate transport
    if req.transport not in ("http", "sse", "stdio", "ws"):
        raise HTTPException(status_code=400, detail="transport must be http, sse, stdio, or ws")
    if req.transport in ("http", "sse", "ws") and not req.url:
        raise HTTPException(status_code=400, detail=f"url is required for transport='{req.transport}'")
    if req.transport == "stdio" and not req.command:
        raise HTTPException(status_code=400, detail="command is required for transport='stdio'")

    try:
        await db.execute(
            text(
                "INSERT INTO mcp_servers "
                "(name, platform, transport, url, auth_token, headers_json, "
                "command, args_json, env_json, description, created_by, is_active) "
                "VALUES (:name, :pl, :tr, :url, :tok, :hdr, :cmd, :args, :env, :desc, :by, 1) "
                "ON DUPLICATE KEY UPDATE "
                "transport=:tr, url=:url, auth_token=:tok, headers_json=:hdr, "
                "command=:cmd, args_json=:args, env_json=:env, description=:desc, is_active=1"
            ),
            {
                "name": req.name[:128], "pl": req.platform[:128],
                "tr": req.transport,
                "url": req.url,
                "tok": req.auth_token,
                "hdr": json.dumps(req.headers) if req.headers else None,
                "cmd": req.command,
                "args": json.dumps(req.args) if req.args else None,
                "env": json.dumps(req.env) if req.env else None,
                "desc": req.description,
                "by": req.created_by,
            },
        )
        await db.commit()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)[:200])

    return {"status": "ok", "message": f"MCP server '{req.name}' registered for platform '{req.platform}'"}


@router.get("/servers", summary="List registered MCP servers for a platform")
async def api_list_servers(platform: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "SELECT name, transport, url, command, description, is_active, created_at "
            "FROM mcp_servers WHERE platform = :pl ORDER BY name"
        ),
        {"pl": platform},
    )
    rows = result.fetchall()
    return {
        "status": "ok",
        "data": [
            {
                "name": r[0], "transport": r[1], "url": r[2],
                "command": r[3], "description": r[4],
                "is_active": bool(r[5]), "created_at": str(r[6]),
            }
            for r in rows
        ],
    }


@router.delete("/servers/{name}", summary="Deactivate an MCP server")
async def api_remove_server(name: str, platform: str, db: AsyncSession = Depends(get_db)):
    await db.execute(
        text("UPDATE mcp_servers SET is_active = 0 WHERE name = :n AND platform = :pl"),
        {"n": name, "pl": platform},
    )
    await db.commit()
    return {"status": "ok", "message": f"Server '{name}' deactivated"}


@router.get("/tools", summary="List all available tools (built-in + registered servers)")
async def api_list_tools(platform: str = "", db: AsyncSession = Depends(get_db)):
    tools = await get_all_tools(platform, db)
    # Strip internal _server key before returning
    cleaned = [{k: v for k, v in t.items() if not k.startswith("_")} for t in tools]
    return {
        "status": "ok",
        "data": {
            "tools": cleaned,
            "count": len(cleaned),
            "builtin_count": len(BUILTIN_TOOLS),
            "external_count": len(cleaned) - len(BUILTIN_TOOLS),
        },
    }


@router.post("/tools/call", summary="Call a tool directly")
async def api_call_tool(req: CallToolRequest, db: AsyncSession = Depends(get_db)):
    result = await execute_tool(
        tool_name=req.tool_name,
        tool_input=req.arguments,
        platform=req.platform,
        db=db,
        session_id=req.session_id,
    )
    return {
        "status": "ok",
        "tool": req.tool_name,
        "result": result,
    }


@router.post("/servers/{name}/ping", summary="Test-connect to a server and fetch its tools")
async def api_ping_server(name: str, platform: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text(
            "SELECT transport, url, auth_token, headers_json, command, args_json, env_json "
            "FROM mcp_servers WHERE name = :n AND platform = :pl AND is_active = 1"
        ),
        {"n": name, "pl": platform},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found for platform '{platform}'")

    server = {
        "name": name,
        "transport": row[0], "url": row[1], "auth_token": row[2],
        "headers_json": row[3], "command": row[4], "args_json": row[5], "env_json": row[6],
    }
    tools = await client_list_tools(server)
    has_error = tools and "error" in tools[0]
    return {
        "status": "ok" if not has_error else "error",
        "server": name,
        "tools": tools if not has_error else [],
        "error": tools[0].get("error") if has_error else None,
        "tool_count": len(tools) if not has_error else 0,
    }
