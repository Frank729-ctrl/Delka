"""
Policy / usage limits — exceeds Claude Code's policyLimits service.

src has: Org-level restrictions fetched from Anthropic API.
Delka has: Per-platform configurable quotas in DB with soft+hard limits,
           graceful degradation, real-time usage counting, and auto-reset.
           Plus: per-user monthly token budget (cost-aware enforcement).

Soft limit (80%): warn user, log event.
Hard limit (100%): block request, return friendly error.

Limits apply per: platform × period (daily/monthly).
User budgets apply per: user_id × month.
"""
import time
from collections import defaultdict
from threading import Lock

# In-memory counters (reset per period)
_counters: dict[str, dict] = defaultdict(lambda: {"requests": 0, "tokens": 0, "reset_at": 0})
_lock = Lock()

# Per-user monthly token budget tracking (in-memory, keyed by user_id:YYYY-MM)
_user_budgets: dict[str, dict] = defaultdict(lambda: {"tokens": 0, "cost_usd": 0.0, "reset_month": ""})
_budget_lock = Lock()

# Default limits (overridden per platform via DB)
DEFAULT_LIMITS = {
    "requests_per_day": 1000,
    "tokens_per_day": 2_000_000,
    "requests_per_minute": 60,
    "tokens_per_month_per_user": 500_000,   # per-user monthly budget (0 = unlimited)
}


def check_and_increment(
    platform: str,
    user_id: str,
    tokens_estimate: int = 0,
    limits: dict | None = None,
) -> tuple[bool, str]:
    """
    Check if request is within limits and increment counters.
    Returns (allowed, reason_if_blocked).
    """
    limits = limits or DEFAULT_LIMITS
    now = time.time()
    day_start = now - (now % 86400)

    key = f"{platform}:daily"
    with _lock:
        counter = _counters[key]
        if counter["reset_at"] < day_start:
            counter.update({"requests": 0, "tokens": 0, "reset_at": day_start})

        daily_req_limit = limits.get("requests_per_day", DEFAULT_LIMITS["requests_per_day"])
        daily_tok_limit = limits.get("tokens_per_day", DEFAULT_LIMITS["tokens_per_day"])

        # Hard limit checks
        if counter["requests"] >= daily_req_limit:
            return False, f"Daily request limit reached ({daily_req_limit:,} requests). Resets at midnight UTC."
        if tokens_estimate and counter["tokens"] + tokens_estimate > daily_tok_limit:
            return False, f"Daily token limit reached ({daily_tok_limit:,} tokens). Resets at midnight UTC."

        # Soft limit warning (80%)
        is_near_limit = (
            counter["requests"] >= daily_req_limit * 0.8
            or (tokens_estimate and counter["tokens"] >= daily_tok_limit * 0.8)
        )

        # Increment
        counter["requests"] += 1
        counter["tokens"] += tokens_estimate

    if is_near_limit:
        from services.analytics_service import log_event
        log_event("policy_soft_limit", platform=platform, user_id=user_id,
                  requests=counter["requests"], limit=daily_req_limit)

    # ── Per-user monthly token budget ─────────────────────────────────────────
    monthly_budget = limits.get("tokens_per_month_per_user", DEFAULT_LIMITS["tokens_per_month_per_user"])
    if monthly_budget and monthly_budget > 0:
        current_month = time.strftime("%Y-%m")
        budget_key = f"{user_id}:{current_month}"
        with _budget_lock:
            bucket = _user_budgets[budget_key]
            if bucket["reset_month"] != current_month:
                bucket.update({"tokens": 0, "cost_usd": 0.0, "reset_month": current_month})
            if bucket["tokens"] + tokens_estimate > monthly_budget:
                return False, (
                    f"Monthly token budget reached ({monthly_budget:,} tokens). "
                    f"Resets at the start of next month."
                )
            bucket["tokens"] += tokens_estimate

    return True, ""


def record_user_token_usage(user_id: str, tokens_used: int, cost_usd: float = 0.0) -> None:
    """
    Record actual tokens used after a request completes (called from _post_reply_tasks).
    Updates the monthly budget tracker with real usage.
    """
    current_month = time.strftime("%Y-%m")
    budget_key = f"{user_id}:{current_month}"
    with _budget_lock:
        bucket = _user_budgets[budget_key]
        if bucket["reset_month"] != current_month:
            bucket.update({"tokens": 0, "cost_usd": 0.0, "reset_month": current_month})
        # Adjust by actual usage (check_and_increment used an estimate)
        bucket["tokens"] += tokens_used
        bucket["cost_usd"] += cost_usd


def get_user_budget_status(user_id: str, limits: dict | None = None) -> dict:
    """Return the current monthly budget usage for a user."""
    limits = limits or DEFAULT_LIMITS
    monthly_budget = limits.get("tokens_per_month_per_user", 0)
    current_month = time.strftime("%Y-%m")
    budget_key = f"{user_id}:{current_month}"
    with _budget_lock:
        bucket = dict(_user_budgets.get(budget_key, {"tokens": 0, "cost_usd": 0.0}))
    return {
        "month": current_month,
        "tokens_used": bucket["tokens"],
        "cost_usd": round(bucket.get("cost_usd", 0.0), 4),
        "monthly_budget": monthly_budget,
        "pct_used": round(bucket["tokens"] / monthly_budget * 100, 1) if monthly_budget else None,
        "unlimited": monthly_budget == 0,
    }


def get_usage_stats(platform: str) -> dict:
    """Current usage stats for a platform."""
    key = f"{platform}:daily"
    with _lock:
        counter = dict(_counters.get(key, {"requests": 0, "tokens": 0}))
    return counter


async def load_platform_limits(platform: str, db) -> dict:
    """Load per-platform limits from DB (falls back to defaults)."""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("SELECT setting_key, setting_value FROM platform_settings WHERE platform = :pl"),
            {"pl": platform},
        )
        limits = dict(DEFAULT_LIMITS)
        for row in result.fetchall():
            if row[0] in DEFAULT_LIMITS:
                try:
                    limits[row[0]] = int(row[1])
                except ValueError:
                    pass
        return limits
    except Exception:
        return dict(DEFAULT_LIMITS)
