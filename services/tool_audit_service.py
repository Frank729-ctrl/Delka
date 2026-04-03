"""
Tool Audit Trail — log every tool invocation with inputs, outputs, and latency.

log_tool_call() is designed to be fire-and-forget (use asyncio.create_task).
query_audit_log() powers GET /v1/audit/tools.

Tool types tracked:
  search    — web/vector search calls
  sandbox   — Python / JavaScript / bash execution
  fetch     — URL fetch via webfetch_service
  mcp       — MCP tool invocations
  skill     — slash command / skill executions
  memory    — memory read/write operations
"""
from __future__ import annotations

import time
from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text


async def log_tool_call(
    user_id: str,
    platform: str,
    session_id: str,
    tool_name: str,
    tool_type: str,
    db: AsyncSession,
    inputs: Optional[dict] = None,
    outputs: Optional[dict] = None,
    success: bool = True,
    error_msg: str = "",
    latency_ms: float = 0.0,
) -> None:
    """
    Persist one tool invocation to the audit log.
    Designed to run as asyncio.create_task() — never blocks the caller.
    Inputs are sanitised (no secrets, truncated).
    """
    from models.tool_audit_model import ToolAuditLog

    safe_inputs = _sanitise(inputs)
    safe_outputs = _sanitise(outputs, max_str=300)

    entry = ToolAuditLog(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        tool_name=tool_name,
        tool_type=tool_type,
        inputs=safe_inputs,
        outputs=safe_outputs,
        success=1 if success else 0,
        error_msg=error_msg[:500] if error_msg else None,
        latency_ms=latency_ms,
    )
    try:
        db.add(entry)
        await db.commit()
    except Exception:
        pass  # audit failure must never break the caller


async def query_audit_log(
    user_id: str,
    platform: str,
    db: AsyncSession,
    session_id: Optional[str] = None,
    tool_type: Optional[str] = None,
    tool_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Query the audit log with optional filters."""
    from models.tool_audit_model import ToolAuditLog

    conditions = [
        ToolAuditLog.user_id == user_id,
        ToolAuditLog.platform == platform,
    ]
    if session_id:
        conditions.append(ToolAuditLog.session_id == session_id)
    if tool_type:
        conditions.append(ToolAuditLog.tool_type == tool_type)
    if tool_name:
        conditions.append(ToolAuditLog.tool_name == tool_name)

    result = await db.execute(
        select(ToolAuditLog)
        .where(*conditions)
        .order_by(ToolAuditLog.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "session_id": r.session_id,
            "tool_name": r.tool_name,
            "tool_type": r.tool_type,
            "inputs": r.inputs,
            "outputs": r.outputs,
            "success": bool(r.success),
            "error_msg": r.error_msg,
            "latency_ms": r.latency_ms,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]


async def get_audit_stats(
    user_id: str,
    platform: str,
    db: AsyncSession,
    session_id: Optional[str] = None,
) -> dict:
    """Return aggregate stats — call counts and error rates by tool type."""
    where = "WHERE user_id = :uid AND platform = :pl"
    params: dict = {"uid": user_id, "pl": platform}
    if session_id:
        where += " AND session_id = :sid"
        params["sid"] = session_id

    result = await db.execute(
        text(
            f"SELECT tool_type, COUNT(*) as calls, "
            f"SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors, "
            f"AVG(latency_ms) as avg_latency "
            f"FROM tool_audit_logs {where} "
            f"GROUP BY tool_type ORDER BY calls DESC"
        ),
        params,
    )
    rows = result.fetchall()
    return {
        "by_type": [
            {
                "tool_type": r[0],
                "calls": r[1],
                "errors": r[2],
                "error_rate": round(r[2] / r[1], 3) if r[1] else 0,
                "avg_latency_ms": round(r[3] or 0, 1),
            }
            for r in rows
        ]
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

_SENSITIVE_KEYS = {"password", "token", "secret", "key", "api_key", "auth", "credential"}


def _sanitise(data: Any, max_str: int = 500) -> Optional[dict]:
    """Redact sensitive keys and truncate long strings."""
    if data is None:
        return None
    if not isinstance(data, dict):
        return {"value": str(data)[:max_str]}
    out = {}
    for k, v in data.items():
        if any(s in k.lower() for s in _SENSITIVE_KEYS):
            out[k] = "[REDACTED]"
        elif isinstance(v, str):
            out[k] = v[:max_str]
        elif isinstance(v, (int, float, bool)):
            out[k] = v
        elif isinstance(v, (dict, list)):
            out[k] = str(v)[:max_str]
        else:
            out[k] = str(v)[:max_str]
    return out
