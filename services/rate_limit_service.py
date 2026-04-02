"""
Rate limit UX — inspired by Claude Code's rateLimitMessages.ts

When a provider is rate-limited or unavailable, instead of silently
switching providers, Delka surfaces a friendly, honest status message
so the user knows what's happening and when to retry.

Also tracks provider health so repeated failures trigger earlier fallback.
"""
import time
from collections import defaultdict
from threading import Lock


# ── Provider health tracker ───────────────────────────────────────────────────

_lock = Lock()
_failure_counts: dict[str, int] = defaultdict(int)
_last_failure_ts: dict[str, float] = defaultdict(float)
_rate_limited_until: dict[str, float] = defaultdict(float)

# Reset failure count after this many seconds of no failures
_FAILURE_RESET_SECONDS = 300
# Treat provider as unhealthy after this many consecutive failures
_UNHEALTHY_THRESHOLD = 3


def record_provider_failure(provider: str, is_rate_limit: bool = False) -> None:
    """Called by inference_service when a provider fails."""
    now = time.time()
    with _lock:
        # Reset counter if last failure was long ago
        if now - _last_failure_ts[provider] > _FAILURE_RESET_SECONDS:
            _failure_counts[provider] = 0
        _failure_counts[provider] += 1
        _last_failure_ts[provider] = now
        if is_rate_limit:
            # Back off for 60s on rate limit
            _rate_limited_until[provider] = now + 60


def record_provider_success(provider: str) -> None:
    """Called when a provider succeeds — resets its failure count."""
    with _lock:
        _failure_counts[provider] = 0
        _rate_limited_until[provider] = 0


def is_provider_healthy(provider: str) -> bool:
    """Returns False if provider has been consistently failing."""
    now = time.time()
    with _lock:
        if _rate_limited_until[provider] > now:
            return False
        return _failure_counts[provider] < _UNHEALTHY_THRESHOLD


def get_degraded_message(active_provider: str, original_provider: str) -> str | None:
    """
    Returns a user-visible status message when we've fallen back to a
    secondary provider. Returns None if primary is healthy (no message needed).
    """
    if active_provider == original_provider:
        return None

    provider_display = {
        "groq": "Groq",
        "nvidia": "NVIDIA NIM",
        "gemini": "Gemini",
        "cerebras": "Cerebras",
        "ollama": "local Ollama",
    }

    original_name = provider_display.get(original_provider, original_provider)
    active_name = provider_display.get(active_provider, active_provider)

    return (
        f"_(Using {active_name} — {original_name} is currently rate-limited or unavailable. "
        f"Response may be slightly slower.)_"
    )


def get_rate_limit_eta(provider: str) -> int:
    """Returns seconds until provider rate limit expires (0 if not rate-limited)."""
    now = time.time()
    with _lock:
        eta = _rate_limited_until[provider] - now
        return max(0, int(eta))


# ── Provider status summary (for admin dashboard) ─────────────────────────────

def get_provider_health_summary() -> dict:
    """Returns health status for all tracked providers."""
    now = time.time()
    with _lock:
        return {
            provider: {
                "healthy": _failure_counts[provider] < _UNHEALTHY_THRESHOLD
                           and _rate_limited_until[provider] <= now,
                "failure_count": _failure_counts[provider],
                "rate_limited": _rate_limited_until[provider] > now,
                "rate_limit_eta_seconds": max(0, int(_rate_limited_until[provider] - now)),
            }
            for provider in set(list(_failure_counts.keys()) + list(_rate_limited_until.keys()))
        }
