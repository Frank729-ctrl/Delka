"""
Speculative follow-up generation — exceeds Claude Code's speculation.ts.

src speculation: pre-generates the assistant's NEXT response before user types.
Delka speculation: after every reply, pre-generate 3 likely follow-up QUESTIONS
the user might ask + cache them for instant retrieval. Much more useful for a
chat API since we can't predict what command the user runs next, but we CAN
predict what they'll want to know.

Also pre-generates a "brief mode" version of the last response in case the
user asks for a shorter version.

Runs as a background asyncio task — never delays the streamed response.
Cache TTL: 5 minutes (evicted if user sends a different message).
"""
import asyncio
import time
from dataclasses import dataclass, field

@dataclass
class SpeculationCache:
    follow_up_questions: list[str]
    brief_version: str
    cached_at: float = field(default_factory=time.time)
    for_message: str = ""  # The assistant message this was generated from


_cache: dict[str, SpeculationCache] = {}  # session_id → SpeculationCache
_CACHE_TTL = 300  # 5 minutes


_FOLLOW_UP_SYSTEM = """Given an AI assistant's response, generate exactly 3 short follow-up questions a user might naturally ask next.

Rules:
- Each question max 12 words
- Make them specific to the content, not generic
- Cover different angles (deeper dive, practical next step, related topic)
- Output ONLY the 3 questions, one per line, no numbering, no bullets

Example output:
How does that work with MTN Mobile Money specifically?
What happens if I miss the deadline?
Can I do this on my phone instead?
"""

_BRIEF_SYSTEM = """Rewrite the following response in 1-2 sentences maximum.
Keep the key answer but remove all explanation and examples.
Output ONLY the brief version, nothing else."""


async def speculate_background(
    session_id: str,
    assistant_reply: str,
    platform: str = "",
) -> None:
    """
    Fire-and-forget background task.
    Generates follow-up questions and a brief version of the last reply.
    """
    from services.analytics_service import get_feature_flag
    if not get_feature_flag("speculation", True):
        return

    if len(assistant_reply) < 50:
        return  # Too short to speculate on

    try:
        from services.inference_service import generate_full_response

        # Run follow-ups and brief version in parallel
        followup_task = asyncio.create_task(_generate_follow_ups(assistant_reply))
        brief_task = asyncio.create_task(_generate_brief(assistant_reply))

        follow_ups_raw, brief = await asyncio.gather(followup_task, brief_task)

        questions = [q.strip() for q in follow_ups_raw.strip().split("\n") if q.strip()][:3]

        _cache[session_id] = SpeculationCache(
            follow_up_questions=questions,
            brief_version=brief.strip(),
            for_message=assistant_reply[:100],
        )
    except Exception:
        pass


async def _generate_follow_ups(reply: str) -> str:
    from services.inference_service import generate_full_response
    text, _, _ = await generate_full_response(
        task="support",
        system_prompt=_FOLLOW_UP_SYSTEM,
        user_prompt=reply[:1500],
        temperature=0.7,
        max_tokens=150,
    )
    return text


async def _generate_brief(reply: str) -> str:
    if len(reply) < 200:
        return reply  # Already short enough
    from services.inference_service import generate_full_response
    text, _, _ = await generate_full_response(
        task="support",
        system_prompt=_BRIEF_SYSTEM,
        user_prompt=reply[:2000],
        temperature=0.1,
        max_tokens=100,
    )
    return text


def get_speculation(session_id: str) -> SpeculationCache | None:
    """Retrieve cached speculation for a session (returns None if expired)."""
    entry = _cache.get(session_id)
    if not entry:
        return None
    if time.time() - entry.cached_at > _CACHE_TTL:
        del _cache[session_id]
        return None
    return entry


def get_brief_version(session_id: str) -> str | None:
    """Return the pre-generated brief version of the last reply."""
    entry = get_speculation(session_id)
    return entry.brief_version if entry else None


def get_follow_up_questions(session_id: str) -> list[str]:
    """Return the pre-generated follow-up questions."""
    entry = get_speculation(session_id)
    return entry.follow_up_questions if entry else []
