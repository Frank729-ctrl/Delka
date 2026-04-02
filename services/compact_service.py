"""
Auto-compact service — summarizes old conversation history when the context
window is approaching its limit.

Inspired by Claude Code's compact.ts + autoCompact.ts.

How it works:
1. After each streamed reply, chat_service calls maybe_compact().
2. If usage ratio > COMPACT_THRESHOLD (80%), we run a background summarization.
3. The summarizer condenses the oldest messages into a single summary block.
4. The summary replaces the old messages in the DB, so future calls are lean.
5. The most recent N exchanges are always kept verbatim (never summarized).

Delka improvement over Claude Code:
- Works server-side across API calls (not just one terminal session)
- Persists compact boundaries to the DB so they survive restarts
- Includes plugin/search context summary so nothing useful is lost
"""
from __future__ import annotations

import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from services.token_counter import should_compact, context_usage_ratio
from services.inference_service import generate_full_response

# Keep this many recent exchanges verbatim (never compact them)
_RECENT_KEEP = 6  # = 3 user + 3 assistant turns

_COMPACT_SYSTEM = """You are a conversation summarizer. Your job is to compress old conversation history into a concise summary that preserves all important context.

Include:
- What the user is working on (project, goal, domain)
- Key facts established (names, preferences, constraints, decisions)
- Topics already discussed so they aren't repeated
- Any corrections the user made
- Important code, data, or content that was referenced

Exclude:
- Small talk and filler
- Greetings
- Anything that is now superseded by a later correction

Output format: a single markdown text block starting with "## Conversation Summary"
Be specific. Names, numbers, and concrete details matter."""


async def maybe_compact(
    user_id: str,
    platform: str,
    session_id: str,
    messages: list[dict],
    model: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Check if compaction is needed. If yes, run it in the background and return
    the compacted message list. Otherwise return messages unchanged.
    """
    if not should_compact(messages, model):
        return messages

    return await _compact(user_id, platform, session_id, messages, model, db)


async def _compact(
    user_id: str,
    platform: str,
    session_id: str,
    messages: list[dict],
    model: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Summarize the oldest portion of the conversation and replace it with
    a compact summary block. Updates the DB and returns the new message list.
    """
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conv_msgs = [m for m in messages if m.get("role") != "system"]

    if len(conv_msgs) <= _RECENT_KEEP * 2:
        return messages  # nothing old enough to compact

    # Split: old (to summarize) + recent (keep verbatim)
    split_at = len(conv_msgs) - (_RECENT_KEEP * 2)
    old_msgs = conv_msgs[:split_at]
    recent_msgs = conv_msgs[split_at:]

    # Build summary prompt
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in old_msgs
        if isinstance(m.get("content"), str)
    )

    try:
        summary, _, _ = await generate_full_response(
            task="chat",
            system_prompt=_COMPACT_SYSTEM,
            user_prompt=f"Summarize this conversation history:\n\n{history_text}",
            temperature=0.3,
            max_tokens=1024,
        )
    except Exception:
        return messages  # compact failed — return unchanged

    summary_msg = {
        "role": "system",
        "content": (
            f"[COMPACT SUMMARY — replaces earlier conversation]\n\n{summary}"
        ),
    }

    # Persist compaction to DB
    try:
        from services import conversation_history_service
        await conversation_history_service.replace_history_with_summary(
            user_id, platform, session_id, summary, db
        )
    except Exception:
        pass  # DB update is best-effort

    return system_msgs + [summary_msg] + recent_msgs


def get_context_stats(messages: list[dict], model: str) -> dict:
    """Return token usage stats for logging/display."""
    from services.token_counter import estimate_messages_tokens, get_context_window
    used = estimate_messages_tokens(messages)
    total = get_context_window(model)
    ratio = context_usage_ratio(messages, model)
    return {
        "tokens_used": used,
        "tokens_total": total,
        "usage_pct": round(ratio * 100, 1),
        "needs_compact": ratio >= 0.80,
    }
