"""
Cron / Scheduled Tasks router.

POST   /v1/cron/tasks        — create a new scheduled task
GET    /v1/cron/tasks        — list tasks for a user
DELETE /v1/cron/tasks/{id}   — delete / cancel a task
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from database import get_db
from services.cron_service import create_scheduled_task, list_scheduled_tasks, delete_scheduled_task

router = APIRouter(prefix="/v1/cron")


class CreateTaskRequest(BaseModel):
    user_id: str
    platform: str
    prompt: str
    schedule: str                   # "every_hour" | "every_morning" | "every_evening" | "every_day"
    webhook_url: Optional[str] = None


@router.post("/tasks")
async def api_create_task(req: CreateTaskRequest, db: AsyncSession = Depends(get_db)):
    task = await create_scheduled_task(
        user_id=req.user_id,
        platform=req.platform,
        prompt=req.prompt,
        schedule=req.schedule,
        webhook_url=req.webhook_url,
        db=db,
    )
    if "error" in task:
        raise HTTPException(status_code=400, detail=task["error"])
    return {"status": "ok", "data": task}


@router.get("/tasks")
async def api_list_tasks(user_id: str, platform: str, db: AsyncSession = Depends(get_db)):
    tasks = await list_scheduled_tasks(user_id=user_id, platform=platform, db=db)
    return {"status": "ok", "tasks": tasks}


@router.delete("/tasks/{task_id}")
async def api_delete_task(task_id: int, user_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await delete_scheduled_task(task_id=task_id, user_id=user_id, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"status": "ok", "deleted": task_id}
