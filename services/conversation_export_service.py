"""
Conversation export — export full session as markdown, JSON, or plain text.

GET /v1/chat/export?session_id=&format=markdown|json|plain&user_id=&platform=

Markdown format includes:
  - Session metadata header (session_id, date, message count, total cost)
  - Per-message blocks with role, content, and metadata (provider, model, cost)
  - Artifacts listed at the end

JSON format is a structured object with the same data machine-readable.
Plain text is clean prose — just role: content, no markup.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal


ExportFormat = Literal["markdown", "json", "plain"]


async def export_session(
    user_id: str,
    platform: str,
    session_id: str,
    fmt: ExportFormat,
    db,
) -> tuple[str, str]:
    """
    Export a conversation session.
    Returns (content, content_type).
    """
    from services.conversation_history_service import get_session_history

    history = await get_session_history(user_id, session_id, db)
    messages = [m for m in history if m["role"] in ("user", "assistant")]

    if not messages:
        empty = "No messages found for this session."
        return (empty, "text/plain")

    if fmt == "json":
        return _export_json(session_id, platform, messages), "application/json"
    elif fmt == "plain":
        return _export_plain(session_id, messages), "text/plain"
    else:
        return _export_markdown(session_id, platform, messages), "text/markdown"


def _export_markdown(session_id: str, platform: str, messages: list[dict]) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    total_cost = sum(
        (m.get("meta") or {}).get("cost_usd") or 0.0 for m in messages
    )
    lines = [
        f"# Conversation Export",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Session | `{session_id}` |",
        f"| Platform | {platform} |",
        f"| Exported | {now} |",
        f"| Messages | {len(messages)} |",
        f"| Total cost | ${total_cost:.4f} USD |",
        f"",
        f"---",
        f"",
    ]

    for i, msg in enumerate(messages, 1):
        role = msg["role"].title()
        content = msg["content"]
        meta = msg.get("meta") or {}
        created = msg.get("created_at", "")[:19]

        lines.append(f"### [{i}] {role}  _{created}_")
        if meta.get("model"):
            cost_str = f" · ${meta['cost_usd']:.4f}" if meta.get("cost_usd") else ""
            lines.append(
                f"_via {meta['provider']}/{meta['model']}"
                f" · {(meta.get('input_tokens') or 0) + (meta.get('output_tokens') or 0)} tokens"
                f"{cost_str}_"
            )
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _export_json(session_id: str, platform: str, messages: list[dict]) -> str:
    total_cost = sum((m.get("meta") or {}).get("cost_usd") or 0.0 for m in messages)
    payload = {
        "session_id": session_id,
        "platform": platform,
        "exported_at": datetime.utcnow().isoformat(),
        "message_count": len(messages),
        "total_cost_usd": round(total_cost, 6),
        "messages": [
            {
                "index": i,
                "role": m["role"],
                "content": m["content"],
                "created_at": m.get("created_at"),
                "meta": m.get("meta"),
            }
            for i, m in enumerate(messages, 1)
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def _export_plain(session_id: str, messages: list[dict]) -> str:
    lines = [f"Session: {session_id}", "=" * 60, ""]
    for msg in messages:
        role = "You" if msg["role"] == "user" else "Delka"
        lines.append(f"{role}:")
        lines.append(msg["content"])
        lines.append("")
    return "\n".join(lines)
