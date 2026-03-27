from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from schemas.support_schema import SupportChatRequest
from services.support_service import handle_chat

router = APIRouter(prefix="/v1/support", tags=["support"])


@router.post("/chat")
async def support_chat(data: SupportChatRequest) -> StreamingResponse:
    return await handle_chat(data)
