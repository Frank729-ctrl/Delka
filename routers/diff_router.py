"""
Document diff router.

POST /v1/diff          — diff two text documents
POST /v1/diff/versions — diff two saved CV/letter versions by ID
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from database import get_db
from services.document_diff_service import diff_documents, format_diff_for_response

router = APIRouter(prefix="/v1/diff")


class DiffRequest(BaseModel):
    original: str
    revised: str
    show_patch: bool = False


class VersionDiffRequest(BaseModel):
    user_id: str
    doc_type: str        # "cv" | "letter"
    version_a: int       # version number
    version_b: int


@router.post("")
async def api_diff(req: DiffRequest):
    if not req.original or not req.revised:
        raise HTTPException(status_code=400, detail="Both original and revised are required")

    result = diff_documents(req.original, req.revised)
    return {
        "status": "ok",
        "summary": result.summary,
        "added_words": result.added_words,
        "removed_words": result.removed_words,
        "change_pct": result.change_pct,
        "section_changes": result.section_changes,
        "word_changes": result.word_changes[:10],
        "patch": result.unified_patch if req.show_patch else None,
        "formatted": format_diff_for_response(result, show_patch=req.show_patch),
    }


@router.post("/versions")
async def api_diff_versions(req: VersionDiffRequest, db: AsyncSession = Depends(get_db)):
    from services.cv_version_service import get_version
    v_a = await get_version(req.user_id, req.doc_type, req.version_a, db)
    v_b = await get_version(req.user_id, req.doc_type, req.version_b, db)

    if not v_a:
        raise HTTPException(status_code=404, detail=f"Version {req.version_a} not found")
    if not v_b:
        raise HTTPException(status_code=404, detail=f"Version {req.version_b} not found")

    result = diff_documents(v_a, v_b)
    return {
        "status": "ok",
        "version_a": req.version_a,
        "version_b": req.version_b,
        "summary": result.summary,
        "added_words": result.added_words,
        "removed_words": result.removed_words,
        "change_pct": result.change_pct,
        "section_changes": result.section_changes,
        "formatted": format_diff_for_response(result),
    }
