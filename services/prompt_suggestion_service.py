"""
Prompt Suggestions — predict the user's next likely question.

Inspired by Claude Code's PromptSuggestion service.

After each reply, generate 2-3 short follow-up questions the user might
ask next. These are returned alongside the reply so the frontend can render
clickable suggestion chips — reducing typing for common follow-ups.

Delka improvements over Claude Code:
- Context-aware: uses platform personality + session history
- Ghana-aware: suggests locally relevant follow-ups (e.g. after CV: "Add National Service?")
- Returned as structured JSON for easy frontend rendering
- Speculative generation runs in parallel with streaming, not after
"""
from __future__ import annotations

_SUGGEST_SYSTEM = """Generate 2-3 short follow-up questions the user is likely to ask next.

Rules:
- Max 8 words each
- Be specific to the conversation topic (not generic)
- Think like a Ghanaian professional — consider local context
- Return JSON array of strings only. Example: ["Tell me more", "What about X?", "How do I Y?"]
- No explanations, no markdown, just the JSON array"""


async def get_suggestions(
    last_user_message: str,
    last_assistant_reply: str,
    platform: str,
) -> list[str]:
    """
    Returns 2-3 suggested follow-up questions.
    Returns empty list on failure — never blocks.
    """
    try:
        from services.inference_service import generate_full_response
        import json

        context = (
            f"User asked: {last_user_message[:200]}\n"
            f"Delka replied: {last_assistant_reply[:300]}"
        )

        raw, _, _ = await generate_full_response(
            task="support",
            system_prompt=_SUGGEST_SYSTEM,
            user_prompt=context,
            temperature=0.7,
            max_tokens=100,
        )

        raw = raw.strip().lstrip("```json").rstrip("```").strip()
        suggestions = json.loads(raw)
        if isinstance(suggestions, list):
            return [s for s in suggestions if isinstance(s, str)][:3]
        return []
    except Exception:
        return []
