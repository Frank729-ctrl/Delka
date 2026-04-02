"""
Document Workspace router.

POST   /v1/workspace/files          — upload a file
GET    /v1/workspace/files          — list all files
GET    /v1/workspace/files/{name}   — read a file
PUT    /v1/workspace/files/{name}   — edit (targeted string replace)
DELETE /v1/workspace/files/{name}   — delete a file
GET    /v1/workspace/search         — search across all files
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from database import get_db
from services.workspace_service import (
    upload_file, read_file, list_files, edit_file,
    delete_file, search_workspace,
)

router = APIRouter(prefix="/v1/workspace")


class UploadRequest(BaseModel):
    user_id: str
    platform: str
    filename: str
    content: str
    file_type: str = "text"


class EditRequest(BaseModel):
    user_id: str
    platform: str
    old_string: str
    new_string: str


@router.post("/files")
async def api_upload(req: UploadRequest, db: AsyncSession = Depends(get_db)):
    result = await upload_file(req.user_id, req.platform, req.filename, req.content, req.file_type, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "ok", **result}


@router.get("/files")
async def api_list(user_id: str, platform: str, db: AsyncSession = Depends(get_db)):
    files = await list_files(user_id, platform, db)
    return {"status": "ok", "files": files}


@router.get("/files/{filename}")
async def api_read(filename: str, user_id: str, platform: str, db: AsyncSession = Depends(get_db)):
    content = await read_file(user_id, platform, filename, db)
    if content is None:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    return {"status": "ok", "filename": filename, "content": content}


@router.put("/files/{filename}")
async def api_edit(filename: str, req: EditRequest, db: AsyncSession = Depends(get_db)):
    result = await edit_file(req.user_id, req.platform, filename, req.old_string, req.new_string, db)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"status": "ok", **result}


@router.delete("/files/{filename}")
async def api_delete(filename: str, user_id: str, platform: str, db: AsyncSession = Depends(get_db)):
    deleted = await delete_file(user_id, platform, filename, db)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    return {"status": "ok", "deleted": filename}


@router.get("/search")
async def api_search(user_id: str, platform: str, q: str, db: AsyncSession = Depends(get_db)):
    results = await search_workspace(user_id, platform, q, db)
    return {"status": "ok", "query": q, "results": results}
