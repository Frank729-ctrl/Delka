from datetime import datetime
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


async def store_message(
    user_id: str,
    platform: str,
    session_id: str,
    role: str,
    content: str,
    db: AsyncSession,
    *,
    provider: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    effort_tier: str | None = None,
    latency_ms: float | None = None,
) -> None:
    from models.conversation_log_model import ConversationLog

    entry = ConversationLog(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        role=role,
        content=content,
        tokens_estimate=estimate_tokens(content),
        provider=provider,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        effort_tier=effort_tier,
        latency_ms=latency_ms,
    )
    db.add(entry)
    await db.commit()


async def get_recent_history(
    user_id: str,
    platform: str,
    db: AsyncSession,
    limit: int = 20,
    session_id: str = "",
) -> list[dict]:
    from models.conversation_log_model import ConversationLog

    conditions = [
        ConversationLog.user_id == user_id,
        ConversationLog.platform == platform,
    ]
    if session_id:
        conditions.append(ConversationLog.session_id == session_id)

    result = await db.execute(
        select(ConversationLog)
        .where(*conditions)
        .order_by(ConversationLog.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    # Reverse to oldest-first for prompt injection
    return [
        {
            "role": r.role,
            "content": r.content,
            "created_at": str(r.created_at),
            "meta": {
                "provider": r.provider,
                "model": r.model_name,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "effort_tier": r.effort_tier,
                "latency_ms": r.latency_ms,
            } if r.provider or r.model_name else None,
        }
        for r in reversed(rows)
        if r.role in ("user", "assistant")
    ]


async def get_session_history(
    user_id: str,
    session_id: str,
    db: AsyncSession,
) -> list[dict]:
    from models.conversation_log_model import ConversationLog

    result = await db.execute(
        select(ConversationLog)
        .where(
            ConversationLog.user_id == user_id,
            ConversationLog.session_id == session_id,
        )
        .order_by(ConversationLog.created_at.asc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "role": r.role,
            "content": r.content,
            "created_at": str(r.created_at),
            "meta": {
                "provider": r.provider,
                "model": r.model_name,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "cost_usd": r.cost_usd,
                "effort_tier": r.effort_tier,
                "latency_ms": r.latency_ms,
            } if r.provider or r.model_name else None,
        }
        for r in rows
    ]


async def summarize_old_history(
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> str:
    from models.conversation_log_model import ConversationLog

    result = await db.execute(
        select(ConversationLog)
        .where(
            ConversationLog.user_id == user_id,
            ConversationLog.platform == platform,
        )
        .order_by(ConversationLog.created_at.asc())
    )
    all_rows = result.scalars().all()

    if len(all_rows) <= 50:
        return ""

    # Keep last 20, summarize the rest
    to_summarize = all_rows[:-20]
    to_keep = all_rows[-20:]

    combined = "\n".join(
        f"{r.role}: {r.content[:200]}" for r in to_summarize
    )

    from services.inference_service import generate_full_response
    summary_text, _, _ = await generate_full_response(
        task="support",
        system_prompt="Summarize the following conversation history in 3-5 sentences. Focus on key facts about the user and what was discussed.",
        user_prompt=combined,
        temperature=0.3,
        max_tokens=300,
    )

    # Delete old messages
    old_ids = [r.id for r in to_summarize]
    await db.execute(
        delete(ConversationLog).where(ConversationLog.id.in_(old_ids))
    )

    # Insert summary record
    summary_entry = ConversationLog(
        user_id=user_id,
        platform=platform,
        session_id="summary",
        role="summary",
        content=summary_text,
        tokens_estimate=estimate_tokens(summary_text),
    )
    db.add(summary_entry)
    await db.commit()
    return summary_text


async def replace_history_with_summary(
    user_id: str,
    platform: str,
    session_id: str,
    summary: str,
    db: AsyncSession,
) -> None:
    """
    Called by compact_service after auto-compaction.
    Deletes old messages for this session and inserts a summary record
    so future calls start lean.
    """
    from models.conversation_log_model import ConversationLog

    # Get all messages for this session, keep the most recent 12
    result = await db.execute(
        select(ConversationLog)
        .where(
            ConversationLog.user_id == user_id,
            ConversationLog.platform == platform,
            ConversationLog.session_id == session_id,
        )
        .order_by(ConversationLog.created_at.asc())
    )
    rows = result.scalars().all()
    if len(rows) <= 12:
        return

    to_delete = rows[:-12]
    old_ids = [r.id for r in to_delete]
    await db.execute(
        delete(ConversationLog).where(ConversationLog.id.in_(old_ids))
    )

    # Insert compact summary as a system role entry
    summary_entry = ConversationLog(
        user_id=user_id,
        platform=platform,
        session_id=session_id,
        role="compact_summary",
        content=f"[AUTO-COMPACT]\n{summary}",
        tokens_estimate=estimate_tokens(summary),
    )
    db.add(summary_entry)
    await db.commit()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
