"""
Token counter — estimates token usage for messages and enforces context limits.

Inspired by Claude Code's tokenEstimation.ts + contextAnalysis.ts.

Uses a fast character-based heuristic (4 chars ≈ 1 token) rather than a
full tokenizer — accurate enough for routing decisions without adding a
heavy dependency. Falls back to exact count via tiktoken if available.

Context window budgets per model family:
  - groq/llama-3.1-8b-instant:     128k tokens
  - groq/llama-3.3-70b-versatile:  128k tokens
  - gemini-2.5-pro:                1M  tokens
  - cerebras/qwen3-235b:           128k tokens
  - nvidia/meta-llama-3.1-70b:     128k tokens
  - ollama/llama3.1:               8k  tokens (conservative)
"""
from __future__ import annotations

_CONTEXT_WINDOWS: dict[str, int] = {
    # Groq
    "llama-3.1-8b-instant":       131_072,
    "llama-3.3-70b-versatile":    131_072,
    "llama-3.1-70b-versatile":    131_072,
    # Gemini
    "gemini-2.5-pro":           1_048_576,
    "gemini-2.0-flash":         1_048_576,
    # Cerebras
    "qwen3-235b":                 131_072,
    "llama-3.3-70b":              131_072,
    # NVIDIA NIM
    "meta/llama-3.1-70b-instruct": 131_072,
    # Ollama (conservative defaults)
    "llama3.1":                     8_192,
    "mistral":                      8_192,
    "codellama":                    16_384,
    "llava:13b":                    4_096,
}

# Reserve this many tokens for the model's output — never fill the whole window
_OUTPUT_RESERVE = 4_096

# Trigger auto-compact at this fraction of the usable context
COMPACT_THRESHOLD = 0.80


def estimate_tokens(text: str) -> int:
    """Fast heuristic: ~4 chars per token (works well for English + code)."""
    if not text:
        return 0
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Estimate total tokens for a messages array (OpenAI format)."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += estimate_tokens(block.get("text", "") or block.get("content", ""))
        # ~4 tokens overhead per message (role + formatting)
        total += 4
    return total


def get_context_window(model: str) -> int:
    """Return the context window size for a given model name."""
    for key, size in _CONTEXT_WINDOWS.items():
        if key in model.lower():
            return size
    return 8_192  # safe default


def get_usable_window(model: str) -> int:
    """Usable tokens = context window minus output reserve."""
    return get_context_window(model) - _OUTPUT_RESERVE


def should_compact(messages: list[dict], model: str) -> bool:
    """Return True if the conversation is approaching the context limit."""
    used = estimate_messages_tokens(messages)
    usable = get_usable_window(model)
    return used >= int(usable * COMPACT_THRESHOLD)


def context_usage_ratio(messages: list[dict], model: str) -> float:
    """Return how full the context window is (0.0 → 1.0)."""
    used = estimate_messages_tokens(messages)
    usable = get_usable_window(model)
    return min(1.0, used / usable)


def trim_messages_to_fit(
    messages: list[dict],
    model: str,
    keep_system: bool = True,
) -> list[dict]:
    """
    Hard trim: drop oldest non-system messages until messages fit.
    Used as a last resort when auto-compact is unavailable.
    """
    usable = get_usable_window(model)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    # Always keep system + last user message
    while other_msgs and estimate_messages_tokens(system_msgs + other_msgs) > usable:
        if len(other_msgs) <= 1:
            break
        other_msgs.pop(0)  # drop oldest

    return (system_msgs + other_msgs) if keep_system else other_msgs
