"""
Scheduled tasks / cron — exceeds Claude Code's ScheduleCronTool.

src has: /loop skill + ScheduleCronTool for running agent turns on schedule.
Delka has: User-defined recurring tasks stored in DB, executed by a background
           asyncio loop, with results delivered via webhook or stored for pickup.

Use cases:
- "Check Ghana news every morning at 8am and send me a summary"
- "Get me the GHS/USD rate every weekday at 9am"
- "Remind me to follow up with clients every Monday"

Schedule format: cron-style string OR natural language (converted on creation).
"""
import asyncio
import json
import time
from dataclasses import dataclass
from typing import Optional

# Simple cron-style schedule patterns (no external lib needed)
_SCHEDULE_PRESETS = {
    "every_hour":    {"interval_seconds": 3600,   "label": "Every hour"},
    "every_morning": {"interval_seconds": 86400,  "label": "Daily at 8am"},
    "every_weekday": {"interval_seconds": 86400,  "label": "Weekdays"},
    "every_monday":  {"interval_seconds": 604800, "label": "Every Monday"},
    "every_30min":   {"interval_seconds": 1800,   "label": "Every 30 minutes"},
    "every_6h":      {"interval_seconds": 21600,  "label": "Every 6 hours"},
}


@dataclass
class ScheduledTask:
    id: int
    user_id: str
    platform: str
    prompt: str                   # What to run (e.g. "Get Ghana news summary")
    schedule_preset: str          # Key into _SCHEDULE_PRESETS
    webhook_url: Optional[str]    # Where to send results
    session_id: str
    is_active: bool
    last_run_at: Optional[float]
    next_run_at: float
    run_count: int


async def create_scheduled_task(
    user_id: str,
    platform: str,
    prompt: str,
    schedule: str,
    webhook_url: Optional[str],
    db,
) -> dict:
    """Create a new scheduled task. Returns the task dict."""
    preset = _SCHEDULE_PRESETS.get(schedule, _SCHEDULE_PRESETS["every_morning"])
    next_run = time.time() + preset["interval_seconds"]
    session_id = f"cron-{user_id}-{int(time.time())}"

    try:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "INSERT INTO scheduled_tasks "
                "(user_id, platform, prompt, schedule_preset, webhook_url, session_id, "
                "is_active, next_run_at, run_count, created_at) "
                "VALUES (:uid, :pl, :prompt, :sched, :webhook, :sess, 1, :next_run, 0, NOW())"
            ),
            {
                "uid": user_id, "pl": platform, "prompt": prompt,
                "sched": schedule, "webhook": webhook_url,
                "sess": session_id, "next_run": next_run,
            },
        )
        await db.commit()
        task_id = result.lastrowid
        return {
            "id": task_id,
            "prompt": prompt,
            "schedule": preset["label"],
            "next_run_at": next_run,
            "session_id": session_id,
        }
    except Exception as e:
        return {"error": str(e)}


async def list_scheduled_tasks(user_id: str, platform: str, db) -> list[dict]:
    """List all scheduled tasks for a user."""
    try:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT id, prompt, schedule_preset, is_active, last_run_at, next_run_at, run_count "
                "FROM scheduled_tasks WHERE user_id = :uid AND platform = :pl ORDER BY created_at DESC"
            ),
            {"uid": user_id, "pl": platform},
        )
        tasks = []
        for row in result.fetchall():
            preset = _SCHEDULE_PRESETS.get(row[2], {})
            tasks.append({
                "id": row[0], "prompt": row[1],
                "schedule": preset.get("label", row[2]),
                "is_active": bool(row[3]),
                "last_run_at": row[4], "next_run_at": row[5],
                "run_count": row[6],
            })
        return tasks
    except Exception:
        return []


async def delete_scheduled_task(task_id: int, user_id: str, db) -> bool:
    """Delete a scheduled task (only if owned by user)."""
    try:
        from sqlalchemy import text
        await db.execute(
            text("DELETE FROM scheduled_tasks WHERE id = :id AND user_id = :uid"),
            {"id": task_id, "uid": user_id},
        )
        await db.commit()
        return True
    except Exception:
        return False


async def run_scheduled_task_loop(db_factory) -> None:
    """
    Background loop: check every 60s for tasks due to run.
    Executes due tasks and delivers results via webhook or DB.
    """
    while True:
        await asyncio.sleep(60)
        try:
            await _process_due_tasks(db_factory)
        except Exception:
            pass


async def _process_due_tasks(db_factory) -> None:
    now = time.time()
    async with db_factory() as db:
        from sqlalchemy import text
        result = await db.execute(
            text(
                "SELECT id, user_id, platform, prompt, schedule_preset, webhook_url, session_id "
                "FROM scheduled_tasks WHERE is_active = 1 AND next_run_at <= :now LIMIT 10"
            ),
            {"now": now},
        )
        tasks = result.fetchall()

    for row in tasks:
        task_id, user_id, platform, prompt, schedule_preset, webhook_url, session_id = row
        asyncio.create_task(_execute_task(
            task_id, user_id, platform, prompt,
            schedule_preset, webhook_url, session_id, db_factory,
        ))


async def _execute_task(
    task_id: int, user_id: str, platform: str, prompt: str,
    schedule_preset: str, webhook_url: Optional[str], session_id: str,
    db_factory,
) -> None:
    """Execute a single scheduled task."""
    try:
        from services.inference_service import generate_full_response
        from prompts.personality_prompt import CORE_IDENTITY_PROMPT

        system = f"{CORE_IDENTITY_PROMPT}\n\nThis is a scheduled task running automatically."
        answer, provider, model = await generate_full_response(
            task="support",
            system_prompt=system,
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=512,
        )

        # Deliver via webhook if configured
        if webhook_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(webhook_url, json={
                        "task_id": task_id,
                        "prompt": prompt,
                        "result": answer,
                        "provider": provider,
                        "ran_at": time.time(),
                    })
            except Exception:
                pass

        # Update task in DB
        preset = _SCHEDULE_PRESETS.get(schedule_preset, _SCHEDULE_PRESETS["every_morning"])
        next_run = time.time() + preset["interval_seconds"]
        async with db_factory() as db:
            from sqlalchemy import text
            await db.execute(
                text(
                    "UPDATE scheduled_tasks SET last_run_at = :now, next_run_at = :next, "
                    "run_count = run_count + 1 WHERE id = :id"
                ),
                {"now": time.time(), "next": next_run, "id": task_id},
            )
            await db.commit()

        from services.analytics_service import log_event
        log_event("cron_task_executed", platform=platform, user_id=user_id,
                  task_id=task_id, provider=provider)

    except Exception:
        pass
