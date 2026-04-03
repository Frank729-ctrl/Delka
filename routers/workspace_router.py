"""
Document Workspace router — ports Claude Code's file system tools.

POST   /v1/workspace/files          — Write: upload / overwrite a file
GET    /v1/workspace/files          — list all files
GET    /v1/workspace/files/{name}   — Read: full or line-range (?offset=&limit=)
PUT    /v1/workspace/files/{name}   — Edit: targeted string replace
DELETE /v1/workspace/files/{name}   — delete a file
GET    /v1/workspace/glob           — Glob: fnmatch pattern on filenames
GET    /v1/workspace/grep           — Grep: regex search with line numbers + context
GET    /v1/workspace/search         — keyword search (legacy, used by chat plugin)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from database import get_db
from services.workspace_service import (
    upload_file, read_file, read_file_range,
    glob_files, grep_files,
    list_files, edit_file,
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
async def api_read(
    filename: str,
    user_id: str,
    platform: str,
    offset: int = Query(0, ge=0, description="0-based line to start from"),
    limit: Optional[int] = Query(None, ge=1, description="Max lines to return"),
    db: AsyncSession = Depends(get_db),
):
    if offset or limit:
        result = await read_file_range(user_id, platform, filename, db, offset=offset, limit=limit)
        if result is None:
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
        return {"status": "ok", **result}
    content = await read_file(user_id, platform, filename, db)
    if content is None:
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
    lines = content.splitlines()
    return {"status": "ok", "filename": filename, "content": content, "total_lines": len(lines)}


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


@router.get("/glob")
async def api_glob(
    user_id: str,
    platform: str,
    pattern: str = Query(..., description="Glob pattern, e.g. *.py or **/*.md"),
    db: AsyncSession = Depends(get_db),
):
    """Find files by name pattern — ports Claude Code's Glob tool."""
    matched = await glob_files(user_id, platform, pattern, db)
    return {"status": "ok", "pattern": pattern, "matches": matched, "count": len(matched)}


@router.get("/grep")
async def api_grep(
    user_id: str,
    platform: str,
    pattern: str = Query(..., description="Regex pattern to search for"),
    glob: str = Query("*", description="Only search files matching this glob"),
    context: int = Query(0, ge=0, le=5, description="Lines of context before+after each match"),
    max_results: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Regex search across workspace files — ports Claude Code's Grep tool."""
    results = await grep_files(user_id, platform, pattern, db, glob_filter=glob,
                               context_lines=context, max_results=max_results)
    if results and "error" in results[0]:
        raise HTTPException(status_code=400, detail=results[0]["error"])
    return {
        "status": "ok",
        "pattern": pattern,
        "glob": glob,
        "matches": results,
        "count": len(results),
    }


@router.get("/search")
async def api_search(user_id: str, platform: str, q: str, db: AsyncSession = Depends(get_db)):
    results = await search_workspace(user_id, platform, q, db)
    return {"status": "ok", "query": q, "results": results}
