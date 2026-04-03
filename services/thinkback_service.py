"""
Thinkback — deep conversation analysis for self-improvement and user insight.

Exceeds Claude Code's session summarization by extracting structured intelligence:
  - Key decisions made (and alternatives that were rejected)
  - Errors committed (wrong answers, hallucinations, misunderstandings)
  - User intent evolution (how the goal shifted during the session)
  - Action items + open questions still unresolved
  - Patterns in how the user asks questions (so future sessions adapt)
  - Confidence calibration (was the AI over/under-confident?)
  - Topic map: what subjects were covered and in what depth

src reference:
  - compactConversation.ts: only collapses history into a summary
  - No structured insight extraction, no error detection, no pattern analysis

Delka adds:
  POST /v1/chat/analyze — analyze any session on demand, returns JSON insight object
  The insight object is optionally stored as a project-type memory for future recall.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ConversationInsight:
    session_id: str
    turn_count: int

    # Structured insight fields
    summary: str = ""
    key_decisions: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)         # {turn, description, severity}
    intent_evolution: list[str] = field(default_factory=list)  # how user goal shifted
    action_items: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    user_patterns: list[str] = field(default_factory=list)   # how user prefers to communicate
    confidence_issues: list[str] = field(default_factory=list)  # where AI was poorly calibrated

    # Meta
    model_used: str = ""
    analysis_ms: float = 0.0


_ANALYSIS_SYSTEM = """\
You are a conversation analyst. Your job is to extract structured intelligence
from a conversation transcript between a user and an AI assistant.

Respond with ONLY valid JSON matching this exact schema:
{
  "summary": "2-3 sentence summary of what was accomplished",
  "key_decisions": ["decision 1", "decision 2"],
  "errors": [
    {"turn": 2, "description": "AI gave wrong date", "severity": "medium"}
  ],
  "intent_evolution": [
    "Started: user wanted X",
    "Shifted to: user actually needed Y"
  ],
  "action_items": ["todo item 1", "todo item 2"],
  "open_questions": ["question still unresolved"],
  "topics": ["topic1", "topic2"],
  "user_patterns": [
    "User asks follow-up questions when unsatisfied",
    "User prefers numbered lists"
  ],
  "confidence_issues": [
    "AI said 'definitely' but then retracted in turn 5"
  ]
}

