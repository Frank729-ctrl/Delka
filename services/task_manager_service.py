"""
Task Manager — Delka port of Claude Code's task system.

src equivalents: TaskCreateTool, TaskListTool, TaskGetTool,
                 TaskUpdateTool, TaskStopTool, TaskOutputTool

State machine:  pending → running → completed | failed | stopped

Each task runs an agent prompt in an asyncio background task.
Output lines stream into task.output_lines and are readable via SSE.

Key differences from src:
  - In-memory store (no DB persistence — tasks are ephemeral per server run)
  - asyncio.create_task() for background execution
  - SSE `/v1/tasks/{id}/output` streams lines as they arrive
  - `owner` is session_id or user_id passed at creation
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, AsyncGenerator

# ── Task model ─────────────────────────────────────────────────────────────────

VALID_STATUSES = {"pending", "running", "completed", "failed", "stopped"}


@dataclass
class ManagedTask:
    task_id: str
    subject: str                    # short title  ("Run tests")
    description: str                # what to do   (full instructions)
    active_form: str                # present continuous ("Running tests")
    status: str                     # pending | running | completed | failed | stopped
    owner: str                      # session_id or user_id
    output_lines: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)       # task IDs this blocks
    blocked_by: list[str] = field(default_factory=list)   # task IDs blocking this
    metadata: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    _asyncio_task: Optional[asyncio.Task] = field(default=None, repr=False)

    def to_summary(self) -> dict:
        return {
            "task_id": self.task_id,
            "subject": self.subject,
            "active_form": self.active_form,
            "status": self.status,
            "owner": self.owner,
            "blocks": self.blocks,
            "blocked_by": self.blocked_by,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def to_detail(self) -> dict:
        return {
            **self.to_summary(),
            "description": self.description,
            "metadata": self.metadata,
            "output_lines": self.output_lines,
        }


# ── In-memory store ────────────────────────────────────────────────────────────

_store: dict[str, ManagedTask] = {}
_output_events: dict[str, asyncio.Event] = {}   # signalled when new line appended


def _get_task(task_id: str) -> Optional[ManagedTask]:
    return _store.get(task_id)


def _all_for_owner(owner: str) -> list[ManagedTask]:
    return [t for t in _store.values() if t.owner == owner]


# ── Output helpers ─────────────────────────────────────────────────────────────

def _append_line(task: ManagedTask, line: str) -> None:
    task.output_lines.append(line)
    ev = _output_events.get(task.task_id)
    if ev:
        ev.set()
        ev.clear()


# ── Task executor ──────────────────────────────────────────────────────────────

async def _run_task(task: ManagedTask) -> None:
    """
    Execute task.description via the inference service.
    Streams output line by line into task.output_lines.
    """
    task.status = "running"
    _append_line(task, f"[task:{task.task_id}] Started — {task.active_form}")

    try:
        from services.inference_service import stream_response
        system = (
            "You are an autonomous agent executing an assigned task. "
            "Think step by step. Output each step clearly on its own line. "
            "When done, end with: TASK COMPLETE."
        )
        buffer = ""
        async for chunk in stream_response(
            task="chat",
            system_prompt=system,
            user_prompt=task.description,
            temperature=0.4,
            max_tokens=2000,
        ):
            buffer += chunk
            # Flush complete lines
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if line:
                    _append_line(task, line)

        # Flush remainder
        if buffer.strip():
            _append_line(task, buffer.strip())

        task.status = "completed"
        task.completed_at = time.time()
        _append_line(task, f"[task:{task.task_id}] Completed.")

    except asyncio.CancelledError:
        task.status = "stopped"
        task.completed_at = time.time()
        _append_line(task, f"[task:{task.task_id}] Stopped.")

    except Exception as exc:
        task.status = "failed"
        task.completed_at = time.time()
        _append_line(task, f"[task:{task.task_id}] Failed: {exc!s:.200}")


# ── Public API ─────────────────────────────────────────────────────────────────

def create_task(
    subject: str,
    description: str,
    active_form: str,
    owner: str,
    metadata: dict | None = None,
    blocks: list[str] | None = None,
    blocked_by: list[str] | None = None,
    autostart: bool = True,
) -> ManagedTask:
    """Create and (optionally) immediately start a task."""
    task_id = str(uuid.uuid4())
    task = ManagedTask(
        task_id=task_id,
        subject=subject,
        description=description,
        active_form=active_form or subject,
        status="pending",
        owner=owner,
        metadata=metadata or {},
        blocks=blocks or [],
        blocked_by=blocked_by or [],
    )
    _store[task_id] = task
    _output_events[task_id] = asyncio.Event()

    if autostart:
        asyncio_task = asyncio.create_task(_run_task(task))
        task._asyncio_task = asyncio_task

    return task


def get_task(task_id: str) -> Optional[ManagedTask]:
    return _get_task(task_id)


def list_tasks(owner: str) -> list[ManagedTask]:
    return sorted(_all_for_owner(owner), key=lambda t: t.created_at, reverse=True)


def stop_task(task_id: str) -> bool:
    """Cancel a running task. Returns True if cancelled, False if not found/already done."""
    task = _get_task(task_id)
    if not task:
        return False
    if task.status not in ("pending", "running"):
        return False
    if task._asyncio_task and not task._asyncio_task.done():
        task._asyncio_task.cancel()
    else:
        task.status = "stopped"
        task.completed_at = time.time()
    return True


def update_task(
    task_id: str,
    subject: str | None = None,
    description: str | None = None,
    active_form: str | None = None,
    status: str | None = None,
    metadata: dict | None = None,
) -> Optional[ManagedTask]:
    """Update mutable fields on a task."""
    task = _get_task(task_id)
    if not task:
        return None
    if subject is not None:
        task.subject = subject
    if description is not None:
        task.description = description
    if active_form is not None:
        task.active_form = active_form
    if status is not None and status in VALID_STATUSES:
        task.status = status
        if status in ("completed", "failed", "stopped") and not task.completed_at:
            task.completed_at = time.time()
    if metadata is not None:
        task.metadata.update(metadata)
    return task


async def stream_output(task_id: str) -> AsyncGenerator[str, None]:
    """
    SSE generator — yields output lines as they arrive.
    Exits when task reaches a terminal state and all lines are consumed.
    """
    task = _get_task(task_id)
    if not task:
        yield f"data: {{'error': 'Task not found'}}\n\n"
        return

    cursor = 0
    ev = _output_events.get(task_id) or asyncio.Event()

    while True:
        # Drain any new lines
        while cursor < len(task.output_lines):
            line = task.output_lines[cursor]
            cursor += 1
            import json
            yield f"data: {json.dumps({'line': line, 'index': cursor - 1})}\n\n"

        # If terminal and all lines sent → close stream
        if task.status in ("completed", "failed", "stopped"):
            yield f"data: {{'done': true, 'status': '{task.status}'}}\n\n"
            break

        # Wait for next line (1-second poll fallback)
        try:
            await asyncio.wait_for(ev.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass


def purge_old_tasks(max_age_seconds: int = 3600) -> int:
    """Remove completed/failed/stopped tasks older than max_age_seconds."""
    cutoff = time.time() - max_age_seconds
    to_remove = [
        tid for tid, t in _store.items()
        if t.status in ("completed", "failed", "stopped")
        and (t.completed_at or 0) < cutoff
    ]
    for tid in to_remove:
        del _store[tid]
        _output_events.pop(tid, None)
    return len(to_remove)
