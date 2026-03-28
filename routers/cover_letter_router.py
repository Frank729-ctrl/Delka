from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from schemas.cover_letter_schema import CoverLetterRequest
from services.cover_letter_service import generate_cover_letter

router = APIRouter(prefix="/v1/letter", tags=["cover_letter"])


@router.post("/generate")
async def letter_generate(
    request: Request,
    data: CoverLetterRequest,
    db: AsyncSession = Depends(get_db),
):
    user_id = getattr(request.state, "user_id", "anon") or "anon"
    platform = getattr(request.state, "platform", "unknown") or "unknown"
    result = await generate_cover_letter(data, db, user_id=user_id, platform=platform)

    request_id = getattr(request.state, "request_id", "")

    if isinstance(result, dict):
        return JSONResponse(
            status_code=202,
            content={
                "status": "success",
                "message": "Cover letter generation queued.",
                "data": result,
            },
        )

    pdf_bytes, template_name, color_key, provider, model, quality = result
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cover_letter_{request_id}.pdf"',
            "X-Template-Used": template_name,
            "X-Color-Scheme": color_key,
            "X-Request-ID": request_id,
            "X-Provider-Used": provider,
            "X-Model-Used": model,
            "X-Quality-Score": str(quality["total_score"]),
            "X-Quality-Passed": str(quality["passed"]).lower(),
        },
    )
