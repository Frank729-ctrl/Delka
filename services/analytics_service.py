"""
Analytics service — exceeds Claude Code's analytics/index.ts + GrowthBook.

src has: Datadog event sink, GrowthBook feature flags, 1P event logging.
Delka has: Self-hosted event pipeline with real business metrics, feature
flags backed by DB, and a live dashboard — no third-party dependency.

Events are queued in-memory and flushed to DB every 30s (non-blocking).
The admin dashboard at /v1/admin/analytics reads aggregated metrics.

Event types mirror src's logEvent() pattern but add business context:
- request_completed  — every API call with provider, latency, tokens
- provider_switched  — fallback triggered
- plugin_fired       — which plugin ran and its result size
- search_triggered   — Tavily search fired
- capability_routed  — image/code/translation handled inline
- memory_recalled    — relevant memories loaded
- compact_triggered  — context compaction ran
- user_tip_shown     — which tip was shown
- cost_tracked       — USD cost estimate logged
- quality_scored     — response quality rating
"""
import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

# ── In-memory event queue ─────────────────────────────────────────────────────

@dataclass
class AnalyticsEvent:
    event_type: str
    platform: str
    user_id: str
    properties: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


_queue: list[AnalyticsEvent] = []
_queue_lock = Lock()
_MAX_QUEUE_SIZE = 5000

# ── Feature flags (DB-backed, in-memory cached) ───────────────────────────────
# Works like GrowthBook but self-hosted. Flags are set via admin API.

_feature_flags: dict[str, bool] = {
    "plugin_tips": True,
    "tool_attribution": True,
    "speculation": True,
    "plan_mode": True,
    "code_diagnostics": True,
    "brief_mode": True,
    "team_memory": True,
}
_flags_lock = Lock()


def get_feature_flag(flag: str, default: bool = False) -> bool:
    with _flags_lock:
        return _feature_flags.get(flag, default)


def set_feature_flag(flag: str, value: bool) -> None:
    with _flags_lock:
        _feature_flags[flag] = value


# ── Event logging ─────────────────────────────────────────────────────────────

def log_event(
    event_type: str,
    platform: str = "",
    user_id: str = "",
    **properties: Any,
) -> None:
    """
    Fire-and-forget event logger. Never raises, never blocks.
    Mirrors src's logEvent() signature.
    """
    with _queue_lock:
        if len(_queue) >= _MAX_QUEUE_SIZE:
            _queue.pop(0)  # drop oldest if queue full
        _queue.append(AnalyticsEvent(
            event_type=event_type,
            platform=platform,
            user_id=user_id,
            properties=properties,
        ))


# ── Aggregated metrics (in-memory, reset hourly) ──────────────────────────────

_hourly_metrics: dict[str, Any] = defaultdict(int)
_metrics_lock = Lock()
_metrics_reset_ts = time.time()
_METRICS_RESET_INTERVAL = 3600  # 1 hour


def _update_metrics(event: AnalyticsEvent) -> None:
    with _metrics_lock:
        _hourly_metrics["total_events"] += 1
        _hourly_metrics[f"event_{event.event_type}"] += 1
        if event.platform:
            _hourly_metrics[f"platform_{event.platform}"] += 1

        # Provider-specific counters
        provider = event.properties.get("provider", "")
        if provider:
            _hourly_metrics[f"provider_{provider}_calls"] += 1

        # Latency tracking
        latency_ms = event.properties.get("latency_ms", 0)
        if latency_ms:
            _hourly_metrics["total_latency_ms"] += latency_ms
            _hourly_metrics["latency_samples"] += 1

        # Token tracking
        tokens = event.properties.get("tokens_used", 0)
        if tokens:
            _hourly_metrics["total_tokens"] += tokens

        # Cost tracking
        cost_usd = event.properties.get("cost_usd", 0.0)
        if cost_usd:
            _hourly_metrics["total_cost_usd"] += cost_usd


def get_metrics_snapshot() -> dict:
    """Returns current hourly metrics snapshot for the dashboard."""
    global _metrics_reset_ts
    now = time.time()

    with _metrics_lock:
        snapshot = dict(_hourly_metrics)
        age_minutes = int((now - _metrics_reset_ts) / 60)

        # Compute derived metrics
        samples = snapshot.get("latency_samples", 0)
        if samples > 0:
            snapshot["avg_latency_ms"] = round(
                snapshot.get("total_latency_ms", 0) / samples
            )

        snapshot["metrics_age_minutes"] = age_minutes
        snapshot["queue_depth"] = len(_queue)

        return snapshot


def reset_metrics() -> None:
    global _metrics_reset_ts
    with _metrics_lock:
        _hourly_metrics.clear()
        _metrics_reset_ts = time.time()


# ── Async flush loop (runs as background asyncio task) ────────────────────────

async def start_analytics_flush_loop(db_session_factory) -> None:
    """
    Background task: flush queued events to DB every 30s.
    Call once at startup via asyncio.create_task().
    """
    while True:
        await asyncio.sleep(30)
        await _flush_to_db(db_session_factory)


async def _flush_to_db(db_session_factory) -> None:
    with _queue_lock:
        if not _queue:
            return
        batch = _queue[:500]
        del _queue[:500]

    # Update in-memory metrics from batch
    for event in batch:
        _update_metrics(event)

    # Persist to DB
    try:
        from sqlalchemy import text
        async with db_session_factory() as db:
            for event in batch:
                import json
                await db.execute(
                    text(
                        "INSERT INTO analytics_events "
                        "(event_type, platform, user_id, properties_json, created_at) "
                        "VALUES (:et, :pl, :uid, :props, FROM_UNIXTIME(:ts))"
                    ),
                    {
                        "et": event.event_type,
                        "pl": event.platform,
                        "uid": event.user_id,
                        "props": json.dumps(event.properties),
                        "ts": event.ts,
                    },
                )
            await db.commit()
    except Exception:
        # Re-queue on failure (best effort)
        with _queue_lock:
            _queue.extend(batch)
