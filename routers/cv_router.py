import json
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from schemas.cv_schema import CVRequest
from services.cv_service import generate_cv

router = APIRouter(prefix="/v1/cv", tags=["cv"])

_PARSE_SYSTEM = """You are a data extraction assistant.
Extract CV information from free-form text and return ONLY a valid JSON object
with these exact keys (use empty string / empty list when data is missing):
{
  "full_name": "string",
  "email": "string",
  "phone": "string",
  "location": "string",
  "summary": "string (2-3 sentence professional summary)",
  "skills": ["string"],
  "experience": [
    {
      "company": "string",
      "title": "string",
      "start_date": "string",
      "end_date": "string",
      "bullets": ["string"]
    }
  ],
  "education": [
    {
      "school": "string",
      "degree": "string",
      "field": "string",
      "year": "string"
    }
  ]
}
Return JSON only — no markdown, no explanation."""


async def _parse_raw_text(raw_text: str) -> dict:
    """Use the inference service to convert free-form text into CV fields."""
    from services.inference_service import generate_full_response
    response_text, _, _ = await generate_full_response(
        "cv",
        _PARSE_SYSTEM,
        f"Extract CV data from this text:\n\n{raw_text}",
        temperature=0.1,
    )
    # Strip markdown fences if present
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail="Could not parse raw_text into CV fields. Please provide more detail or use structured fields.",
        )


@router.post("/generate")
async def cv_generate(
    request: Request,
    data: CVRequest,
    db: AsyncSession = Depends(get_db),
):
    user_id  = getattr(request.state, "user_id",  "anon")    or "anon"
    platform = getattr(request.state, "platform", "unknown") or "unknown"

    # If raw_text provided and structured fields are empty, parse it first
    raw = data.raw_text.strip()
    if raw and not data.full_name.strip():
        parsed = await _parse_raw_text(raw)
        # Merge parsed fields, keeping any explicitly set fields
        merged = {**parsed}
        if data.phone:       merged["phone"]       = data.phone
        if data.location:    merged["location"]    = data.location
        if data.linkedin:    merged["linkedin"]    = data.linkedin
        if data.website:     merged["website"]     = data.website
        if data.webhook_url: merged["webhook_url"] = data.webhook_url

        # Fallbacks: use raw_text as summary if AI returned nothing
        if not merged.get("summary", "").strip():
            merged["summary"] = raw
        # Fallback: minimal education entry so pipeline doesn't break
        if not merged.get("education"):
            merged["education"] = [{"school": "Not specified", "degree": "Not specified", "year": ""}]
        # Fallback: keep raw_text so the CV prompt has full context
        merged["raw_text"] = raw

        try:
            data = CVRequest(**merged)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Parsed CV data invalid: {e}")

    # Validate required fields
    if not data.full_name.strip():
        raise HTTPException(status_code=422, detail="full_name is required (or provide raw_text).")
    if not data.summary.strip():
        raise HTTPException(status_code=422, detail="summary is required (or provide raw_text).")

    result = await generate_cv(data, db, user_id=user_id, platform=platform)

    request_id = getattr(request.state, "request_id", "")

    if isinstance(result, dict):
        return JSONResponse(
            status_code=202,
            content={
                "status": "success",
                "message": "CV generation queued.",
                "data": result,
            },
        )

    pdf_bytes, template_name, color_key, provider, model, quality = result
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="cv_{request_id}.pdf"',
            "X-Template-Used": template_name,
            "X-Color-Scheme": color_key,
            "X-Request-ID": request_id,
            "X-Provider-Used": provider,
            "X-Model-Used": model,
            "X-Quality-Score": str(quality["total_score"]),
            "X-Quality-Passed": str(quality["passed"]).lower(),
        },
    )
