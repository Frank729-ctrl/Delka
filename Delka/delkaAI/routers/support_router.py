from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from schemas.support_schema import SupportChatRequest
from services.support_service import handle_chat

router = APIRouter(prefix="/v1/support", tags=["support"])


@router.post("/chat")
async def support_chat(
    data: SupportChatRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    return await handle_chat(data, db)
