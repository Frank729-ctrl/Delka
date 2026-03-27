from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.vision_schema import (
    IndexRequest,
    IndexResponse,
    IndexStatusResponse,
    VisionSearchRequest,
    VisionSearchResponse,
)
from services import index_service, visual_search_service

router = APIRouter(prefix="/v1/vision")


@router.post("/search", response_model=VisionSearchResponse)
async def vision_search(
    request: VisionSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    return await visual_search_service.search(request, db)


@router.post("/index", response_model=IndexResponse)
async def vision_index(
    request: IndexRequest,
    db: AsyncSession = Depends(get_db),
):
    if len(request.items) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 items per request")
    return await visual_search_service.index_batch(request, db)


@router.delete("/index/{item_id}")
async def vision_remove_item(
    item_id: str,
    platform: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    await index_service.remove_item(platform, item_id, db)
    return {"status": "success", "item_id": item_id, "platform": platform}


@router.get("/index/status", response_model=IndexStatusResponse)
async def vision_index_status(
    platform: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    stats = await index_service.get_index_stats(platform, db)
    return IndexStatusResponse(**stats)
