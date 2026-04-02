"""
Notebook router — interactive code execution sessions.

POST   /v1/notebook/sessions            — create session
GET    /v1/notebook/sessions            — list user sessions
DELETE /v1/notebook/sessions/{id}       — delete session
POST   /v1/notebook/sessions/{id}/run   — run a cell
GET    /v1/notebook/sessions/{id}/cells — list cells
GET    /v1/notebook/sessions/{id}/export — export as .ipynb
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from services.notebook_service import (
    create_session, get_session, list_sessions, delete_session,
    add_and_run_cell, export_to_ipynb, format_cell_result,
)

router = APIRouter(prefix="/v1/notebook")


class CreateSessionRequest(BaseModel):
    user_id: str
    platform: str
    language: str = "python"
    title: str = ""


class RunCellRequest(BaseModel):
    source: str
    language: Optional[str] = None


@router.post("/sessions")
async def api_create_session(req: CreateSessionRequest):
    session = create_session(req.user_id, req.platform, req.language, req.title)
    return {
        "status": "ok",
        "session_id": session.session_id,
        "title": session.title,
        "language": session.language,
    }


@router.get("/sessions")
async def api_list_sessions(user_id: str, platform: str):
    return {"status": "ok", "sessions": list_sessions(user_id, platform)}


@router.delete("/sessions/{session_id}")
async def api_delete_session(session_id: str):
    deleted = delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok", "deleted": session_id}


@router.post("/sessions/{session_id}/run")
async def api_run_cell(session_id: str, req: RunCellRequest):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    try:
        cell = await add_and_run_cell(session_id, req.source, req.language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "ok",
        "cell_id": cell.cell_id,
        "execution_count": cell.execution_count,
        "cell_status": cell.status,
        "output": cell.output,
        "error": cell.error,
        "execution_ms": (cell.executed_at or 0),
        "formatted": format_cell_result(cell),
    }


@router.get("/sessions/{session_id}/cells")
async def api_list_cells(session_id: str):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "status": "ok",
        "session_id": session_id,
        "title": session.title,
        "cells": [
            {
                "cell_id": c.cell_id,
                "execution_count": c.execution_count,
                "source": c.source,
                "output": c.output,
                "error": c.error,
                "status": c.status,
                "language": c.language,
            }
            for c in session.cells
        ],
    }


@router.get("/sessions/{session_id}/export")
async def api_export(session_id: str):
    ipynb = export_to_ipynb(session_id)
    if not ipynb:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(
        content={"status": "ok", "session_id": session_id, "notebook": ipynb},
        headers={"Content-Disposition": f'attachment; filename="{session_id}.ipynb"'},
    )
