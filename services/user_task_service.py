"""
User Task Tracking — exceeds Claude Code's TodoWrite/TodoRead tools.

src: Internal task list the AI uses to track its own steps.
Delka: User-visible task board. The AI creates tasks during multi-step jobs
       (plan execution, CV generation, research) and updates them in real time
       via SSE so the user sees a live checklist in the frontend.

The AI creates tasks by emitting a special SSE event:
  data: {"type": "task_update", "tasks": [...]}

Tasks are also persisted in DB so users can retrieve them across sessions.

Used by: coordinator_service (multi-step plans), plan_mode_service (step tracking),
         job_queue (CV/letter async jobs).
"""
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


# ── In-memory session board (fast path for active sessions) ──────────────────

@dataclass
class Task:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    status: str = "pending"        # pending | in_progress | completed | failed
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None


_boards: dict[str, list[Task]] = {}   # session_id → [Task, ...]


# ── Board operations ──────────────────────────────────────────────────────────

def create_task(session_id: str, content: str) -> Task:
    task = Task(content=content)
    if session_id not in _boards:
        _boards[session_id] = []
    _boards[session_id].append(task)
    return task


def update_task(session_id: str, task_id: str, status: str) -> Optional[Task]:
    for task in _boards.get(session_id, []):
        if task.task_id == task_id:
            task.status = status
            if status == "completed":
                task.completed_at = time.time()
            return task
    return None


def get_tasks(session_id: str) -> list[Task]:
    return _boards.get(session_id, [])


def clear_tasks(session_id: str) -> None:
    _boards.pop(session_id, None)


def create_board_from_plan(session_id: str, steps: list[str]) -> list[Task]:
    """Convert a plan's steps into a task board. Used by plan_mode_service."""
    clear_tasks(session_id)
    return [create_task(session_id, step) for step in steps]


# ── SSE event builder ─────────────────────────────────────────────────────────

def build_task_sse_event(session_id: str) -> str:
    """Emit current board state as SSE for real-time frontend updates."""
    import json
    tasks = [asdict(t) for t in get_tasks(session_id)]
    return f"data: {json.dumps({'type': 'task_update', 'tasks': tasks})}\n\n"


# ── DB persistence ────────────────────────────────────────────────────────────

async def persist_tasks(session_id: str, user_id: str, platform: str, db: AsyncSession) -> None:
    """Save current board to DB for cross-session retrieval."""
    import json
    tasks = get_tasks(session_id)
    if not tasks:
        return
    try:
        await db.execute(
            text(
                "INSERT INTO user_task_boards (session_id, user_id, platform, tasks_json, updated_at) "
                "VALUES (:sid, :uid, :pl, :tj, NOW()) "
                "ON DUPLICATE KEY UPDATE tasks_json = :tj, updated_at = NOW()"
            ),
            {
                "sid": session_id,
                "uid": user_id,
                "pl": platform,
                "tj": json.dumps([asdict(t) for t in tasks]),
            },
        )
        await db.commit()
    except Exception:
        pass


async def load_tasks_from_db(session_id: str, db: AsyncSession) -> list[Task]:
    """Reload a saved board (e.g. user returns to an in-progress job)."""
    import json
    try:
        result = await db.execute(
            text("SELECT tasks_json FROM user_task_boards WHERE session_id = :sid"),
            {"sid": session_id},
        )
        row = result.fetchone()
        if not row:
            return []
        raw = json.loads(row[0])
        tasks = [Task(**t) for t in raw]
        _boards[session_id] = tasks
        return tasks
    except Exception:
        return []


# ── Helper: mark steps in sequence ───────────────────────────────────────────

async def tick_step(session_id: str, step_index: int) -> Optional[Task]:
    """
    Mark step N as completed and step N+1 as in_progress.
    Used by coordinator to advance through a plan live.
    """
    tasks = get_tasks(session_id)
    if step_index < len(tasks):
        update_task(session_id, tasks[step_index].task_id, "completed")
    if step_index + 1 < len(tasks):
        update_task(session_id, tasks[step_index + 1].task_id, "in_progress")
    return tasks[step_index] if step_index < len(tasks) else None
