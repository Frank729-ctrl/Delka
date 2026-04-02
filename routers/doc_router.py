"""
Document Q&A router — POST /v1/doc/ask
Upload a document (text or base64 PDF) and ask questions about it.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/v1/doc", tags=["Document Q&A"])


class DocAskRequest(BaseModel):
    session_id: str
    question: str
    document_text: Optional[str] = None
    document_base64: Optional[str] = None   # base64 PDF or image


class DocAskResponse(BaseModel):
    answer: str
    doc_hash: Optional[str] = None
    doc_word_count: Optional[int] = None
    provider: Optional[str] = None
    is_new_document: bool = False
    error: Optional[str] = None


@router.post("/ask", response_model=DocAskResponse)
async def ask_document(request: DocAskRequest, db: AsyncSession = Depends(get_db)):
    from services.doc_qa_service import answer_question
    result = await answer_question(
        question=request.question,
        session_id=request.session_id,
        document_text=request.document_text,
        document_base64=request.document_base64,
    )
    if "error" in result:
        return DocAskResponse(answer="", error=result["error"])
    return DocAskResponse(**result)
