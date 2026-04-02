"""
Context window analytics — inspired by Claude Code's contextAnalysis.ts

Breaks down exactly what is consuming the context window per request:
- System prompt (base + plugins + search + memories)
- Conversation history (number of turns, token estimate)
- Current message
- Available remaining tokens

Used to:
1. Surface warnings before context overflows
2. Inform compact_service on what to prune first
3. Admin dashboard insight into context usage patterns
"""
from dataclasses import dataclass, field


# Rough token estimations (1 token ≈ 4 chars for English)
def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# Context windows per provider/model
_CONTEXT_WINDOWS: dict[str, int] = {
    # Groq
    "llama-3.1-8b-instant": 131_072,
    "llama-3.3-70b-versatile": 131_072,
    # Gemini
    "gemini-2.5-pro": 1_048_576,
    # Cerebras
    "llama-3.3-70b": 8_192,
    "qwen3-235b": 8_192,
    # NVIDIA
    "meta/llama-3.1-70b-instruct": 131_072,
    # Ollama
    "llama3.1": 8_192,
    "mistral": 32_768,
    "codellama": 16_384,
}

DEFAULT_CONTEXT_WINDOW = 32_768
SAFETY_BUFFER = 0.15   # Reserve 15% for response


@dataclass
class ContextBreakdown:
    system_prompt_tokens: int = 0
    history_tokens: int = 0
    plugin_context_tokens: int = 0
    search_context_tokens: int = 0
    memory_tokens: int = 0
    current_message_tokens: int = 0
    total_tokens: int = 0
    context_window: int = DEFAULT_CONTEXT_WINDOW
    available_tokens: int = DEFAULT_CONTEXT_WINDOW
    utilization_pct: float = 0.0
    is_near_limit: bool = False     # > 70% used
    is_critical: bool = False       # > 90% used
    warnings: list[str] = field(default_factory=list)


def analyze_context(
    system_prompt: str,
    history: list[dict],
    current_message: str,
    plugin_context: str = "",
    search_context: str = "",
    memory_context: str = "",
    model: str = "",
) -> ContextBreakdown:
    """
    Analyze context usage for a single request.
    Returns a ContextBreakdown with token estimates and warnings.
    """
    context_window = _CONTEXT_WINDOWS.get(model, DEFAULT_CONTEXT_WINDOW)
    usable = int(context_window * (1 - SAFETY_BUFFER))

    system_tokens = _estimate_tokens(system_prompt)
    plugin_tokens = _estimate_tokens(plugin_context)
    search_tokens = _estimate_tokens(search_context)
    memory_tokens = _estimate_tokens(memory_context)
    message_tokens = _estimate_tokens(current_message)

    history_tokens = sum(
        _estimate_tokens(m.get("content", ""))
        for m in history
        if isinstance(m.get("content"), str)
    )

    total = system_tokens + plugin_tokens + search_tokens + memory_tokens + history_tokens + message_tokens
    available = max(0, usable - total)
    utilization = total / usable if usable > 0 else 1.0

    warnings = []
    if utilization > 0.9:
        warnings.append("Context is 90%+ full — oldest history will be compacted on next turn.")
    elif utilization > 0.7:
        warnings.append("Context is 70%+ full — consider starting a new session for long conversations.")
    if history_tokens > system_tokens * 3:
        warnings.append("Conversation history is the largest context consumer — compact is recommended.")
    if search_tokens > 2000:
        warnings.append("Web search results are consuming significant context.")

    return ContextBreakdown(
        system_prompt_tokens=system_tokens,
        history_tokens=history_tokens,
        plugin_context_tokens=plugin_tokens,
        search_context_tokens=search_tokens,
        memory_tokens=memory_tokens,
        current_message_tokens=message_tokens,
        total_tokens=total,
        context_window=context_window,
        available_tokens=available,
        utilization_pct=round(utilization * 100, 1),
        is_near_limit=utilization > 0.7,
        is_critical=utilization > 0.9,
        warnings=warnings,
    )


def format_breakdown(bd: ContextBreakdown) -> str:
    """Human-readable breakdown for admin/debug use."""
    lines = [
        f"Context Usage: {bd.total_tokens:,} / {bd.context_window:,} tokens ({bd.utilization_pct}%)",
        f"  System prompt:  {bd.system_prompt_tokens:,}",
        f"  History:        {bd.history_tokens:,}",
        f"  Plugin context: {bd.plugin_context_tokens:,}",
        f"  Search context: {bd.search_context_tokens:,}",
        f"  Memory:         {bd.memory_tokens:,}",
        f"  Current msg:    {bd.current_message_tokens:,}",
        f"  Available:      {bd.available_tokens:,}",
    ]
    if bd.warnings:
        lines += [""] + [f"⚠ {w}" for w in bd.warnings]
    return "\n".join(lines)
