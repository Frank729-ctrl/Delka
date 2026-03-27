import io
import json
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from schemas.feedback_schema import FeedbackRequest, FeedbackResponse
from services import feedback_service

router = APIRouter()


async def _get_user_id_from_request(request) -> str:
    """Extract user_id from request state (set by api_key_middleware)."""
    return getattr(request.state, "user_id", "") or ""


async def require_master_key(
    x_delkaai_master_key: str = Header(..., alias="X-DelkaAI-Master-Key"),
) -> None:
    if x_delkaai_master_key != settings.SECRET_MASTER_KEY:
        raise HTTPException(status_code=401, detail="Invalid master key.")


@router.post("/v1/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    data: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    x_delkaai_key: str = Header("", alias="X-DelkaAI-Key"),
):
    # user_id and platform derived from the api key context
    # Use session_id as fallback user identifier
    user_id = data.session_id.split("-")[0] if data.session_id else "anon"
    platform = "generic"

    result = await feedback_service.store_feedback(data, user_id, platform, db)
    return FeedbackResponse(
        status="success",
        message="Feedback recorded.",
        correction_stored=result["correction_stored"],
    )


@router.get("/v1/admin/feedback/summary", dependencies=[Depends(require_master_key)])
async def feedback_summary(
    platform: str = Query(...),
    service: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    summaries = await feedback_service.get_feedback_summary(platform, db, service)
    return {
        "status": "success",
        "data": [s.model_dump() for s in summaries],
    }


@router.get("/v1/admin/feedback/export", dependencies=[Depends(require_master_key)])
async def feedback_export(
    platform: str = Query(...),
    min_rating: int = Query(4),
    db: AsyncSession = Depends(get_db),
):
    data = await feedback_service.export_training_data(platform, db, min_rating)
    jsonl = "\n".join(json.dumps(row) for row in data)

    return StreamingResponse(
        io.BytesIO(jsonl.encode()),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f"attachment; filename=training_data_{platform}.jsonl"
        },
    )
