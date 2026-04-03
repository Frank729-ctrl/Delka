"""
Effort Estimation + Smart Model Routing — exceeds Claude Code's effort.ts.

src: effort.ts estimates quick/medium/slow from request to inform behaviour.
     But src is locked to one provider (Anthropic), so effort only adjusts
     temperature/max_tokens — it can't change the model.

Delka: effort classification DRIVES MODEL SELECTION across 5 providers.
       Each effort tier maps to a different provider+model optimised for that
       cost/quality tradeoff. This is the key advantage over src.

Effort tiers:
  quick    → Groq llama-3.1-8b       (< 200ms, simple Q&A, chitchat, lookups)
  medium   → Groq llama-3.3-70b      (reasoning, explanations, summaries)
  complex  → Gemini 2.5 Pro          (multi-step plans, long documents, analysis)
  code     → Cerebras Qwen3-235B     (any code-related task)
  creative → Groq llama-3.3-70b      (writing, emails, brainstorming)
  vision   → NVIDIA vision model     (images, diagrams)

Classification is rule-based (fast, no extra API call) with token-count
and regex signals. The result is injected into inference_service's
get_task_chain() to override the generic task chain.

Why this beats src:
  - src: effort → adjust temperature only (same model always)
  - Delka: effort → different provider+model (Cerebras for code = 10x faster
    than Gemini for code; Groq for quick = cheapest; Gemini for complex = best
    reasoning)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


# ── Effort tier dataclass ─────────────────────────────────────────────────────

@dataclass
class EffortEstimate:
    tier: str                  # quick | medium | complex | code | creative | vision
    task: str                  # maps to inference_service task chain key
    confidence: float          # 0.0–1.0
    signals: list[str]         # human-readable list of what triggered this
    temperature: float         # suggested temperature
    max_tokens: int            # suggested max tokens
    reasoning: str             # one-line explanation (logged + emitted in SSE metadata)


# ── Signal patterns ───────────────────────────────────────────────────────────

# Code signals — highest priority
_CODE_RE = re.compile(
    r"""
    \b(
        write\s+(a\s+)?(function|class|script|program|api|endpoint|test|module|decorator|hook|component|query|migration|dockerfile|makefile|schema)
      | (fix|debug|refactor|optimize|review|explain|analyse|analyze)\s+.{0,30}(code|function|class|script|bug|error|exception|traceback|stacktrace)
      | (?:def|class|import|export|const|let|var|function|async|await|return|yield|interface|type\s+\w+\s*=)\s
      | (sql|regex|bash|shell|docker|kubernetes|terraform|git\s+|npm|pip|cargo|make)\s
      | (implement|create|build)\s.{0,30}(api|endpoint|service|server|client|database|orm|model|schema|migration|route|middleware|hook|component|reducer|action|selector|store)
      | code\s+(review|quality|smell|coverage|style|lint|format)
      | (unit\s+test|integration\s+test|pytest|jest|mocha|cypress|playwright)
      | (algorithm|data\s+structure|complexity|big.o|recursion|dynamic\s+programming|graph\s+traversal)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Complex signals — deep analysis, multi-step, long content
_COMPLEX_RE = re.compile(
    r"""
    \b(
        (analyse|analyze|evaluate|assess|compare|contrast|critique|review)\s.{0,40}(report|document|essay|research|plan|strategy|proposal|thesis|paper|article)
      | (write|draft|create|generate)\s.{0,20}(detailed|comprehensive|thorough|complete|full|in-depth|exhaustive)
      | (explain|describe|summarize)\s.{0,30}(in\s+detail|step\s+by\s+step|thoroughly|comprehensively)
      | (business\s+plan|market\s+research|competitive\s+analysis|swot|pestle|financial\s+model|investment\s+thesis)
      | (translate|rewrite|restructure)\s.{0,20}(entire|whole|full|complete|all\s+of)
      | (synthesize|synthesise|integrate)\s.{0,30}(multiple|several|various|all)
      | (strategy|roadmap|architecture|framework|methodology|curriculum|lesson\s+plan)
      | multiple\s+(steps?|parts?|sections?|components?|aspects?)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Creative signals
_CREATIVE_RE = re.compile(
    r"""
    \b(
        (write|draft|compose|create)\s.{0,30}(email|letter|essay|story|poem|blog|post|caption|bio|speech|cover\s+letter|proposal|pitch|message|announcement|newsletter|ad\s+copy|tagline|slogan)
      | (brainstorm|ideas?\s+for|come\s+up\s+with|think\s+of|suggest)\s
      | (make\s+(it|this|the)\s+(sound|feel|look|seem|more|less)|(reword|rephrase|paraphrase|improve|polish|rewrite)\s)
      | creative|storytelling|narrative|tone|voice|style
      | (professional|formal|casual|friendly|persuasive|engaging)\s+(tone|voice|style|version)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Vision signals
_VISION_RE = re.compile(
    r"\b(image|photo|picture|diagram|chart|graph|screenshot|figure|illustration|logo|infographic|visual)\b",
    re.IGNORECASE,
)

# Quick signals — simple, closed-form answers
_QUICK_RE = re.compile(
    r"""
    \b(
        (what\s+(is|are|does|time|day|date)|when\s+(is|was|did)|where\s+(is|are)|who\s+(is|was|are))
      | (how\s+much|how\s+many|how\s+long|how\s+far|how\s+old)
      | (yes\s+or\s+no|true\s+or\s+false|is\s+it\s+true)
      | (hi|hello|hey|thanks|thank\s+you|ok|okay|sure|got\s+it|understood|makes\s+sense|sounds\s+good)
      | (define|definition\s+of|meaning\s+of|what\s+does\s+.{1,30}\s+mean)
      | (list\s+.{0,20}(top\s+\d+|few|some|examples?\s+of))
      | (convert|calculate|how\s+to\s+convert|what\s+is\s+\d+\s+\w+\s+in)
      | \d+\s*[\+\-\*\/\%]\s*\d+   # arithmetic expression
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ── Token-count signals ───────────────────────────────────────────────────────

def _estimate_word_count(text: str) -> int:
    return len(text.split())


def _has_long_content(text: str) -> bool:
    """Long messages usually mean complex tasks (user pasted content to work with)."""
    return _estimate_word_count(text) > 150


def _has_multiple_questions(text: str) -> bool:
    return text.count("?") >= 2 or bool(re.search(r"\b(and\s+also|additionally|furthermore|as\s+well\s+as|plus)\b", text, re.I))


def _has_code_block(text: str) -> bool:
    return "```" in text or text.count("    ") >= 3  # fenced or indented code


# ── Classification ────────────────────────────────────────────────────────────

def estimate_effort(message: str, history_length: int = 0) -> EffortEstimate:
    """
    Classify a message into an effort tier and return provider/model guidance.

    Args:
        message:        The user's message text
        history_length: Number of prior messages in session (longer sessions
                        skew toward complex routing)

    Returns:
        EffortEstimate with tier, task, temperature, max_tokens, reasoning
    """
    signals: list[str] = []
    word_count = _estimate_word_count(message)

    # ── Tier detection (priority order: code > complex > creative > vision > quick > medium) ──

    # Code — highest priority (specialized provider gives best results)
    if _CODE_RE.search(message) or _has_code_block(message):
        if _has_code_block(message):
            signals.append("contains code block")
        else:
            signals.append("code-task keywords")
        return EffortEstimate(
            tier="code",
            task="code",
            confidence=0.90,
            signals=signals,
            temperature=0.2,    # low temp for deterministic code
            max_tokens=4096,
            reasoning="Code task → Cerebras Qwen3-235B (fastest large model for code)",
        )

    # Vision — image in message or explicit image request
    if _VISION_RE.search(message):
        signals.append("vision/image keywords")
        # Only override if no code or complex context
        if word_count < 80:
            return EffortEstimate(
                tier="vision",
                task="chat",        # chat chain with NVIDIA vision capable
                confidence=0.75,
                signals=signals,
                temperature=0.5,
                max_tokens=1024,
                reasoning="Vision task → routed via vision-capable provider",
            )

    # Complex — long content, multi-part, deep analysis
    complex_match = _COMPLEX_RE.search(message)
    if complex_match or _has_long_content(message) or _has_multiple_questions(message):
        if complex_match:
            signals.append(f"complex-task keyword: '{complex_match.group(0).strip()[:40]}'")
        if _has_long_content(message):
            signals.append(f"long message ({word_count} words)")
        if _has_multiple_questions(message):
            signals.append("multiple questions detected")
        return EffortEstimate(
            tier="complex",
            task="cv",              # cv chain = Gemini 2.5 Pro primary (best reasoning)
            confidence=0.85,
            signals=signals,
            temperature=0.6,
            max_tokens=8192,
            reasoning="Complex task → Gemini 2.5 Pro (best reasoning, large context)",
        )

    # Creative — writing, drafting, brainstorming
    creative_match = _CREATIVE_RE.search(message)
    if creative_match:
        signals.append(f"creative-task keyword: '{creative_match.group(0).strip()[:40]}'")
        return EffortEstimate(
            tier="creative",
            task="support",         # support chain = Groq 70b primary (fluent writing)
            confidence=0.80,
            signals=signals,
            temperature=0.85,       # higher temp for creativity
            max_tokens=2048,
            reasoning="Creative task → Groq llama-3.3-70b (fluent, fast writing)",
        )

    # Quick — simple closed-form answer
    quick_match = _QUICK_RE.search(message)
    if quick_match and word_count < 40 and not _has_multiple_questions(message):
        signals.append(f"quick-answer pattern: '{quick_match.group(0).strip()[:40]}'")
        return EffortEstimate(
            tier="quick",
            task="chat",            # chat chain = Groq 8b (fastest, cheapest)
            confidence=0.85,
            signals=signals,
            temperature=0.5,
            max_tokens=512,
            reasoning="Quick lookup → Groq llama-3.1-8b (fastest, no reasoning needed)",
        )

    # Medium fallback — general conversation, explanations, moderate reasoning
    signals.append("no strong tier signal → medium default")
    return EffortEstimate(
        tier="medium",
        task="chat",
        confidence=0.60,
        signals=signals,
        temperature=0.7,
        max_tokens=2048,
        reasoning="Medium effort → Groq llama-3.3-70b (good balance of speed + quality)",
    )


# ── Override helpers for inference_service ────────────────────────────────────

def get_effort_chain_override(estimate: EffortEstimate) -> list[dict] | None:
    """
    Returns a modified task chain if effort routing should override the default.
    Returns None if the default chain is fine (medium tier).

    This is the key function — it lets inference_service swap the chain
    based on what the message actually needs, not just what endpoint was called.
    """
    from config import settings

    overrides: dict[str, list[dict]] = {
        "quick": [
            # Groq 8b — fastest, cheapest, sufficient for simple Q&A
            {"provider": "groq", "model": settings.SUPPORT_PRIMARY_MODEL},
            {"provider": "ollama", "model": settings.OLLAMA_MODEL},
        ],
        "code": [
            # Cerebras first (fastest large model for code), then Groq, then Ollama
            {"provider": "cerebras", "model": settings.CODE_PRIMARY_MODEL},
            {"provider": "groq", "model": settings.CODE_SECONDARY_MODEL},
            {"provider": "ollama", "model": settings.OLLAMA_MODEL},
        ],
        "complex": [
            # Gemini 2.5 Pro first (best reasoning + 1M token context), then Groq 70b
            {"provider": "gemini", "model": settings.CV_PRIMARY_MODEL},
            {"provider": "groq", "model": settings.SUPPORT_SECONDARY_MODEL},
            {"provider": "ollama", "model": settings.OLLAMA_MODEL},
        ],
        "creative": [
            # Groq 70b (fluent, fast), then Cerebras, then Ollama
            {"provider": "groq", "model": settings.SUPPORT_SECONDARY_MODEL},
            {"provider": "cerebras", "model": settings.CODE_PRIMARY_MODEL},
            {"provider": "ollama", "model": settings.OLLAMA_MODEL},
        ],
    }

    return overrides.get(estimate.tier)   # medium + vision → None (use default chain)


def effort_metadata(estimate: EffortEstimate) -> dict:
    """Return effort info suitable for SSE metadata event."""
    return {
        "tier": estimate.tier,
        "task": estimate.task,
        "confidence": estimate.confidence,
        "reasoning": estimate.reasoning,
        "temperature": estimate.temperature,
        "max_tokens": estimate.max_tokens,
    }
