"""
Task Management API — mirrors Claude Code's 6 task tools:

  TaskCreateTool  → POST   /v1/tasks
  TaskListTool    → GET    /v1/tasks
  TaskGetTool     → GET    /v1/tasks/{task_id}
  TaskUpdateTool  → PATCH  /v1/tasks/{task_id}
  TaskStopTool    → DELETE /v1/tasks/{task_id}
  TaskOutputTool  → GET    /v1/tasks/{task_id}/output   (SSE stream)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional

from services.task_manager_service import (
    create_task,
    get_task,
    list_tasks,
    stop_task,
    update_task,
    stream_output,
    purge_old_tasks,
    VALID_STATUSES,
)

router = APIRouter(prefix="/v1/tasks")


# ── Schemas ────────────────────────────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    subject: str = Field(..., description="Short title, e.g. 'Run tests'")
    description: str = Field(..., description="Full instructions for the agent")
    active_form: str = Field("", description="Present-continuous label, e.g. 'Running tests'")
    owner: str = Field("anonymous", description="Session ID or user ID")
    metadata: dict = Field(default_factory=dict)
    blocks: list[str] = Field(default_factory=list, description="Task IDs this task blocks")
    blocked_by: list[str] = Field(default_factory=list, description="Task IDs blocking this task")
    autostart: bool = Field(True, description="Start immediately (default true)")


class TaskUpdateRequest(BaseModel):
    subject: Optional[str] = None
    description: Optional[str] = None
    active_form: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", summary="Create a task")
async def api_create_task(body: TaskCreateRequest):
    if body.status if hasattr(body, "status") else None:
        pass  # status not in create body
    task = create_task(
        subject=body.subject,
        description=body.description,
        active_form=body.active_form or body.subject,
        owner=body.owner,
        metadata=body.metadata,
        blocks=body.blocks,
        blocked_by=body.blocked_by,
        autostart=body.autostart,
    )
    return {
        "status": "ok",
        "message": "Task created",
        "data": task.to_summary(),
    }


@router.get("", summary="List tasks for an owner")
async def api_list_tasks(owner: str = "anonymous"):
    tasks = list_tasks(owner)
    return {
        "status": "ok",
        "data": {
            "tasks": [t.to_summary() for t in tasks],
            "count": len(tasks),
        },
    }


@router.get("/{task_id}", summary="Get a single task")
async def api_get_task(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"status": "ok", "data": task.to_detail()}


@router.patch("/{task_id}", summary="Update a task")
async def api_update_task(task_id: str, body: TaskUpdateRequest):
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of: {', '.join(VALID_STATUSES)}",
        )
    task = update_task(
        task_id=task_id,
        subject=body.subject,
        description=body.description,
        active_form=body.active_form,
        status=body.status,
        metadata=body.metadata,
    )
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"status": "ok", "message": "Task updated", "data": task.to_summary()}


@router.delete("/{task_id}", summary="Stop / cancel a task")
async def api_stop_task(task_id: str):
    if not get_task(task_id):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    stopped = stop_task(task_id)
    msg = "Task stopped" if stopped else "Task already in terminal state"
    return {"status": "ok", "message": msg}


@router.get("/{task_id}/output", summary="SSE stream of task output lines")
async def api_task_output(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return StreamingResponse(
        stream_output(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/purge", summary="Remove old completed/failed/stopped tasks")
async def api_purge_tasks(max_age_seconds: int = 3600):
    removed = purge_old_tasks(max_age_seconds)
    return {"status": "ok", "message": f"Removed {removed} old tasks"}
