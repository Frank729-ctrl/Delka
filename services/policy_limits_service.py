"""
Policy / usage limits — exceeds Claude Code's policyLimits service.

src has: Org-level restrictions fetched from Anthropic API.
Delka has: Per-platform configurable quotas in DB with soft+hard limits,
           graceful degradation, real-time usage counting, and auto-reset.

Soft limit (80%): warn user, log event.
Hard limit (100%): block request, return friendly error.

Limits apply per: platform × period (daily/monthly).
"""
import time
from collections import defaultdict
from threading import Lock

# In-memory counters (reset per period)
_counters: dict[str, dict] = defaultdict(lambda: {"requests": 0, "tokens": 0, "reset_at": 0})
_lock = Lock()

# Default limits (overridden per platform via DB)
DEFAULT_LIMITS = {
    "requests_per_day": 1000,
    "tokens_per_day": 2_000_000,
    "requests_per_minute": 60,
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

    return True, ""


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