Rules:
- key_decisions: things the user decided to do or not do, or approach changes
- errors: factual mistakes, hallucinations, misunderstandings by the AI
- intent_evolution: only include if the goal actually shifted; empty list if steady
- action_items: concrete next steps mentioned or implied
- open_questions: things raised but not resolved
- topics: subject areas (max 8)
- user_patterns: communication style observations (max 5)
- confidence_issues: only real problems, not just hedging language
- severity levels: low | medium | high
- If a list has nothing meaningful, return []
"""


def _format_transcript(history: list[dict], max_chars: int = 12_000) -> str:
    """Format conversation history as a numbered transcript."""
    lines = []
    for i, msg in enumerate(history, 1):
        role = "User" if msg.get("role") == "user" else "Delka"
        content = (msg.get("content") or "")[:500]
        lines.append(f"[{i}] {role}: {content}")
    transcript = "\n".join(lines)
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n... [truncated]"
    return transcript


def _parse_insight(text: str, session_id: str, turn_count: int) -> ConversationInsight:
    """Parse LLM JSON response into ConversationInsight. Tolerant of partial JSON."""
    insight = ConversationInsight(session_id=session_id, turn_count=turn_count)

    # Try full JSON parse first
    try:
        # Strip markdown code fences if present
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
        data = json.loads(clean)
        insight.summary = data.get("summary", "")
        insight.key_decisions = data.get("key_decisions", [])
        insight.errors = data.get("errors", [])
        insight.intent_evolution = data.get("intent_evolution", [])
        insight.action_items = data.get("action_items", [])
        insight.open_questions = data.get("open_questions", [])
        insight.topics = data.get("topics", [])
        insight.user_patterns = data.get("user_patterns", [])
        insight.confidence_issues = data.get("confidence_issues", [])
        return insight
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: extract summary with regex
    m = re.search(r'"summary"\s*:\s*"([^"]+)"', text)
    if m:
        insight.summary = m.group(1)
    return insight


async def analyze_session(
    session_id: str,
    user_id: str,
    platform: str,
    db: AsyncSession,
    store_as_memory: bool = False,
) -> ConversationInsight:
    """
    Analyze a past session and return structured insight.

    Args:
        session_id: The session to analyze
        user_id / platform: Used to fetch history and optionally store memory
        db: DB session
        store_as_memory: If True, saves a project-type memory with key findings
    """
    import time
    start = time.time()

    # Fetch conversation history
    from services.conversation_history_service import get_recent_history
    history = await get_recent_history(user_id, platform, db, session_id=session_id, limit=100)

    turn_count = len(history)
    insight = ConversationInsight(session_id=session_id, turn_count=turn_count)

    if not history:
        insight.summary = "No conversation history found for this session."
        return insight

    transcript = _format_transcript(history)

    # Run LLM analysis
    try:
        from services.inference_service import generate_full_response
        response, model, _ = await generate_full_response(
            task="chat",
            system_prompt=_ANALYSIS_SYSTEM,
            user_prompt=f"Analyze this conversation:\n\n{transcript}",
            temperature=0.1,
            max_tokens=1500,
        )
        insight = _parse_insight(response, session_id, turn_count)
        insight.model_used = model
    except Exception as e:
        insight.summary = f"Analysis failed: {str(e)[:200]}"

    insight.analysis_ms = round((time.time() - start) * 1000, 1)

    # Optionally persist key findings as a project memory
    if store_as_memory and (insight.action_items or insight.key_decisions):
        await _save_insight_as_memory(insight, user_id, platform, db)

    return insight


async def _save_insight_as_memory(
    insight: ConversationInsight,
    user_id: str,
    platform: str,
    db: AsyncSession,
) -> None:
    """Store the most important insight fields as a project-type session memory."""
    parts = []
    if insight.summary:
        parts.append(f"Summary: {insight.summary}")
    if insight.key_decisions:
        parts.append("Decisions: " + "; ".join(insight.key_decisions[:3]))
    if insight.action_items:
        parts.append("Action items: " + "; ".join(insight.action_items[:3]))
    if insight.open_questions:
        parts.append("Open questions: " + "; ".join(insight.open_questions[:2]))

    content = " | ".join(parts)[:800]
    title = f"Session analysis [{insight.session_id[:12]}]"

    try:
        from sqlalchemy import text
        await db.execute(
            text(
                "INSERT INTO session_memories (user_id, platform, mem_type, title, content) "
                "VALUES (:uid, :pl, 'project', :title, :content) "
                "ON CONFLICT (user_id, platform, title) DO UPDATE SET content = EXCLUDED.content"
            ),
            {"uid": user_id, "pl": platform, "title": title, "content": content},
        )
        await db.commit()
    except Exception:
        pass  # Memory storage failure is non-fatal


def format_insight_markdown(insight: ConversationInsight) -> str:
    """Format a ConversationInsight as a readable markdown report."""
    lines = [
        f"## Session Analysis",
        f"_Session: `{insight.session_id}` · {insight.turn_count} turns · "
        f"analyzed in {insight.analysis_ms}ms_",
        "",
    ]

    if insight.summary:
        lines += ["### Summary", insight.summary, ""]

    if insight.topics:
        lines += [f"**Topics:** {', '.join(insight.topics)}", ""]

    if insight.key_decisions:
        lines.append("### Key Decisions")
        lines += [f"- {d}" for d in insight.key_decisions]
        lines.append("")

    if insight.action_items:
        lines.append("### Action Items")
        lines += [f"- [ ] {a}" for a in insight.action_items]
        lines.append("")

    if insight.open_questions:
        lines.append("### Open Questions")
        lines += [f"- {q}" for q in insight.open_questions]
        lines.append("")

    if insight.intent_evolution:
        lines.append("### Intent Evolution")
        lines += [f"- {e}" for e in insight.intent_evolution]
        lines.append("")

    if insight.errors:
        lines.append("### AI Errors / Issues")
        for err in insight.errors:
            severity = err.get("severity", "?")
            desc = err.get("description", "")
            turn = err.get("turn", "?")
            lines.append(f"- [turn {turn}, {severity}] {desc}")
        lines.append("")

    if insight.user_patterns:
        lines.append("### User Communication Patterns")
        lines += [f"- {p}" for p in insight.user_patterns]
        lines.append("")

    if insight.confidence_issues:
        lines.append("### Confidence Calibration Issues")
        lines += [f"- {c}" for c in insight.confidence_issues]
        lines.append("")

    return "\n".join(lines)
