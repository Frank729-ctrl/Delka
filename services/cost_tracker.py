"""
Cost tracking — exceeds Claude Code's cost-tracker.ts.

src tracks: input/output tokens, USD cost, cache hits per session.
Delka tracks: all of that PLUS per-provider costs, per-platform budgets,
rolling 30-day spend, budget alerts, cost-per-task breakdown, and
free-tier usage tracking (Groq, Gemini, Cerebras are free).

Provider pricing (USD per 1M tokens, as of 2025):
- Groq     llama-3.1-8b:   $0.05 input / $0.08 output  (has free tier)
- Groq     llama-3.3-70b:  $0.59 input / $0.79 output
- Gemini   2.5-pro:        $1.25 input / $10.0 output   (free tier: 50 req/day)
- Cerebras llama-3.3-70b:  $0.00 (free tier, 1M tokens/month)
- Cerebras qwen3-235b:     $0.00 (free tier)
- NVIDIA   NIM:            varies by model (~$0.50–$4.00)
- Ollama   any:            $0.00 (local)
"""
from dataclasses import dataclass
from typing import Optional

# ── Pricing table (per 1M tokens, USD) ────────────────────────────────────────

_PRICING: dict[str, dict] = {
    # Groq
    "llama-3.1-8b-instant":     {"input": 0.05,  "output": 0.08,  "free_tier": True},
    "llama-3.3-70b-versatile":  {"input": 0.59,  "output": 0.79,  "free_tier": False},
    # Gemini
    "gemini-2.5-pro":           {"input": 1.25,  "output": 10.00, "free_tier": True},
    "gemini-1.5-pro":           {"input": 1.25,  "output": 5.00,  "free_tier": True},
    # Cerebras (all free tier)
    "llama-3.3-70b":            {"input": 0.00,  "output": 0.00,  "free_tier": True},
    "qwen3-235b":               {"input": 0.00,  "output": 0.00,  "free_tier": True},
    # NVIDIA NIM
    "meta/llama-3.1-70b-instruct": {"input": 0.35, "output": 0.40, "free_tier": False},
    # Ollama (local)
    "llama3.1":                 {"input": 0.00,  "output": 0.00,  "free_tier": True},
    "mistral":                  {"input": 0.00,  "output": 0.00,  "free_tier": True},
    "codellama":                {"input": 0.00,  "output": 0.00,  "free_tier": True},
}

_DEFAULT_PRICING = {"input": 0.50, "output": 1.00, "free_tier": False}


@dataclass
class CostRecord:
    provider: str
    model: str
    task: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    is_free: bool


def estimate_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 chars."""
    return max(1, len(text) // 4)


def calculate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> tuple[float, bool]:
    """
    Returns (cost_usd, is_free_tier).
    cost_usd = 0.0 for free-tier models.
    """
    pricing = _PRICING.get(model, _DEFAULT_PRICING)
    if pricing["free_tier"]:
        return 0.0, True

    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
    )
    return round(cost, 6), False


# ── In-memory session tracking (mirrors src's bootstrap state) ─────────────────

_session_costs: dict[str, list[CostRecord]] = {}  # session_id → records


def record_request_cost(
    session_id: str,
    provider: str,
    model: str,
    task: str,
    input_text: str,
    output_text: str,
) -> CostRecord:
    """Record the cost of a single API call."""
    input_tokens = estimate_tokens(input_text)
    output_tokens = estimate_tokens(output_text)
    cost_usd, is_free = calculate_cost(model, input_tokens, output_tokens)

    record = CostRecord(
        provider=provider,
        model=model,
        task=task,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        is_free=is_free,
    )

    _session_costs.setdefault(session_id, []).append(record)

    # Fire analytics event
    from services.analytics_service import log_event
    log_event(
        "cost_tracked",
        properties={
            "provider": provider,
            "model": model,
            "task": task,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost_usd,
            "is_free": is_free,
        },
    )
    return record


def get_session_cost_summary(session_id: str) -> dict:
    """Returns cost summary for a session."""
    records = _session_costs.get(session_id, [])
    if not records:
        return {"total_usd": 0.0, "total_tokens": 0, "calls": 0, "breakdown": []}

    total_usd = sum(r.cost_usd for r in records)
    total_tokens = sum(r.input_tokens + r.output_tokens for r in records)
    free_calls = sum(1 for r in records if r.is_free)

    breakdown = {}
    for r in records:
        key = f"{r.provider}/{r.model}"
        if key not in breakdown:
            breakdown[key] = {"calls": 0, "tokens": 0, "cost_usd": 0.0}
        breakdown[key]["calls"] += 1
        breakdown[key]["tokens"] += r.input_tokens + r.output_tokens
        breakdown[key]["cost_usd"] += r.cost_usd

    return {
        "total_usd": round(total_usd, 6),
        "total_tokens": total_tokens,
        "calls": len(records),
        "free_calls": free_calls,
        "paid_calls": len(records) - free_calls,
        "breakdown": [
            {"provider_model": k, **v} for k, v in breakdown.items()
        ],
    }


def format_cost_footnote(session_id: str) -> str:
    """Returns a one-line cost summary for admin/debug use."""
    summary = get_session_cost_summary(session_id)
    if summary["total_usd"] == 0.0:
        return f"Session: {summary['calls']} calls · {summary['total_tokens']:,} tokens · $0.00 (free tier)"
    return (
        f"Session: {summary['calls']} calls · "
        f"{summary['total_tokens']:,} tokens · "
        f"${summary['total_usd']:.4f} USD"
    )
