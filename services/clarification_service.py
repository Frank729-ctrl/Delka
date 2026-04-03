"""
Request Clarification Workflow — gates on ambiguous requests before LLM call.

src equivalent: Claude Code prompts the user with specific questions when a
request is ambiguous before burning tokens on a potentially wrong response.

How it works:
  1. Fast regex pre-filter: detect obviously vague patterns (quick + cheap)
  2. If vague: LLM generates 2-3 targeted clarifying questions (fast, small model)
  3. Chat service returns {"type": "clarification", "questions": [...]} and stops
  4. Client presents questions; user answers; next request is now specific

Why this beats "just trying to answer":
  - Saves tokens on large complex requests where the answer would be wrong
  - Improves response quality: vague input → generic answer
  - Matches src's approach: ask before acting, not ask after failing

Thresholds are conservative — only triggers for genuinely ambiguous requests,
not for short questions that are clear in context.

NOT triggered for:
  - Simple factual questions (even if brief)
  - Questions with clear intent from context
  - Creative requests (ambiguity is sometimes desirable)
  - Requests < 5 words (too short to be genuinely complex)
  - When recent_history >= 3 turns (context usually resolves ambiguity)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── Ambiguity signals ─────────────────────────────────────────────────────────
# Patterns that strongly suggest the request needs clarification.
# These are high-precision — many false negatives is OK, false positives hurt UX.

_VAGUE_RE = re.compile(
    r"""
    ^(
        (make|do|fix|improve|help|update|change|build|create|write|add|get)\s+
        (it|this|that|them|my|the|a|an)?\s*
        (better|good|nice|right|work|correct|proper|it)?\s*$
      | (do\s+)?something\s+(about|with|for)\s+(it|this|that)\s*$
      | (can\s+you\s+)?(help|assist)\s+(me\s+)?(with\s+)?(this|it|that)\s*$
      | (what|how)\s+do\s+i\s+(do|fix|make|get)\s+(this|it|that)\s*$
      | (fix|debug|improve)\s+this\s*$
      | make\s+it\s+(work|better|faster|good)\s*$
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Multi-word vague patterns (for longer messages)
_AMBIGUOUS_SIGNALS = [
    (r"\b(it|this|that|them)\b", 3),          # 3+ pronouns without clear referent
    (r"\b(stuff|things|everything|anything)\b", 1),  # vague nouns
    (r"\b(somehow|somehow|kinda|sort of|kind of)\b", 1),  # hedging
    (r"\b(make it|fix it|change it|do it)\b", 1),   # action without object
]


@dataclass
class ClarificationResult:
    needs_clarification: bool
    questions: list[str]
    confidence: float      # 0.0–1.0 how confident we are that clarification is needed
    reason: str            # why we think this is ambiguous


_NO_CLARIFICATION = ClarificationResult(
    needs_clarification=False, questions=[], confidence=0.0, reason=""
)

_CLARIFICATION_SYSTEM = """\
You are a request analyzer. Your job is to identify if a user request is too vague
to answer well, and if so, generate 2-3 targeted clarifying questions.

A request needs clarification if:
- The subject/object is unclear (pronouns without referent: "fix it", "make it better")
- The scope is undefined ("improve my app" — which part?)
- The goal is ambiguous ("help me with this" — what outcome?)
- Multiple valid interpretations exist that would lead to different responses

A request does NOT need clarification if:
- It's a simple factual question
- The intent is clear even if brief
- It's creative (some ambiguity is fine)
- The context makes it clear

Respond with ONLY valid JSON:
{
  "needs_clarification": true|false,
  "questions": ["question 1", "question 2"],
  "reason": "one sentence explaining why this is ambiguous"
}

Rules:
- 2-3 questions maximum, never more
- Questions must be specific and answerable
- If needs_clarification is false, questions must be []
- Be conservative: only flag genuinely ambiguous requests
"""


def _fast_check(message: str, history_length: int) -> Optional[ClarificationResult]:
    """
    Regex pre-filter. Returns a result only for obviously vague messages.
    Returns None if we can't determine from regex alone (escalate to LLM).
    """
    msg = message.strip()
    word_count = len(msg.split())

    # Too short to be a complex ambiguous request
    if word_count < 4:
        return _NO_CLARIFICATION

    # Lots of conversation history → context usually resolves ambiguity
    if history_length >= 3:
        return _NO_CLARIFICATION

    # Exact vague pattern match → definitely needs clarification
    if _VAGUE_RE.match(msg):
        return ClarificationResult(
            needs_clarification=True,
            questions=[],   # will be filled by LLM
            confidence=0.9,
            reason="Request matches a known vague pattern",
        )

    # Score ambiguity signals
    score = 0
    for pattern, weight in _AMBIGUOUS_SIGNALS:
        matches = re.findall(pattern, msg, re.IGNORECASE)
        score += len(matches) * weight

    # High ambiguity score on a short message → likely vague
    if score >= 4 and word_count <= 15:
        return ClarificationResult(
            needs_clarification=True,
            questions=[],
            confidence=0.6,
            reason=f"High ambiguity signal score ({score}) on short message",
        )

    return None  # undetermined — escalate to LLM if needed


async def check_needs_clarification(
    message: str,
    history_length: int = 0,
    use_llm: bool = True,
) -> ClarificationResult:
    """
    Two-tier ambiguity check:
      1. Fast regex (always) — catches obvious cases
      2. LLM classifier (optional, only for messages 10–50 words) — catches subtle ones

    Returns ClarificationResult. If needs_clarification is True but questions is [],
    the caller should generate questions separately via generate_clarifications().

    Args:
        message: The user's message
        history_length: Number of prior turns (more context = less likely to need clarification)
        use_llm: Set False to skip LLM (faster, lower accuracy)
    """
    # Tier 1: fast regex
    fast_result = _fast_check(message, history_length)
    if fast_result is not None:
        return fast_result

    # Only run LLM for messages in the ambiguous middle zone
    word_count = len(message.split())
    if not use_llm or word_count < 5 or word_count > 80:
        return _NO_CLARIFICATION

    # Tier 2: LLM classifier (fast, small model, short response)
    try:
        import asyncio
        from services.inference_service import generate_full_response
        import json, re as _re

        response, _, _ = await asyncio.wait_for(
            generate_full_response(
                task="support",   # faster chain than "chat" — classifiers don't need quality
                system_prompt=_CLARIFICATION_SYSTEM,
                user_prompt=f"Analyze this request:\n{message}",
                temperature=0.0,
                max_tokens=200,
            ),
            timeout=3.0,
        )

        # Parse JSON response
        clean = _re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()
        data = json.loads(clean)
        needs = data.get("needs_clarification", False)
        questions = data.get("questions", [])
        reason = data.get("reason", "")

        return ClarificationResult(
            needs_clarification=bool(needs),
            questions=questions[:3],
            confidence=0.8,
            reason=reason,
        )

    except Exception:
        # Fail-open — on any error, don't block the request
        return _NO_CLARIFICATION


async def generate_clarifications(
    message: str,
    context: str = "",
) -> list[str]:
    """
    Generate 2-3 targeted clarifying questions for a vague message.
    Called when check_needs_clarification returns True but questions=[].
    """
    try:
        import asyncio
        from services.inference_service import generate_full_response
        import json, re as _re

        ctx_block = f"\nRecent context:\n{context[:300]}" if context else ""
        response, _, _ = await asyncio.wait_for(
            generate_full_response(
                task="support",
                system_prompt=_CLARIFICATION_SYSTEM,
                user_prompt=f"Generate clarifying questions for this vague request:{ctx_block}\n\nRequest: {message}",
                temperature=0.2,
                max_tokens=200,
            ),
            timeout=4.0,
        )

        clean = _re.sub(r"```(?:json)?\s*|\s*```", "", response).strip()
        data = json.loads(clean)
        return data.get("questions", [])[:3]

    except Exception:
        # Fallback: generic questions if LLM fails
        return [
            "Could you be more specific about what you'd like me to do?",
            "What outcome are you hoping for?",
        ]


def format_clarification_response(questions: list[str], reason: str = "") -> dict:
    """Format the clarification result as an SSE-compatible JSON event."""
    return {
        "type": "clarification",
        "questions": questions,
        "message": "I need a bit more detail to give you the best answer:",
        "reason": reason,
    }
